# 功能、文件、测试与产物映射

更新日期：2026-11-02。本文回答“某个功能在哪里实现、如何验证、会产生什么证据”。状态分为：`已实现`、`实验室演示`、`待 C 实现`、`文档/计划`。

## 1. 总体功能地图

| 功能 | 负责人 | 状态 | 主要代码文件 | 主要测试/命令 | 主要产物 |
| --- | --- | --- | --- | --- | --- |
| Web API 与前端静态服务 | A | 已实现 | `app/main.py`、`frontend/index.html`、`frontend/app.js`、`frontend/styles.css` | `tests/test_api.py`、`tests/test_frontend_security.py` | 页面、健康检查和 API 响应 |
| 自然语言生成候选 SQL | A | 已实现 | `app/service.py`、`app/providers.py`、`app/prompts.py`、`app/prompt_templates/` | `tests/test_providers.py`、`tests/test_prompts.py`、`tests/test_generation_attacks.py` | `GenerationResponse`、模型评估 JSON |
| SQL 诊断与危险提示 | A | 已实现 | `app/diagnostics.py`、`app/models.py` | `tests/test_diagnostics.py`、`tests/test_api.py` | `parseable`、语句数、警告和 provenance |
| Ollama 本地推理 | A | 已实现/环境依赖 | `app/providers.py`、`app/config.py` | `tests/test_ollama_integration.py`、`scripts/evaluate.py` | `artifacts/experiments/*.json` |
| 查询编排协议 | A/C 接口 | 已实现协议 | `app/query_service.py`、`app/gateway.py`、`app/models.py` | `tests/test_query_route.py` | `POST /api/v1/queries` 响应 |
| 安全默认拒绝 | A | 已实现 | `app/gateway.py` 的 `NotConnectedGateway`、`app/query_service.py` | `tests/test_query_route.py` | 网关未接入时 HTTP 503 |
| PostgreSQL 表结构 | B | 已实现 | `db/migrations/001_schema.sql`、`db/migrations/002_identity_helpers.sql` | `tests/db/test_permissions.py` | PostgreSQL schema |
| 数据库角色与最小权限 | B | 已实现 | `db/manage.py`、`db/profiles/*.sql`、`db/settings.py` | `tests/db/test_permissions.py`、`scripts/verify_db_permissions.py` | RLS、列权限、只读角色结果 |
| 合成种子和固定摘要 | B | 已实现 | `db/seed/__init__.py`、`db/seed/manifest.json` | `tests/db/test_reset.py` | 种子版本和 SHA-256 摘要 |
| 数据库初始化与重置 | B | 已实现 | `scripts/init_db.py`、`scripts/reset_db.py`、`db/manage.py` | `tests/db/test_reset.py` | 三实例、重置报告 |
| 三类攻击案例 | B | 已实现为固定候选 | `tests/attacks/cases/*.json`、`docs/attack-cases.md` | `tests/attacks/` | 攻击样例、预期决策和证据 |
| 固定 SQL 权限回放 | B | 实验室演示 | `app/lab_gateway.py`、`app/main.py` | `tests/test_query_lab.py` | `artifacts/database-evidence.json` |
| 一次性危险写实验 | B | 实验室演示 | `db/profiles/write_lab.sql`、`docs/write-lab-experiment.md` | `tests/attacks/test_database_controls.py` | write_lab 状态变更和重置证据 |
| 独立 SQL 解析 | C | 待实现 | `app/gateway.py` 目前只有协议和安全默认实现 | 待新增网关回归测试 | `ALLOW/BLOCK` 决策 |
| 表/列/身份授权策略 | C | 待实现 | 计划放入 `app/gateway.py` 或独立策略模块 | 待新增越权测试 | policy version、reason code |
| 结果限行与敏感字段脱敏 | C | 待实现 | 计划放入正式网关执行器 | 待新增 `MASK` 测试 | `masked_columns`、`truncated` |
| 业务审计写入 | C | 待实现 | B 已提供 `audit` 数据库边界，C 尚未接入 | 待新增审计测试 | `audit_id`、SQL digest、决策 |
| 正式查询结果前端 | C/A | 待实现 | 当前前端只显示生成对照 | 待新增前端结果测试 | 决策、结果表、审计 ID |
| Pre 汇报材料 | C 主责 | 计划/整理中 | `docs/team-division.md`、`docs/acceptance-report.md` | 现场演练 | PPT、录屏、演示脚本 |

## 2. 成员 A 文件与产物

### 代码

- `app/main.py`：FastAPI 应用、健康检查、生成接口、查询编排接口和实验室路由；
- `app/service.py`：生成请求编排、Prompt 构造、模型响应标准化；
- `app/providers.py`：Mock Provider、Ollama Provider、超时和响应大小限制；
- `app/prompts.py`、`app/prompt_templates/`：baseline/hardened Prompt 版本；
- `app/catalog.py`：`campus_lab_v1` Schema、身份和演示场景；
- `app/diagnostics.py`：SQL 语法、语句类型和危险性诊断；
- `frontend/`：候选 SQL 生成对照页。

