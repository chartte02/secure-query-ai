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

- 当前环境的 `TestClient` 在 Python 3.13/AnyIO 生命周期入口挂起，API live 验收改用 ASGI 直连；这不是成功测试，应在标准运行环境补跑完整 HTTP 测试。
- GPU 加速仍需排查 Ollama 服务安装/运行配置；GPU 硬件可见不等于 Ollama 已使用 GPU。
- 模型生成统计、模型拒答和固定 SQL 回放不能替代正式网关的安全指标。
