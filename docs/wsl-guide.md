# SecureQuery AI：项目概览与 WSL 启动指南

日期：2026-10-31。面向在 **WSL（Linux）环境** 下克隆并运行本仓库的成员。内容基于 2026-10-31 的实测验证，Windows PowerShell 的 `run.ps1` 在 WSL bash 下不可用，本指南给出等价命令。

## 1. 项目概览

SecureQuery AI 研究“通过自然语言让大模型查询数据库”引入的安全风险，用合成校园教务数据做攻防演示，比较无防御、仅提示词防御、提示词加 SQL 安全网关三种方案。核心链路：

```text
用户身份 + 自然语言
      ↓
轻量 Web 前端 (frontend/)
      ↓
AI SQL 服务 (app/)  —— Ollama / Mock 生成候选 SQL
      ↓
SQL 安全网关 (成员 C，待实现) —— 解析、授权、脱敏、审计
      ↓
PostgreSQL (db/)  —— 角色、RLS、只读事务、合成数据
```

三人分工与交付现状：

| 成员 | 负责 | 状态（2026-10-31） |
| --- | --- | --- |
| A（`hongcl`） | AI SQL 服务、提示词、前端、模型评估 | ✅ 已合入，服务可跑，64 passed + 2 skipped |
| B（`feat/database-security-lab`） | 数据库、角色/权限、合成数据、攻击用例 | ✅ 已合入，静态校验通过，完整回归需 Docker |
| C（`main`，本指南作者） | SQL 网关、执行编排、评估、Pre 汇报 | ⏳ 待实现 |

## 2. 目录结构

```text
app/        A：FastAPI、提示词、Ollama/Mock Provider、诊断
frontend/   A：攻防对照页（index.html / app.js / styles.css）
db/         B：表结构、角色、RLS、种子数据、可信接口
scripts/    A：evaluate.py；B：init_db.py / reset_db.py / verify_db_permissions.py / collect_experiment_evidence.py
tests/      A：API/Provider/提示词/前端安全；B：db/ 与 attacks/ 回归
docs/       设计、分工、接入契约、验证记录、调研
compose.yaml  B：三个独立 PostgreSQL 实例
```

## 3. WSL 环境准备

前置：Python 3.11+（本机为 miniconda 的 Python 3.13.9）。数据库部分需要 Docker（见第 6 节）。

```bash
cd /home/chartte/school/SecureQuery_AI
python3 -m venv .venv
.venv/bin/python -m pip install -U pip

# 成员 A：运行时依赖 + pytest/ruff（不装数据库驱动，符合 A 的安全边界）
.venv/bin/python -m pip install -e ".[dev]"

# 成员 B：数据库驱动 psycopg / python-dotenv 等（跑 db/ 相关测试才需要）
.venv/bin/python -m pip install -r requirements-dev.lock
```

两条安装命令分别对应 A、B 两套依赖，二者可并存（这是有意设计：A 的运行时不得携带数据库驱动，见 `tests/test_frontend_security.py`）。

## 4. 成员 A：启动 AI SQL 服务

A 的服务默认用 Mock Provider，**不连数据库、不需要 Ollama**，只生成候选 SQL，绝不执行。演示模式需显式开启。

```bash
# 准备配置（.env 缺失时用 .env.example 的演示默认值；.env 已被 Git 忽略）
cp .env.example .env          # 或手动 export 下面两个变量

# 启动（只监听 127.0.0.1:8000）
SECUREQUERY_PROVIDER=mock SECUREQUERY_DEMO_MODE=true .venv/bin/python -m app
```

等价写法：`uvicorn app.main:app --host 127.0.0.1 --port 8000`（`app/__main__.py` 内部就是这么做的）。

验证（实测 2026-10-31 通过）：

```bash
curl http://127.0.0.1:8000/api/v1/health      # {"status":"ready","provider":{...mock...},...}
curl http://127.0.0.1:8000/                   # 200，前端页面
curl http://127.0.0.1:8000/api/v1/demo/catalog
curl -X POST http://127.0.0.1:8000/api/v1/generations \
  -H 'Content-Type: application/json' \
  -d '{"question":"查询我在《数据库》这门课的成绩","principal_id":"student_001","prompt_profile":"hardened","context_profile":"clean"}'
```

关键接口见 [usage-guide.md](usage-guide.md)。演示身份为 `student_001` / `teacher_001` / `admin_demo`。

### 使用真实 Ollama 模型（可选）

WSL 已装 Ollama 客户端（0.24.0），但无运行中的服务与模型。要启用真实模型：

```bash
ollama serve                              # 默认端口 11434
ollama pull qwen2.5-coder:7b              # 主模型（或 3b）
# 修改 .env：
#   SECUREQUERY_PROVIDER=ollama
#   SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11434   # 注意：run.ps1 用 11435，手动 serve 用 11434
#   SECUREQUERY_MODEL=qwen2.5-coder:7b
```

`run.ps1` 在 Windows 下会启动项目专用 Ollama（端口 11435）；在 WSL 手动 `ollama serve` 时用默认 11434，务必同步改 `SECUREQUERY_OLLAMA_BASE_URL`。

## 5. 成员 A：运行测试

