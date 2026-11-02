# Windows 原生 GPU 推理环境验证记录（成员 B，给成员 C 的对照参考）

日期：2026-11-02。执行人：成员 B。目的：回应 [gpu-inference.md](gpu-inference.md) 记录的 GPU 阻塞（WSL Ollama `100% CPU`、WSL→Windows 互操作 `UtilBindVsockAnyPort` 失败），提供一条**已完整验证的替代路径**：不走 WSL，整个栈原生运行在 Windows 上。同型号 GPU、同一模型 digest，全部本记录实测。

## 1. 结论

**Windows 原生路径 GPU 推理可用且已通过全量实验验证**：CUDA 识别正常、模型驻留显存、720 次正式实验 + 180 次回放在此环境完成（23.9 分钟）。C 的 WSL 路线可以暂停——两台机器的差异不在 Ollama 版本，在**运行环境**：C 的 WSL Ollama runner 日志自报 `inference compute id=cpu library=cpu, total_vram="0 B"`（WSL 内该构建看不到 GPU），而 Windows 原生 Ollama 0.21.2 直接识别 CUDA（版本更旧反而有 GPU——升级不是关键，环境才是）。

## 2. 本机实测事实（与 C 的机器同型号 GPU）

| 项 | 值 | 验证方式 |
| --- | --- | --- |
| GPU | RTX 4060 Laptop 8GB（与 C 相同） | nvidia-smi |
| Ollama | **0.21.2**（Windows 原生，非 WSL） | `ollama --version` |
| CUDA 识别 | `inference compute library=CUDA compute=8.9`，可用 6.9 GiB | Ollama 服务日志 `discovering available GPUs` |
| 模型驻留 | `qwen2.5-coder:7b` digest `dae161e2…`（**与 C 文档记录的 digest 一致**），**4528 MiB 显存常驻** | `curl /api/ps` |
| 生成速度 | 53 tok/s；项目真实提示（512 token 上限）单次 1.6–11.9 s | /api/chat 实测 |
| 批量实测 | **720 次正式实验 23.9 分钟**（中位 ~1.7 s/次，P95 4.3 s） | e0e4-evaluation JSONL latency_ms |
| GPU 利用率 | 跑批期间连续采样 **38–47%**，显存 4.9 GB | nvidia-smi 5 秒采样 |

对照 C 的 CPU 数据：单条最小请求 34.7 s——速度差一个数量级以上，可作为"是否真的在 GPU 上"的行为级判据。

## 3. 踩过的三个坑（C 切换路径时会遇到）

1. **模型标签**：本地权重是 `qwen2.5-coder:latest`，项目配置只接受 `:7b`——`ollama cp qwen2.5-coder:latest qwen2.5-coder:7b` 打别名即可，零下载。
2. **format schema maxLength 崩溃**：Ollama 0.21.x llamarunner 遇 format 带 `maxLength` 直接崩溃（`model runner has unexpectedly stopped`）——已由 PR #5 修复合入 main（`app/providers.py` 剥离长度约束，pydantic 解析时仍强制）。
3. **端口**：`AppSettings.ollama_base_url` 默认 **11435**（非标准），标准安装是 **11434**——必须显式设置 `SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11434`，否则 ProviderUnavailable。**建议 C 注意**：你在 gpu-inference.md 的探测命令也用的 11435；如果你机器上的 Ollama 服务实际在 11434，冒烟结论可能受端口错位影响，值得先 `OLLAMA_HOST=127.0.0.1:11434 ollama ps` 复核一遍。

另：8755 端口疑问——本仓库 FastAPI 固定 8000（`python -m app` 实测），Ollama 标准为 11434；8755 不属于两者，可用 `netstat -ano | findstr 8755` 查占用进程确认来源。

## 4. C 的最小切换清单（WSL → Windows 原生）

1. 在 **Windows PowerShell**（非 WSL）重建 `.venv`：`python -m venv .venv; .venv\Scripts\python -m pip install -e ".[dev]"`；正式网关再加 `pip install -r requirements-database.lock`
2. 确认 Windows 侧 Ollama 服务在跑（`curl http://127.0.0.1:11434/api/version`），模型在列（`/api/tags`）
3. `.env` / 环境变量：`SECUREQUERY_PROVIDER=ollama`、`SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11434`
4. GPU 三件套验收（同 gpu-inference.md 的验收依据，本机全部通过）：`ollama ps` 显示显存驻留；`nvidia-smi` 可见 Ollama 进程与占用；同一请求延迟显著低于 CPU 实测
5. 已知非阻塞项：WSL 的 TestClient/AnyIO 挂起在 Windows + Python 3.12 **不复现**（member-b-verification.md §3）；共享 conftest 已修（PR #1）

## 5. 此路径已承载的验证（不只是冒烟）

- 全量测试 213→217 passed（PR #1/#5 各阶段）
- 正式网关 live：`/api/v1/queries` ALLOW + audit.events 落库（Windows 实测）
- **E0–E4 正式 720 次真实模型实验**（docs/experiment-results.md）+ E3 回放 180 次
- 长跑稳定性：720 次连续运行无 GPU 掉队、无 runner 崩溃（maxLength 修复后）

## 6. 证据边界

本记录只声称"Windows 原生环境 GPU 推理可用且已承载全部实验"，不声称 C 机器的问题已解决（WSL Ollama CPU-only 构建的诊断与处置仍归 C）；`gpu_verified=false` 的历史记录针对 C 的 WSL 环境，不以本记录推翻。
