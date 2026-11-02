# A / B / C 联调交接记录

> **2026-11-02 状态更新**：A/B 已完成 Schema/身份对齐，C 已接入正式 `RealGateway`、审计和前端安全查询。当前实测以 [状态与交接](status.md) 和 [C 验证记录](c-gateway-verification.md) 为准；本文保留为身份、权限和接口交接清单。

本文记录当前三人联调的边界、入口和验收责任。A/B/C 的主要代码已经合入 `main`；历史规划中的“建议新增”文件不再作为当前任务清单。完整启动命令见 [WSL 指南](wsl-guide.md)，完整结果见 [验收报告](acceptance-report.md)。

## 先确认现有接口与占位

| 现有位置 | 已实现 | 对接时的含义 |
|---|---|---|
| [`app/catalog.py`](../app/catalog.py) 的 `SCHEMA_VERSION`、`SCHEMA_SQL`、`PRINCIPALS`、`CONTEXTS` | 模型看到的 `campus_lab_v1` Schema、演示身份和固定上下文 | `SCHEMA_SQL` **不会建表**；演示身份不是真实认证；恶意备注不能自动证明来自数据库 |
| [`app/prompts.py`](../app/prompts.py) 的 `build_prompt()` | 把服务端 Schema、身份、上下文和问题放进结构化消息 | B 的实际表结构或身份范围变化时，由 A 同步版本和提示词上下文 |
| [`app/main.py`](../app/main.py) 的 `POST /api/v1/generations` | 只返回候选 SQL、拒答、诊断和模型来源 | 不连接 B 的库、不执行 SQL、不作最终授权 |
| [`app/models.py`](../app/models.py) 的 `GatewayHandoff` | 定义 `request_id`、可信 `principal_id`、`candidate_sql`、`schema_version` 等字段 | 由查询编排传给 C；浏览器不能提交待执行 SQL 或数据库连接信息 |
| [`app/diagnostics.py`](../app/diagnostics.py) 的 `diagnose_sql()` | 给出解析、语句数、表/列和危险候选警告 | C 必须独立重新解析并授权；A 的诊断不是 `ALLOW` |
| [`frontend/index.html`](../frontend/index.html)、[`frontend/app.js`](../frontend/app.js) | 显示候选 SQL 对照和正式安全查询结果 | 只提交自然语言、演示身份和上下文；只渲染 C 处理后的结果 |
| [`docs/integration.md`](integration.md) 的 `POST /api/v1/queries` | 请求、状态和结果 JSON 契约 | 正式网关已接入；未显式开启时仍返回 503 `unavailable`。文档中的分数仅为接口示例 |

## 成员 B：数据库与攻击样例

数据库材料已经位于 `db/`，以下是当前交接入口：

| 当前文件 | 内容 | A/C 已核实项 |
|---|---|---|
| `db/migrations/`、`db/profiles/` | PostgreSQL 表、角色、RLS、列权限、只读和脱敏视图 | 已与 `campus_lab_v1` 和 C 的 hardened 连接对齐 |
| `db/seed/`、`db/fixtures/` | 可重复的合成数据、干净/污染反馈和固定摘要 | 已由 `scripts/init_db.py --all` 与数据库回归验证 |
| `db/client.py`、`db/manage.py`、`scripts/reset_db.py` | 可信 actor 映射、初始化、重置和受限连接 | C 只使用预设身份和 hardened 角色 |
| `docs/attack-cases.md`、`tests/attacks/` | 三类攻击的前提、固定候选和数据库控制证据 | 固定 SQL 回放与模型生成结果分开记录 |

B 还需专门核实**间接 Prompt Injection**：当前 [`CONTEXTS`](../app/catalog.py) 只是服务端固定的“恶意课程备注”字符串。若演示要声称攻击来自真实数据库内容，B 应在 `db/seed.sql` 放入可定位的恶意课程描述；C/查询编排组件负责受限读取，A 在 [`app/prompts.py`](../app/prompts.py) 的 `build_prompt()` 中把该字段标成**不可信上下文**，同时调整当前固定夹具的使用方式。完成这条链路前，演示和报告只能称它为“恶意上下文夹具”。

建议 B 给三人一张最终数据字典：Schema 版本、每张表的字段/类型、S001/T001 对应记录、课程名、敏感字段、各正常问题的预期行，以及三类攻击的预期结果。尤其要确认“学生只能看本人”“教师只能看所授课”“管理员也不能通过查询服务写库”的范围。

## 成员 C：网关、执行与审计

C 的正式实现放在 FastAPI 进程内的独立模块，数据库凭据只由执行组件读取：