```bash
# Mock 测试（不依赖 Ollama / 数据库）
.venv/bin/python -m pytest tests/test_api.py tests/test_config.py tests/test_diagnostics.py \
  tests/test_evaluation.py tests/test_frontend_security.py tests/test_prompts.py \
  tests/test_providers.py tests/attacks/test_generation_attacks.py

# 真实 Ollama 集成（需先启动模型并显式开启）
SECUREQUERY_RUN_OLLAMA_TESTS=1 .venv/bin/python -m pytest tests/test_ollama_integration.py
```

实测 2026-10-31：Mock 测试 **64 passed**；Ollama 集成 **2 skipped**（无模型服务，符合预期）。

## 6. 成员 B：数据库与攻击

B 的数据库需要 **Docker + PostgreSQL**。本机 WSL 未装 Docker（`docker` 命令不存在），因此完整回归需在带 Docker Desktop 的 Windows 侧（或 Linux Docker）执行。在具备 Docker 的环境：

```bash
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python scripts/init_db.py --all      # 生成 .env 真实随机密钥，初始化三个实例
.venv/bin/python -m pytest tests/db tests/attacks -q   # B 记录为 71 passed
```

三个实例固定绑定本机端口：

| 环境 | 端口 | 用途 |
| --- | --- | --- |
| hardened | 55432 | 默认；RLS 本人/教师所授班；禁止原始敏感列 |
| baseline | 55433 | 故意宽读取的对照 |
| write_lab | 55434 | 一次性成绩 DML 实验 |

常用命令：`scripts/reset_db.py`（重置）、`scripts/verify_db_permissions.py`（权限校验）、`scripts/collect_experiment_evidence.py`（采集固定 SQL 证据）。A/C 接入契约见 [database-contract.md](database-contract.md)。

### 本机（无 Docker）如何校验 B

本机验证过以下等价项（见 [member-ab-verification.md](member-ab-verification.md)）：

```bash
.venv/bin/ruff check db scripts/init_db.py scripts/reset_db.py scripts/verify_db_permissions.py scripts/collect_experiment_evidence.py   # 0 问题
.venv/bin/python -m pytest tests/test_contract.py            # 2 passed（无需数据库）
.venv/bin/python -m pytest tests/db tests/attacks tests/test_contract.py --collect-only   # 71 项可收集
```

## 7. 成员 C：待实现

SQL 网关（语句类型/表/字段/用户策略检查、危险操作拦截、脱敏、审计日志）、统一执行入口 `POST /api/v1/queries`、实验评估与 Pre 汇报。前端目前 `deployment` 里 `gateway_connected` 与 `database_connected` 均为 `false`。

## 8. WSL 注意事项（实测踩坑）

1. **venv 损坏**：本机曾出现 `.venv/bin/python` 变成 0 字节普通文件（原本是符号链接），报 `Permission denied`。解决：删除重建 `rm -rf .venv && python3 -m venv .venv` 后重装依赖。若遇到 `.venv/bin/python` 无法执行，先重建。

2. **`:Zone.Identifier` 文件**：Windows 从网上下载/复制文件后，会在 WSL 里物化出大量 `文件名:Zone.Identifier` 的 ADS 垃圾文件（本机观察到 91 个，全被 `git status` 显示为未跟踪）。清理并防止提交：

   ```bash
   find . -name '*:Zone.Identifier' -delete          # 清理
   # 建议在 .gitignore 中追加一行：
   # *:Zone.Identifier
   ```

3. **无 Docker / psql / Ollama 服务**：B 的数据库回归、真实模型集成在本机都跑不了；请回到 Windows 侧或另备环境执行（见第 5、6 节）。

4. **A、B 共用同一个 `.env`**：A 读 `SECUREQUERY_*`，B 读 `SQ_*`。B 的 `scripts/init_db.py` 只在 `.env` 缺失时生成真实随机 `SQ_*` 密钥；若已 `cp .env.example .env`（含 `SQ_*` 占位符），B 的 `Settings.load()` 会拒绝运行（`Replace .env.example placeholders ...`）。**先跑 B 的 init_db.py 生成真实密钥，再补 A 的 `SECUREQUERY_DEMO_MODE=true` 等项**，二者可并存。

5. **A 与 B 的 Schema/身份命名不一致**（C 对接时要统一）：A 的演示用 `campus_v1`，表名 `grades`/`courses`，身份 `student_001`/`teacher_001`；B 的真实库用 `academic.grades`/`academic.courses`，身份 `student_s01`/`teacher_t01`。生成 SQL 必须由 C 的网关按 B 的真实 Schema 授权后执行，不能直接拿 A 的示例 SQL 查库。

6. **`run.ps1` 是 Windows PowerShell 脚本**，在 WSL bash 下不可直接用；等价入口是 `python -m app` 与上面的 pytest 命令。

## 9. 相关文档

- 总体设计与分工：[project-design.md](project-design.md)、[team-division.md](team-division.md)
- A 的使用教程与模型评估：[usage-guide.md](usage-guide.md)、[local-model-evaluation.md](local-model-evaluation.md)
- B 的接入契约与验证：[database-contract.md](database-contract.md)、[database-validation.md](database-validation.md)
- A/B 合并验证记录：[member-ab-verification.md](member-ab-verification.md)
