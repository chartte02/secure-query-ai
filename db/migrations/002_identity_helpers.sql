SET ROLE sq_owner;
-- These narrow helpers intentionally run as the table owner to avoid RLS recursion.
-- The caller is session_user, not current_user (which is the definer here).
CREATE FUNCTION private_auth.student_id_for_session() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $$ SELECT student_id FROM private_auth.actor_map WHERE db_role = session_user $$;

CREATE FUNCTION private_auth.teacher_id_for_session() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $$ SELECT teacher_id FROM private_auth.actor_map WHERE db_role = session_user $$;

CREATE FUNCTION private_auth.can_read_offering(target text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $$
    SELECT EXISTS (
        SELECT 1 FROM private_auth.actor_map a
        JOIN academic.course_offerings o ON o.teacher_id = a.teacher_id
        WHERE a.db_role = session_user AND o.offering_id = target
    )
$$;

CREATE FUNCTION private_auth.can_read_student(target text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $$
    SELECT EXISTS (
        SELECT 1 FROM private_auth.actor_map a
        WHERE a.db_role = session_user AND (
            a.student_id = target OR EXISTS (
                SELECT 1 FROM academic.enrollments e
                JOIN academic.course_offerings o USING (offering_id)
                WHERE e.student_id = target AND o.teacher_id = a.teacher_id
            )
        )
    )
$$;

CREATE FUNCTION private_auth.can_submit_feedback(target text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog
AS $$
    SELECT EXISTS (
        SELECT 1 FROM academic.enrollments e
        JOIN private_auth.actor_map a ON a.student_id = e.student_id
        WHERE a.db_role = session_user AND e.offering_id = target
    )
$$;
RESET ROLE;
