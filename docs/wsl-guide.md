# SecureQuery AI：WSL 完整启动与验收指南

更新日期：2026-11-02。本文是 WSL 下的主启动入口；功能状态看 [`status.md`](status.md)，C 的实测命令看 [`c-gateway-verification.md`](c-gateway-verification.md)，不要在多份文档重复维护同一组结果。

## 1. 运行模式

完整链路为：

```text
浏览器前端 → FastAPI/A 生成服务 → C RealGateway → hardened PostgreSQL
                                      ↓
                                audit.events
```

项目身份和 Schema 固定为 `student_s01`、`student_s02`、`teacher_t01` 与 `campus_lab_v1`。`lab_direct` 只用于 B 的固定 SQL 回放，不是正式安全网关。

## 2. WSL 前置条件

- WSL2 Linux 发行版，建议 Ubuntu；
- Windows Docker Desktop 已启动，并在 Docker Desktop 的 WSL Integration 中启用当前发行版；
- WSL 内可执行 `docker`、`python3`；真实模型另需 `ollama`；
- 项目位于 WSL 可访问路径，例如 `/home/chartte/school/SecureQuery_AI`。

```bash
cd /home/chartte/school/SecureQuery_AI
docker version
python3 --version
```

若 `docker version` 报 `permission denied`，先启动 Docker Desktop；不要自行修改项目代码绕过 Docker。

## 3. 安装依赖

数据库初始化前不要直接把 `.env.example` 复制成 `.env`，其中的 `SQ_*` 是占位符。让初始化脚本生成随机本地凭据：

```bash
cd /home/chartte/school/SecureQuery_AI
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install -r requirements-database.lock
```

`requirements-dev.lock` 提供 B 的测试工具；`requirements-database.lock` 是 C 正式网关的显式数据库依赖。A-only 安装仍不把数据库驱动放入主运行依赖。

## 4. 初始化并启动 PostgreSQL

```bash
.venv/bin/python scripts/init_db.py --all
docker compose --profile lab ps
```

预期三个服务均为 `healthy`：

| 服务 | 端口 | 用途 |
| --- | ---: | --- |
| `hardened` | `55432` | 正式 C 网关，RLS、列权限、只读 |
| `baseline` | `55433` | 宽权限对照 |
| `write_lab` | `55434` | 隔离的写操作实验 |

只需要正式主库时可以使用：

```bash
.venv/bin/python scripts/init_db.py --profile hardened
```

若数据库已经存在且只想重置合成数据：

```bash
.venv/bin/python scripts/reset_db.py --profile hardened
.venv/bin/python scripts/reset_db.py --profile baseline
.venv/bin/python scripts/reset_db.py --profile write_lab
```

## 5. 启动 Ollama

### Mock 模式

默认 Mock 不需要 Ollama，可直接跳到下一节。完整数据库链路仍需要第 4 节的 PostgreSQL。

### 本地 Ollama 模式

另开一个 WSL 终端，推荐让项目 Ollama 独占 `11435`，与系统默认 `11434` 服务隔离：

```bash
export OLLAMA_HOST=127.0.0.1:11435
ollama serve
```

再开第三个 WSL 终端，使用同一个端口拉取和检查模型：

```bash
export OLLAMA_HOST=127.0.0.1:11435
ollama pull qwen2.5-coder:7b
ollama list
curl -fsS http://127.0.0.1:11435/api/tags
```

API 终端也必须配置同一个地址：

```text
SECUREQUERY_PROVIDER=ollama
SECUREQUERY_MODEL=qwen2.5-coder:7b
SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11435
```

如果已经有系统 Ollama 在 `11434` 运行，也可以不启动第二个服务，改为把 `SECUREQUERY_OLLAMA_BASE_URL` 设置为 `http://127.0.0.1:11434`，并先用 `curl .../api/tags` 确认模型在同一个服务中。项目根目录的 Windows `run.ps1` 使用独立的项目 Ollama 端口 `11435`；不要把两个服务的模型、端口和状态混用。Mock 模式不需要 Ollama，也不会读取模型服务。

推理期间另开终端确认实际 placement：

```bash
OLLAMA_HOST=127.0.0.1:11435 ollama ps
nvidia-smi
.venv/bin/python scripts/verify_ollama_gpu.py --smoke \
  --host 127.0.0.1:11435 \
  --output /tmp/securequery-ollama-gpu-evidence.json
```

必须以 `ollama ps` 和 `nvidia-smi` 共同证明 GPU；本机 2026-11-02 实测为 `100% CPU`，应记录为 CPU fallback，不能仅因检测到 RTX 4060 就宣称 GPU 推理。

## 6. 启动完整应用和前端

在 API 终端执行：

```bash
export SECUREQUERY_PROVIDER=mock
export SECUREQUERY_DEMO_MODE=true
export SECUREQUERY_LAB_GATEWAY=false
export SECUREQUERY_FORMAL_GATEWAY=true
.venv/bin/python -m app
```

使用本地 Ollama 时，不要只修改 Provider；必须同时设置模型和同一个端口：

```bash
export SECUREQUERY_PROVIDER=ollama
export SECUREQUERY_MODEL=qwen2.5-coder:7b
export SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11435
export SECUREQUERY_DEMO_MODE=true
export SECUREQUERY_LAB_GATEWAY=false
export SECUREQUERY_FORMAL_GATEWAY=true
.venv/bin/python -m app
```

