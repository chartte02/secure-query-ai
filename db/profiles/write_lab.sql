-- A disposable DML experiment. The writer still cannot DROP business tables.
GRANT USAGE ON SCHEMA academic TO sq_lab_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA academic TO sq_lab_writer;
GRANT UPDATE, DELETE ON academic.grades TO sq_lab_writer;
