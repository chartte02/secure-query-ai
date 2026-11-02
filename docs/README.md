# 文档总索引

更新日期：2026-11-01。已合入成员 A 的 AI SQL 服务与成员 B 的数据库/权限基础；成员 B 已交付数据字典与攻击案例卡；成员 C 的 SQL 网关、统一执行入口与前端结果表待接入。
更新日期：2026-11-01。已合入成员 A 的 AI SQL 服务与成员 B 的数据库/权限基础；成员 B 已交付 S4 冻结评估样例集（60 条）；成员 C 的 SQL 网关、统一执行入口与前端结果表待接入。
更新日期：2026-11-01。当前进度与剩余工作以 [状态与交接](status.md) 为准；本文是文档索引。

## 按任务阅读

| 任务 | 入口 | 内容状态 |
| --- | --- | --- |
| 查看当前进度与剩余工作 | [状态与交接](status.md) | 唯一进度来源 |
| 启动环境、运行测试 | [根 README](../README.md) | 可执行操作说明 |
| 梳理 A 的 AI SQL 服务、接入 Docker、查看路由 | [成员 A 实施指南](member-a-ai-sql-server-guide.md) | 代码脉络、Docker 配置、查询编排与实验室回放 |
| A/C 接入数据库 | [数据库接入契约](database-contract.md) | 已实现接口和授权规则 |
| 查表结构、身份、预期行（A 对齐 v2 用） | [数据字典](data-dictionary.md) | 最终数据契约 v1；含三个待三人定的口径 |
| 三类攻击的前提与预期结果 | [攻击案例卡](attack-cases.md) | 威胁模型+案例卡；数据库层已实证，模型/网关层待接入 |
| 检查目前验证了什么 | [数据库验证记录](database-validation.md) | 71 项自动测试及固定 SQL 对照；不代表模型攻击结果 |
| S4 正式评估样例集（60 条冻结） | [evaluation.json](../tests/attacks/cases/evaluation.json) | 20 正常/10 跨用户/8 敏感/8 直接/8 间接/6 危险；预期行 hardened 实测，配套契约测试 |
| write_lab 一次性 DML 实验正式记录 | [write-lab-experiment.md](write-lab-experiment.md) | 写权限边界、实例隔离与重置可复现的固定 SQL 实测 |
| 了解课题应用背景 | [市场与应用调研](research/01-market-landscape.md) | 2026-10-26 的来源核查 |
| 找相近项目及源码 | [开源实现调研](research/02-open-source-implementations.md) | 固定提交、入口、许可与借鉴建议 |
| 组织安全案例 | [案例剖析](research/03-security-case-studies.md) | 原始证据、攻击前提和校园映射 |
| 安排后续开发和实验 | [项目细化计划](research/04-project-plan.md) | 研究与实施目标，部分尚待完成 |
| 查询原始方案和分工 | [总体设计](project-design.md)、[三人分工](team-division.md) | 原文件保留；内容不等于已实现功能 |
| 查看 A/B 分支合并与验证结果 | [成员 A/B 合并验证记录](member-ab-verification.md) | 2026-10-29 合并、分别验证与遗留问题 |

研究文档的详细目录和证据边界见 [research/README.md](research/README.md)，原始来源及源码文件摘要见 [source-inventory.json](research/source-inventory.json)。

## 当前实现入口

| 内容 | 文件或目录 |
| --- | --- |
| A 查询编排、网关协议、实验室回放 | [app/query_service.py](../app/query_service.py)、[app/gateway.py](../app/gateway.py)、[app/lab_gateway.py](../app/lab_gateway.py) |
| 身份、受限连接和上下文接口 | [db/client.py](../db/client.py) |
| 表结构和身份辅助函数 | [db/migrations](../db/migrations/) |
| 各实验环境的权限配置 | [db/profiles](../db/profiles/) |
| 合成数据生成与固定摘要 | [db/seed](../db/seed/) |
| 初始化、重置和证据采集 | [scripts](../scripts/) |
| 权限、攻击对照和正常参考样例 | [tests](../tests/) |

A 负责模型候选与真实上下文记录；B 维护数据库、权限和攻击数据；C 实现网关、执行编排及业务审计。接入以数据库契约为准，规划中的功能完成后再更新契约和实测记录。

## 共享资料与本地内容

- 共享：代码、SQL、测试、配置示例、本目录中的设计、调研、接入和验证文档。
- 本地：实际凭据 `.env`、虚拟环境 `.venv/`、自动生成证据 `artifacts/` 和工具缓存。
- B 的个人实施计划单独保留并由 Git 忽略；共享索引不依赖该文件。

正式实验报告应把审核后的结果整理到可共享文档，并引用运行记录。当前 `artifacts/database-evidence.json` 可由采集脚本重新生成，不能作为真实模型实验结果引用。
