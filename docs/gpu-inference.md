# GPU 推理说明

## 1. 当前机器检查

2026-11-02 实测：

| 项目 | 结果 |
| --- | --- |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU |
| 显存 | 8188 MiB |
| 驱动 | 616.64 |
| Ollama | 0.24.0 |
| 模型 | `qwen2.5-coder:7b` |
| 当前处理器 | `ollama ps` 显示 `100% CPU` |

因此本机硬件具备 GPU 推理条件，但本次检查时 Ollama 没有使用 GPU。模型已经拉取不代表模型已经在 GPU 上运行。

## 2. 如何确认是否使用 GPU

在一个终端启动或保持 Ollama 服务，在另一个终端运行：

```bash
ollama run qwen2.5-coder:7b
```

推理期间另开终端检查：

```bash
ollama ps
nvidia-smi
```

验收依据：

- `ollama ps` 的 `PROCESSOR` 应显示 `GPU` 或 CPU/GPU 混合，而不是 `100% CPU`；
- `nvidia-smi` 应能看到 Ollama 相关进程和显存占用；
- 同一问题重复运行时，响应延迟应明显低于当前 CPU 实测。

## 3. 项目连接配置

项目只通过本地 Ollama HTTP 接口调用模型，不需要在 Python 中安装 CUDA 或 PyTorch。确认 GPU 生效后，将 `.env` 设置为：

```text
SECUREQUERY_PROVIDER=ollama
SECUREQUERY_MODEL=qwen2.5-coder:7b
SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11434
SECUREQUERY_DEMO_MODE=true
```

如果 Windows 脚本启动项目专用 Ollama，则使用脚本打印的专用端口，不能同时把服务地址写成另一个端口。

## 4. GPU 未生效时排查

1. 确认 `nvidia-smi` 能识别 GPU 和驱动。
2. 确认 Ollama 服务与当前终端使用的是同一个用户和同一个端口。
3. 停止旧模型进程后重新启动 Ollama，再重新加载模型。
4. 检查 `ollama ps`，不要只看 `nvidia-smi` 的瞬时 GPU 利用率。
5. 若仍为 CPU，记录 `ollama --version`、`ollama ps` 和 `nvidia-smi`，再处理驱动、WSL GPU 透传或 Ollama 安装问题。

GPU 加速只改变模型推理性能，不改变 SQL 网关、PostgreSQL 权限、脱敏和审计的安全边界。即使模型在 GPU 上运行，生成 SQL 仍必须经过 C 的独立网关。
