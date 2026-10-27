# 给成员 B、C 的待核实与待完成清单

本文用于三人联调。当前项目完成了成员 A 的候选 SQL 生成与攻防对照；**没有 PostgreSQL 建库脚本、C 网关、真实查表接口或数据库结果表格**。下文标注“建议新增”的文件目前不存在，是建议的代码归属；若 B/C 在自己的仓库开发，请交付同版本文件及可复现命令，再由三人决定如何合入。

## 先确认现有接口与占位

| 现有位置 | 已实现 | 对接时的含义 |
|---|---|---|
| [`app/catalog.py`](../app/catalog.py) 的 `SCHEMA_VERSION`、`SCHEMA_SQL`、`PRINCIPALS`、`CONTEXTS` | 模型看到的 `campus_v1` 示例表结构、S001/T001 演示身份、固定恶意上下文 | `SCHEMA_SQL` **不会建表**；演示身份不是真实认证；恶意备注不是从数据库读取的 |
| [`app/prompts.py`](../app/prompts.py) 的 `build_prompt()` | 把服务端 Schema、身份、上下文和问题放进结构化消息 | B 的实际表结构或身份范围变化时，由 A 同步版本和提示词上下文 |
| [`app/main.py`](../app/main.py) 的 `POST /api/v1/generations` | 只返回候选 SQL、拒答、诊断和模型来源 | 不连接 B 的库、不执行 SQL、不作最终授权 |
| [`app/models.py`](../app/models.py) 的 `GatewayHandoff` | 定义 `request_id`、`principal_id`、`candidate_sql`、`schema_version` 四个字段 | 只是交接数据模型，尚无调用 C 的代码 |
| [`app/diagnostics.py`](../app/diagnostics.py) 的 `diagnose_sql()` | 给出解析、语句数、表/列和危险候选警告 | C 必须独立重新解析并授权；A 的诊断不是 `ALLOW` |
| [`frontend/index.html`](../frontend/index.html) 的第三列与 [`frontend/app.js`](../frontend/app.js) 的 `runExperiment()` | 显示准备交给网关的 JSON | 前端目前没有发送到 C，也没有展示数据库行 |
| [`docs/integration.md`](integration.md) 的 `POST /api/v1/queries` | 未来请求、状态和结果 JSON 示例 | **接口尚未实现**；示例分数不是实测结果 |

## 成员 B：数据库与攻击样例

建议把可复现数据库材料放在新目录 `db/`，至少交付以下文件；文件名可以协商，但用途和运行顺序必须明确。

| 建议文件（当前不存在） | 需要完成的内容 | A/C 需要核实什么 |
|---|---|---|
| `db/schema.sql` | PostgreSQL 表、主外键、字段类型、非空约束；覆盖学生、课程、选课、成绩、奖助学金和必要的审计表/视图 | 与 `app/catalog.py` 的 `campus_v1` 逐列比对；若不同，由 A 发布新 Schema 版本，不改写旧实验记录 |
| `db/seed.sql` | 完全合成、重复运行可得到相同结果的数据；包含 S001、另一名学生、T001、正常成绩、空结果和敏感字段测试记录 | `tests/fixtures/generation_benchmark.json` 的正常问题和参考 SQL 能否查出预期结果；课程名“数据库”是否一致 |
| `db/roles.sql` | 学生/教师/管理员实验角色、只读应用角色、视图及最小授权 | C 的执行账户应只能读允许的对象，写操作在数据库层也失败；凭据不提交仓库 |
| `db/README.md` 与建议新增的 `scripts/reset_db.py` | 从空库建表、初始化、重置、检查版本的完整命令与依赖 | 其他成员能独立重建同一合成环境，无需 B 手工操作 |
| 建议新增 `docs/attack-cases.md` | 三类正式攻击的前提、正常/攻击问题、预期 SQL/网关决策、实际影响与证据路径 | 与当前 [`app/catalog.py`](../app/catalog.py) 场景、[`tests/fixtures/generation_benchmark.json`](../tests/fixtures/generation_benchmark.json) 保持同一口径 |

B 还需专门核实**间接 Prompt Injection**：当前 [`CONTEXTS`](../app/catalog.py) 只是服务端固定的“恶意课程备注”字符串。若演示要声称攻击来自真实数据库内容，B 应在 `db/seed.sql` 放入可定位的恶意课程描述；C/查询编排组件负责受限读取，A 在 [`app/prompts.py`](../app/prompts.py) 的 `build_prompt()` 中把该字段标成**不可信上下文**，同时调整当前固定夹具的使用方式。完成这条链路前，演示和报告只能称它为“恶意上下文夹具”。

建议 B 给三人一张最终数据字典：Schema 版本、每张表的字段/类型、S001/T001 对应记录、课程名、敏感字段、各正常问题的预期行，以及三类攻击的预期结果。尤其要确认“学生只能看本人”“教师只能看所授课”“管理员也不能通过查询服务写库”的范围。

## 成员 C：网关、执行与审计

建议把 C 的实现放在独立 `gateway/` 组件（当前不存在），由 C 保管数据库连接配置；如决定放进同一 FastAPI 进程，也必须维持清晰模块边界，由三人同步修改下表路径与启动说明。

