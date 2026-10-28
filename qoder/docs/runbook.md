# 运行与运维手册

## 1. 环境要求

- Python 3.11 或更高版本；开发与验收使用 3.12.4。
- 首次安装依赖需要能访问 PyPI；运行期不需要网络、不需要模型 API Key。
- 平台：Windows 10/11、macOS、Linux。Windows 建议使用 PowerShell 或 Git Bash。
- 资源：单实例、SQLite；演示数据下内存与 CPU 占用很低，无外部服务依赖。

## 2. 安装与启动

### 2.1 手动方式

```bash
cd qoder
python -m venv .venv

# Windows PowerShell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py

# macOS / Linux
. .venv/bin/activate
pip install -r requirements.txt
python run.py
```

### 2.2 脚本方式

```bash
./run.sh          # macOS / Linux / Git Bash，自动建 venv、装依赖
.\run.ps1         # Windows PowerShell
```

启动后访问 <http://127.0.0.1:8010>。首次启动会在空库中写入演示学员「林知夏」。

### 2.3 空数据启动

```bash
WENGU_AUTO_SEED=0 python run.py
```

PowerShell：

```powershell
$env:WENGU_AUTO_SEED = "0"
.venv\Scripts\python.exe run.py
```

## 3. 配置

复制 `.env.example` 为 `qoder/.env` 后修改；应用启动时读取，已存在的环境变量优先。

```dotenv
WENGU_HOST=127.0.0.1
WENGU_PORT=8010
WENGU_DATA_DIR=./data
WENGU_TIMEZONE=Asia/Shanghai
WENGU_AUTO_SEED=1
WENGU_DEFAULT_DAILY_MINUTES=20
WENGU_DEFAULT_STYLE=图示 + 生活类比
WENGU_MAX_IMPORT_CHARS=120000
WENGU_MAX_ANSWER_BYTES=6000
WENGU_RELOAD=0
```

说明：

- `WENGU_DATA_DIR` 的相对路径按 `qoder/` 解析，不受启动时工作目录影响。
- 修改端口后，验证脚本需同步设置：`WENGU_URL=http://127.0.0.1:<port>`。
- `WENGU_RELOAD=1` 仅用于开发；生产/演示保持 `0`，避免重载时重复打开数据库。

### 局域网或容器演示

```bash
WENGU_HOST=0.0.0.0 python run.py
```

此时同一网络的人可访问 `http://<你的IP>:8010`。**应用没有登录与权限控制**，仅适合受控演示环境；公网发布必须加反向代理、TLS 与访问控制。

## 4. 数据管理

### 4.1 数据目录

| 文件 | 说明 |
| --- | --- |
| `data/wengu.db` | PowerContext 内嵌数据库 |
| `data/wengu.db-wal` / `-shm` | WAL 日志与共享内存 |
| `data/wengu.scheduler.db` | PowerContext 调度器 |
| `data/usage.jsonl` | API 使用日志（真实使用证据来源） |

### 4.2 备份

SQLite 使用 WAL。最稳妥的备份方式：停止服务后复制整个 `data/`。

运行中需要单学员导出时：

```bash
curl -OJ http://127.0.0.1:8010/api/learners/demo/export
```

导出文件包含 Scope 信息、memory revision 与全部记忆（含原始文本与类型化元数据）。

### 4.3 重置演示数据

停止服务后：

```bash
# 方式一：重建演示学员，保留其他学员
python scripts/seed_demo.py --force

# 方式二：完全清空（会删除所有学员、反馈与使用日志）
rm -rf data
```

Windows PowerShell 清空用 `Remove-Item -Recurse -Force data`。删除前请确认没有需要保留的真实使用数据。

### 4.4 手动种子

```bash
python scripts/seed_demo.py
python scripts/seed_demo.py --force
```

脚本直接打开数据目录，**不要与运行中的服务同时写同一个数据库**。正常启动时如果库中已有学习者，不会自动重复种子。

## 5. 验证与测试

### 5.1 只读验收脚本

服务启动后：

```bash
python scripts/verify_powercontext.py
WENGU_URL=http://127.0.0.1:8010 python scripts/verify_powercontext.py   # 显式指定
```

期望最后一行类似：

```text
Result: 15/15 checks passed
```

检查项：server、PowerContext 1.2、learner、scope、knowledge、review replay、memory entries、sources captured、chinese FTS、model requests、sources、context.prepare、citations、revision history、web app。

### 5.2 单元与集成测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

测试使用临时目录，不会触碰 `qoder/data/`。

### 5.3 使用日志汇总

```bash
python scripts/export_usage.py
python scripts/export_usage.py --days 30 --out docs/usage-summary.json
```

输出请求数、活跃天数、成功写入数、路由分布、状态码分布与观察到的学员。数字只来自 `usage.jsonl`，不手工编造。

## 6. 作为常驻服务运行（可选）

Linux systemd 示例（按实际路径修改）：

```ini
[Unit]
Description=WenGu study coach
After=network.target

[Service]
WorkingDirectory=/opt/powercontext/qoder
Environment=WENGU_HOST=127.0.0.1
Environment=WENGU_PORT=8010
Environment=PYTHONUTF8=1
ExecStart=/opt/powercontext/qoder/.venv/bin/python run.py
Restart=on-failure
User=wengu

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wengu
sudo systemctl status wengu
journalctl -u wengu -f
```

也可以用 uvicorn 直接启动：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --workers 1
```

不要增加 workers：SQLite 与进程内写锁按单实例设计。

## 7. 故障排查

| 现象 | 原因与处理 |
| --- | --- |
| 端口被占用 | 改 `WENGU_PORT` 或结束占用进程；Windows：`netstat -ano | findstr :8010` |
| 页面能开但数据为空 | `WENGU_AUTO_SEED=0` 且库为空；运行 `python scripts/seed_demo.py` 或调用 `POST /api/demo/seed` |
| 演示学员重复/数据混乱 | 用 `seed_demo.py --force`，或停止服务后清空 `data/` |
| `database is locked` | 同时运行了多个进程或 seed 脚本与服务并用；只保留一个写入者 |
| 中文检索无结果 | 确认运行时为 1.2.0；FTS 对空格分词敏感，尝试更短的关键词（如「卡点」） |
| 时间/streak 不对 | 检查 `WENGU_TIMEZONE`；streak 按该时区的本地日期计算 |
| Windows 终端中文乱码 | 设置 `PYTHONUTF8=1`（`run.ps1`/`run.sh` 已设置） |
| 验证脚本 `FAIL server` | 服务未启动或端口不符；先打开 `/api/health` 确认 |
| 依赖安装失败 | 确认 Python ≥3.11；升级 pip；确认可访问 PyPI |
| 修改 `.env` 不生效 | 环境变量优先级更高；检查当前 shell 是否已 export 同名变量 |

## 8. 升级与回滚

- 依赖版本固定在 `requirements.txt`；升级 PowerContext 前先在临时数据目录跑 `pytest` 与 `verify_powercontext.py`。
- 升级前备份 `data/`；回滚时恢复代码与数据目录即可。
- 本项目不修改 PowerContext 源码，也不写入其内部表结构，除运行时正常 API 外无私有耦合。
