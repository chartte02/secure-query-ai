# 成员 B：Docker 环境完整复现记录

日期：2026-11-01（Asia/Shanghai）。执行人：成员 B。范围：补齐 [member-ab-verification.md](member-ab-verification.md) 第 4 节记录的验证缺口——成员 C 合并 A/B 分支时本机无 Docker，成员 B 的 71 项数据库回归当时只完成了静态验证（ruff、测试收集、静态审阅）。本记录在带 Docker 的 Windows 环境中完成真实复现，并记录过程中发现的一个合并集成问题。

## 1. 环境

- Windows（Git Bash / PowerShell），Python 3.12.4；Docker Engine 29.1.3（Docker Desktop Linux containers）。
- 基线：合并后的 `origin/main` @ `a0f6e24`（含成员 C 的两次 `--no-ff` 合并与验证提交），本地 fast-forward，无本地提交。
- 依赖：`pip install -r requirements-dev.lock` 后追加 `pip install -e ".[dev]"`（原因见第 4 节缺陷）。
- PostgreSQL 实测版本 17.11，镜像 digest `sha256:31ba9c94…35b08f`，与 `compose.yaml` 固定值一致。

## 2. 合并一致性核对

`git diff 6909dfd main -- db tests/db scripts compose.yaml requirements-dev.lock` 确认：

- B 侧核心代码（`db/`、`tests/db`、B 的攻击用例与管理脚本、`compose.yaml`、`requirements-dev.lock`）与被合并版本逐字节一致。
- 差异仅 3 处新增文件（A 的 `scripts/evaluate.py`、`tests/attacks/test_generation_attacks.py`、`scripts/__init__.py` 加一行）与 `tests/conftest.py` 的已知冲突处理（A 的 `app_settings`/`client` 新增，B 的 `settings` 原样保留）。

## 3. 复现步骤与结果

从空卷完整重建（最强复现证据）：

```powershell
docker compose --profile lab down -v      # 移除三个容器与全部数据卷
.\.venv\Scripts\python.exe scripts/init_db.py --all
```

三个实例（hardened 55432 / baseline 55433 / write_lab 55434）均报告 `status: created`、`seed_version: 20261028-v1`，**三库种子摘要一致且等于冻结值 `63ce8f08e7265feda1e36801dff013ee8d9e6dfcef65b84ce5599214aae6354e`**，与 [database-validation.md](database-validation.md) 及 `db/seed/manifest.json` 记录完全一致。

| 验证项 | 命令 | 结果 | 与既有记录对照 |
| --- | --- | --- | --- |
| B 侧数据库/攻击回归 | `pytest tests/db tests/attacks/test_database_controls.py tests/attacks/test_development_contract.py tests/test_contract.py` | **71 passed**（2.19s） | 补齐 C 无法执行的核心缺口；与 database-validation.md 的 71 passed 一致 |
| ruff lint | `ruff check db scripts/init_db.py scripts/reset_db.py scripts/verify_db_permissions.py scripts/collect_experiment_evidence.py` | All checks passed | 与 C 的静态结果一致 |
| ruff format | `ruff format --check`（同上范围） | 9 files already formatted | 与 C 的静态结果一致 |
| A 侧 Mock 测试 | `pytest tests/test_api.py tests/test_config.py tests/test_diagnostics.py tests/test_evaluation.py tests/test_frontend_security.py tests/test_prompts.py tests/test_providers.py tests/attacks/test_generation_attacks.py` | **64 passed** | 与 C 记录的 64 passed 一致（C 的 WSL 环境另见 2 skipped，本机 0 skipped，pass 数相同） |
| 固定 SQL 证据重建 | `python scripts/collect_experiment_evidence.py` | 生成 `artifacts/database-evidence.json` | 与 database-validation.md 实测对照逐项一致：hardened 本人成绩 3 行、他人成绩 0 行（RLS）、敏感列 `42501`；baseline 下他人成绩 3 行与合成证件标记泄露 |

