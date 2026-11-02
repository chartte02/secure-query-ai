# GPU 推理说明

## 1. 当前机器检查

2026-11-02 实测（Windows 原生环境）：

| 项目 | 结果 |
| --- | --- |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU |
| 显存 | 8188 MiB |
| 驱动 | 616.64 |
| Ollama | 0.23.2（Windows 原生版） |
| 模型 | `qwen2.5-coder:7b` |
| 推理 placement | `ollama ps` 显示 **100% GPU**，显存占用约 5.5 GB |
| 最小 READY 请求 | 4.7 秒（含 4.5 秒首次加载，eval 仅 ~25 ms） |

本机 GPU 推理已生效。此前记录的 `100% CPU` fallback 是 **WSL 内 Linux Ollama** 的 CUDA 库路径错乱（`/usr/local/lib/ollama/cuda_v12` 与 `/usr/lib/ollama` 布局不一致）所致；改用 Windows 原生 Ollama 后直接用上 GPU，与 WSL 安装无关。

## 2. 如何确认是否使用 GPU

在一个终端启动或保持 Ollama 服务，在另一个终端运行：

```bash
OLLAMA_HOST=127.0.0.1:11435 ollama run qwen2.5-coder:7b
```

推理期间另开终端检查：

```bash
OLLAMA_HOST=127.0.0.1:11435 ollama ps
nvidia-smi
```

仓库可重复采集证据：

```bash
.venv/bin/python scripts/verify_ollama_gpu.py --smoke \
  --host 127.0.0.1:11435 \
  --output artifacts/securequery-ollama-gpu-evidence.json
```

验收依据：

- `ollama ps` 的 `PROCESSOR` 应显示 `GPU` 或 CPU/GPU 混合，而不是 `100% CPU`；
- `nvidia-smi` 应能看到 Ollama 相关进程和显存占用；
- 同一问题重复运行时，响应延迟应明显低于 CPU 实测。

## 3. 项目连接配置

项目只通过本地 Ollama HTTP 接口调用模型，不需要在 Python 中安装 CUDA 或 PyTorch。确认 GPU 生效后，将 `.env` 设置为：

```text
SECUREQUERY_PROVIDER=ollama
SECUREQUERY_MODEL=qwen2.5-coder:7b
SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11435
SECUREQUERY_DEMO_MODE=true
```

若 Windows 脚本启动项目专用 Ollama，则使用脚本打印的专用端口，不能同时把服务地址写成另一个端口。

## 4. GPU 未生效时排查

1. 确认 `nvidia-smi` 能识别 GPU 和驱动。
2. 确认 Ollama 服务与当前终端使用的是同一个用户和同一个端口。
3. 停止旧模型进程后重新启动 Ollama，再重新加载模型。
4. 检查 `ollama ps`，不要只看 `nvidia-smi` 的瞬时 GPU 利用率。
5. 若仍为 CPU，记录 `ollama --version`、`ollama ps` 和 `nvidia-smi`，再处理驱动、Ollama 安装或 GPU 可用性问题。

GPU 加速只改变模型推理性能，不改变 SQL 网关、PostgreSQL 权限、脱敏和审计的安全边界。即使模型在 GPU 上运行，生成 SQL 仍必须经过 C 的独立网关。
