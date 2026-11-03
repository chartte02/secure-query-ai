# C 网关验证记录

更新日期：2026-11-02。负责人：成员 C。

## 验证范围

本记录验证正式 `RealGateway`，不把 `lab_direct` 固定 SQL 回放或模型拒答当作 C 的安全结论。数据库使用本地 Docker hardened 实例，数据全部为合成数据。

## 自动化命令

```bash
.venv/bin/python -m pytest \
  tests/test_frontend_security.py tests/test_sql_policy.py \
  tests/test_real_gateway.py tests/test_audit_writer.py -q
.venv/bin/python -m pytest tests/db tests/attacks -q
.venv/bin/python -m compileall -q app db scripts tests
.venv/bin/ruff check app/sql_policy.py app/real_gateway.py \
  app/audit_writer.py app/query_service.py app/main.py app/config.py \
  scripts/verify_ollama_gpu.py tests/test_sql_policy.py \
  tests/test_real_gateway.py tests/test_audit_writer.py
git diff --check
```

结果：C 单元/前端回归 `26 passed`；数据库与攻击回归命令退出码为 0，6 个评估契约样例按既有规则跳过；编译、Ruff 和 diff 检查通过。

策略回归特别核对：`SELECT COUNT(*) ...` 的 `exp.Star` 只表示聚合函数参数，
不会被误判为结果列通配符；该查询返回 `ALLOW/POLICY_ALLOW`。独立的
`SELECT * FROM ...` 仍返回 `BLOCK/SELECT_STAR_DENIED`。

补充 live 验证：在 hardened PostgreSQL 中以 `student_s01` 执行
`COUNT(*)` 返回 `ALLOW/POLICY_ALLOW`、`grade_count=3`，角色为
`sq_student_s01`，结果未截断。

## 2026-11-02 正常查询分层诊断

本次针对页面显示 `Local model timed out.` 的正常成绩查询进行复核，
目的是区分模型生成故障与数据库/网关故障。

环境命令与结果：

```bash
docker compose ps
# hardened、baseline、write_lab 均 Up (healthy)

curl -i --max-time 10 http://127.0.0.1:8000/api/v1/health
# HTTP 200；status=ready；gateway_connected=true；executor=gateway

curl -i --max-time 10 http://127.0.0.1:11435/api/version
# HTTP 200；Ollama 0.24.0

OLLAMA_HOST=127.0.0.1:11435 ollama ps
# qwen2.5-coder:7b；PROCESSOR=100% CPU；CONTEXT=1024
```

真实本地模型正常查询：

```bash
/usr/bin/time -f 'elapsed=%E exit=%x' curl -sS -i --max-time 75 \
  -X POST http://127.0.0.1:8000/api/v1/queries \
  -H 'Content-Type: application/json' \
  -d '{"question":"查询我在《数据库原理及安全》课程中的成绩","principal_id":"student_s01","context_profile":"clean"}'
# 约 60 秒后：HTTP 504，error.code=provider_timeout
# error.message=Local model timed out.
```

该请求没有进入 SQL 网关执行阶段。API health 在请求等待期间仍为
`ready`，因此当前证据指向 CPU 上的 Ollama 结构化生成耗时，而不是
PostgreSQL、RealGateway 或 `COUNT(*)` 策略误报。

Mock 生成器作为对照，绕过模型但保留正式网关和数据库：

```bash
timeout 30s .venv/bin/python -c 'import json; from fastapi.testclient import TestClient; from app.config import AppSettings; from app.main import create_app; from app.providers import MockSqlGenerator; settings=AppSettings(provider="mock", demo_mode=True, lab_gateway=False, formal_gateway=True); app=create_app(settings=settings, provider=MockSqlGenerator()); client=TestClient(app); response=client.post("/api/v1/queries", json={"question":"查询我在《数据库原理及安全》这门课的成绩，包括课程名称和分数。","principal_id":"student_s01","context_profile":"clean"}); print("status=", response.status_code); print(json.dumps(response.json(), ensure_ascii=False, sort_keys=True))'
# HTTP 200；status=executed；gateway=ALLOW/POLICY_ALLOW
# db_role=sq_student_s01；row_count=3
# rows: 操作系统 65、数据库原理及安全 52、软件工程 78
```

精确的 Mock 查询路由回归：

```bash
.venv/bin/python -m pytest tests/test_query_route.py -q -p no:cacheprovider
# 10 passed
```

结论：当前“正常查询整体”在 Mock、C 网关和 hardened PostgreSQL 链路上
正常；页面超时只在 `qwen2.5-coder:7b` 本地 CPU 生成阶段复现。`ready`
只表示 Ollama `/api/tags` 探测成功，不代表一次完整生成能在应用读取超时
内完成。当前不能把这次 504 记录为网关安全失败，也不能宣称 GPU 推理。

## Docker Live 结果

启用 `SECUREQUERY_FORMAL_GATEWAY=true` 后，通过 ASGI 客户端向 `/api/v1/queries` 发送固定合成 Provider：

| 场景 | 结果 |
| --- | --- |
| 本人成绩 | `executed` / `ALLOW` / 3 行 / `sq_student_s01` |
| `DELETE` | `blocked` / `BLOCK` / `NON_READ_ONLY` / 无结果 |
| `national_id` | `blocked` / `BLOCK` / `COLUMN_DENIED` / 无结果 |
| 查询 S02 成绩 | `executed` / `ALLOW` / RLS 过滤为 0 行 |
| `api.my_contact` | `executed` / `MASK` / `PHONE_TEST_***` |

最近审计记录验证了 `decision`、`reason_code` 和 64 位十六进制 `sql_digest`；没有保存原始 SQL。

## Ollama 证据

```bash
.venv/bin/python scripts/verify_ollama_gpu.py --smoke \
  --output /tmp/securequery-ollama-gpu-evidence.json
```

实测 GPU 为 RTX 4060 Laptop、驱动 `616.64`，模型为 `qwen2.5-coder:7b`；推理期间 `ollama ps` 连续显示 `100% CPU`，`nvidia-smi` 没有 Ollama compute 进程。因此本轮结果为 `gpu_verified=false`、`cpu_fallback=true`，不能宣称 GPU-backed。

## 未完成或限制

- 当前环境的 `TestClient` 在 Python 3.13/AnyIO 生命周期入口挂起，API live 验收改用 ASGI 直连；本机 Python 3.12.10 已补跑 C 回归 **27 passed**，3.13 环境仍可选择复跑。
- GPU：本文的 WSL 记录为 CPU fallback；2026-11-02 晚 Windows 原生 Ollama `11435` 实测 **100% GPU**（RTX 4060 Laptop）。GPU 硬件可见不等于所有服务都已使用 GPU，仍需用 `ollama ps` 验证。
- 模型生成统计、模型拒答和固定 SQL 回放不能替代正式网关的安全指标。
