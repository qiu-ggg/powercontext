# 验收记录

## 环境

| 项 | 值 |
| --- | --- |
| 机器 | macOS，Intel（x86_64），无容器运行时 |
| Python | 3.13 |
| 安装方式 | `pip install -e`，包位于 `site-packages/powercontext` |
| 额外依赖 | `pydantic-ai-slim[openai]>=2.27.1,<3`、`anthropic` |

## 命令

```bash
cd competition
python -m pytest challenges/processing-01-count-trigger challenges/context-02-incremental-pack \
  -q -o addopts="-p no:cacheprovider --import-mode=importlib" --basetemp=/tmp/pcC
```

## 结果

```
...............................                                          [100%]
31 passed in 344.19s (0:05:44)
```

拆分：`processing-01-count-trigger` 17 项，`context-02-incremental-pack` 14 项。

同一轮改动前的记录：其余七题回归 63 项全部通过。

## 改动前后

`processing-01` 的三处改动在合入前跑过一次全量：8 失败 9 通过（587 秒）。失败原因不是实现，是环境——topic-memory 的子进程起不来。补上 `anthropic` 之后 17/17 通过（355 秒）。

`context-02` 的两处加固（批量游标读取、Base64 规范形式校验）合入后重跑，14/14 通过（5.89 秒），未引入回归。

## 补丁自检

```bash
cp -R <冻结基线副本> /tmp/applytest
cd /tmp/applytest
patch -p1 --dry-run < processing-01-count-trigger.patch   # 三个文件均无冲突
patch -p1 < processing-01-count-trigger.patch
cmp src/powercontext/builtin/runtime/config.py            <开发分支>/config.py
cmp src/powercontext/builtin/runtime/composition.py       <开发分支>/composition.py
cmp src/powercontext/builtin/runtime/artifact_processing.py <开发分支>/artifact_processing.py
```

`cmp` 三次均无输出，应用结果与开发分支逐字节一致。

## 未能验证的部分

**`context-02` 的 45% 传输成本门槛。** 验收用例不检查这一项，但它是该题的实际得分门槛。本地用 40 轮对话、三种查询切换节奏复现，节省率全部为负：

| 切换节奏 | 节省率 |
| --- | --- |
| 每轮切换 | −0.78 |
| 每 5 轮切换 | −0.73 |
| 每 10 轮切换 | −0.70 |

定位到两个叠加原因：`prepare` 输出里第一个变化的字节在 406 字符附近，前缀复用当场失效；Base64 的 4/3 膨胀让增量体积超过原始正文。要过门槛，需要让稳定前缀足够长，或者改成分块级复用而不是整段前缀复用。

**`retrieval-02-hybrid-search`。** `@seekdb/js-bindings` 只发布 `linux-x64`、`linux-arm64`、`darwin-arm64`，本机是 Intel Mac，无 Docker / Podman / Colima / Homebrew，无法构造运行环境。
