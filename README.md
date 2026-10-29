# SecureQuery AI：数据库安全课程实验

目前已实现成员 B 的数据库与权限基础：Docker PostgreSQL、合成教务数据、逐主体行权限、敏感列保护、受限脱敏视图、反馈上下文、初始化／重置和数据库回归测试。

模型服务、SQL 网关和前端尚未实现。固定 SQL 测试用于验证数据库控制，不代表大模型已被成功攻击。

## 目录与阅读入口

```text
secure-query-ai/
├── README.md                 # 启动、测试和协作入口
├── AGENTS.md                 # 仓库开发要求
├── compose.yaml              # 三个独立 PostgreSQL 实例
├── pyproject.toml            # Python 依赖范围与工具配置
├── requirements-dev.lock     # 已验证的开发依赖快照
├── db/
│   ├── client.py             # A/C 使用的身份、连接、上下文和反馈接口
│   ├── settings.py           # 本地配置与固定实验目标
│   ├── manage.py             # 建库、重置和安装标识检查
│   ├── migrations/           # 表结构与身份辅助函数
│   ├── profiles/             # 加固、宽读取和写操作权限配置
│   ├── seed/                 # 确定性数据生成与冻结摘要
│   └── fixtures/             # 干净／污染反馈的配对说明
├── scripts/                  # 初始化、重置、验证和证据采集命令
├── tests/
│   ├── db/                   # 数据库与权限回归
│   └── attacks/              # 固定 SQL 对照和开发样例
└── docs/
    ├── README.md             # 文档总索引与当前进展
    ├── database-contract.md  # A/C 接入契约
    ├── database-validation.md # 数据库实测记录
    └── research/             # 共享调研、案例与项目规划
```

首次了解项目看[文档总索引](docs/README.md)，接入开发看[数据库契约](docs/database-contract.md)。原总体设计和分工保留在 `docs/`，用于与当前实现对照。

`.env`、`.venv/`、`artifacts/` 和工具缓存是本地运行内容，由 Git 忽略。`docs/research/` 中仅 B 的个人 `05` 计划被忽略，其余调研可提交和分享。

## 本地启动（Windows PowerShell）

需要 Docker Desktop（Linux containers）和 Python 3.11+。从仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe scripts/init_db.py --all
.\.venv\Scripts\python.exe -m pytest -q
```

初始化自动创建含随机凭据的 `.env`；不要直接复制 `.env.example` 的占位密码。三个实例只向本机绑定端口，镜像已固定 digest。`--all` 启动独立基线和写操作实验库；仅初始化默认加固环境可省略 `--all`，此时运行 `tests/db`。

| 环境 | 本机端口 | 用途 |
| --- | --- | --- |
| hardened | 55432 | 默认；学生本人／教师所授教学班；禁止原始敏感字段 |
| baseline | 55433 | 故意宽读取的隔离对照 |
| write_lab | 55434 | 一次性成绩 DML 实验，不授予业务表 DROP 权限 |

## 常用操作

```powershell
.\.venv\Scripts\python.exe scripts/verify_db_permissions.py
.\.venv\Scripts\python.exe -m pytest tests/attacks -q
.\.venv\Scripts\python.exe scripts/reset_db.py
.\.venv\Scripts\python.exe scripts/reset_db.py --profile baseline --fixture poisoned-01
.\.venv\Scripts\python.exe scripts/reset_db.py --profile baseline --fixture clean
.\.venv\Scripts\python.exe scripts/collect_experiment_evidence.py
.\.venv\Scripts\python.exe -m ruff check db scripts tests
.\.venv\Scripts\python.exe -m ruff format --check db scripts tests
docker compose --profile lab stop
```

重置仅接受固定实验目标并核查本地安装标识；会清除该目标的反馈和实验改动，保留角色后重新构建合成 fixture。测试中的写操作只作用于专用副本并恢复种子；运行全套测试前，应保持各环境为 clean 状态且无并发实验。

## 协作入口

- [文档总索引](docs/README.md)：按研究背景、原始设计、当前接口和验证记录导航。
- [给 A/C 的数据库接入契约](docs/database-contract.md)：表、权限、接口、正常任务及实验配置。
- [数据库已验证行为](docs/database-validation.md)：测试范围与验证边界。
- [共享调研](docs/research/README.md)：市场、仓库、公开案例和项目计划。
- [最初总体设计](docs/project-design.md)与[三人分工](docs/team-division.md)保持原样，部分内容是尚未实现的后续目标。

所有数据均为合成。应用层必须在使用数据库查询连接前执行独立 SQL 网关检查；本模块不提供绕过网关的模型执行接口。凭据、虚拟环境和生成证据存放在 Git 忽略路径中，B 的个人实施计划仍单独忽略。
