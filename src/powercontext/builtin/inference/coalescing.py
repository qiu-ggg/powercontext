# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Cross-call coalescing and bounded caching for embedding models.

A single :class:`CoalescingEmbeddingModel` is shared by every concurrent
caller in one event loop. Identical text is embedded once: calls that arrive
while a provider request is still running attach to that request, and calls
that arrive inside the coalescing window are dispatched together. Successful
vectors are kept in an LRU cache so later calls never reach the provider again.

Each caller keeps its own ordering, its own ``usage`` accounting and its own
cancellation scope: cancelling one caller never cancels work another caller is
waiting on, and a provider failure is only reported to the callers that waited
for the failing batch.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import TYPE_CHECKING

from powercontext.builtin.inference.models import (
    EmbeddingResult,
    EmbeddingVector,
    InferenceUsage,
)

if TYPE_CHECKING:
    from powercontext.builtin.artifacts.memory.models import EmbeddingProfile
    from powercontext.builtin.inference.protocols import EmbeddingModel

DEFAULT_MAX_BATCH_SIZE = 64
DEFAULT_COALESCE_MS = 5.0
DEFAULT_CACHE_SIZE = 1024


class _Batch:
    """One provider request shared by every caller that needs one of its texts."""

    __slots__ = ("texts", "task", "usage", "vectors")

    def __init__(self, texts: tuple[str, ...]) -> None:
        self.texts = texts
        self.task: asyncio.Task[None] | None = None
        self.usage = InferenceUsage(requests=0)
        self.vectors: tuple[EmbeddingVector, ...] = ()


class _Entry:
    """One text that is waiting to be assigned to a batch."""

    __slots__ = ("text", "batch")

    def __init__(self, text: str) -> None:
        self.text = text
        self.batch: _Batch | None = None


def _deduplicate(texts: tuple[str, ...]) -> tuple[str, ...]:
    """Return the distinct texts of one call in first-seen order."""

    return tuple(dict.fromkeys(texts))


def _add_optional(left: int | None, right: int | None) -> int | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right


def _merge_usage(total: InferenceUsage, extra: InferenceUsage) -> InferenceUsage:
    """Fold one batch's usage into a caller's running total."""

    return InferenceUsage(
        requests=total.requests + extra.requests,
        input_tokens=_add_optional(total.input_tokens, extra.input_tokens),
        output_tokens=_add_optional(total.output_tokens, extra.output_tokens),
    )


class CoalescingEmbeddingModel:
    """Share provider work across concurrent calls and cache successful vectors.

    ``max_batch_size`` bounds the number of distinct texts in one provider
    request, ``coalesce_ms`` is the window during which concurrent calls are
    dispatched together, and ``cache_size`` bounds the LRU cache of successful
    vectors (``0`` disables the cross-call cache without disabling in-flight
    sharing).
    """

    def __init__(
        self,
        model: EmbeddingModel,
        *,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
        coalesce_ms: float = DEFAULT_COALESCE_MS,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ) -> None:
        if max_batch_size < 1:
            raise ValueError("max_batch_size must be at least 1")
        if coalesce_ms < 0:
            raise ValueError("coalesce_ms must not be negative")
        if cache_size < 0:
            raise ValueError("cache_size must not be negative")

        self._model = model
        self._max_batch_size = int(max_batch_size)
        self._coalesce_seconds = float(coalesce_ms) / 1000.0
        self._cache_size = int(cache_size)
        self.profile: EmbeddingProfile = model.profile
        self._cache: OrderedDict[str, EmbeddingVector] = OrderedDict()
        self._entries: dict[str, _Entry] = {}
        self._pending: list[_Entry] = []
        self._flusher: asyncio.Task[None] | None = None

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        """Return one vector per input text, preserving order and duplicates."""

        if not texts:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))

        resolved: dict[str, EmbeddingVector] = {}
        waiting: list[_Entry] = []
        for text in _deduplicate(texts):
            vector = self._cached(text)
            if vector is not None:
                resolved[text] = vector
                continue
            entry = self._entries.get(text)
            if entry is None:
                entry = _Entry(text)
                self._entries[text] = entry
                self._pending.append(entry)
            waiting.append(entry)

        usage = InferenceUsage(requests=0)
        if waiting:
            await self._dispatch(waiting)
            batches: list[_Batch] = []
            seen: set[int] = set()
            for entry in waiting:
                batch = entry.batch
                if batch is None or id(batch) in seen:
                    continue
                seen.add(id(batch))
                batches.append(batch)
            # ``shield`` keeps a cancelled caller from cancelling the shared
            # request that other callers are still waiting on.
            for batch in batches:
                assert batch.task is not None
                await asyncio.shield(batch.task)
            for batch in batches:
                usage = _merge_usage(usage, batch.usage)
                for text, vector in zip(batch.texts, batch.vectors, strict=True):
                    resolved.setdefault(text, vector)

        return EmbeddingResult(
            vectors=tuple(resolved[text] for text in texts),
            usage=usage,
        )

    async def _dispatch(self, waiting: list[_Entry]) -> None:
        """Drive the shared flusher until every awaited entry owns a batch."""

        while any(entry.batch is None for entry in waiting):
            flusher = self._flusher
            if flusher is None or flusher.done():
                flusher = asyncio.ensure_future(self._flush())
                self._flusher = flusher
            await asyncio.shield(flusher)

    async def _flush(self) -> None:
        """Wait out the coalescing window, then split pending texts into batches."""

        if self._coalesce_seconds > 0.0:
            await asyncio.sleep(self._coalesce_seconds)
        pending = self._pending
        self._pending = []
        for start in range(0, len(pending), self._max_batch_size):
            chunk = pending[start : start + self._max_batch_size]
            batch = _Batch(tuple(entry.text for entry in chunk))
            for entry in chunk:
                entry.batch = batch
            task: asyncio.Task[None] = asyncio.ensure_future(self._execute(batch))
            batch.task = task
            task.add_done_callback(lambda _task, settled=batch: self._settle(settled))

    async def _execute(self, batch: _Batch) -> None:
        """Run one provider request and publish its result on the batch."""

        result = await self._model.embed(batch.texts)
        vectors = tuple(result.vectors)
        if len(vectors) != len(batch.texts):
            raise ValueError(
                f"embedding model returned {len(vectors)} vectors "
                f"for {len(batch.texts)} texts"
            )
        batch.vectors = vectors
        batch.usage = result.usage

    def _settle(self, batch: _Batch) -> None:
        """Release the batch's texts and cache the vectors of a successful run."""

        for text in batch.texts:
            entry = self._entries.get(text)
            if entry is not None and entry.batch is batch:
                del self._entries[text]
        task = batch.task
        if task is None or task.cancelled():
            return
        if task.exception() is not None:
            # Failures stay out of the cache so the same text can be retried.
            return
        for text, vector in zip(batch.texts, batch.vectors, strict=True):
            self._store(text, vector)

    def _cached(self, text: str) -> EmbeddingVector | None:
        if self._cache_size <= 0:
            return None
        vector = self._cache.get(text)
        if vector is None:
            return None
        self._cache.move_to_end(text)
        return vector

    def _store(self, text: str, vector: EmbeddingVector) -> None:
        if self._cache_size <= 0:
            return
        self._cache[text] = vector
        self._cache.move_to_end(text)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)


__all__ = ["CoalescingEmbeddingModel"]
