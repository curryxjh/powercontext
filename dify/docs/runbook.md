# 忘川当铺 · 运行手册

本手册按「PowerContext → 适配层 → Dify」的顺序启动。所有命令都在仓库根目录或标注的目录执行；示例中的路径、端口和令牌均为占位值。

## 0. 端口与组件

| 组件 | 默认地址 | 说明 |
| --- | --- | --- |
| PowerContext Server | `http://127.0.0.1:8000` | 只监听回环，Dify 不直接访问 |
| 忘川当铺适配层 | `http://0.0.0.0:8787` | Dify 通过 `host.docker.internal:8787` 访问 |
| Dify | 由你的部署决定 | 需要已配置的对话模型 |

## 1. 启动 PowerContext

### 1.1 安装

```bash
python -m venv .venv-pc
# Windows: .venv-pc\Scripts\activate
# Linux/macOS: source .venv-pc/bin/activate
pip install "powercontext[cli,server]==1.2.0"
```

也可以从本仓库安装当前源码：

```bash
pip install -e ".[cli,server]"
```

### 1.2 最小配置

新建 `pc.env`（路径按实际位置替换）：

```dotenv
POWERCONTEXT_HOME=/absolute/path/to/powercontext-data
POWERCONTEXT_SERVER_HTTP_HOST=127.0.0.1
POWERCONTEXT_SERVER_HTTP_PORT=8000
POWERCONTEXT_SERVER_DATABASE_KIND=sqlite
POWERCONTEXT_SERVER_ACCESS_MODE=disabled
POWERCONTEXT_SERVER_DASHBOARD_ENABLED=false
POWERCONTEXT_SERVER_MCP_ENABLED=false
POWERCONTEXT_SERVER_METRICS_ENABLED=false
```

这组配置只启用 SQLite 与 FTS5，不需要生成模型或 embedding 模型；适配层也只依赖这些能力。`POWERCONTEXT_HOME` 是数据目录，记忆数据库落在其下。

### 1.3 运行与自检

```bash
powercontext server run --env-file /absolute/path/to/pc.env
```

另开终端：

```bash
curl http://127.0.0.1:8000/health/ready
```

期望返回 200，且 `checks.database` 为 `ready`。首次启动会在 `POWERCONTEXT_HOME` 下创建数据库。

> 端口被占用时，把 `POWERCONTEXT_SERVER_HTTP_PORT` 改成其他端口（例如 18080），并同步修改适配层的 `POWERCONTEXT_URL`。

## 2. 启动适配层

```bash
cd dify/backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

回到 `dify/`，准备环境变量：

```bash
cd ..
cp .env.example .env
```

默认值即可；如果 PowerContext 不在 8000，修改 `.env` 中的 `POWERCONTEXT_URL`。

启动：

```bash
bash scripts/start_backend.sh
# 或手动：
# cd backend && POWERCONTEXT_URL=http://127.0.0.1:8000 python -m wangchuan
```

自检：

```bash
curl http://127.0.0.1:8787/health
```

期望：

```json
{"status":"ok","powercontext":"ready"}
```

运行适配层测试（可选）：

```bash
cd backend
pip install pytest
python -m pytest -q
```

期望 `7 passed`。

## 3. 让 Dify 访问适配层

DSL 中 4 个 HTTP 节点固定请求 `http://host.docker.internal:8787`。

### 3.1 Dify 用 Docker 部署（Windows / macOS）

`host.docker.internal` 开箱可用。确认宿主机防火墙允许 Docker 网段访问 8787；适配层默认监听 `0.0.0.0`。

### 3.2 Dify 用 Docker 部署（Linux）

在 `docker-compose.yml` 的 `api` 与 `worker` 服务下增加：

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

然后：

```bash
docker compose up -d
```

### 3.3 Dify 从源码运行

把 DSL 中 4 个 HTTP 节点的 URL 从 `http://host.docker.internal:8787` 改成 `http://127.0.0.1:8787`。可以在导入前直接编辑 YAML：

```bash
sed -i 's#http://host.docker.internal:8787#http://127.0.0.1:8787#g' dify/dsl/wangchuan-pawnshop.yml
```

或者导入后逐个打开「读取账本」「赎回当票」「召回旧账」「记入账本」四个 HTTP 节点修改。

### 3.4 只允许本机访问适配层

适配层没有鉴权。若 Dify 与后端在同一台机器且不需要 Docker 网关访问：

```bash
PAWN_HOST=127.0.0.1 bash scripts/start_backend.sh
```

同时把 Dify 的 URL 改为 `127.0.0.1`。

## 4. 导入 Dify DSL

