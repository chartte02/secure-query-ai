# 项目完成情况、启动与验收说明

更新日期：2026-11-02  
当前负责人：成员 C  
当前分支：`main`

## 1. 当前完成情况

项目已经完成 A/B 基础工作线和 C 正式网关主线；当前 GPU 推理仍未启用，Pre 截图/录屏仍需整理。

| 模块 | 当前状态 | 说明 |
| --- | --- | --- |
| A：AI SQL 服务 | 已完成 | FastAPI、Mock/Ollama Provider、提示词、Schema 上下文、候选 SQL 生成和查询编排已合入 |
| B：数据库安全实验室 | 已完成 | PostgreSQL 三实例、角色、RLS、列权限、只读限制、合成数据、重置和固定攻击回放已合入 |
| C：SQL 安全网关 | 已完成 | `RealGateway` 独立解析、授权、hardened 只读执行、BLOCK/MASK/ALLOW |
| 统一执行与审计 | 已完成 | `/api/v1/queries` 接入 `audit.events`，记录决策和 SQL 摘要 |
| 前端完整攻防结果页 | 已完成 | 显示安全状态、原因、结果、脱敏字段、空结果和审计 ID |
| 调研与项目文档 | 基本完成 | 设计、分工、数据字典、攻击案例、数据库验证和实验计划已在 `docs/` |

必须区分：B 的固定 SQL 回放证明数据库权限行为，不证明模型已经生成攻击 SQL；A 的模型拒答率也不等于网关拦截率。

## 2. 已有可验证证据

- `main` 已包含 A/B 合并后的应用、数据库、前端、测试和实验文档。
- `.venv` 可运行，`pytest` 版本为 9.2.0。
- 配置安全测试本次实测为 **13 passed**。
- 历史验证文档记录 A/B 全套测试为 **163 passed / 2 skipped**，数据库与攻击回归为 **74 passed**；这些数字需在具备 Docker 的环境重新复跑后才能作为本次验收结果。
- Docker 三实例本次实测 healthy；Ollama 模型冒烟可用，但 placement 连续显示 `100% CPU`。
- C 单元/前端回归为 **26 passed**；改动文件 Ruff 为 **All checks passed**。

## 3. 启动方式

### 3.1 仅启动 A 的 Mock Demo

适合验证前端、API、提示词和候选 SQL，不需要 Docker 或 Ollama：

```bash
cd /home/chartte/school/SecureQuery_AI
test -x .venv/bin/python || python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
cp .env.example .env
SECUREQUERY_PROVIDER=mock SECUREQUERY_DEMO_MODE=true \
  .venv/bin/python -m app
```

启用正式 C 网关时再增加：

```text
SECUREQUERY_FORMAL_GATEWAY=true
```

首次使用正式网关需安装数据库依赖：

```bash
.venv/bin/python -m pip install -r requirements-database.lock
```

打开 `http://127.0.0.1:8000/`。如果 8000 端口已被占用，先停止旧服务，不能通过修改前端地址绕过配置。

### 3.2 启动 B 的 PostgreSQL 实验室

需要 Docker Desktop 或可访问 Docker daemon：

```bash
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python scripts/init_db.py --all
docker compose --profile lab up -d --wait
.venv/bin/python -m pytest tests/db tests/attacks -q
```

三个实例分别为 `hardened:55432`、`baseline:55433` 和 `write_lab:55434`。不要把真实个人数据写入种子文件。

### 3.3 启用 B 的固定回放

在 `.env` 中明确设置：

```text
SECUREQUERY_DEMO_MODE=true
SECUREQUERY_LAB_GATEWAY=true
```

重启 API 后访问：

```text
POST /api/v1/lab/replay/own_grades
POST /api/v1/lab/replay/rls_cross_student
POST /api/v1/lab/replay/column_denied
POST /api/v1/lab/replay/write_denied
```

这是数据库控制演示，不是 C 的正式网关。

### 3.4 启动真实 Ollama

先启动本地 Ollama，并准备项目允许的模型，例如 `qwen2.5-coder:7b`。再将 `.env` 设置为 `SECUREQUERY_PROVIDER=ollama`，确认 `SECUREQUERY_OLLAMA_BASE_URL` 使用当前实际端口。真实模型评估只运行固定合成样例，不把模型生成的 SQL直接执行。

