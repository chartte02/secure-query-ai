# 本机使用教程

所有常用操作从项目根目录的 `run.ps1` 进入。当前机器已有 Python 虚拟环境、Ollama、coder 7B 和 3B；不用重新安装或拉取模型。

## 1. 启动、查看和停止

在系统自带的 Windows PowerShell 中进入项目目录；以下命令不依赖 `pwsh`：

```powershell
cd "C:\Users\loong\Desktop\数据库大作业\secure-query-ai"
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 start
```

看到 `Ready: http://127.0.0.1:8000` 后打开 <http://127.0.0.1:8000>。服务在后台运行，终端命令会返回；不需要另开窗口手动执行 `ollama serve`。相同配置下重复 `start` 会显示已运行。

网页选择场景后点击“运行攻防对照”，按顺序比较 baseline 与 hardened。顶部显示模型和版本；第三列“网关未接入”表示 C 的查询链路还未完成，不是模型故障。

后端已提供查询编排入口 `POST /api/v1/queries`：它先生成候选 SQL，再交给 `SqlGateway`。C 的网关尚未接入，所以当前返回 HTTP 503 + `status=unavailable`，响应中仍包含生成结果；该入口不会执行 SQL。

```powershell
# 查看配置、实际运行模型、地址、模型目录和日志目录
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 status

# 停止本项目管理的 API 和 Ollama，保留模型文件
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 stop
```

`stop` 根据 `.runtime/services.json` 核对进程 PID、名称和启动时间，不会接管或停止其他 Ollama 实例。关闭网页标签页不会停止服务。

## 2. 配置与切换模型

当前 `.env` 的主要配置如下：

```dotenv
SECUREQUERY_PROVIDER=ollama
SECUREQUERY_DEMO_MODE=true
SECUREQUERY_MODEL=qwen2.5-coder:7b
SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11435
```

修改 `.env` 后先 `stop`，再 `start`；启动命令会核对完整配置指纹，包括 Demo 开关、超时和大小限制，发现变化时会要求重启。`status` 分别显示配置与实际运行中的模型和 Demo 状态。也可用命令参数临时切换，参数不会改写 `.env` 或系统环境变量：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 stop
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 start -Model qwen2.5-coder:3b
```

无模型彩排使用明确标记的 Mock：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 stop
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 start -Provider mock
```

恢复 `.env` 中的 7B 配置，只需再次 `stop` → `start`。切换后刷新页面，检查顶部模型名称。临时参数可能让 `status` 中的“配置模型”和“实际运行模型”不同，这是两者分别展示的原因。

模型不会静默降级、自动下载或自动更新。`qwen2.5:7b` 通用模型与 `qwen2.5-coder:7b` 编程模型不同；本项目使用后者。

## 3. 文件和端口在哪里

| 内容 | 位置 |
|---|---|
| Ollama 程序 | `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` |
| 项目模型 | `.runtime/models/`，7B 约 4.68 GB、3B 约 1.93 GB |
| 当前日志 | `.runtime/logs/` |
| 受管理的服务身份 | `.runtime/services.json` |
| 旧日志与启动项备份 | `.runtime/backups/` |
| 实验结果 / 截图 | `artifacts/experiments/` / `artifacts/screenshots/` |

项目 Ollama 独占 `127.0.0.1:11435`；前端/API 使用 `127.0.0.1:8000`。系统默认 `11434` 实例与本项目分开，机器级模型路径没有被项目改写。

`OLLAMA_MODELS` 只为项目新启动的服务进程设置；通过哪个服务下载或运行模型，就使用那个服务的模型目录。不要通过托盘或默认 11434 服务判断本项目是否安装了模型。

需要查看专用实例时，另开 PowerShell 执行：

```powershell
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
$env:OLLAMA_HOST = "127.0.0.1:11435"
& $ollamaExe list  # 磁盘上已经安装的模型
& $ollamaExe ps    # 当前驻留内存/显存的模型
```

`ps` 为空不表示模型被删除，下次生成会重新加载。完全结束本项目时优先用 `run.ps1 stop`。

## 4. 测试和实验

