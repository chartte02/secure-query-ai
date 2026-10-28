# 相近开源仓库与源码路径调研

核查日期：2026-10-26。下面是固定提交的静态阅读，不是部署测试或完整漏洞审计。具体文件的永久链接和 SHA-256 见 [source-inventory.json](source-inventory.json)。

## 1. 先决定借鉴什么

**最适合作为研究主线的是 P2SQL，最适合参考小型执行链路的是 LangChain／LlamaIndex，最接近中文完整应用的是 SQLBot／DB-GPT。** Vanna 和 WrenAI 适合研究用户上下文、语义层与工具执行边界；Supabase MCP 适合研究间接注入和连续工具调用。

建议自己实现小而清楚的实验链路；只读懂和借鉴必要部分。不要同时部署多个完整平台来比较谁“最安全”：不同配置、模型、权限和任务会使这种结论缺少可比性。

## 2. 仓库核查总表

| 仓库 | 本次提交 | 公开范围／许可快照 | 相关性与建议 |
| --- | --- | --- | --- |
| [rodrigo-pedro/P2SQL](https://github.com/rodrigo-pedro/P2SQL/tree/ff5a0226b6c63407ae19ba5567ae251b51d4f98e) | `ff5a0226b6c6` | 根许可 MIT；含研究实验与第三方应用副本，引用副本需保留各自说明 | **最高优先级**：直接对应攻防研究题材 |
| [langchain-experimental](https://github.com/langchain-ai/langchain-experimental/tree/f10d5c3247fb102d4d45d29a35a0266760288542) | `f10d5c3247fb` | MIT；含 SQLDatabaseChain | 分析历史案例与单链执行位置，不要求采用整套框架 |
| [langchain-community](https://github.com/langchain-ai/langchain-community/tree/f425a3ed1933173fb3694b81359d1519c4f82d36) | `f425a3ed1933` | MIT；SQLDatabase、SQL 工具等源码 | 查清 Schema、样例行与 SQL 执行的实际关系 |
| [run-llama/llama_index](https://github.com/run-llama/llama_index/tree/619d74664e8404612038bc15a1a40c686037277c) | `619d74664e84` | MIT；框架及 SQL 组件可读 | 清楚区分检索、SQL 生成、执行、答案综合 |
| [vanna-ai/vanna](https://github.com/vanna-ai/vanna/tree/365d0617c1a4567ffee1b19b40c27feb4206bfcf) | `365d0617c1a4` | MIT；主线 2.0 和 legacy | 对比工具访问权与数据库行权限，注意版本差异 |
| [dataease/SQLBot](https://github.com/dataease/SQLBot/tree/8520213f91b2599b90888e8407d5ebdd84bc38af) | `8520213f91b2` | 修改版 GPLv3，含标识等附加条款；部分依赖实现不在主仓中 | 中文应用的首选架构参考，不直接认定可完整审计 |
| [eosphoros-ai/DB-GPT](https://github.com/eosphoros-ai/DB-GPT/tree/06a46eea2d248a0f2b3e9096035424df4f2dc2eb) | `06a46eea2d24` | MIT；Python 平台与应用代码 | 数据库摘要和自动执行路径值得读，全平台偏重 |
| [Canner/WrenAI](https://github.com/Canner/WrenAI/tree/86fcca2d26cb20bcca9c09aa59a97286290abd3f) | `86fcca2d26cb` | 当前 core/sdk/skills 等 Apache-2.0，docs 为 CC-BY-4.0；按路径看许可 | 语义模型与确定性 SQL 策略的参考 |
| [supabase/mcp](https://github.com/supabase/mcp/tree/8aca22cee8aa32815134dd9eca2d6e4c180ec352) | `8aca22cee8aa` | Apache-2.0；MCP 工具与平台适配源码 | 工具结果如何返回模型、只读配置如何传递 |
| [Dataherald/dataherald](https://github.com/Dataherald/dataherald/tree/f8946182e6db55522b88cd5a831c788339b8fc42) | `f8946182e6db` | 根及 engine 许可 Apache-2.0；服务边界另核查 | 企业问答 API 和相关表检索；本次主线提交日期为 2024-07-11 |
| [Chat2DB/Chat2DB](https://github.com/Chat2DB/Chat2DB/tree/53f4174335ba2a247032314cac21006dc3ae42a4) | `53f4174335ba` | 当前 5.3.0 起为修改版 Apache 条款／源码可用；历史版本不同 | SQL 客户端与 AI 工具的对照，不作为最小实现基础 |

提交日期不是发布日期；本次未用 GitHub 星数排序，也未将“最后提交较早”推导为仓库已归档。完整 SHA、提交时间和许可证文件链接在机器可读清单中。

## 3. P2SQL：最接近本项目的已有研究

固定源码入口：

- [研究仓库 README](https://github.com/rodrigo-pedro/P2SQL/blob/ff5a0226b6c63407ae19ba5567ae251b51d4f98e/README.md)：按 RQ1—RQ4 组织攻击、模型实验、红队和防御。
- [数据库问答 Chain 后端](https://github.com/rodrigo-pedro/P2SQL/blob/ff5a0226b6c63407ae19ba5567ae251b51d4f98e/RQ1/code/app-backend-chain/app_backend.py)：PostgreSQL、Schema 样例、系统约束和 SQLDatabaseChain 的组合。
- [间接注入 RI1](https://github.com/rodrigo-pedro/P2SQL/blob/ff5a0226b6c63407ae19ba5567ae251b51d4f98e/RQ1/prompts/RI1.md)：查询结果中的文本影响最终回答。
- [间接注入 RI2](https://github.com/rodrigo-pedro/P2SQL/blob/ff5a0226b6c63407ae19ba5567ae251b51d4f98e/RQ1/prompts/RI2.md)：工具返回内容诱发后续查询。
- [SQL 类型检查](https://github.com/rodrigo-pedro/P2SQL/blob/ff5a0226b6c63407ae19ba5567ae251b51d4f98e/RQ4/langshield-langchain/langshield/sql_query_checker.py)和[查询重写](https://github.com/rodrigo-pedro/P2SQL/blob/ff5a0226b6c63407ae19ba5567ae251b51d4f98e/RQ4/langshield-langchain/langshield/sql_query_rewriter.py)：可读的非提示词控制示例。

适合借鉴：分清攻击入口和后果；保留失败尝试；把攻击和正常样例一起评价；将权限约束放在模型输出之后。论文和仓库标题并不完全相同，引用时分别写原题目及版本。

不能直接照搬：旧依赖、历史云模型、示例特权连接、类型枚举式拦截及任意 SQL 重写。其代码是研究工件，不应未经测试便当作现代 PostgreSQL 安全网关。我们可以贡献中文校园场景、Ollama 固定模型、数据库权限对照及可追溯实验；不能声称首次发现这类风险。

## 4. LangChain：单链与工具代理要区分

### 4.1 单链执行

`langchain_experimental/sql/base.py` 中 `_call()` 先获取表信息，再调用模型，随后可调用 `database.run()`，最后可把结果交给模型组织答案。`return_sql` 可只生成；`use_query_checker` 是模型参与的查询检查，不等同于用户授权验证。

源码：[SQLDatabaseChain](https://github.com/langchain-ai/langchain-experimental/blob/f10d5c3247fb102d4d45d29a35a0266760288542/libs/experimental/langchain_experimental/sql/base.py)。

### 4.2 Schema 不一定只有结构

本次 `SQLDatabase` 构造参数的 `sample_rows_in_table_info` 默认值为 3；`get_table_info()` 可附加样例行，当前 `_get_sample_rows()` 对各值有截断处理。这证明数据库内容可能在第一次生成 SQL 之前进入上下文。是否启用、选中了哪些表、恶意内容是否被截断，均需记录。

`include_tables` 影响这层包装器看到的表信息，不是底层数据库授权替代品。执行器使用其连接持有的实际权限。

源码：[SQLDatabase](https://github.com/langchain-ai/langchain-community/blob/f425a3ed1933173fb3694b81359d1519c4f82d36/libs/community/langchain_community/utilities/sql_database.py)。

### 4.3 代理执行

`SQLDatabaseToolkit` 暴露列表、Schema、查询和检查工具；`QuerySQLDatabaseTool` 最终委托数据库包装器执行。每一次工具调用都可能成为新的数据库访问，因此网关应位于统一执行入口。

源码：[toolkit.py](https://github.com/langchain-ai/langchain-community/blob/f425a3ed1933173fb3694b81359d1519c4f82d36/libs/community/langchain_community/agent_toolkits/sql/toolkit.py)、[tool.py](https://github.com/langchain-ai/langchain-community/blob/f425a3ed1933173fb3694b81359d1519c4f82d36/libs/community/langchain_community/tools/sql_database/tool.py)。

本项目优先采用单链，显式增加一条可追踪的公开反馈上下文入口。多轮工具调用留作扩展，不需要为复现风险引入复杂代理平台。

## 5. LlamaIndex：把 SQL 生成与执行拆开

源码入口：[sql_retriever.py](https://github.com/run-llama/llama_index/blob/619d74664e8404612038bc15a1a40c686037277c/llama-index-core/llama_index/core/indices/struct_store/sql_retriever.py)、[sql_query.py](https://github.com/run-llama/llama_index/blob/619d74664e8404612038bc15a1a40c686037277c/llama-index-core/llama_index/core/indices/struct_store/sql_query.py)、[sql_wrapper.py](https://github.com/run-llama/llama_index/blob/619d74664e8404612038bc15a1a40c686037277c/llama-index-core/llama_index/core/utilities/sql_wrapper.py)。

`NLSQLRetriever` 构造相关表上下文并生成 SQL；`sql_only` 可停止在 SQL 输出；常规路径交给 `SQLRetriever`，再到 `SQLDatabase.run_sql()`。上层查询引擎可综合结果为答案。源码有明确的任意 SQL 执行风险提示。

借鉴点是阶段分离：B 能提供上下文和数据，A 只生成候选，C 统一决定能否执行。生成正确性、数据库执行成功和答案正确性应独立记录。

当前 README 的公司产品重点已演进到文档处理，但 SQL 组件仍在所查代码中；不能把框架组件存在写成其所有商业产品都以 SQL 问数为核心。

## 6. Vanna：重点核查“用户感知”落到哪里

主线 2.0 中，用户进入工具上下文，工具注册表检查分组访问，SQL 工具调用 runner。其 PostgreSQL runner 使用配置的连接执行 SQL；该文件中没有自动把应用用户映射为 PostgreSQL 用户或注入行权限的逻辑。

更关键的是：`ToolRegistry.transform_args()` 提供基于用户修改参数的扩展点，默认实现不修改参数。因此“支持自定义行权限”与“默认 runner 已实施逐用户行权限”不能混写。这是静态观察，不能据此断言所有 Vanna 部署可被越权。

固定源码：[registry.py](https://github.com/vanna-ai/vanna/blob/365d0617c1a4567ffee1b19b40c27feb4206bfcf/src/vanna/core/registry.py)、[run_sql.py](https://github.com/vanna-ai/vanna/blob/365d0617c1a4567ffee1b19b40c27feb4206bfcf/src/vanna/tools/run_sql.py)、[PostgresRunner](https://github.com/vanna-ai/vanna/blob/365d0617c1a4567ffee1b19b40c27feb4206bfcf/src/vanna/integrations/postgres/sql_runner.py)。

旧模式在 [legacy/base/base.py](https://github.com/vanna-ai/vanna/blob/365d0617c1a4567ffee1b19b40c27feb4206bfcf/src/vanna/legacy/base/base.py)：检索相关 DDL、说明和问答 SQL；`allow_llm_to_see_data` 控制一条中间查询回流路径。该参数不能阻止所有其他结果回流或输出路径，尤其不能概括主线 2.0 的行为。

建议借鉴用户上下文与 runner 分离；不要复制整套工具平台。历史可视化代码执行漏洞另见[案例调研](03-security-case-studies.md)，不可外推到当前 2.0。

## 7. SQLBot：最贴近中文应用，但公开范围要逐层核查

在 [llm.py](https://github.com/dataease/SQLBot/blob/8520213f91b2599b90888e8407d5ebdd84bc38af/backend/apps/chat/task/llm.py) 可看到选表、SQL 生成、权限过滤生成、图表和执行等阶段；[table_embedding.py](https://github.com/dataease/SQLBot/blob/8520213f91b2599b90888e8407d5ebdd84bc38af/backend/apps/datasource/embedding/table_embedding.py) 提供相关表的检索逻辑。

[db.py](https://github.com/dataease/SQLBot/blob/8520213f91b2599b90888e8407d5ebdd84bc38af/backend/apps/db/db.py) 的 `exec_sql()` 在执行前调用只读查询检查。因此不能只看到模型参与过滤就认定产品完全依赖提示词。

但 [permission.py](https://github.com/dataease/SQLBot/blob/8520213f91b2599b90888e8407d5ebdd84bc38af/backend/apps/datasource/crud/permission.py) 导入 `sqlbot_xpack`；所查主仓文件树未包含这个包的实现。主仓能看到权限调用和部分处理，尚不足以证明完整权限链可独立审阅。需另核查实际安装包、版本和分发范围。

对我们有价值的研究问题是：自然语言、检索、权限过滤与确定性执行检查分别发生在哪里。未部署和验证前，不声称 SQLBot 有可利用漏洞。许可见[固定 LICENSE](https://github.com/dataease/SQLBot/blob/8520213f91b2599b90888e8407d5ebdd84bc38af/LICENSE)。

## 8. DB-GPT：关注自动执行场景即可

[auto_execute/chat.py](https://github.com/eosphoros-ai/DB-GPT/blob/06a46eea2d248a0f2b3e9096035424df4f2dc2eb/packages/dbgpt-app/src/dbgpt_app/scene/chat_db/auto_execute/chat.py) 获取数据库摘要和方言，并向动作阶段提供 `run_to_df`；[out_parser.py](https://github.com/eosphoros-ai/DB-GPT/blob/06a46eea2d248a0f2b3e9096035424df4f2dc2eb/packages/dbgpt-app/src/dbgpt_app/scene/chat_db/auto_execute/out_parser.py) 解析模型输出并调用执行函数。

底层连接在 [rdbms/base.py](https://github.com/eosphoros-ai/DB-GPT/blob/06a46eea2d248a0f2b3e9096035424df4f2dc2eb/packages/dbgpt-core/src/dbgpt/datasource/rdbms/base.py)。仅凭这条路径不能判定平台其他模块没有权限保护；它足以说明本项目应在解析结果与连接调用之间设置统一控制点。

借鉴数据库摘要、方言信息和可观测动作；不纳入其更大的工作流、代码执行和多代理系统。根许可为 MIT。

## 9. WrenAI：当前主线的语义规划与策略边界

当前 [mcp_server.py](https://github.com/Canner/WrenAI/blob/86fcca2d26cb20bcca9c09aa59a97286290abd3f/core/wren/src/wren/mcp_server.py) 暴露 Schema／MDL、上下文、已存查询、规划和查询等工具；[ask.py](https://github.com/Canner/WrenAI/blob/86fcca2d26cb20bcca9c09aa59a97286290abd3f/core/wren/src/wren/ask.py) 是提示模板渲染入口，不能把它单独画成内部 LLM 执行器。

[engine.py](https://github.com/Canner/WrenAI/blob/86fcca2d26cb20bcca9c09aa59a97286290abd3f/core/wren/src/wren/engine.py) 在规划中调用策略并检查规划结果；[policy.py](https://github.com/Canner/WrenAI/blob/86fcca2d26cb20bcca9c09aa59a97286290abd3f/core/wren/src/wren/policy.py) 区分只读语句限制和 strict 模式下的模型／函数限制；[config.py](https://github.com/Canner/WrenAI/blob/86fcca2d26cb20bcca9c09aa59a97286290abd3f/core/wren/src/wren/config.py) 中 strict 模式默认关闭。

值得借鉴：输入 SQL 与规划后 SQL 都可能需要检查；元数据白名单和函数能力是不同维度；语义层不等于提示词。上述是所查路径的行为，不构成“产品绝对安全”的证明。[许可映射](https://github.com/Canner/WrenAI/blob/86fcca2d26cb20bcca9c09aa59a97286290abd3f/LICENSE)按目录规定，应避免仅因根目录包含 AGPL 文本就认定当前全部代码为 AGPL。

## 10. Supabase MCP：模型在客户端，工具执行在服务端

[database-operation-tools.ts](https://github.com/supabase/mcp/blob/8aca22cee8aa32815134dd9eca2d6e4c180ec352/packages/mcp-server-supabase/src/tools/database-operation-tools.ts) 定义原始 SQL 工具、只读参数和特定配置下的破坏性操作确认，并把结果放在不可信数据边界中返回；[api-platform.ts](https://github.com/supabase/mcp/blob/8aca22cee8aa32815134dd9eca2d6e4c180ec352/packages/mcp-server-supabase/src/platform/api-platform.ts) 展示平台 API 适配。

所查源码能够证明参数传递与工具结果包装，不能独立证明托管后端全部实现。`readOnlyHint` 是工具描述元数据；实际只读还要看执行参数和数据库角色，不能把 hint 当作数据库授权。

2025 年公开研究演示和当前含确认逻辑的代码不是同一个版本。我们只复现信任边界失守的机制；不据旧演示宣称当前服务可被同样利用。

## 11. Dataherald 与 Chat2DB：补充对照

Dataherald 的 [SQL agent](https://github.com/Dataherald/dataherald/blob/f8946182e6db55522b88cd5a831c788339b8fc42/services/engine/dataherald/sql_generator/dataherald_sqlagent.py) 包含相关表、Schema、查询和用户说明工具；[数据库包装器](https://github.com/Dataherald/dataherald/blob/f8946182e6db55522b88cd5a831c788339b8fc42/services/engine/dataherald/sql_database/base.py)承接数据库操作。README 区分 engine、enterprise、admin-console 等服务，不能把 engine 自身当作整套身份系统。它适合作为历史研究与架构参考，依赖能否在当前环境直接运行尚未验证。

Chat2DB 的 [AiToolServiceImpl](https://github.com/Chat2DB/Chat2DB/blob/53f4174335ba2a247032314cac21006dc3ae42a4/chat2db-community-server/chat2db-community-domain/chat2db-community-domain-core/src/main/java/ai/chat2db/community/domain/core/impl/ai/AiToolServiceImpl.java) 提供元数据和 AI 工具服务，并出现连接范围、自动执行策略等控制；[SECURITY.md](https://github.com/Chat2DB/Chat2DB/blob/53f4174335ba2a247032314cac21006dc3ae42a4/SECURITY.md)说明部署信任边界。根 [LICENSE](https://github.com/Chat2DB/Chat2DB/blob/53f4174335ba2a247032314cac21006dc3ae42a4/LICENSE) 明确当前许可与历史版本的差异。本文仅作事实性许可记录，代码复用时仍应按实际选定文件核查。

## 12. 给 A/B/C 的具体取舍

| 成员 | 优先读 | 可复用的思想 | 本轮不承担 |
| --- | --- | --- | --- |
| A | P2SQL 单链、LangChain Schema、LlamaIndex SQL-only | 上下文显式组装、候选生成与执行分离 | 多平台适配、模型微调、通用代理 |
| B | P2SQL 攻击目录、Supabase 原始案例、Vanna runner | 攻击前提、权限差异、证据与版本固定 | 把未验证产品描述为漏洞对象 |
| C | Wren policy、P2SQL checker/rewriter、SQLBot 执行入口 | 统一执行控制、语法解析、受支持子集、审计 | 证明任意 SQL 安全、照搬旧重写器 |

如果后续复制代码，记录原仓库、固定提交、原始文件、修改内容和许可证。只借鉴思路时也应在报告相关部分注明来源。
