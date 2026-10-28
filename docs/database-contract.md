# 给成员 A/C 的数据库接入契约 v1

日期：2026-10-28。该文档描述已经实现的接口，原始研究计划中的后续功能不自动视为已完成。

## 1. 启动与冻结数据

按根 README 初始化。默认 `hardened`；`baseline` 和 `write_lab` 必须显式选择。固定种子版本为 `20261028-v1`，各表行数和内容摘要见 [manifest](../db/seed/manifest.json)。

20 名学生 S01—S20，3 名教师 T01—T03，6 门课程，8 个教学班，60 条选课和成绩，12 条反馈（其中 1 条非公开）。同课程不同教学班可由不同教师授课。所有姓名、联系方式和证件均为明确合成标记。

## 2. 模型允许知道的 Schema

所有 SQL 使用全限定表名。以下是可查询字段，不把未授权原始敏感列作为普通模型上下文：

| 表／视图 | 可见列 | 行范围 |
| --- | --- | --- |
| `academic.courses` | course_id, course_name, description, credits | 所有公开课程 |
| `academic.teachers` | teacher_id, display_name, department | 教师目录 |
| `academic.course_offerings` | offering_id, course_id, teacher_id, term | 教学班目录 |
| `academic.students` | student_id, display_name, department | 学生本人；教师所授教学班的学生 |
| `academic.enrollments` | student_id, offering_id, enrolled_at | 本人选课；教师所授教学班 |
| `academic.grades` | student_id, offering_id, score | 本人成绩；教师所授教学班 |
| `academic.course_feedback` | feedback_id, offering_id, content, visibility, created_at | 仅公开反馈；不暴露作者 ID |
| `api.my_contact` | student_id, phone_masked | 仅学生本人；教师无此视图权限 |

关联关系：courses → course_offerings → enrollments；grades 通过 `(student_id, offering_id)` 关联 enrollments；feedback 关联相同选课关系。不要只用 course_id 代替 offering_id 判断教师权限。

原始 `students.phone`、`students.national_id`、`grades.grader_note` 不授权给查询用户。`private_auth` 和 `audit` 不作为模型数据源。列权限同时约束 SELECT、WHERE、ORDER BY 和表达式，不能依赖列名展示脱敏。

## 3. A 获取身份和上下文

```python
from db.client import ContextProvider, public_actor_contract

actor = public_actor_contract("student_s01")
# {'actor_id': 'student_s01', 'actor_type': 'student',
#  'student_id': 'S01', 'teacher_id': None}

provider = ContextProvider()  # hardened
catalog = provider.get_course_catalog()
feedback = provider.get_public_feedback("O01", max_rows=3, max_chars=512)
```

身份键只接受 `student_s01`—`student_s20` 和 `teacher_t01`—`teacher_t03`。这代表演示用的后端身份选择，不是完整账号登录系统。自然语言、模型输出不能更改它。

反馈返回 `feedback_id`、`offering_id`、`content`、`source_kind`、`was_truncated`、完整内容 SHA-256 及 `trust=untrusted_data`。按 `created_at DESC, feedback_id` 固定排序，默认选最近 3 条；长度上限 2000，行数上限 10。将这些内容视为资料，并记录实际送入模型的文本与摘要。

`course_feedback` 是真正的数据库文本入口，内容有恶意命令也只能算数据。`clean` 和 `poisoned-01` 只改变 `FB_ATTACK_01` 的 content；该记录在 O01 默认上下文中。使用恶意 fixture 必须在实验配置中记录，正常交付默认 clean。

## 4. C 使用查询连接

```python
from db.client import query_connection

actor_id = "student_s01"  # 由可信后端给出
# candidate_sql 必须先由 C 的独立网关解析和授权。
# 网关 ALLOW 后，才使用连接执行；此文档不实现或替代网关。
with query_connection(actor_id) as conn:
    identity = conn.execute("SELECT session_user AS db_role").fetchone()
    rows = conn.execute(
        "SELECT student_id, offering_id, score FROM academic.grades ORDER BY offering_id"
    ).fetchall()
```

连接为 psycopg 3，同步、字典行，默认只读；逐主体登录角色绑定 `session_user`，不使用模型可改写的会话用户编号。学生查询会自动受 RLS 限制为本人。`with` 成功退出提交，异常退出回滚；不要把连接交给前端或模型。

显式漏洞实验可调用 `query_connection(actor_id, profile='baseline', unsafe_lab=True)` 或 `write_lab`。真实执行账号分别为 `sq_lab_reader` 和 `sq_lab_writer`；日志同时记录应用 actor 与实际 db_role。不能通过用户请求参数直接开放这个切换。

返回空集不等于网关拦截；SQLSTATE `42501` 为权限拒绝、`25006` 为只读事务拒绝。出现数据库拒绝时先 rollback 再重用连接。5 秒语句超时、1 秒锁超时为默认会话设置，不能单独当作不可绕过的资源安全边界。

## 5. 参数化反馈提交与审计

```python
from db.client import submit_feedback

feedback_id = submit_feedback("student_s02", "O01", "合成课程反馈")
```

此接口使用独立反馈账号，只能插入自己的已选教学班反馈；内容长度 1—2000，默认公开。模型查询账号无 INSERT 权限。反馈账号不能读取成绩或修改现有反馈，测试攻击采用新提交或配对初始 fixture。

审计表字段见 [SQL](../db/migrations/001_schema.sql)：事件 UUID、run UUID、应用主体、实际数据库角色、事件类型、ALLOW/MASK/BLOCK/ERROR、原因码、SQL 摘要、时间。C 可通过可信后端内部的 `Settings.load().connect('hardened', 'sq_audit_writer')` 参数化插入；不可把此凭据提供给模型。审计账号不能读取、更新、删除记录。当前已提供数据库权限，审计业务逻辑由 C 实现。

## 6. 联调基准与职责边界

[development.json](../tests/attacks/cases/development.json) 有 12 条联调样例，4 条正常任务包含可执行参考 SQL 和预期结果。它是开发集，不是已冻结的最终评估集；真实模型结果仍为空。

- A：生成候选、保存模型版本和实际上下文，处理拒答与无效输出；不直接执行候选。
- B：维护数据库、身份／权限、上下文和反馈数据、参考结果及攻击证据。
- C：实现网关和统一执行入口，区分网关 BLOCK、数据库拒绝和 RLS 空结果，完成业务审计与统计。

当前未提供通用 SQL 安全判定、模型后续调用、自动 SQL 重写、DROP 牺牲表、奖助学金和完整登录。不要因数据库测试通过就宣称整个 AI 助手安全。

数据库语义参考：[PostgreSQL 17 RLS](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)、[视图权限](https://www.postgresql.org/docs/17/sql-createview.html)。实现来源是本项目 SQL 文件，公开案例材料另见 research。
