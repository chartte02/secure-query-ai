# 本机部署记录与重启方式

> 历史部署快照：模型路径和启动命令已调整。当前使用方法以项目 README 与 `docs/usage-guide.md` 为准。

2026-10-26 下载，10 月 27 日完成模型评测和联调检查。本记录对应当前机器；其他机器仍需按 README 安装 Python、Ollama 并明确拉取模型。

## 已安装环境

- Python 3.12.10，项目独立虚拟环境 `.venv`。
- Ollama 0.40.11，当前用户安装于 `%LOCALAPPDATA%\Programs\Ollama`。
- 官方安装包：<https://github.com/ollama/ollama/releases/download/v0.40.11/OllamaSetup.exe>。
- 安装包 1,662,012,016 bytes，SHA256 与官方 Winget 清单一致：`87309d23b423abeae1d8df2f98df95f94bf35659debfdf3761d65b7b62a75508`；Authenticode 验证为 Valid，签名主体 Ollama Inc.。
- `qwen2.5-coder:7b` 和 `qwen2.5-coder:3b` 均已拉取并校验；详细 digest/量化/许可见实测报告及部署元数据。

## 本项目启动

从项目根目录执行：

```powershell
pwsh -File scripts/start_local.ps1
```

浏览器打开 <http://127.0.0.1:8000>。此命令选择 Ollama、7B 主模型并显式开启 Demo。脚本优先用安装的完整路径，不依赖当前终端的 PATH 刷新。

备用模型与无模型彩排：

```powershell
pwsh -File scripts/start_local.ps1 -Model qwen2.5-coder:3b
pwsh -File scripts/start_local.ps1 -Provider mock
```

启动前先结束占用 8000 端口的本项目旧进程。若 11434 已有 Ollama，脚本会复用它；已有服务保留原来的环境变量，切换服务配置需要先结束该服务再运行脚本。脚本不会自动拉取或更新模型。

本机忽略文件 `.env` 已明确设置 Ollama + 7B + Demo；`.env.example` 保留可离线使用的 Mock 示例。不要提交 `.env`、模型、安装包、运行日志或本机启动项备份。

## 本机环境冲突与处理

本机原有全局 `OLLAMA_MODELS` 指向不可写的 D 盘目录。未修改这一全局值；本项目启动脚本为新服务使用 `artifacts/runtime/models`。模型下载、服务和 API 启动均使用项目配置。

本次安装新增的 `Startup/Ollama.lnk` 会继承旧 D 盘配置而反复启动失败，已移动到 `artifacts/runtime/Ollama-autostart.lnk` 备份。需要恢复自动启动时，可将此快捷方式移回当前用户启动文件夹，并先修正其模型路径配置。本项目日常使用上述脚本启动，不依赖托盘自动启动。

新建的服务固定 `OLLAMA_HOST=127.0.0.1:11434`、`OLLAMA_NO_CLOUD=1`、`OLLAMA_NUM_PARALLEL=1`、`OLLAMA_MAX_LOADED_MODELS=1`、`OLLAMA_CONTEXT_LENGTH=4096`。这些只设置在启动进程中，不改系统级变量。

模型和日志位于忽略目录 `artifacts/runtime/`，合成实验结果位于 `artifacts/experiments/`。所有候选 SQL 都未执行；没有安装数据库驱动或数据库凭据。
