# processing-01：按源计数触发处理

## 题目要求

在现有的定时通道之外，增加一条按“累积源数量”触发的准入通道：某个 scope 自上次成功消费以来新增的源条目达到阈值时，启动一次普通的处理调用，而不是等到下一个时间点。

硬约束四条：

1. 不能改动时间通道的行为，时间触发照旧。
2. 重复采集同一条记录，不能让计数虚增。
3. receipt 可信度升级之类的元数据变化，也不能让计数虚增。
4. 已经被消费过的历史不能重复计入。

## 结论：用“日志头 − 游标”算待处理量，四条约束自动满足

待处理量定义为：

```
pending = source_journal_heads.position − source_cursors.sequence
```

- `position` 是这个 scope 在源日志里的**持久化写入位置**，只在新条目真正落盘时前进。
- `sequence` 是这个 binding **最后一次成功提交**的游标位置。

选这两个量，四条约束不是靠额外判断绕过去的，而是结构上不可能违反：

| 约束 | 为什么自动成立 |
| --- | --- |
| 重复采集不虚增 | 同一条记录重复写入不改变 `position`，差值不变 |
| receipt 升级不虚增 | receipt 可信度是元数据，不进源日志，`position` 不动 |
| 已消费历史不重算 | `sequence` 随成功提交前进，差值天然扣掉已消费部分 |
| 不动时间通道 | 新通道读的是另外两张表，与 `schedule_seconds` 那条路径无交集 |

如果改成“累加每次采集到的条数”，前两条都要额外去重；如果改成“用 intent 的 requested_generation 计数”，第三条会算重。这个定义把这四个坑一次绕开。

## 三处改动

### 1. `config.py`：加两个字段和严格校验

```python
memory_source_count_threshold: int | None = None
topic_memory_source_count_threshold: int | None = None
```

校验用 `mode="before"` 手写，而不是 `strict=True`：

```python
@field_validator("memory_source_count_threshold", "topic_memory_source_count_threshold", mode="before")
@classmethod
def reject_non_strict_count_threshold(cls, value: Any) -> Any:
    if value is None:
        return None
    if type(value) is not int:
        raise ValueError("Source count threshold must be a positive integer")
    if value < 1:
        raise ValueError("Source count threshold must be a positive integer")
    return value
```

必须是 `type(value) is not int`，不能写 `isinstance`。`bool` 是 `int` 的子类，用 `isinstance` 会让 `True` 被当成阈值 1 静默通过。同理，`1.0` 在宽松模式下会被 pydantic 转成 `1`，所以要在 `mode="before"` 阶段就拒掉。

### 2. `artifact_processing.py`：新开一条发现通道

绑定上加一个字段，`_FamilyState` 上记两个状态：

```python
source_count_threshold: int | None = None
# _FamilyState
count_after: str | None = None      # 分页游标，按 scope_id 升序翻页
next_count_at: float = 0.0          # 下一次允许扫描的时刻
```

`_next_wake_seconds()` 的等待列表里加上 `state.next_count_at`，否则计数通道会被定时通道的等待时长拖住。

扫描本体：

