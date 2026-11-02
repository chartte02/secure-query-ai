# 项目状态与交接

更新日期：2026-11-02。分支：`main`。

> 本文只回答“现在做到哪、还剩什么”。设计与权限细节见 [联调契约](integration.md)、[数据库契约](database-contract.md)；启动和复现见 [WSL 指南](wsl-guide.md)。进度以本文为准。

## 1. 一句话

A/B 的 Schema 与身份已对齐到 `campus_lab_v1`；A 的生成、查询编排、实验室直连和固定 SQL 回放均已完成。C 的正式网关、审计和前端结果面板已接入，当前 GPU 仍记录为 CPU fallback。

## 2. 完成度

| 成员 | 状态 | 已完成 | 未完成 |
| --- | --- | --- | --- |
| A | ✅ | Schema/Prompt v2、Mock、查询编排、实验室直连、固定回放、契约测试 | v2 评估已生成 26 条，人工审阅待完成 |
| B | ✅ | 建表/角色/RLS/列权限/种子数据、74 项回归、Docker 三实例 | 无；Schema 变更需先升版本 |
| C | 🟡 | SQLGlot 策略、hardened 只读执行、MASK/限行、audit.events、前端安全查询 | TestClient 在当前 Python 3.13/AnyIO 环境生命周期入口挂起；GPU 尚未启用 |

## 3. 当前可用接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/v1/health` | 模型、Schema、`gateway_connected`、`executor` |
| GET | `/api/v1/demo/catalog` | 身份、场景、Prompt 版本、`database_connected` |
| POST | `/api/v1/generations` | 只生成候选 SQL，不执行 |
| POST | `/api/v1/queries` | 生成 → 执行器；默认 `503 unavailable`，实验室模式下直连 B |
| GET | `/api/v1/lab/scenarios` | 仅实验室模式：固定回放场景列表 |
| POST | `/api/v1/lab/replay/{id}` | 仅实验室模式：固定 SQL 回放，不调用模型 |

`POST /api/v1/queries` 请求：

```json
{
  "question": "查询我在《数据库原理及安全》这门课的成绩",
  "principal_id": "student_s01",
  "context_profile": "clean"
}
```

`principal_id` 仅允许 `student_s01`、`student_s02`、`teacher_t01`；不接受 `prompt_profile`、SQL、角色或 DSN。

响应关键字段：

| 字段 | 含义 |
| --- | --- |
| `status` | `refused` / `invalid_output` / `blocked` / `executed` / `unavailable` / `error` |
| `generation` | 完整生成结果：候选 SQL、拒答、诊断、provenance |
| `gateway` | C 的决策：`ALLOW` / `MASK` / `BLOCK`、`reason_code`、`audit_id`、`policy_version` |
| `result` | 列、行、`row_count`、`truncated`、`masked_columns`、`execution_ms` |
| `error` | B 的执行错误：`code`、`stage`、`sqlstate`、`message` |
| `db_role` | 实际执行的数据库角色，如 `sq_student_s01` |
| `executor` | `gateway`（C）或 `lab_direct`（实验室，仅演示） |

HTTP：业务结果 200；`unavailable` 为 503；字段校验失败 422。

## 4. 本机验证结果

| 项目 | 结果 |
| --- | --- |
| C 单元/前端回归 | **26 passed**（策略、执行、审计、前端） |
| A 离线测试 | **80 passed** |
| `tests/db + tests/attacks` | **74 passed** |
| 实验室直连/回放 | **12 passed** |
| `ruff check`（C 改动文件） | All checks passed |

> 分组统计有少量重叠（`tests/attacks/test_generation_attacks.py` 同时属于 A 与 attacks），总数以全套 **163 passed / 2 skipped** 为准。

8000 端口实测（实验室模式）：

| 场景 | 结果 |
| --- | --- |
| `/api/v1/queries` 正常成绩 | `executed`，1 行 52 分，`db_role=sq_student_s01` |
| `own_grades` 回放 | 3 行 |
| `rls_cross_student` 回放 | `executed` + 0 行（RLS 静默过滤） |
| `column_denied` 回放 | `error` + `42501` + `permission denied for table students` |
| `write_denied` 回放 | `error` + `25006` + `cannot execute DELETE in a read-only transaction` |
| `row_limit` 回放 | 100 行，`truncated=true` |

真实 7B 冒烟：`hardened_v2` + `campus_lab_v1` 生成的 SQL 可在 hardened 库执行并返回正确行；这是单样本，不是成功率。真实模型对明显越权/写请求会先拒答，因此 B 的 SQLSTATE 演示使用固定回放。

正式 C 网关 live 验收（ASGI 直连 + Docker hardened）：

| 场景 | 实测结果 |
| --- | --- |
| 本人成绩 | HTTP 200，`executed`，`ALLOW/POLICY_ALLOW`，3 行 |
| 危险写入 | HTTP 200，`blocked`，`BLOCK/NON_READ_ONLY`，无结果 |
| 敏感列 | HTTP 200，`blocked`，`BLOCK/COLUMN_DENIED`，无结果 |
| 跨学生查询 | HTTP 200，`executed`，`ALLOW`，RLS 过滤为 0 行 |
| 脱敏联系方式 | HTTP 200，`executed`，`MASK/MASKED_VIEW`，`PHONE_TEST_***` |
| 审计 | 最近记录含决策、原因和 64 位 `sql_digest`，不保存 SQL 原文 |

v2 评估记录（2026-11-01，文件未提交）：`artifacts/experiments/ollama-qwen2.5-coder-7b-20261101T110745Z-483c31af.json`，26 条记录，Prompt/Schema 为 `baseline_v2/hardened_v2` + `campus_lab_v1`。

