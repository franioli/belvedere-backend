"""Un-shadow the core tables from the legacy public views.

`public.points` (an aggregate view) and `public.surveys` shadowed the real
`core.points` / `core.surveys` tables via the `public,core` search_path, so
Django models were reading views instead of tables (and Point writes failed,
as aggregate views are not updatable). The view-only Point fields
(first_survey_date, last_survey_date, num_measurements) are removed from
model state only — they never existed as table columns.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0007_alter_measurementphoto_file_name_and_more"),
    ]

    # On a fresh database (e.g. the test database) the legacy views do not
    # exist and `points`/`surveys` are real tables, so all DDL is guarded.
    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON c.relnamespace = n.oid
                    WHERE n.nspname = 'public' AND c.relname = 'points'
                      AND c.relkind = 'v'
                ) THEN
                    ALTER VIEW public.points RENAME TO points_summary;
                END IF;
            END $$;
            """,
            reverse_sql="""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON c.relnamespace = n.oid
                    WHERE n.nspname = 'public' AND c.relname = 'points_summary'
                      AND c.relkind = 'v'
                ) THEN
                    ALTER VIEW public.points_summary RENAME TO points;
                END IF;
            END $$;
            """,
        ),
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON c.relnamespace = n.oid
                    WHERE n.nspname = 'public' AND c.relname = 'surveys'
                      AND c.relkind = 'v'
                ) THEN
                    DROP VIEW public.surveys;
                END IF;
            END $$;
            """,
            reverse_sql="""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON c.relnamespace = n.oid
                    WHERE n.nspname = 'core' AND c.relname = 'surveys'
                ) THEN
                    CREATE VIEW public.surveys AS
                        SELECT id, date, year, notes
                        FROM core.surveys ORDER BY date DESC;
                END IF;
            END $$;
            """,
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="point", name="first_survey_date"),
                migrations.RemoveField(model_name="point", name="last_survey_date"),
                migrations.RemoveField(model_name="point", name="num_measurements"),
            ],
        ),
    ]