附带观察：修复前 `pytest tests/db tests/attacks -q`（README 中成员 B 的命令）收集 **76** 项——B 的 71 项之外，A 的 `tests/attacks/test_generation_attacks.py`（5 项）位于同一目录被一并收集（5 项在本机全部通过）。第 4 节修复将该文件移回 A 的测试位置后，该命令恢复为恰好收集 B 的 69 项（`tests/db` 60 + `tests/attacks` 9），连同 `tests/test_contract.py` 共 71 项。

## 4. 发现的合并集成问题（已在本分支修复，待 A/C 复核）

**共享 `tests/conftest.py` 顶层导入 A 的应用依赖，破坏了 B 的文档化最小环境。**

合并后的 `tests/conftest.py` 在模块顶层执行 `from fastapi.testclient import TestClient`、`from app.config import AppSettings`、`from app.main import create_app`、`from app.providers import MockSqlGenerator`。而成员 B 的快速开始（根 README 与 [database-contract.md](database-contract.md)）只安装 `requirements-dev.lock`（psycopg/pytest/ruff/python-dotenv，无 fastapi 等）。后果：

- 纯 B 环境执行 `pytest tests/db` 直接失败：`ModuleNotFoundError: No module named 'fastapi'`（本机实测复现）。
- README 的成员 B 快速开始在任何新机器上按文档执行都会中断；"任何成员都能从空数据库重复建立实验环境"的验收标准受影响。
- 成员 C 当时以 `pip install -e ".[dev]"` 验证，故未暴露。

`tests/attacks/test_generation_attacks.py` 放入 B 的用例目录加剧了同一问题：它 import `app.catalog` 并依赖 `client` fixture，即使 conftest 改为惰性导入，B 的目录命令仍会因其收集而需要 A 的依赖。

修复方案（已由成员 B 在分支 `fix/conftest-lazy-imports` 实施，待 A/C 复核后合入）：

1. **conftest 惰性导入**：A 的 `app_settings`/`client` fixture 将 `fastapi`/`app.*` 导入移入 fixture 函数体内（保留 `TYPE_CHECKING` 类型标注）。B 环境恢复零 A 依赖；A 环境行为不变。
2. **测试归位**：`tests/attacks/test_generation_attacks.py` 移至 `tests/test_generation_attacks.py`（A 其余测试所在位置），`tests/attacks/` 恢复为仅含 B 的用例。README 成员 A 测试命令路径同步更新；C 的 [member-ab-verification.md](member-ab-verification.md) 为带日期的历史记录，保持原样，路径以本节为准。

未采用"requirements-dev.lock 补装 A 依赖"的方案：与 C 在 member-ab-verification.md 第 5.1 节确立的"AI 服务不携带数据库驱动、两侧依赖分离"方向相悖。

修复验证（两种环境实测）：

| 环境 | 命令 | 结果 |
| --- | --- | --- |
| 纯 B 依赖（卸载 fastapi/httpx/pydantic/pydantic-settings/sqlglot/uvicorn 及 editable 安装，仅剩 `requirements-dev.lock`） | `pytest tests/db tests/attacks tests/test_contract.py` | **71 passed**，收集阶段不再触碰 A 依赖 |
| 完整环境（`pip install -e ".[dev]"`） | A 全套（含移动后的 `tests/test_generation_attacks.py`）+ B 全套 | **64 + 71 = 135 passed**，`pytest tests/db tests/attacks -q` 恰为 B 的用例 |

## 5. 结论

- C 留下的验证缺口已关闭：合并后的 main 在带 Docker 的环境中，B 的 71 项回归、种子可复现性（空卷重建摘要一致）、固定 SQL 证据全部复现通过；A 侧 64 项 Mock 测试亦通过，证明合并后的 conftest 对两侧同时成立（在安装 A 依赖的前提下）。
- member-ab-verification.md 第 4 节"B 的 71 项回归需在带 Docker 的环境中初始化后运行"的待办已由本记录完成，可勾销。
- 第 4 节发现的 conftest 集成缺陷已在本分支修复并经两种环境实测（见第 4 节修复验证表），因涉及 A 的 fixture 与测试文件位置，待 A/C 复核后合入。
