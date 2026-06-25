from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Convert legacy IntegerField PKs to AutoField so Django omits 'id' from
    INSERT statements and lets PostgreSQL sequences generate values.

    AlterField is wrapped in SeparateDatabaseAndState (state-only) because
    Django emits ALTER COLUMN DDL even for IntegerField→AutoField despite both
    mapping to integer, and PostgreSQL refuses that when views depend on the
    column. The RunSQL blocks handle sequences directly; the state operations
    update Django's internal model registry only.

    The live DB already has sequences (inherited from the original core schema
    via migration 0009's ALTER TABLE ... SET SCHEMA). For fresh/test DBs built
    from scratch, the RunSQL blocks create the sequences and wire up the DEFAULT.
    CREATE SEQUENCE IF NOT EXISTS makes every step idempotent on both paths.
    """

    dependencies = [
        ("surveys", "0016_remove_product3d_proj4_remove_product3d_texture"),
    ]

    operations = [
        # surveys
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="survey",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunSQL(
            sql="""
                CREATE SEQUENCE IF NOT EXISTS surveys_id_seq OWNED BY surveys.id;
                ALTER TABLE surveys ALTER COLUMN id SET DEFAULT nextval('surveys_id_seq');
                SELECT setval('surveys_id_seq', COALESCE((SELECT MAX(id) FROM surveys), 1));
            """,
            reverse_sql="ALTER TABLE surveys ALTER COLUMN id DROP DEFAULT;",
        ),
        # instruments
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="instrument",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunSQL(
            sql="""
                CREATE SEQUENCE IF NOT EXISTS instruments_id_seq OWNED BY instruments.id;
                ALTER TABLE instruments ALTER COLUMN id SET DEFAULT nextval('instruments_id_seq');
                SELECT setval('instruments_id_seq', COALESCE((SELECT MAX(id) FROM instruments), 1));
            """,
            reverse_sql="ALTER TABLE instruments ALTER COLUMN id DROP DEFAULT;",
        ),
        # surveys_has_instruments
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="surveyhasinstrument",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunSQL(
            sql="""
                CREATE SEQUENCE IF NOT EXISTS surveys_has_instruments_id_seq OWNED BY surveys_has_instruments.id;
                ALTER TABLE surveys_has_instruments ALTER COLUMN id SET DEFAULT nextval('surveys_has_instruments_id_seq');
                SELECT setval('surveys_has_instruments_id_seq', COALESCE((SELECT MAX(id) FROM surveys_has_instruments), 1));
            """,
            reverse_sql="ALTER TABLE surveys_has_instruments ALTER COLUMN id DROP DEFAULT;",
        ),
        # flights
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="flight",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunSQL(
            sql="""
                CREATE SEQUENCE IF NOT EXISTS flights_id_seq OWNED BY flights.id;
                ALTER TABLE flights ALTER COLUMN id SET DEFAULT nextval('flights_id_seq');
                SELECT setval('flights_id_seq', COALESCE((SELECT MAX(id) FROM flights), 1));
            """,
            reverse_sql="ALTER TABLE flights ALTER COLUMN id DROP DEFAULT;",
        ),
        # points
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="point",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunSQL(
            sql="""
                CREATE SEQUENCE IF NOT EXISTS points_id_seq OWNED BY points.id;
                ALTER TABLE points ALTER COLUMN id SET DEFAULT nextval('points_id_seq');
                SELECT setval('points_id_seq', COALESCE((SELECT MAX(id) FROM points), 1));
            """,
            reverse_sql="ALTER TABLE points ALTER COLUMN id DROP DEFAULT;",
        ),
        # measurements
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="measurement",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunSQL(
            sql="""
                CREATE SEQUENCE IF NOT EXISTS measurements_id_seq OWNED BY measurements.id;
                ALTER TABLE measurements ALTER COLUMN id SET DEFAULT nextval('measurements_id_seq');
                SELECT setval('measurements_id_seq', COALESCE((SELECT MAX(id) FROM measurements), 1));
            """,
            reverse_sql="ALTER TABLE measurements ALTER COLUMN id DROP DEFAULT;",
        ),
        # measurement_photos
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="measurementphoto",
                    name="id",
                    field=models.AutoField(primary_key=True, serialize=False),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunSQL(
            sql="""
                CREATE SEQUENCE IF NOT EXISTS measurement_photos_id_seq OWNED BY measurement_photos.id;
                ALTER TABLE measurement_photos ALTER COLUMN id SET DEFAULT nextval('measurement_photos_id_seq');
                SELECT setval('measurement_photos_id_seq', COALESCE((SELECT MAX(id) FROM measurement_photos), 1));
            """,
            reverse_sql="ALTER TABLE measurement_photos ALTER COLUMN id DROP DEFAULT;",
        ),
    ]
