# SecureQuery AI：Windows 本机启动与验收指南

更新日期：2026-11-02。本文是 **Windows 原生环境** 的主启动入口（Git Bash + Windows 原生 Ollama，GPU 加速）。功能状态看 [`status.md`](status.md)，C 的实测命令看 [`c-gateway-verification.md`](c-gateway-verification.md)，不要在多份文档重复维护同一组结果。

## 1. 运行模式

完整链路为：

```text
浏览器前端 → FastAPI/A 生成服务 → C RealGateway → hardened PostgreSQL
                                      ↓
                                audit.events
```

项目身份和 Schema 固定为 `student_s01`、`student_s02`、`teacher_t01` 与 `campus_lab_v1`。`lab_direct` 只用于 B 的固定 SQL 回放，不是正式安全网关。

## 2. 前置条件

- Windows 11 + Docker Desktop（Linux containers，即 WSL2 后端已由 Docker Desktop 接管）；
- Git Bash（或 PowerShell）；本机 Python 唯一满足 `>=3.11` 的是 `py -3.13`（`D:\Applications\CODE\Python`，3.13.5）；
- Ollama **Windows 原生版**（`%LOCALAPPDATA%\Programs\Ollama\ollama.exe`），模型 `qwen2.5-coder:7b` 已拉取到系统默认模型目录 `%USERPROFILE%\.ollama\models`；
- NVIDIA GPU 由 Windows 原生 Ollama 直接使用（本机 RTX 4060 Laptop，驱动 616.64，实测 `100% GPU`）。

确认：

```bash
docker version
py -3.13 --version
ollama --version
ollama list          # 应包含 qwen2.5-coder:7b
```

若 `docker version` 报 `permission denied`，先启动 Docker Desktop。

## 3. 安装依赖

数据库初始化前不要直接复制 `.env.example` 成 `.env`，其中的 `SQ_*` 是占位符，让初始化脚本生成随机本地凭据：

```bash
cd D:/Document/CODE/School/secure-query-ai
py -3.13 -m venv .venv
./.venv/Scripts/python.exe -m pip install -U pip
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
./.venv/Scripts/python.exe -m pip install -r requirements-dev.lock -r requirements-database.lock
```

`requirements-dev.lock` 提供 B 的测试工具；`requirements-database.lock` 是 C 正式网关的显式数据库依赖（`psycopg[binary]`）。A-only 安装仍不把数据库驱动放入主运行依赖。

## 4. 初始化 PostgreSQL

```bash
./.venv/Scripts/python.exe scripts/init_db.py --all
```

该命令首次运行会：生成 `.env` 随机凭据 → 启动三个容器 → 建表/角色/RLS/种子数据。预期三个服务均为 `healthy`：

| 服务 | 端口 | 用途 |
| --- | ---: | --- |
| `hardened` | `55432` | 正式 C 网关，RLS、列权限、只读 |
| `baseline` | `55433` | 宽权限对照 |
| `write_lab` | `55434` | 隔离的写操作实验 |

只需要正式主库时可 `--profile hardened`。若数据库已存在且只想重置合成数据：

```bash
./.venv/Scripts/python.exe scripts/reset_db.py --profile hardened
./.venv/Scripts/python.exe scripts/reset_db.py --profile baseline
./.venv/Scripts/python.exe scripts/reset_db.py --profile write_lab
```

## 5. 配置 .env

`init_db.py` 已写入 `SQ_*`（随机凭据）。再追加 `SECUREQUERY_*`（Ollama + 正式网关）：

```dotenv
SECUREQUERY_PROVIDER=ollama
SECUREQUERY_DEMO_MODE=true
SECUREQUERY_LAB_GATEWAY=false
SECUREQUERY_FORMAL_GATEWAY=true
SECUREQUERY_MODEL=qwen2.5-coder:7b
SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11435
```

校验配置：

```bash
./.venv/Scripts/python.exe -m app.cli_config
# 应输出 provider=ollama、model=qwen2.5-coder:7b、ollama_url=http://127.0.0.1:11435
```

Mock 模式不需要 Ollama：把 `SECUREQUERY_PROVIDER` 改为 `mock`，并保持 `SECUREQUERY_FORMAL_GATEWAY=true` 即可用 Mock 生成器验证网关。

## 6. 启动 Ollama（GPU）

项目约定 Ollama 独占 `11435`，与系统默认 `11434` 服务隔离。直接用系统默认模型目录（模型已拉取，无需设置 `OLLAMA_MODELS`）：

```bash
OLLAMA_HOST=127.0.0.1:11435 "$LOCALAPPDATA/Programs/Ollama/ollama.exe" serve
```

另开一个终端，用同一端口确认模型与 GPU：

```bash
export OLLAMA_HOST=127.0.0.1:11435
ollama list                                   # qwen2.5-coder:7b 已安装
curl -fsS http://127.0.0.1:11435/api/tags     # 模型可访问
```

推理期间确认实际 placement（**GPU 验收依据**）：

```bash
OLLAMA_HOST=127.0.0.1:11435 ollama ps
# PROCESSOR 应显示 100% GPU（或 GPU/CPU 混合），而不是 100% CPU
nvidia-smi --query-gpu=name,memory.used,utilization.gpu --format=csv,noheader
# 应看到显存占用约 5.5GB，且存在 Ollama compute 进程
```