| 建议文件（当前不存在） | 需要完成的内容 | 验收点 |
|---|---|---|
| `gateway/policy.py` | 独立解析 PostgreSQL SQL；限制单条只读语句；检查表、列、用户范围、绕过和危险操作 | 不信任 A 的 `diagnostics`；多语句、`DROP`、`DELETE`、注释绕过及越权请求稳定 `BLOCK` |
| `gateway/executor.py` | 使用 B 提供的只读角色和只读事务执行通过策略的查询；设置超时、最大行数和结果大小 | 只由 C 持有数据库凭据；返回空行与执行失败有不同状态；不执行被阻断候选 |
| `gateway/audit.py` | 记录请求 ID、可信身份、SQL 摘要、策略版本、决策和原因 | 不记录身份证号、完整敏感结果或连接口令；可追溯同一次请求 |
| `gateway/main.py` 或 C 提供的固定内部接口 | 接收后端交接载荷，返回 `ALLOW`/`MASK`/`BLOCK`、原因、审计 ID 和经脱敏的结果 | 地址与调用认证由服务端固定配置；浏览器不能直接提交 SQL 供执行 |
| 建议新增 `tests/integration/` | 在 B 的合成库上覆盖允许、脱敏、阻断、空结果、数据库超时和只读角色拒写 | 每个策略有允许与阻断对照；三类攻击有可复现证据 |

B/C 需要先共同确定政策矩阵：哪些身份可见哪些表和列；`phone`、`national_id` 等字段是 `MASK` 还是 `BLOCK`；学生跨人查询、教师跨课查询如何判定；最大返回行数与超时；审计字段和保留方式。数据库原生权限和 C 的策略应各自能说明作用，不能把模型拒答算作网关拦截。

## 三人共同接入现有页面

1. **先锁定契约。** B 提交数据库版本与合成数据，A 更新 [`app/catalog.py`](../app/catalog.py) 和 [`tests/fixtures/generation_benchmark.json`](../tests/fixtures/generation_benchmark.json) 中不再匹配的 Schema/样例；若演示身份或 ID 改变，也要同步 [`app/models.py`](../app/models.py) 的请求白名单和 [`app/providers.py`](../app/providers.py) 的 Mock 夹具。C 记录策略版本。原始历史实验 JSON 保持不变。
2. **再做安全执行。** C 在合成库上通过 `ALLOW`、`MASK`、`BLOCK` 测试后，约定固定的网关调用方式。交给 C 的四字段结构见 [`GatewayHandoff`](../app/models.py)，但可信身份必须由服务端取得；浏览器当前的 `principal_id` 只是演示夹具，C 不能直接相信它。
3. **新增查询编排。** A/C 建议新建 `app/query_service.py`，并在 [`app/main.py`](../app/main.py) 增加 `POST /api/v1/queries`，在 [`app/models.py`](../app/models.py) 增加请求和统一响应模型。编排端点先取得可信身份，再内部调用生成服务；有候选才调用 C，并返回生成、网关、结果三部分。请求/响应样例和 `refused`、`blocked`、`executed`、`unavailable` 状态见 [`docs/integration.md`](integration.md)。浏览器不能把自己编辑的 SQL 回传为执行来源。
4. **最后接页面。** A/C 在 [`frontend/index.html`](../frontend/index.html) 和 [`frontend/app.js`](../frontend/app.js) 增加独立“安全查询”入口和结果表格；保留当前双提示词实验。只渲染 C 处理后的行、列、脱敏标记与审计 ID，区分“查询成功但无行”“模型拒答”“C 阻断”“服务错误”。所有模型文本与数据库值继续以文本节点渲染。
5. **做端到端验收。** 建议新增 `tests/test_query_flow.py` 验证编排状态和身份传递，并在 B/C 的集成测试上检查正常成绩、错误课程过滤、空结果、敏感字段、跨学生、直接/间接注入、DML/DDL、多语句、超时与脱敏。真实执行正确率、泄露率、拦截率和误拦截率只有此时才能统计；[`scripts/evaluate.py`](../scripts/evaluate.py) 目前只测模型生成。

完成时应能从空库启动，页面的一次自然语言输入贯穿同一个请求 ID，展示候选 SQL、C 的策略决策和真实合成数据结果；危险候选在 A 页面可见，但在 C/B 链路中没有被执行。成员 C 还需按[分工说明](team-division.md)整合最终实验结果、汇报材料和演练证据。

## 联调签收

- [ ] B：从空库执行 DDL、角色、种子和重置命令；交付 Schema 版本、数据字典与稳定 ID。
- [ ] B+A：对齐 `app/catalog.py`、身份白名单、固定测试集及恶意上下文来源，记录任何版本变化。
- [ ] B+C：签定身份/表/字段访问矩阵、`MASK` 与 `BLOCK` 规则、只读角色和结果上限。
- [ ] C：在合成库上通过 `ALLOW`、`MASK`、`BLOCK`、拒写、空结果与超时测试，提供审计证据。
- [ ] A+C：实现可信身份的 `/api/v1/queries` 和前端结果表格，核对拒答、阻断、执行和故障状态。
- [ ] 三人：跑通三组防御对比，核对 SQL 执行正确率和安全指标，更新演示脚本与汇报材料。