```python
async def _discover_counted(self, state: _FamilyState) -> None:
    binding = state.binding
    threshold = binding.source_count_threshold
    if threshold is None:
        return
    heads = SOURCE_JOURNAL_HEADS_TABLE
    statement = select(heads.c.scope_id, heads.c.position).order_by(heads.c.scope_id).limit(_DISCOVERY_PAGE_SIZE)
    if state.count_after is not None:
        statement = statement.where(heads.c.scope_id > state.count_after)
    admitted: list[str] = []
    capacity = self._fresh_capacity(state)
    if capacity <= 0:
        return
    last_examined: str | None = None
    truncated = False
    async with self._database.transaction() as connection:
        await self._leases.require_fence(connection, self._require_current_fence())
        rows = (await connection.execute(statement)).all()
        # One batched cursor read per page keeps the scan flat as the number
        # of Scopes grows; a per-Scope load would cost one round trip each.
        cursors = await SourceCursorRepository().load_many(
            connection, [scope for scope, _ in rows], binding.binding_name
        )
        for scope, high in rows:
            if len(admitted) >= capacity:
                # Leave the rest of the page for the next pass instead of
                # overflowing the bounded ready queue.
                truncated = True
                break
            last_examined = scope
            if scope in state.queued or scope in state.running or scope in state.retries:
                continue
            stored = cursors.get(scope)
            consumed = 0 if stored is None else stored.cursor.sequence
            if int(high) - consumed < threshold:
                continue
            intent = await self._intents.load(connection, scope, binding.binding_name, for_update=True)
            # An accepted call that has not been acknowledged keeps its own
            # authorization; retry owns it, so the gate must not duplicate it.
            if intent is not None and intent.requested_generation > intent.handled_generation:
                continue
            await self._intents.request(connection, scope, binding.binding_name)
            admitted.append(scope)
    if truncated:
        state.count_after = last_examined
    else:
        state.count_after = str(rows[-1][0]) if len(rows) == _DISCOVERY_PAGE_SIZE else None
    for scope in admitted:
        self._enqueue(state, scope)
```

四个必须这么写的点：

- **`intent.requested_generation > intent.handled_generation` 要跳过。** 这个条件是“已经受理、还没回执”。此时那次调用归 retry 通道管，计数通道再受理一次就是重复启动。这一条不加，长任务会被反复拉起来。
- **容量上限截断而不是溢出。** ready 队列有硬上限（`_fresh_capacity` 封顶 50），一页扫出几百个达标 scope 会直接把队列撑爆。截断后把 `count_after` 设成最后一个检查过的 scope，下一轮接着翻。
- **翻页游标要能被重置。** 一页没取满说明扫到底了，`count_after` 归 `None`，下一轮从 0 开始。否则新出现的、`scope_id` 排序靠前的 scope 永远轮不到。
- **游标要批量读。** 一页 50 个 scope 逐个 `load()` 就是 50 次往返；`SourceCursorRepository.load_many()` 内部按 `SELECTION_BATCH_SIZE` 分批 `IN` 查询，一次搞定。

### 3. `composition.py`：把阈值接到绑定上

```python
source_count_threshold=getattr(config.runtime, f"{prefix}_source_count_threshold", None),
```

用 `getattr` 而不是直接取属性，是因为 `memory` 和 `topic_memory` 两个前缀共用这段构造代码，字段名不同。

## 应用补丁

```bash
git apply --check competition/submission/patches/processing-01-count-trigger.patch
git apply competition/submission/patches/processing-01-count-trigger.patch
```

补丁基于冻结基线 `9db1753434162c0aa7c9f1189a1722e617880a52` 生成。当前仓库这三个文件与基线一致，可以直接应用。

应用后跑验收：

```bash
cd competition
python -m pytest challenges/processing-01-count-trigger -q \
  -o addopts="-p no:cacheprovider --import-mode=importlib" \
  --basetemp=/tmp/pcrun
```

需要先 `pip install anthropic`，否则 topic-memory 的用例会在子进程里失败，日志只留一行 `worker_failed`。

## 验证结果

| 范围 | 结果 |
| --- | --- |
| `challenges/processing-01-count-trigger` | 17 passed |
| `challenges/context-02-incremental-pack` | 14 passed |
| 其余七题回归 | 63 passed |

补丁本身在冻结基线副本上验证过：`patch -p1 --dry-run` 无冲突，应用后三个文件与开发分支逐字节一致（`cmp` 无输出）。

## 踩过的坑

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 16 个用例报 `FileExistsError: pytest-of-unknown` | 沙箱禁止 `mkdir(exist_ok=True)` | `--basetemp=/tmp/xxx` |
| `Plugin already registered under a different name: asyncio` | 仓库 `pytest.ini` 与新版插件入口点重名 | `-o addopts="-p no:cacheprovider --import-mode=importlib"` |
| topic-memory 用例全部超时，日志只有 `worker_failed` | 子进程 `from anthropic import AsyncAnthropic` 失败 | `pip install anthropic` |
| 阈值传 `True` 被当成 1 通过 | `bool` 是 `int` 子类 | 校验用 `type(v) is not int` |