## 4. 当前验收步骤与预期结果

### A 侧验收

```bash
.venv/bin/python -m pytest -q tests/test_config.py
.venv/bin/python -m pytest -q tests/test_api.py tests/test_prompts.py \
  tests/test_providers.py tests/test_diagnostics.py
```

预期：测试完成且无失败；Mock 模式不应访问外部云服务。`/api/v1/generations` 只返回候选 SQL 或拒答，不执行 SQL。

### B 侧验收

```bash
.venv/bin/python -m pytest -q tests/db tests/attacks
.venv/bin/python scripts/verify_db_permissions.py
.venv/bin/python scripts/collect_experiment_evidence.py
```

预期：

- 学生只能读取本人行；
- 跨学生查询在 hardened 中返回 0 行；
- 未授权敏感列返回 SQLSTATE `42501`；
- 只读角色执行危险写操作返回 `25006` 或 `42501`；
- `write_lab` 的一次性写实验不会污染 hardened；
- 重置后种子摘要恢复一致。

### C 侧最终验收

C 网关验收结果：

| 场景 | 预期 |
| --- | --- |
| 本人正常成绩查询 | `executed`，`ALLOW`，返回正确行 |
| 合法但包含敏感字段 | `executed`，`MASK`，返回脱敏列 |
| 跨学生查询 | `executed` + `row_count=0`，由 RLS 过滤 |
| 越权表/列 | `blocked`，`BLOCK`，无结果集 |
| 多语句、`DELETE`、`UPDATE`、`DROP` | 网关确定性 `BLOCK`，不依赖模型拒答 |
| RLS 过滤后无行 | `executed` + `row_count=0`，不能误报为 BLOCK |
| 数据库权限错误 | `error`，保留 `42501`/`25006` 等 SQLSTATE |
| 每次请求 | 生成、策略、执行和审计共用 `request_id`，返回 `audit_id` |

最终页面应显示用户身份、自然语言请求、候选 SQL、网关决策、原因、结果行数、脱敏字段、截断状态和审计 ID。

## 5. 最终通过标准

项目只有同时满足以下条件，才能称为“完成最终验收”：

1. A/B 测试在干净环境可重复运行；
2. C 的独立解析和授权先于数据库执行；
3. 至少三类攻击均有攻击前、攻击后和日志证据；
4. 前端不直接连接 Ollama 或 PostgreSQL；
5. 模型拒答、网关阻断、数据库错误和空结果在页面上明确区分；
6. 汇报演示有固定样例、离线 Mock/录屏备用路径；
7. 报告明确区分历史验证、本次实测和尚未完成的指标。

当前准确结论是：**A/B 基础与 C 正式网关已完成；模型安全指标仍需独立评估，GPU 仍是 CPU fallback。**

## 6. 2026-11-02 实测记录

以下命令均在仓库根目录执行，执行人是成员 C。凭据只保存在本地 `.env`，没有写入文档或 Git。

### 6.1 环境与数据库初始化

```bash
docker info --format 'server={{.ServerVersion}} os={{.OperatingSystem}}'
docker compose --profile lab ps
ollama list
docker compose --profile lab down -v
.venv/bin/python scripts/init_db.py --all
```

结果：

- Docker Server `29.8.2`，三个 PostgreSQL 容器均为 `healthy`；
- Ollama 已有 `qwen2.5-coder:7b`，模型大小约 `4.7 GB`；
- 因旧容器使用 `.env.example` 占位密码，先删除项目专用的三个合成数据库卷；
- `init_db.py --all` 成功创建 `hardened`、`baseline`、`write_lab`；
- 三个实例的种子版本均为 `20261028-v1`，总摘要均为 `63ce8f08e7265feda1e36801dff013ee8d9e6dfcef65b84ce5599214aae6354e`。

### 6.2 A 侧离线测试

```bash
.venv/bin/python -m pytest -q \
  tests/test_api.py tests/test_config.py tests/test_diagnostics.py \
  tests/test_evaluation.py tests/test_frontend_security.py tests/test_prompts.py \
  tests/test_providers.py tests/test_generation_attacks.py \
  tests/test_schema_contract.py tests/test_query_route.py
```

