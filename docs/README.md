# 文档导航

更新日期：2026-11-02。当前阶段是 **A/B 已完成、C 的正式 SQL 网关尚未完成**。文档中的“已实现”以代码和实测为准；设计文档、历史记录和固定 SQL 回放不能替代端到端模型安全证据。

## 快速入口

| 目的 | 文档 |
| --- | --- |
| 先了解项目当前状态 | [status.md](status.md) |
| 按命令启动和验收 | [acceptance-report.md](acceptance-report.md) |
| 查找功能对应的代码、测试和产物 | [feature-file-artifacts.md](feature-file-artifacts.md) |
| 了解总体架构 | [project-design.md](project-design.md) |
| 查看三人分工 | [team-division.md](team-division.md) |
| 查看本次 A/B/C 验证结果 | [member-ab-verification.md](member-ab-verification.md)、[acceptance-report.md](acceptance-report.md) |
| 在 WSL 中启动和排障 | [wsl-guide.md](wsl-guide.md) |

## 按成员查找

### 成员 A：AI SQL 服务

| 内容 | 文档 |
| --- | --- |
| 服务使用、接口和启动 | [usage-guide.md](usage-guide.md)、[member-a-ai-sql-server-guide.md](member-a-ai-sql-server-guide.md) |
| Ollama/Mock 模型评估 | [local-model-evaluation.md](local-model-evaluation.md) |
| GPU 推理检查与排障 | [gpu-inference.md](gpu-inference.md) |

### 成员 B：数据库与攻击实验

| 内容 | 文档 |
| --- | --- |
| 数据库字段、身份和预期行 | [data-dictionary.md](data-dictionary.md) |
| A/B 接入字段和权限契约 | [database-contract.md](database-contract.md) |
| 权限验证结果 | [database-validation.md](database-validation.md) |
| 三类攻击的前提和影响 | [attack-cases.md](attack-cases.md) |
| 一次性写权限实验 | [write-lab-experiment.md](write-lab-experiment.md) |

### 成员 C：安全网关与 Pre

| 内容 | 文档 |
| --- | --- |
| A/B 交接和 C 的接口边界 | [team-bc-handoff.md](team-bc-handoff.md)、[integration.md](integration.md) |
| C 当前验收和剩余工作 | [status.md](status.md)、[acceptance-report.md](acceptance-report.md) |
| 三人协作、Pre 工作量和交付物 | [team-division.md](team-division.md) |

## 按研究内容查找

| 研究内容 | 文档 |
| --- | --- |
| 应用背景与市场场景 | [research/01-market-landscape.md](research/01-market-landscape.md) |
| 相近开源实现 | [research/02-open-source-implementations.md](research/02-open-source-implementations.md) |
| 真实/典型安全案例 | [research/03-security-case-studies.md](research/03-security-case-studies.md) |
| 项目实施与实验计划 | [research/04-project-plan.md](research/04-project-plan.md) |
| 研究目录和来源清单 | [research/README.md](research/README.md)、[research/source-inventory.json](research/source-inventory.json) |

## 环境与历史资料

- [wsl-guide.md](wsl-guide.md)：WSL 环境、Docker、Ollama、端口和常见故障的启动记录；
- [archive/](archive/)：阶段性旧方案和成员个人记录，只用于追溯，不作为当前实现状态；
- [member-ab-verification.md](member-ab-verification.md)：A/B 合并后的历史验证记录，当前实测以 [acceptance-report.md](acceptance-report.md) 为准。

## 代码与产物索引

完整的“功能 → 文件 → 测试 → 产物”映射见 [feature-file-artifacts.md](feature-file-artifacts.md)。

主要代码入口：

- `app/`：FastAPI、Prompt、Mock/Ollama、查询编排、网关协议和实验室回放；
- `db/`：PostgreSQL 迁移、角色、RLS、种子数据和受限连接；
- `frontend/`：候选 SQL 对照页面；
- `scripts/`：初始化、重置、权限验证、固定证据采集和模型评估；
- `tests/`：API、模型、前端安全、数据库权限和攻击回归；
- `artifacts/`：人工核对实验记录和可重新生成的本地证据。

## 证据边界

- `artifacts/database-evidence.json` 是固定 SQL 回放证据，不是模型攻击结果；
- `artifacts/experiments/` 中的 Mock/Ollama 文件是生成评估记录，必须查看 `provider`、`model_invoked`、`semantic_review` 和完成状态；
- `lab_direct` 是 B 的实验室直连执行器，不是 C 的正式 SQL 网关；
- C 完成前，正式 `/api/v1/queries` 默认应返回 `503 unavailable`，不得伪造查询结果。