| 当前文件 | 已实现内容 | 验收证据 |
|---|---|---|
| `app/sql_policy.py` | SQLGlot 独立解析、单条只读检查、表/列/身份策略 | `tests/test_sql_policy.py` 覆盖允许、危险操作、多语句和越权 |
| `app/real_gateway.py` | hardened 只读执行、限行、脱敏、SQLSTATE 映射 | `tests/test_real_gateway.py` 与 Docker live 验收 |
| `app/audit_writer.py` | 写入 `audit.events`，保存决策、原因和摘要 | `tests/test_audit_writer.py` 与审计表查询 |
| `app/query_service.py`、`app/main.py` | 生成 → C 网关 → 统一响应和状态映射 | `/api/v1/queries` 和前端安全查询面板 |
| `tests/test_frontend_security.py`、`docs/c-gateway-verification.md` | 前端回归和命令级实测记录 | C/前端回归 `26 passed`，Docker live 覆盖 ALLOW/MASK/BLOCK/RLS |

B/C 需要先共同确定政策矩阵：哪些身份可见哪些表和列；`phone`、`national_id` 等字段是 `MASK` 还是 `BLOCK`；学生跨人查询、教师跨课查询如何判定；最大返回行数与超时；审计字段和保留方式。数据库原生权限和 C 的策略应各自能说明作用，不能把模型拒答算作网关拦截。

## 三人共同接入现有页面

1. **先锁定契约。** B 提交数据库版本与合成数据，A 更新 [`app/catalog.py`](../app/catalog.py) 和 [`tests/fixtures/generation_benchmark.json`](../tests/fixtures/generation_benchmark.json) 中不再匹配的 Schema/样例；若演示身份或 ID 改变，也要同步 [`app/models.py`](../app/models.py) 的请求白名单和 [`app/providers.py`](../app/providers.py) 的 Mock 夹具。C 记录策略版本。原始历史实验 JSON 保持不变。
2. **再做安全执行。** C 在合成库上通过 `ALLOW`、`MASK`、`BLOCK` 测试后，约定固定的网关调用方式。交给 C 的四字段结构见 [`GatewayHandoff`](../app/models.py)，但可信身份必须由服务端取得；浏览器当前的 `principal_id` 只是演示夹具，C 不能直接相信它。
3. **新增查询编排。** A/C 建议新建 `app/query_service.py`，并在 [`app/main.py`](../app/main.py) 增加 `POST /api/v1/queries`，在 [`app/models.py`](../app/models.py) 增加请求和统一响应模型。编排端点先取得可信身份，再内部调用生成服务；有候选才调用 C，并返回生成、网关、结果三部分。请求/响应样例和 `refused`、`blocked`、`executed`、`unavailable` 状态见 [`docs/integration.md`](integration.md)。浏览器不能把自己编辑的 SQL 回传为执行来源。
4. **最后接页面。** A/C 在 [`frontend/index.html`](../frontend/index.html) 和 [`frontend/app.js`](../frontend/app.js) 增加独立“安全查询”入口和结果表格；保留当前双提示词实验。只渲染 C 处理后的行、列、脱敏标记与审计 ID，区分“查询成功但无行”“模型拒答”“C 阻断”“服务错误”。所有模型文本与数据库值继续以文本节点渲染。
5. **做端到端验收。** 使用 `docs/wsl-guide.md` 的启动顺序和 `docs/c-gateway-verification.md` 的命令检查正常成绩、敏感列、跨学生、DML/DDL、多语句、RLS 空结果、脱敏和审计。真实执行正确率、泄露率、拦截率和误拦截率仍需基于固定实验集单独统计；[`scripts/evaluate.py`](../scripts/evaluate.py) 只测模型生成。

完成时应能从空库启动，页面的一次自然语言输入贯穿同一个请求 ID，展示候选 SQL、C 的策略决策和真实合成数据结果；危险候选在 A 页面可见，但在 C/B 链路中没有被执行。成员 C 还需按[分工说明](team-division.md)整合最终实验结果、汇报材料和演练证据。

## 联调签收

- [x] B：从空库执行 DDL、角色、种子和重置命令；交付 Schema 版本、数据字典与稳定 ID。
- [x] B+A：对齐 `app/catalog.py`、身份白名单、固定测试集及恶意上下文来源，记录版本变化。
- [x] B+C：确定身份/表/字段访问矩阵、`MASK` 与 `BLOCK` 规则、只读角色和结果上限。
- [x] C：在合成库上通过 `ALLOW`、`MASK`、`BLOCK`、拒写、空结果与审计测试。
- [x] A+C：实现可信身份的 `/api/v1/queries` 和前端结果表格，核对拒答、阻断、执行和故障状态。
- [ ] 三人：跑通三组防御对比，核对 SQL 执行正确率和安全指标，更新演示脚本与汇报材料。