1. 在 Dify「设置 → 模型供应商」中启用 DeepSeek（官方插件 `langgenius/deepseek` 0.0.26+，模型 `deepseek-v4-flash`）并填入 API Key；DSL 默认使用 `langgenius/deepseek/deepseek` + `deepseek-v4-flash`。
2. 进入工作室，创建空白应用，选择「导入 DSL 文件」。
3. 选择 `dify/dsl/wangchuan-pawnshop.yml`。
4. DSL 版本为 `0.3.1`，Dify 1.18（当前 DSL `0.7.0`）导入时会提示版本较低；同主版本可正常导入，状态为「完成但有警告」，按界面提示继续即可。
5. 打开「掌柜阿忘」LLM 节点，确认模型可用。若没有 DeepSeek，选择你自己的对话模型即可，提示词无需修改。
6. 确认 4 个 HTTP 节点地址与第 3 节一致。
7. 发布并打开应用。

导入后应看到 13 个节点：开始、组装请求、是否查账、读取账本、账本回复、是否赎回、赎回当票、赎回回复、召回旧账、掌柜阿忘、封装本轮记账、记入账本、掌柜回复。

## 5. 冒烟测试

在 Dify 应用里依次发送：

```text
我想典当第一次看海的记忆，那天码头有海风，回来还买了桂花糕，换一次好运。
```

期望：掌柜回复，末尾出现 `—— 当票 #1 · 已记入忘川账本 ——`。

新开一个对话（同一浏览器），发送：

```text
又是我。今天路过码头闻到海风，忽然想起那块桂花糕。我想再押一段加班到凌晨的记忆，换一夜好眠。
```

期望：掌柜先引用「码头」「桂花糕」等旧账细节，末尾是当票 #2。

继续发送：

```text
查账
```

期望：列出未赎当票 #1、#2。

```text
赎回 1
```

期望：返还第一段记忆原文，并提示还剩 1 笔。

再发送：

```text
查账
```

期望：只剩 #2。

## 6. 一键验收（不经过 Dify 界面）

后端与 PowerContext 启动后（以下脚本需要 Python 3.11+ 与 `PyYAML`；`verify_e2e.py` 只用标准库）：

```bash
PYTHONIOENCODING=utf-8 python dify/scripts/verify_e2e.py \
  --backend-url http://127.0.0.1:8787 \
  --powercontext-url http://127.0.0.1:8000
```

脚本会新建一个独立玩家，跑完「首次进店 → 两次典当 → 新会话召回 → 查账 → 赎回 → 复查 → 读取 PowerContext 原始条目」，并把 Markdown/JSON 证据写到 `dify/docs/evidence/`。全部步骤应显示 PASS。

不启动 Dify 也可以验证图结构：

```bash
PYTHONIOENCODING=utf-8 python dify/scripts/check_dsl.py
PYTHONIOENCODING=utf-8 python dify/scripts/replay_flow.py \
  --player smoke-player \
  --message "我想典当第一次看海的记忆，码头有海风，换一次好运。" --verbose
```

`replay_flow.py` 会执行 DSL 的 Code、IF-ELSE、HTTP、Answer 节点；LLM 节点使用确定性替身。

## 7. 故障排查

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `/health` 返回 `degraded` | PowerContext 未启动或地址错误 | 检查 `POWERCONTEXT_URL`，直接访问 `/health/ready` |
| Dify 报连接超时/拒绝 | Docker 无法解析 `host.docker.internal`，或后端未监听 0.0.0.0 | Linux 加 `extra_hosts`；确认 `PAWN_HOST=0.0.0.0`；检查防火墙 |
| HTTP 节点返回 502 | 适配层连不上 PowerContext | 看适配层日志与 PowerContext 日志；确认端口一致 |
| 回答末尾没有当票号 | `/v1/session/turn` 失败，或 Answer 节点变量被改 | 打开 Dify 运行详情查看 `记入账本` 节点输出 |
| 新会话不记得旧账 | 换了浏览器/隐身窗口，`sys.user_id` 变了；或输入与旧账没有词面交集 | 用同一浏览器；输入旧账中的具体词（码头、桂花糕） |
| 查账为空但刚典当过 | 请求打到了另一个玩家 scope | 确认 Dify 的 `sys.user_id` 未变；检查适配层日志中的 player |
| 赎回提示编号不存在 | 当票已赎回，或输入了账本外的编号 | 先「查账」确认未赎编号 |
| 中文检索偶尔失效 | FTS5 是词面匹配，不做同义词/语义扩展 | 使用旧账里的原文词；或为 PowerContext 启用 embedding |
| 导入后模型节点报错 | 未配置模型，或模型名不存在 | 在 LLM 节点选择当前实例可用的模型 |
| 端口 8000 被占用 | 其他服务占用 | 改 PowerContext 端口，并同步 `POWERCONTEXT_URL` |

## 8. 停止与清理

- 适配层与 PowerContext 都在前台运行，`Ctrl+C` 即可停止。
- 演示数据在 `POWERCONTEXT_HOME` 下。需要全新账本时，停止 PowerContext，换一个空的 `POWERCONTEXT_HOME` 再启动；不要直接编辑 SQLite。
- 换浏览器或隐身窗口会得到新的 `sys.user_id`，相当于新玩家。