| 指标 | baseline_v2 | hardened_v2 |
| --- | ---: | ---: |
| 正常问题可解析 | 7/7 | 6/7 |
| 正常问题拒答 | 0/7 | 1/7 |
| 攻击问题模型拒答 | 0/6 | 6/6 |
| 输出/传输错误 | 0 | 0 |
| 平均生成耗时 | 1,593 ms | 1,197 ms |

`sql_execution_correctness` 与 `data_leakage_rate` 仍为 `not_measured`；这是**生成统计**，不能当作网关拦截率、执行正确率或安全结论。人工语义审阅待完成。

## 5. 剩余工作

### C：策略网关与执行器（已实现）

实现入口为 `app/sql_policy.py`、`app/real_gateway.py`、`app/audit_writer.py` 和 `app/query_service.py`。网关独立解析候选 SQL，执行前检查只读与对象策略，再使用 hardened 受限角色执行；前端不直接提交 SQL、DSN 或角色。

已验证的边界：

- 不信任 A 的诊断、模型拒答或浏览器身份；演示身份映射为固定 actor；
- 区分策略 `BLOCK`、数据库错误和 RLS 过滤后的 `executed + 0 行`；
- 结果具备限行、脱敏、执行耗时和审计 ID；
- `audit.events` 只保存决策、原因、角色和 SQL 摘要，不保存原始 SQL；
- `SECUREQUERY_FORMAL_GATEWAY=true` 才启用正式网关，`lab_direct` 仍是 B 的隔离回放；
- 前端安全查询面板只提交自然语言、演示身份和上下文。

验收：

- 允许、脱敏、阻断、数据库错误、RLS 空结果各有测试。
- 多语句、DROP/DELETE、越权表/列稳定 BLOCK 或由 B 拒绝，不能只靠模型拒答。
- 空结果与阻断、错误不能混淆。

### A：非阻塞

- 人工审阅 2026-11-01 的 26 条 v2 评估记录（含 1 次正常拒答与 6 条攻击输出）；旧 `campus_v1` 结果不能与新结果混统。可补跑 3B 或重复运行。
- 可选：补跑更小模型或重复评估，并完成人工语义审阅。
- 不把 A 改成直连数据库；实验室执行器仅用于本地演示。

### B：保持

- Schema 已冻结在 `campus_lab_v1`。如需改表，先升 `SCHEMA_VERSION`，同步 `app/catalog.py`、Prompt、测试，并通知 A/C。
- 数据库凭据只给 C 的执行组件。

## 6. 不要混淆

| 容易混淆 | 正确理解 |
| --- | --- |
| A 的 `baseline/hardened` | 两套 Prompt |
| B 的 `baseline/hardened` | 两套数据库权限环境（55433 / 55432） |
| RLS 返回 0 行 | 不是 BLOCK，也没有错误；数据库静默过滤 |
| `42501 / 25006` | B 的列权限/只读拒绝，应通过 `error.sqlstate` 展示 |
| `lab_direct` | A 的实验室直连，不是 C 的网关，不提供策略 |
| `/api/v1/lab/replay` | 固定 SQL 回放，`model_invoked=false`，不算模型攻击结果 |

## 7. 改动地图

| 文件 | 作用 |
| --- | --- |
| `app/catalog.py` | `campus_lab_v1`、可见 Schema、身份、场景、真实恶意反馈文本 |
| `app/prompt_templates/*_v2.txt` | 与 B Schema 对齐的 Prompt 版本 |
| `app/providers.py` | Mock 的 SQL 改为 `academic.*` + `offering_id` |
| `app/models.py` | `QueryRequest/Response`、`QueryError`、`LabReplayResponse` |
| `app/gateway.py` | `SqlGateway` 协议、`GatewayOutcome`、`NotConnectedGateway` |
| `app/query_service.py` | 生成 → 网关 → 状态映射；审计哈希 |
| `app/lab_gateway.py` | 实验室直连执行器与固定回放场景 |
| `app/main.py` | `/api/v1/queries`、实验室路由、`executor` 状态 |
| `app/config.py` | `SECUREQUERY_LAB_GATEWAY` |
| `tests/test_schema_contract.py` | A/B Schema、身份、恶意上下文契约 |
| `tests/test_query_route.py` | 编排状态与网关不可用 |
| `tests/test_query_lab.py` | 实验室直连/回放的真实数据库测试 |
| `.env.example` | 实验室开关示例（默认 false） |

## 8. 环境与停止

```powershell
# 启动
Start-Process "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
docker compose --profile lab up -d --wait
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 start

# 查看数据库控制（实验室模式需要 .env 中 SECUREQUERY_LAB_GATEWAY=true）
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/lab/replay/column_denied

# 停止
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 stop
docker compose --profile lab stop
docker desktop stop
wsl --shutdown
```

端口：API 8000、Ollama 11435、hardened 55432、baseline 55433、write_lab 55434。`.env` 与数据库卷保留在本机，不提交。

## 9. 交接清单

- [x] B 的 Schema/权限/种子数据与 A 的模型上下文对齐
- [x] A 的 `/api/v1/queries` 编排与契约
- [x] 实验室直连与固定回放（可稳定演示 B 的结果与 SQLSTATE）
- [x] C 的 `RealGateway` 实现与注入
- [x] C 的 `audit.events` 业务写入与 `audit_id`
- [x] 前端“安全查询”结果表格
- [ ] 人工审阅 v2 评估记录（26 条已生成，文件未提交）
- [x] 三人联调：一次请求 ID 贯穿生成、策略、执行、审计
