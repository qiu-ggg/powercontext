# 运行说明

## 1. 环境要求

- 运行 Flask 应用：Python 3.8+
- 运行真实 PowerContext Server：Python 3.11+（本机实测 3.12.14 + PowerContext 1.4.1）
- 不需要额外数据库；PowerContext 服务使用 SQLite 作为存储后端即可

## 2. 安装应用依赖

```bash
pip install -r requirements.txt
```

依赖：Flask 3.0.0、flask-cors 4.0.0、python-dotenv 1.0.0。

## 3. 启动真实 PowerContext Server（默认模式必需）

默认 `POWERCONTEXT_MODE=remote`，启动应用前必须先连上真实服务；服务不可达会直接报错，不会静默降级。
只有显式设置 `POWERCONTEXT_MODE=local`（离线演示）或 `auto`（允许探测失败后回退）时才不需要本步骤。

### 3.1 安装

PowerContext 需要 Python 3.11 及以上，建议单独建虚拟环境：

```bash
python -m venv .pc-venv
.pc-venv\Scripts\python -m pip install "powercontext[server,cli]"    # Windows
# source .pc-venv/bin/activate && pip install "powercontext[server,cli]"  # macOS/Linux
```

### 3.2 生成配置

```bash
.pc-venv\Scripts\powercontext config init --template --language zh --output .env --force
.pc-venv\Scripts\powercontext config validate --env-file .env
```

默认的 SQLite 配置可直接使用，关键项为：

```env
POWERCONTEXT_SERVER_HTTP_HOST=127.0.0.1
POWERCONTEXT_SERVER_HTTP_PORT=8000
POWERCONTEXT_SERVER_DATABASE_KIND=sqlite
POWERCONTEXT_SERVER_ACCESS_MODE=disabled
```

### 3.3 启动服务

```bash
.pc-venv\Scripts\powercontext server run --env-file .env --role all
```

看到 `PowerContext Server is ready` 后，用下面的命令确认：

```bash
curl http://127.0.0.1:8000/health/ready
curl http://127.0.0.1:8000/v1/capabilities
```

## 4. 初始化数据

```bash
python init_db.py
```

该命令会：

- 创建 `data/seekdb.db`（SQLite + FTS5 全文检索）并导入 12 篇示例文档
- 根据当前后端写入 demo_user 的偏好、3 条学习进度、3 条搜索历史、4 条浏览记录
- 打印实际使用的 PowerContext 后端（`remote` 或 `local`）

## 5. 启动应用

```bash
# 默认：强制真实服务（不可达会直接报错，避免静默降级）
python app.py

# 允许探测失败后回退本地兼容实现
set POWERCONTEXT_MODE=auto && python app.py             # Windows CMD
$env:POWERCONTEXT_MODE="auto"; python app.py            # PowerShell

# 仅离线演示：强制本地兼容实现
set POWERCONTEXT_MODE=local && python app.py
```

访问 `http://localhost:5000`。

环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POWERCONTEXT_MODE` | `remote` | `remote`（默认，不可达即报错）/ `auto` / `local` |
| `POWERCONTEXT_BASE_URL` | `http://127.0.0.1:8000` | 真实服务地址 |
| `FLASK_DEBUG` | `True` | 关闭调试时设为 `false` |

## 6. 确认实际后端

```bash
curl http://127.0.0.1:5000/api/health
```

返回示例：

```json
{
  "status": "ok",
  "powercontext": "remote",
  "powercontext_detail": {
    "mode": "remote",
    "base_url": "http://127.0.0.1:8000",
    "version": "API v1.4（PowerContext Server 1.4.1）",
    "fallback_reason": null
  }
}
```

页面首页、检索页和仪表盘也会显示同一个状态徽标。

## 7. 功能验证

### 搜索

1. 首页输入「深度学习」
2. 预期返回 1 条《深度学习入门指南》，相关度 100%
3. 页面下方显示 PowerContext 记忆搜索命中

### 学习进度

1. 打开 `/document/1`
2. 点击 50%
3. 刷新或重新打开，进度应恢复为 50%
4. 仪表盘「继续学习」出现该文档

### 仪表盘

1. 访问 `/dashboard`
2. 查看已浏览、完成学习、学习时长、搜索次数
3. 查看「最近搜索」与「PowerContext 上下文召回」
4. 修改偏好并保存

### 统计口径回归

1. 打开文档停留 10 秒以上再离开
2. 重新打开仪表盘，学习时长应增加相应秒数
3. 在文档页等待「相关文档」加载，不应新增搜索记录
4. 连续两次搜索同一个词，搜索次数只增加 1

## 8. 数据与重置

| 路径 | 内容 |
|------|------|
| `data/seekdb.db` | 文档与 FTS5 索引 |
| `data/powercontext.db` | 本地兼容实现的记忆（local 模式或回退时） |
| PowerContext Server 的 SQLite 文件 | 真实服务的数据，位置见服务 `.env` |

重置本地数据：删除 `data/` 后重新执行 `python init_db.py`。真实服务的数据通过 `init_db.py` 按 kind 覆盖写入，不会重复创建 Scope。