启动 API 前先验证 Ollama，否则页面出现 `OLLAMA · DEGRADED` 和
`Local model is unavailable.` 是预期结果：

```bash
curl -fsS http://127.0.0.1:11435/api/tags
```

应用只绑定 `127.0.0.1:8000`，前端由同一个 FastAPI 服务提供，不需要单独启动 Node 或静态服务器。

浏览器打开：

```text
http://127.0.0.1:8000/
```

页面操作顺序：

1. 选择 `normal_grade` 或其他场景；
2. 点击“运行攻防对照”；
3. 查看 baseline/hardened 候选；
4. 有 hardened 候选时，前端只提交自然语言、身份和上下文到 `/api/v1/queries`；
5. 查看 C 的 `ALLOW/MASK/BLOCK`、原因、结果、RLS 空结果、截断信息和审计 ID。

## 7. 启动后验收

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsS http://127.0.0.1:8000/
curl -fsS http://127.0.0.1:8000/api/v1/demo/catalog
curl -fsS -X POST http://127.0.0.1:8000/api/v1/queries \
  -H 'Content-Type: application/json' \
  -d '{"question":"查询我的成绩","principal_id":"student_s01","context_profile":"clean"}'
```

正式网关的命令级回归：

```bash
.venv/bin/python -m pytest \
  tests/test_frontend_security.py tests/test_sql_policy.py \
  tests/test_real_gateway.py tests/test_audit_writer.py -q
.venv/bin/python -m pytest tests/db tests/attacks -q
.venv/bin/python -m compileall -q app db scripts tests
.venv/bin/ruff check \
  app/sql_policy.py app/real_gateway.py app/audit_writer.py \
  app/query_service.py app/main.py app/config.py \
  scripts/verify_ollama_gpu.py \
  tests/test_sql_policy.py tests/test_real_gateway.py tests/test_audit_writer.py
git diff --check
```

预期结果：

- C 回归为 `26 passed`；
- 数据库/攻击回归退出码为 0；其中既有无固定候选的评估契约可以跳过；
- 全套 `pytest -q` 在 Docker 已启动时应退出 0；Ollama 集成测试默认跳过，数据库评估契约中无固定候选项会跳过；
- Ruff 这里只检查 C 和本阶段改动文件；全仓历史 A 文件仍有已知格式问题，不能把全仓 Ruff 结果写成通过；
- 正常查询为 `executed + ALLOW`；
- `api.my_contact` 为 `executed + MASK`；
- `DELETE`、敏感列、多语句为 `blocked + BLOCK`；
- 跨学生查询由 RLS 返回 `executed + row_count=0`；
- 审计记录只保存决策、原因、角色和 `sql_digest`，不保存原始 SQL。

完整 C 结果不要重复抄写到本文，查看 [`c-gateway-verification.md`](c-gateway-verification.md)。

## 8. B 固定回放和模型评估

固定回放必须明确是 `lab_direct`，不算模型攻击结果：

```bash
export SECUREQUERY_LAB_GATEWAY=true
export SECUREQUERY_FORMAL_GATEWAY=false
.venv/bin/python -m pytest tests/test_query_lab.py -q
```

模型生成评估不执行 SQL：

```bash
.venv/bin/python scripts/evaluate.py \
  --provider mock --model qwen2.5-coder:7b
# Ollama 已可用时再改为 --provider ollama
```

评估 JSON 位于 `artifacts/experiments/`，应区分 provider error、模型拒答、候选 SQL 和网关实测，不把模型拒答率当成安全结论。

## 9. 停止和排障

停止 API：在 API 终端按 `Ctrl-C`。停止数据库但保留数据卷：

```bash
docker compose --profile lab stop
```

删除容器但保留卷：

```bash
docker compose --profile lab down
```

仅在明确要重建实验数据时才删除卷：

```bash
docker compose --profile lab down -v
.venv/bin/python scripts/init_db.py --all
```

常见问题：

- `SQ_*` 占位符错误：删除本地 `.env` 后重新运行 `scripts/init_db.py --all`，再补 `SECUREQUERY_*` 配置；
- Docker socket 无权限：启动 Docker Desktop 并确认 WSL Integration；
- API 返回 `503 unavailable`：检查 `SECUREQUERY_FORMAL_GATEWAY=true`、`requirements-database.lock` 和 hardened 容器；
- Ollama 超时：先用 Mock 验证网关，再降低模型规模或增加本地超时；不能把超时报告为安全通过；
- `ollama ps` 为 `100% CPU`：记录为 CPU fallback，按 [`gpu-inference.md`](gpu-inference.md) 排查；
- WSL 中出现 `*:Zone.Identifier`：这是 Windows ADS 垃圾文件，清理前先确认不是项目文件。

相关入口：

- [`acceptance-report.md`](acceptance-report.md)：完整启动、验收标准和当前结论；
- [`README.md`](README.md)：文档导航；
- [`feature-file-artifacts.md`](feature-file-artifacts.md)：功能、文件、测试和产物映射；
- [`integration.md`](integration.md)：A/B/C 接口契约。
