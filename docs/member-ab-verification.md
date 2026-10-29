# 成员 A / B 分支合并与验证记录

日期：2026-10-29。执行人：成员 C。范围：把成员 A、B 的远端分支合入 `main`，分别验证两人交付的工作，并记录验证结果与遗留问题。

## 1. 分支与合并结果

| 成员 | 分支 | 提交 | 作者 | 负责内容 |
| --- | --- | --- | --- | --- |
| A | `origin/hongcl` | `4f6c713 feat(member-A): 建立安全 AI SQL 生成与攻防演示基线` | loong6025-ui | AI SQL 服务（`app/`、`frontend/`、Ollama/Mock、提示词、模型评估） |
| B | `origin/feat/database-security-lab` | `6909dfd Add PostgreSQL security lab and Text-to-SQL research` | zaca77 | 数据库与攻击研究（`db/`、角色/权限/种子数据、攻击用例、调研） |

合并方式为两次 `--no-ff` 合并，保留各自提交历史：

```text
00b4b86 Merge branch 'hongcl' (成员 A：AI SQL 服务)
d9b63f1 Merge branch 'feat/database-security-lab' (成员 B：数据库与攻击研究)
c6ca429 分工文档
```

两个分支都改动过根目录的 `README.md`、`pyproject.toml`、`.env.example`、`.gitignore`、`.gitattributes`、`tests/conftest.py`，共 6 处 add/add 冲突，已手工合并。

### 冲突处理要点

- `tests/conftest.py`：A 的 `settings`（AppSettings）与 B 的 `settings`（db Settings，session 级）同名冲突。将 A 的改为 `app_settings`（仅 `client` 依赖它），B 的 `settings` 保持不变，因此 B 的测试无需改动。
- `pyproject.toml`：见第 4 节——A 的“运行时不含数据库驱动”安全不变量，决定了 `psycopg` 不能进入共享 `dependencies`。
- `.gitattributes`：保留 A 记录的团队约定（Windows 工作区 CRLF），补充 B 的 `*.yaml`/`*.yml` 规则。
- `.gitignore`：忽略可再生的 `artifacts/database-evidence.json` 与运行时目录；A 已提交的 `artifacts/experiments/`、`artifacts/screenshots/` 保持跟踪。
- `README.md`：改写为统一快速开始 + A/B 双入口 + 目标链路。

## 2. 验证环境与限制

- Linux（WSL2），Python 3.13.9；依赖安装到 `.venv`，`pip install -e ".[dev]"` 成功。
- **无 Docker、无 PostgreSQL 客户端/服务端、无 sudo**；Ollama 客户端 0.24.0 存在但无运行中的模型服务。
- 因此：成员 A 的 Mock 测试可完整执行；成员 B 需要 Docker PostgreSQL 的 71 项回归**无法在本机执行**，改为静态校验 + 结构收集 + 独立审阅。真实 Ollama 集成测试默认跳过（需显式 `SECUREQUERY_RUN_OLLAMA_TESTS=1`）。

## 3. 成员 A 验证（AI SQL 服务）

命令：

```bash
python -m pytest tests/test_api.py tests/test_config.py tests/test_diagnostics.py \
  tests/test_evaluation.py tests/test_frontend_security.py tests/test_prompts.py \
  tests/test_providers.py tests/attacks/test_generation_attacks.py
python -m pytest tests/test_ollama_integration.py
```

结果：**64 passed，2 skipped**，与 A 文档 [`docs/local-model-evaluation.md`](local-model-evaluation.md) 声明的“64 passed、2 skipped”一致。2 项跳过为真实 Ollama 集成测试（本机无模型服务，且默认显式关闭）。覆盖范围包括：API 契约与安全响应头、输入长度/身份/额外字段校验、危险 SQL 只返回不执行、`baseline`/`hardened` 对照、生产模式禁用 Demo、Provider 超时/重定向/超大响应/连接失败、提示词版本与哈希、Mock 攻防复现、前端 DOM 注入与远程资源检查。

结论：A 的服务在 Mock 路径下行为符合其文档，**生成结果不连接数据库**，且 `pyproject.toml` 运行时依赖不含数据库驱动（见第 4 节）。

## 4. 成员 B 验证（数据库与攻击研究）

本机无 Docker，无法复现 B 记录的“71 passed”。执行了以下替代验证：

