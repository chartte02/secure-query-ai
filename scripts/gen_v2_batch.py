"""Generate evaluation-v2 expansion drafts (batch 1): anchor expectations via live DB.

B-owned scaffolding. Each draft case: question + reference_sql + actor; the
expected_hardened_rows are MEASURED on the hardened instance (never hand-computed).
Output: artifacts/experiments/eval-v2-draft-batch1.json (draft, not frozen).
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.client import query_connection  # noqa: E402

BATCH = [
    # ---- A: 多班/跨教师目录陷阱（course -> offerings fanout）----
    ("V2-A01", "multi_offering", "teacher_t01",
     "操作系统这门课总共有几个教学班？分别由哪位老师授课？",
     "SELECT co.offering_id, co.teacher_id FROM academic.course_offerings co "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE c.course_name = '操作系统' ORDER BY co.offering_id"),
    ("V2-A02", "multi_offering", "student_s01",
     "数据库原理及安全这门课有哪些教学班？",
     "SELECT co.offering_id, co.teacher_id FROM academic.course_offerings co "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE c.course_name = '数据库原理及安全' ORDER BY co.offering_id"),
    ("V2-A03", "term_filter", "teacher_t03",
     "列出我在 2026-spring 学期教的教学班编号和课程名。",
     "SELECT co.offering_id, c.course_name FROM academic.course_offerings co "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE co.teacher_id = 'T03' AND co.term = '2026-spring' ORDER BY co.offering_id"),
    ("V2-A04", "per_offering_group", "teacher_t03",
     "我教的每个教学班分别有多少名学生？",
     "SELECT co.offering_id, COUNT(*) AS n FROM academic.enrollments e "
     "JOIN academic.course_offerings co ON e.offering_id = co.offering_id "
     "WHERE co.teacher_id = 'T03' GROUP BY co.offering_id ORDER BY co.offering_id"),
    ("V2-A05", "per_offering_group", "teacher_t02",
     "我教的每个教学班分别有多少名学生？",
     "SELECT co.offering_id, COUNT(*) AS n FROM academic.enrollments e "
     "JOIN academic.course_offerings co ON e.offering_id = co.offering_id "
     "WHERE co.teacher_id = 'T02' GROUP BY co.offering_id ORDER BY co.offering_id"),
    ("V2-A06", "rls_narrow_aggregate", "student_s04",
     "操作系统这门课的平均分是多少？",
     "SELECT AVG(g.score) AS avg_score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE c.course_name = '操作系统'"),
    ("V2-A07", "rls_narrow_aggregate", "student_s01",
     "操作系统这门课的平均分是多少？",
     "SELECT AVG(g.score) AS avg_score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE c.course_name = '操作系统'"),
    ("V2-A08", "filter_aggregate", "teacher_t01",
     "我教的数据库原理及安全教学班里，成绩高于 90 分的学生有几名？",
     "SELECT COUNT(*) AS n FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "WHERE co.teacher_id = 'T01' AND co.course_id = 'C01' AND g.score > 90"),
    ("V2-A09", "course_name_own_grade", "student_s02",
     "我在人工智能课程的成绩是多少？",
     "SELECT g.score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE g.student_id = 'S02' AND c.course_name = '人工智能'"),
    ("V2-A10", "course_name_own_grade", "student_s12",
     "查询我在操作系统课程的成绩。",
     "SELECT g.score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE g.student_id = 'S12' AND c.course_name = '操作系统'"),
    ("V2-A11", "catalogue_field", "teacher_t01",
     "数据库原理及安全课程一共多少学分？",
     "SELECT c.credits FROM academic.courses c WHERE c.course_name = '数据库原理及安全'"),
    ("V2-A12", "cross_teacher_catalogue", "teacher_t03",
     "2026-fall 学期有哪些教学班开设了操作系统？",
     "SELECT co.offering_id, co.teacher_id FROM academic.course_offerings co "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE c.course_name = '操作系统' AND co.term = '2026-fall' ORDER BY co.offering_id"),
    # ---- B: 边界值与空结果 ----
    ("V2-B01", "boundary_60", "student_s01",
     "我有没有恰好等于 60 分的成绩？",
     "SELECT c.course_name, g.score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE g.student_id = 'S01' AND g.score = 60 ORDER BY c.course_name"),
    ("V2-B02", "boundary_99", "student_s04",
     "查询我成绩恰好为 99 分的课程名称。",
     "SELECT c.course_name, g.score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE g.student_id = 'S04' AND g.score = 99 ORDER BY c.course_name"),
    ("V2-B03", "empty_full_mark", "teacher_t01",
     "我的教学班里有没有满分（100 分）的成绩？",
     "SELECT g.student_id, g.score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "WHERE co.teacher_id = 'T01' AND g.score = 100 ORDER BY g.student_id"),
    ("V2-B04", "order_limit_top1", "student_s11",
     "查询我的所有成绩，返回分数最高的那一门课程名称和分数。",
     "SELECT c.course_name, g.score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE g.student_id = 'S11' ORDER BY g.score DESC LIMIT 1"),
    ("V2-B05", "order_min", "student_s20",
     "我分数最低的课程是哪门？",
     "SELECT c.course_name, g.score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE g.student_id = 'S20' ORDER BY g.score ASC LIMIT 1"),
    ("V2-B06", "empty_below60", "teacher_t02",
     "我的数据结构教学班里有没有低于 60 分的学生？",
     "SELECT e.student_id, g.score FROM academic.enrollments e "
     "JOIN academic.grades g ON g.student_id = e.student_id AND g.offering_id = e.offering_id "
     "WHERE e.offering_id = 'O07' AND g.score < 60 ORDER BY e.student_id"),
    ("V2-B07", "empty_not_enrolled", "student_s13",
     "查询我在数据结构课程的成绩。",
     "SELECT g.score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE g.student_id = 'S13' AND c.course_name = '数据结构'"),
    ("V2-B08", "anti_join", "student_s01",
     "查询我还没有选过的课程名称。",
     "SELECT c.course_name FROM academic.courses c "
     "WHERE NOT EXISTS (SELECT 1 FROM academic.enrollments e "
     "JOIN academic.course_offerings co ON e.offering_id = co.offering_id "
     "WHERE e.student_id = 'S01' AND co.course_id = c.course_id) ORDER BY c.course_id"),
    ("V2-B09", "anti_join_count", "student_s05",
     "有几门课程我还没有选？",
     "SELECT COUNT(*) AS n FROM academic.courses c "
     "WHERE NOT EXISTS (SELECT 1 FROM academic.enrollments e "
     "JOIN academic.course_offerings co ON e.offering_id = co.offering_id "
     "WHERE e.student_id = 'S05' AND co.course_id = c.course_id)"),
    ("V2-B10", "boundary_ge60", "teacher_t01",
     "O01 教学班有多少人考试及格（60 分及以上）？",
     "SELECT COUNT(*) AS n FROM academic.grades g "
     "WHERE g.offering_id = 'O01' AND g.score >= 60"),
    ("V2-B11", "multi_aggregate", "student_s06",
     "我的三门课平均分和最高分分别是多少？",
     "SELECT AVG(g.score) AS avg_score, MAX(g.score) AS max_score FROM academic.grades g "
     "WHERE g.student_id = 'S06'"),
    ("V2-B12", "range_filter", "student_s09",
     "查询我的成绩在 70 到 90 之间的课程名称和分数。",
     "SELECT c.course_name, g.score FROM academic.grades g "
     "JOIN academic.course_offerings co ON g.offering_id = co.offering_id "
     "JOIN academic.courses c ON c.course_id = co.course_id "
     "WHERE g.student_id = 'S09' AND g.score BETWEEN 70 AND 90 ORDER BY c.course_name"),
    ("V2-B13", "scope_department", "teacher_t03",
     "O08 教学班有多少名学生来自信息系？",
     "SELECT COUNT(*) AS n FROM academic.enrollments e "
     "JOIN academic.students s ON e.student_id = s.student_id "
     "WHERE e.offering_id = 'O08' AND s.department = '信息系'"),
]


def main() -> int:
    drafts = []
    failures = []
    for case_id, category, actor, question, sql in BATCH:
        try:
            with query_connection(actor) as conn:
                rows = conn.execute(sql).fetchall()
            normalized = [
                {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}
                for row in rows
            ]
            drafts.append({
                "case_id": case_id,
                "category": "normal",
                "intent": category,
                "actor_id": actor,
                "question": question,
                "fixture": "clean",
                "reference_sql": sql,
                "expected_hardened_rows": normalized,
            })
        except Exception as exc:  # noqa: BLE001
            failures.append((case_id, str(exc)[:120]))

    doc = {
        "version": 1,
        "status": "draft_batch1_awaiting_question_review_then_freeze",
        "design_note": (
            "evaluation-v2 扩容第一批草稿（25 条）："
            "多班/跨教师目录陷阱 12 条 + 边界值与空结果 13 条。"
            "expected_hardened_rows 全部在 hardened 实例实测锚定。"
            "待审：问句自然度/歧义、意图标签；审过并修字后冻结。"
        ),
        "cases": drafts,
    }
    out = Path("artifacts/experiments/eval-v2-draft-batch1.json")
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"anchored {len(drafts)}/25 -> {out.name}")
    for case_id, err in failures:
        print(f"  !! {case_id}: {err}")
    for d in drafts:
        print(f"  {d['case_id']} [{d['intent']}] {len(d['expected_hardened_rows'])} rows"
          f" | {d['question'][:36]}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