只有 `ollama ps` 显示 GPU 且 `nvidia-smi` 观察到显存占用，才能标记 GPU-backed。本机 2026-11-02 实测为 `100% GPU`；若退化为 `100% CPU`，按 [`gpu-inference.md`](gpu-inference.md) 排查，不要仅因检测到 GPU 硬件就宣称 GPU 推理。

新机器缺模型时，先用同一端口拉取：

```bash
export OLLAMA_HOST=127.0.0.1:11435
ollama pull qwen2.5-coder:7b
```

## 7. 启动完整应用和前端

在 API 终端执行：

```bash
export SECUREQUERY_PROVIDER=ollama
export SECUREQUERY_MODEL=qwen2.5-coder:7b
export SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11435
export SECUREQUERY_DEMO_MODE=true
export SECUREQUERY_LAB_GATEWAY=false
export SECUREQUERY_FORMAL_GATEWAY=true
./.venv/Scripts/python.exe -m app
```

应用只绑定 `127.0.0.1:8000`，前端由同一个 FastAPI 服务提供，不需要单独启动 Node 或静态服务器。浏览器打开 <http://127.0.0.1:8000/>：

1. 选择 `normal_grade` 或其他场景；
2. 点击“运行攻防对照”；
3. 查看 baseline/hardened 候选；
4. 有 hardened 候选时，前端只提交自然语言、身份和上下文到 `/api/v1/queries`；
5. 查看 C 的 `ALLOW/MASK/BLOCK`、原因、结果、RLS 空结果、截断信息和审计 ID。

## 8. 启动后验收

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
# 预期 status=ready、gateway_connected=true、executor=gateway

curl -fsS http://127.0.0.1:8000/api/v1/demo/catalog

curl -fsS -X POST http://127.0.0.1:8000/api/v1/queries \
  -H 'Content-Type: application/json' \
  -d '{"question":"查询我的成绩","principal_id":"student_s01","context_profile":"clean"}'
# 预期 status=executed、gateway.decision=ALLOW、db_role=sq_student_s01、row_count=3
```

> 注意措辞：hardened 模型对含具体课程名的问法（“查询我在《数据库原理及安全》这门课的成绩”）可能过度拒答“课程不存在”，因为 `SCHEMA_SQL` 只给表结构、无种子数据。用“查询我的成绩”这类不指定课程名的措辞可稳定走通 `executed + ALLOW`。

正式网关的命令级回归：

```bash
./.venv/Scripts/python.exe -m pytest \
  tests/test_frontend_security.py tests/test_sql_policy.py \
  tests/test_real_gateway.py tests/test_audit_writer.py -q
./.venv/Scripts/python.exe -m pytest tests/db tests/attacks -q
./.venv/Scripts/python.exe -m compileall -q app db scripts tests
./.venv/Scripts/ruff check \
  app/sql_policy.py app/real_gateway.py app/audit_writer.py \
  app/query_service.py app/main.py app/config.py \
  scripts/verify_ollama_gpu.py \
  tests/test_sql_policy.py tests/test_real_gateway.py tests/test_audit_writer.py
git diff --check
```

预期：C 回归 `27 passed`；数据库/攻击回归退出码 0（评估契约无固定候选样例按规则跳过）；Ruff 只检查 C 和本阶段改动文件，全仓历史 A 文件仍有已知格式问题，不能把全仓 Ruff 结果写成通过。完整 C 结果见 [`c-gateway-verification.md`](c-gateway-verification.md)。

## 9. 停止

```bash
# 停止 API / Ollama：在各自终端按 Ctrl-C
docker compose --profile lab stop          # 停止数据库但保留数据卷
docker compose --profile lab down          # 删除容器但保留卷
docker compose --profile lab down -v       # 仅在明确重建实验数据时删卷，随后重新 init_db.py --all
```

## 10. 排障

| 现象 | 处理 |
| --- | --- |
| `password authentication failed for user "sq_admin"` | 本机遗留的 `securequery-ai-lab_*` 卷保留旧密码，而新 `.env` 生成新密码。`docker compose --profile lab down -v` 删卷后重新 `scripts/init_db.py --all`。 |
| `SQ_*` 占位符错误 | 删除本地 `.env` 后重新运行 `scripts/init_db.py --all`，再补 `SECUREQUERY_*` 配置。 |
| API 返回 `503 unavailable` | 检查 `SECUREQUERY_FORMAL_GATEWAY=true`、`requirements-database.lock` 已装、hardened 容器 healthy。 |
| Ollama 超时 / 页面 `Local model timed out.` | 先用 Mock 验证网关，再确认 `ollama ps` 为 GPU 而非 CPU；CPU fallback 下 7B 生成可能超过读取超时。 |
| `ollama ps` 为 `100% CPU` | 记录为 CPU fallback，按 [`gpu-inference.md`](gpu-inference.md) 排查驱动 / GPU 透传 / Ollama 安装。 |
| 找不到模型 | 确认连接的是 11435 服务且模型在系统默认目录，先用 `OLLAMA_HOST=127.0.0.1:11435 ollama list` 核实，不要重复下载。 |