结果：命令成功退出，A 侧 API、配置、诊断、Provider、提示词、前端安全、攻击生成和查询编排测试通过。另行执行的配置测试为 `13 passed`。

### 6.3 B 侧数据库与攻击回归

```bash
.venv/bin/python -m pytest tests/db tests/attacks -ra --tb=short
.venv/bin/python scripts/verify_db_permissions.py
.venv/bin/python scripts/collect_experiment_evidence.py
```

结果：

- `98 passed, 6 skipped in 1.52s`；
- 6 个跳过项是没有固定候选 SQL 的评估契约样例，按测试设计跳过，不是失败；
- 权限验证脚本成功退出；
- 证据文件生成于 `artifacts/database-evidence.json`；
- 证据明确显示：baseline 可读取 S02 成绩和 `national_id`，hardened 对跨学生成绩返回 0 行，对敏感列返回 SQLSTATE `42501`；
- 证据字段标记 `candidate_origin=fixed_sql_replay`、`model_invoked=false`、`gateway_status=not_implemented`，因此不能当作模型攻击或 C 网关证据。

### 6.4 Mock、B 实验室回放和安全默认值

使用 `SECUREQUERY_PROVIDER=mock`、`SECUREQUERY_DEMO_MODE=true` 和
`SECUREQUERY_LAB_GATEWAY=true` 运行 FastAPI TestClient，结果如下：

| 检查 | 实测结果 |
| --- | --- |
| `/api/v1/health` | HTTP 200，`gateway_connected=false`，`executor=lab_direct` |
| `own_grades` | HTTP 200，ALLOW，3 行，角色 `sq_student_s01` |
| `rls_cross_student` | HTTP 200，ALLOW，0 行 |
| `column_denied` | HTTP 200，ALLOW 后由数据库返回 `42501` |
| `write_denied` | HTTP 200，ALLOW 后由只读数据库返回 `25006` |
| `row_limit` | HTTP 200，100 行，结果被截断 |
| 默认关闭实验室网关的 `/api/v1/queries` | HTTP 503，`status=unavailable`，`result=null` |

这里的 `ALLOW` 是实验室直连执行器的结果，不是 C 的策略决策。默认网关关闭时返回 503 且没有结果，证明当前安全默认值没有绕过网关执行 SQL。

### 6.5 Ollama 实测

```bash
curl --max-time 30 http://127.0.0.1:11434/api/tags
curl --max-time 45 http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-coder:7b","stream":false,
       "messages":[{"role":"user","content":"Return only SELECT 1"}],
       "options":{"num_ctx":1024}}'
```

结果：模型列表和单条原生推理均成功。原生请求返回 `SELECT 1`，但总耗时约 34.7 秒，其中模型加载约 16.7 秒。

项目固定评估命令：

```bash
SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11434 \
  .venv/bin/python scripts/evaluate.py \
  --provider ollama --model qwen2.5-coder:7b \
  --case normal_grade --case direct_injection
```

结果：项目固定 Prompt 请求出现 `provider_error`，堆栈显示在
`POST /api/chat` 等待响应头阶段超时；评估被停止，不能据此报告模型成功率或拒答率。该结果只说明当前机器上的 7B 固定评估性能不足或超时配置不匹配，不代表 SQL 网关安全失败。

## 7. 本轮验收结论

本轮可以确认：

1. A 的候选 SQL 生成服务和离线安全测试可运行；
2. B 的三实例 PostgreSQL、RLS、列权限、只读限制和攻击回归可复现；
3. 固定 SQL 的 baseline/hardened 对照证据已生成；
4. Ollama 模型已安装，原生最小推理可用；
5. 网关未接入时，系统不会假装执行 SQL，默认查询返回 503；
6. C live 验收已覆盖 ALLOW、MASK、BLOCK、RLS 空结果和审计摘要。

本轮不能确认：

1. GPU-backed Ollama 推理，当前只能确认 CPU fallback；
2. 7B 固定 Prompt 评估的完整成功率和攻击拒答率；
3. Pre 最终截图/录屏和人工语义审阅。

因此当前验收等级为：**A/B 与 C 主线通过；模型/GPU指标和 Pre 展示材料仍待补齐。**
