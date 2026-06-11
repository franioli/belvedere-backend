"""Move all legacy tables from the `core` schema to `public`.

`ALTER TABLE ... SET SCHEMA` also moves owned sequences and indexes, and the
`compute_measurement_geometry` trigger moves with `measurements` (its function
is moved explicitly). Dependent views in `public` keep working because
Postgres tracks dependencies by OID. The empty `core` schema is then dropped.

On a fresh database (e.g. the test database) `core` does not exist and all
tables are already in `public`, so everything is guarded. The reverse
migration is only meaningful on the legacy production database.
"""

from django.db import migrations

# Explicit list for the reverse migration; the forward pass moves whatever
# tables are present in `core`.
CORE_TABLES = [
    "2d_products",
    "3d_products",
    "flights",
    "instruments",
    "measurement_photos",
    "measurements",
    "points",
    "scatter_measurements",
    "scatter_points",
    "surveys",
    "surveys_has_instruments",
    "volumes",
]

FORWARD_SQL = """
DO $$
DECLARE
    t text;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'core') THEN
        FOR t IN
            SELECT c.relname FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = 'core' AND c.relkind = 'r'
        LOOP
            EXECUTE format('ALTER TABLE core.%I SET SCHEMA public', t);
        END LOOP;

        IF EXISTS (
            SELECT 1 FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = 'core'
              AND p.proname = 'compute_measurement_geometry'
        ) THEN
            ALTER FUNCTION core.compute_measurement_geometry() SET SCHEMA public;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = 'core'
        ) AND NOT EXISTS (
            SELECT 1 FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = 'core'
        ) THEN
            DROP SCHEMA core;
        END IF;
    END IF;
END $$;
"""

REVERSE_SQL = f"""
DO $$
DECLARE
    t text;
BEGIN
    CREATE SCHEMA IF NOT EXISTS core;

    FOREACH t IN ARRAY ARRAY{CORE_TABLES!r}::text[]
    LOOP
        IF EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = 'public' AND c.relname = t AND c.relkind = 'r'
        ) THEN
            EXECUTE format('ALTER TABLE public.%I SET SCHEMA core', t);
        END IF;
    END LOOP;

    IF EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public'
          AND p.proname = 'compute_measurement_geometry'
    ) THEN
        ALTER FUNCTION public.compute_measurement_geometry() SET SCHEMA core;
    END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0008_unshadow_points_surveys_views"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
