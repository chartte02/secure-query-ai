-- Intentionally over-broad read permissions, only on the isolated baseline instance.
GRANT USAGE ON SCHEMA academic TO sq_lab_reader, sq_context_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA academic TO sq_lab_reader;
GRANT SELECT ON academic.courses, academic.course_offerings, academic.teachers
    TO sq_context_reader;
GRANT SELECT (feedback_id, offering_id, content, visibility, created_at)
    ON academic.course_feedback TO sq_context_reader;
-- Context collection remains safe even when the experiment executor is over-privileged.
ALTER TABLE academic.course_feedback ENABLE ROW LEVEL SECURITY;
CREATE POLICY broad_feedback ON academic.course_feedback FOR SELECT TO sq_lab_reader
    USING (true);
CREATE POLICY public_feedback ON academic.course_feedback FOR SELECT TO sq_context_reader
    USING (visibility = 'public');