| 项目 | 结果 |
| --- | --- |
| `ruff check db scripts/init_db.py scripts/reset_db.py scripts/verify_db_permissions.py scripts/collect_experiment_evidence.py` | **All checks passed**（0 问题） |
| `ruff format --check`（同上范围） | 10 个文件已格式化，无改动 |
| `python -m pytest tests/test_contract.py` | **2 passed**（拒绝任意身份/不安全 profile；公开身份对象不含连接秘密） |
| `python -m pytest tests/db tests/attacks tests/test_contract.py --collect-only` | B 的 71 项测试全部可收集（导入无错误） |

静态审阅确认与 [`docs/database-contract.md`](database-contract.md) 一致：

- `db/migrations/001_schema.sql`：`academic`/`private_auth`/`api`/`audit` 四 schema；敏感列 `students.phone`、`students.national_id`、`grades.grader_note` 不授权。
- `db/migrations/002_identity_helpers.sql`：RLS 用 `SECURITY DEFINER` 函数且 `SET search_path = pg_catalog`，以 `session_user`（非 `current_user`）判定，避免 search_path 劫持与 RLS 递归。
- `db/profiles/hardened.sql`：列级 `GRANT SELECT (…)`、四表 RLS 策略、`security_barrier` 脱敏视图 `api.my_contact`、反馈 `WITH CHECK` 约束。
- `db/manage.py`：`ALTER ROLE … SET default_transaction_read_only`（只读在角色层强制，关闭客户端只读仍无写权）、`statement_timeout=5000`、`lock_timeout=1000`、`search_path=pg_catalog, academic, api`。
- `db/client.py`：`query_connection` 仅接受预设身份、非 hardened 需显式 `unsafe_lab=True`、绑定 `session_user`；`ContextProvider` 仅公开目录/反馈并标注 `trust=untrusted_data`；`submit_feedback` 参数化且受 RLS 约束；`public_actor_contract` 剥离 `db_role`。

结论：B 的数据库控制实现与契约一致，权限、RLS、脱敏、只读与审计边界在静态层面成立。**完整 71 项回归需在带 Docker 的环境中由 `scripts/init_db.py --all` 初始化后运行**（B 的验证记录见 [`docs/database-validation.md`](database-validation.md)）。

## 5. 集成发现与处理

1. **（已修复）A 的运行时安全不变量被合并破坏。** 初版合并把 `psycopg[binary]` 写入共享 `pyproject.toml` 的 `dependencies`，触发 A 的测试 `test_runtime_dependencies_do_not_include_database_driver` 失败。该测试体现“AI SQL 生成服务不携带数据库驱动、绝不连库”的边界。修复：`pyproject.toml` 仅保留 A 的运行时依赖与 `app*` 打包；B 的 `psycopg`/`python-dotenv` 由 `requirements-dev.lock` 提供，`db/` 作为仓库内本地包（B 的脚本均自行 `sys.path.insert(0, 仓库根)`，不依赖打包）。修复后 A 全套测试恢复通过。
2. **（待处理）A 的代码不满足 B 的 ruff 配置。** 合并后的 `[tool.ruff]`（line-length 100，E/F/I/UP/B）下，A 的代码有 30 个问题（15×E501、8×I001、4×UP017、1×UP037、1×UP035、1×F401，均位于 `app/`、`scripts/evaluate.py`、A 的 `tests/`），B 的代码 0 个。均为风格/重构类，无 B（bugbear）正确性问题。是否统一格式化由团队决定，本记录不擅自改写 A 的代码。
3. **剩余工作（成员 C）**：SQL 网关、统一执行入口 `POST /api/v1/queries`、审计业务逻辑、实验评估与 Pre 汇报，尚未实现。

## 6. 复现命令

```bash
# 成员 A（Mock，不依赖 Ollama/数据库）
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/test_api.py tests/test_config.py tests/test_diagnostics.py \
  tests/test_evaluation.py tests/test_frontend_security.py tests/test_prompts.py \
  tests/test_providers.py tests/attacks/test_generation_attacks.py

# 成员 B（需 Docker Desktop + 初始化三个实例）
.venv/bin/pip install -r requirements-dev.lock
.venv/bin/python scripts/init_db.py --all
.venv/bin/python -m pytest tests/db tests/attacks -q
```