### 验证与产物

- `tests/test_api.py`：请求校验、状态码和安全响应；
- `tests/test_providers.py`：Ollama HTTP、超时、大小限制和结构化输出；
- `tests/test_prompts.py`：Prompt 和 Schema 上下文；
- `tests/test_generation_attacks.py`：攻击输入只生成候选，不执行；
- `scripts/evaluate.py`：固定合成生成评估；
- `artifacts/experiments/`：模型、Prompt、Schema、延迟和状态记录。

## 3. 成员 B 文件与产物

### 代码

- `db/migrations/`：业务表、辅助函数、RLS 和审计相关结构；
- `db/profiles/baseline.sql`：宽读取基线；
- `db/profiles/hardened.sql`：RLS、列权限、只读和最小权限；
- `db/profiles/write_lab.sql`：隔离的成绩写实验；
- `db/seed/`：clean/poisoned fixture、固定行数和摘要；
- `db/client.py`：可信 actor 映射、受限数据库连接、反馈和上下文接口；
- `db/manage.py`、`db/settings.py`：初始化、角色、安装标记和安全连接；
- `compose.yaml`：三个独立 PostgreSQL 实例。

### 验证与产物

- `tests/db/`：身份、RLS、列权限、只读、反馈和重置；
- `tests/attacks/`：跨用户、敏感字段、间接注入和危险写操作；
- `scripts/verify_db_permissions.py`：权限检查；
- `scripts/collect_experiment_evidence.py`：固定 SQL 证据采集；
- `scripts/init_db.py`、`scripts/reset_db.py`：初始化和安全重置；
- `artifacts/database-evidence.json`：baseline/hardened 固定 SQL 对照；
- `docs/data-dictionary.md`、`docs/database-validation.md`、`docs/attack-cases.md`、`docs/write-lab-experiment.md`：数据库和攻击证据说明。

## 4. 成员 C 文件与待交付产物

### 当前已有接口边界

- `app/gateway.py`：`SqlGateway`、`GatewayOutcome`、`GatewayHandoff` 和 `NotConnectedGateway`；
- `app/query_service.py`：生成结果交给网关、状态映射和审计摘要；
- `app/models.py`：`ALLOW/MASK/BLOCK`、结果、错误和审计字段契约；
- `db/client.py`：C 允许使用的可信身份和受限连接；
- `docs/integration.md`、`docs/status.md`：C 的接口和验收要求。

### C 尚未完成的实现产物

1. 独立 SQL 解析器：只允许单条只读查询，阻断多语句、注释绕过和 DML/DDL；
2. 授权策略：按 `principal_id` 检查表、列和行范围；
3. 执行器：通过 `query_connection()` 使用 hardened 角色和只读事务；
4. 结果处理：限制行数、敏感字段脱敏、记录执行耗时；
5. 审计：写入 `audit.events`，返回 `audit_id` 和 `sql_digest`；
6. 测试：允许、脱敏、阻断、数据库错误、RLS 空结果各一组回归；
7. 前端：显示安全决策、阻断原因、结果、脱敏列、截断状态和审计 ID；
8. Pre 产物：PPT、10 分钟演示脚本、固定样例、录屏和答辩问题清单。

这些是待交付项，不能把 `app/lab_gateway.py` 直接标记为 C 网关。`LocalLabGateway` 只用于观察 B 的数据库控制，代码明确设置 `executor=lab_direct`。

## 5. 运行产物和证据边界

| 产物 | 生成方式 | 是否可作为最终安全结论 |
| --- | --- | --- |
| `artifacts/database-evidence.json` | `scripts/collect_experiment_evidence.py` | 可证明固定 SQL 的数据库行为；不能证明模型攻击 |
| `artifacts/experiments/*.json` | `scripts/evaluate.py` | 可证明模型生成记录；不能替代网关拦截和实际执行 |
| `artifacts/screenshots/*` | 人工运行 Demo 截图 | 可作为汇报展示证据，需标注运行模式 |
| `docs/*-verification.md` | 测试命令和人工记录 | 取决于是否包含命令、时间、环境和原始结果 |
| `.env`、`.venv/`、Docker 卷 | 本地运行状态 | 不提交、不作为共享证据 |

## 6. 推荐查找顺序

1. 先看 [status.md](status.md) 判断功能是否真的完成；
2. 再看本文定位代码、测试和产物；
3. 按 A、B 或 C 阅读对应文档；
4. 最后查看 `artifacts/` 中的 JSON、截图和日志；
5. 若文档结论与代码/测试冲突，以可复现的代码和本次实测结果为准。
