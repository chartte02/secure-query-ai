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
| 当前处理器 | 2026-11-02 冒烟期间连续 5 次显示 `100% CPU` |

因此本机硬件具备 GPU 推理条件，但当前 Ollama 仍没有使用 GPU；`nvidia-smi` 冒烟采样没有 Ollama compute 进程。模型已经拉取不代表模型已经在 GPU 上运行。

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
  --output /tmp/securequery-ollama-gpu-evidence.json
```

验收依据：

- `ollama ps` 的 `PROCESSOR` 应显示 `GPU` 或 CPU/GPU 混合，而不是 `100% CPU`；
- `nvidia-smi` 应能看到 Ollama 相关进程和显存占用；
- 同一问题重复运行时，响应延迟应明显低于当前 CPU 实测。

本次脚本结果：`gpu_verified=false`、`cpu_fallback=true`。当前模型评估不能标记为 GPU-backed。

## 3. 2026-11-02 前端前置部署诊断

本次先绕过前端和 FastAPI，直接在 WSL 启动临时 Ollama 11435，
只发送最小 `READY` 请求。

服务健康检查正常：

```bash
curl -i --max-time 10 http://127.0.0.1:11435/api/version
# HTTP 200，Ollama 0.24.0

curl --max-time 10 http://127.0.0.1:11435/api/tags
# qwen2.5-coder:7b 已安装，digest=dae161e27b0e...
```

但 runner 日志明确显示：

```text
inference compute id=cpu library=cpu
vram-based default context total_vram="0 B"
runner.vram="0 B"
```

最小请求结果：

```bash
/usr/bin/time -f 'elapsed=%E exit=%x' curl -sS --max-time 45 \
  http://127.0.0.1:11435/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-coder:7b","stream":false,
       "messages":[{"role":"user","content":"Return only the word READY."}],
       "options":{"temperature":0,"num_predict":16,"num_ctx":1024}}'
# HTTP 200，elapsed=0:24.38
# load_duration=9.91s，prompt_eval_duration=13.93s
```

因此 API 服务“可访问”不等于模型请求可在 10 秒内完成。当前 504 的直接
原因是 7B 模型在 CPU fallback 上运行，而不是前端路由或 SQL 网关。

另发现本机 Ollama 安装的动态库路径需要核对：

```bash
ldd /usr/local/lib/ollama/cuda_v12/libggml-cuda.so \
  | rg 'not found|ggml|cuda|cublas'
# 未补充路径时：libggml-base.so.0 => not found

find /usr/local /usr/lib -name 'libggml-base.so*' 2>/dev/null
# /usr/lib/ollama/libggml-base.so.0
```

即 `/usr/local/bin/ollama`、`/usr/local/lib/ollama/cuda_v12` 和
`/usr/lib/ollama` 不是同一安装布局。即使临时补充
`LD_LIBRARY_PATH=/usr/lib/ollama:...` 并显式设置
`OLLAMA_LLM_LIBRARY=cuda_v12`，runner 仍报告 `total_vram=0 B`；
这说明还需要修复 Ollama/WSL GPU 运行环境，不能只修改项目超时。

在以下条件满足前不要接入前端：

1. `ollama serve` 日志出现 CUDA 设备而非 `inference compute id=cpu`；
2. `ollama ps` 显示 `GPU` 或 CPU/GPU 混合；
3. `nvidia-smi` 能观察到 Ollama compute 进程和显存占用；
4. 最小 `READY` 请求和项目完整 Prompt 分别完成一次，记录耗时后再启动 API。

本次未通过上述门槛，因此没有重新启动前端进行 GPU 验收。仓库自身的
FastAPI 入口固定为 `127.0.0.1:8000`；日志中的 `127.0.0.1:8755`
不是本仓库配置的 API 端口，应先确认它是否属于旧服务或另一套前端后端。
WSL 中虽然存在 Windows Ollama 可执行文件，但当前互操作调用报
`UtilBindVsockAnyPort`，没有形成可验证的 Windows Ollama HTTP 服务；
不能把该文件存在当成 GPU 服务已接入。

## 4. 项目连接配置

项目只通过本地 Ollama HTTP 接口调用模型，不需要在 Python 中安装 CUDA 或 PyTorch。确认 GPU 生效后，将 `.env` 设置为：

```text
SECUREQUERY_PROVIDER=ollama
SECUREQUERY_MODEL=qwen2.5-coder:7b
SECUREQUERY_OLLAMA_BASE_URL=http://127.0.0.1:11435
SECUREQUERY_DEMO_MODE=true
```

如果 Windows 脚本启动项目专用 Ollama，则使用脚本打印的专用端口，不能同时把服务地址写成另一个端口。

## 5. GPU 未生效时排查

1. 确认 `nvidia-smi` 能识别 GPU 和驱动。
2. 确认 Ollama 服务与当前终端使用的是同一个用户和同一个端口。
3. 停止旧模型进程后重新启动 Ollama，再重新加载模型。
4. 检查 `ollama ps`，不要只看 `nvidia-smi` 的瞬时 GPU 利用率。
5. 若仍为 CPU，记录 `ollama --version`、`ollama ps` 和 `nvidia-smi`，再处理驱动、WSL GPU 透传或 Ollama 安装问题。

GPU 加速只改变模型推理性能，不改变 SQL 网关、PostgreSQL 权限、脱敏和审计的安全边界。即使模型在 GPU 上运行，生成 SQL 仍必须经过 C 的独立网关。
