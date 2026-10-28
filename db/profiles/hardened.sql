GRANT USAGE ON SCHEMA academic, private_auth TO sq_student_reader, sq_teacher_reader,
    sq_feedback_writer, sq_view_owner;
GRANT USAGE ON SCHEMA academic TO sq_context_reader;
GRANT USAGE ON SCHEMA api TO sq_student_reader;
GRANT USAGE ON SCHEMA audit TO sq_audit_writer;
GRANT INSERT ON audit.events TO sq_audit_writer;

GRANT SELECT ON academic.courses, academic.course_offerings, academic.teachers
    TO sq_student_reader, sq_teacher_reader, sq_context_reader;
GRANT SELECT (student_id, display_name, department) ON academic.students
    TO sq_student_reader, sq_teacher_reader;
GRANT SELECT (student_id, offering_id, enrolled_at) ON academic.enrollments
    TO sq_student_reader, sq_teacher_reader;
GRANT SELECT (student_id, offering_id, score) ON academic.grades
    TO sq_student_reader, sq_teacher_reader;
GRANT SELECT (feedback_id, offering_id, content, visibility, created_at)
    ON academic.course_feedback TO sq_student_reader, sq_teacher_reader, sq_context_reader;
GRANT INSERT (feedback_id, student_id, offering_id, content, visibility, created_at)
    ON academic.course_feedback TO sq_feedback_writer;

GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA private_auth
    TO sq_student_reader, sq_teacher_reader, sq_feedback_writer, sq_view_owner;

ALTER TABLE academic.students ENABLE ROW LEVEL SECURITY;
ALTER TABLE academic.enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE academic.grades ENABLE ROW LEVEL SECURITY;
ALTER TABLE academic.course_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY student_scope ON academic.students FOR SELECT
    TO sq_student_reader, sq_teacher_reader
    USING (private_auth.can_read_student(student_id));
CREATE POLICY student_mask_scope ON academic.students FOR SELECT TO sq_view_owner
    USING (student_id = private_auth.student_id_for_session());
CREATE POLICY enrollment_scope ON academic.enrollments FOR SELECT
    TO sq_student_reader, sq_teacher_reader
    USING (student_id = private_auth.student_id_for_session()
        OR private_auth.can_read_offering(offering_id));
CREATE POLICY grade_scope ON academic.grades FOR SELECT
    TO sq_student_reader, sq_teacher_reader
    USING (student_id = private_auth.student_id_for_session()
        OR private_auth.can_read_offering(offering_id));
CREATE POLICY public_feedback ON academic.course_feedback FOR SELECT
    TO sq_student_reader, sq_teacher_reader, sq_context_reader
    USING (visibility = 'public');
CREATE POLICY submit_own_feedback ON academic.course_feedback FOR INSERT
    TO sq_feedback_writer
    WITH CHECK (student_id = private_auth.student_id_for_session()
        AND private_auth.can_submit_feedback(offering_id));

-- View owner has narrow base privileges, is not base owner and cannot bypass RLS.
GRANT SELECT (student_id, phone) ON academic.students TO sq_view_owner;
GRANT CREATE ON SCHEMA api TO sq_view_owner;
SET ROLE sq_view_owner;
CREATE VIEW api.my_contact WITH (security_barrier = true) AS
    SELECT student_id, left(phone, 11) || '***' AS phone_masked
    FROM academic.students;
RESET ROLE;
REVOKE CREATE ON SCHEMA api FROM sq_view_owner;
GRANT SELECT ON api.my_contact TO sq_student_reader;
