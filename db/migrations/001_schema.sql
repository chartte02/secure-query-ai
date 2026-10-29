CREATE SCHEMA academic AUTHORIZATION sq_owner;
CREATE SCHEMA private_auth AUTHORIZATION sq_owner;
CREATE SCHEMA api AUTHORIZATION sq_owner;
CREATE SCHEMA audit AUTHORIZATION sq_owner;

SET ROLE sq_owner;
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
CREATE TABLE academic.students (
    student_id text PRIMARY KEY,
    display_name text NOT NULL,
    department text NOT NULL,
    phone text NOT NULL,
    national_id text NOT NULL
);
CREATE TABLE academic.teachers (
    teacher_id text PRIMARY KEY,
    display_name text NOT NULL,
    department text NOT NULL
);
CREATE TABLE academic.courses (
    course_id text PRIMARY KEY,
    course_name text NOT NULL,
    description text NOT NULL,
    credits numeric(3, 1) NOT NULL CHECK (credits > 0)
);
CREATE TABLE academic.course_offerings (
    offering_id text PRIMARY KEY,
    course_id text NOT NULL REFERENCES academic.courses,
    teacher_id text NOT NULL REFERENCES academic.teachers,
    term text NOT NULL
);
CREATE TABLE academic.enrollments (
    student_id text NOT NULL REFERENCES academic.students,
    offering_id text NOT NULL REFERENCES academic.course_offerings,
    enrolled_at timestamptz NOT NULL,
    PRIMARY KEY (student_id, offering_id)
);
CREATE TABLE academic.grades (
    student_id text NOT NULL,
    offering_id text NOT NULL,
    score numeric(5, 2) CHECK (score BETWEEN 0 AND 100),
    grader_note text NOT NULL,
    PRIMARY KEY (student_id, offering_id),
    FOREIGN KEY (student_id, offering_id) REFERENCES academic.enrollments
);
CREATE TABLE academic.course_feedback (
    feedback_id text PRIMARY KEY,
    student_id text NOT NULL,
    offering_id text NOT NULL,
    content text NOT NULL CHECK (length(content) BETWEEN 1 AND 2000),
    visibility text NOT NULL CHECK (visibility IN ('public', 'private')),
    created_at timestamptz NOT NULL,
    FOREIGN KEY (student_id, offering_id) REFERENCES academic.enrollments
);
CREATE TABLE private_auth.actor_map (
    db_role name PRIMARY KEY,
    actor_id text NOT NULL,
    actor_type text NOT NULL CHECK (actor_type IN ('student', 'teacher')),
    student_id text REFERENCES academic.students,
    teacher_id text REFERENCES academic.teachers,
    CHECK ((actor_type = 'student' AND student_id IS NOT NULL AND teacher_id IS NULL)
        OR (actor_type = 'teacher' AND teacher_id IS NOT NULL AND student_id IS NULL))
);
CREATE TABLE audit.events (
    event_id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    actor_id text NOT NULL,
    db_role text NOT NULL,
    event_type text NOT NULL,
    decision text NOT NULL CHECK (decision IN ('ALLOW', 'MASK', 'BLOCK', 'ERROR')),
    reason_code text NOT NULL,
    sql_digest text NOT NULL CHECK (sql_digest ~ '^[0-9a-f]{64}$'),
    occurred_at timestamptz NOT NULL
);
RESET ROLE;