```powershell
# 离线测试，不请求真实模型
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 test

# 先启动服务，再运行当前配置的固定合成测试集
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 evaluate

# 单个样例彩排，或明确选择 3B 评估
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 evaluate -Case normal_grade
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 evaluate -Model qwen2.5-coder:3b
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 evaluate -Provider mock -Case normal_grade
```

真实模型评估前先 `start`，并避免同时通过网页发起推理。`evaluate` 读取 `.env` 和本次命令参数，不从运行中的网页推断配置；临时使用 Mock 时也要在评估命令指定 `-Provider mock`。输出 JSON 写入 `artifacts/experiments/`，含模型 digest、Prompt/Schema 版本、状态和延迟。Mock 记录与真实模型分开标记；所有评估均不执行 SQL。历史结果和已知语义错误见 [实测报告](local-model-evaluation.md)。

## 5. 新环境初始化与故障处理

仅在新机器或尚无 `.venv` 时初始化 Python 3.12 环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

示例配置显式开启课堂 Demo，并选择无需模型的 Mock；本机已有 `.env`，不要用示例覆盖它。没有 `.env` 时程序默认 Mock 且关闭 Demo。新机器若需真实推理，还需按 [Ollama 官方说明](https://ollama.com/download) 安装软件并准备选定模型，`run.ps1` 不负责安装或下载。

**仅在新机器确实缺模型时**，先将 `.env` 的 Provider 改为 `ollama`，再执行 `start`。脚本会启动项目专用 Ollama；若报告模型缺失，API 暂不启动，已托管的 Ollama 会保留。随后在 PowerShell 中明确连接项目端口下载：

```powershell
$env:OLLAMA_HOST = "http://127.0.0.1:11435"
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull qwen2.5-coder:7b
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 start
```

如演示者明确需要 3B，再用同一专用实例执行 `pull qwen2.5-coder:3b`；不必下载通用的 `qwen2.5:7b`。若修改过项目端口，上述地址也使用 `.env` 中的实际值。当前电脑两个 coder 模型均已具备，无需执行这一步。

| 现象 | 处理 |
|---|---|
| 配置已改变 | `stop` 后重新 `start`，刷新网页确认模型 |
| 8000 或 11435 被非项目进程占用 | 先确认占用者；脚本不会强制结束它。Ollama 可在 `.env` 改用空闲回环端口后重新启动 |
| 找不到模型 | 确认连接的是专用 11435 服务和 `.runtime/models`，先用 `list` 核实，不要重复下载 |
| Demo 未开启 | 在 `.env` 明确设置 `SECUREQUERY_DEMO_MODE=true`，再重启 |
| 504 或服务无响应 | 查看 `status` 与 `.runtime/logs/`，保持电脑唤醒；需要时 `stop` → `start` |

新服务已限制单模型驻留、单并发、4096 上下文并关闭云端推理。首次加载通常较慢；超时不能算作模型拒答。数据库接入后的前端输入、网关和结果显示方式见 [A/B/C 联调契约](integration.md)。

## 6. 查看 B 的数据库控制效果（实验室模式）

在 `.env` 同时设置 `SECUREQUERY_DEMO_MODE=true` 和 `SECUREQUERY_LAB_GATEWAY=true`，然后 `run.ps1 stop` → `start`。该模式把候选 SQL 直接交给 B 的只读角色执行，**不是 C 的策略网关**，只用于本地演示。

```powershell
# 列出固定回放场景
Invoke-RestMethod http://127.0.0.1:8000/api/v1/lab/scenarios | ConvertTo-Json -Depth 5

# 正常结果：3 行 + db_role=sq_student_s01
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/lab/replay/own_grades | ConvertTo-Json -Depth 6

# 列权限拒绝：error.sqlstate=42501
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/lab/replay/column_denied | ConvertTo-Json -Depth 6

# RLS 静默过滤：executed + 0 行
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/lab/replay/rls_cross_student | ConvertTo-Json -Depth 6
```

固定回放标记 `candidate_origin=fixed_sql_replay`、`model_invoked=false`，不能算作模型攻击结果。真实 hardened 模型通常会先拒答明显越权请求，所以现场演示 B 的 SQLSTATE 用回放；`/api/v1/queries` 展示正常生成 + B 的真实结果。
