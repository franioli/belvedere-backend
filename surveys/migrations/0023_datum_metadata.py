"""Record each measurement's datum provenance.

A realization mismatch between campaigns — some RDN2008, some ITRF/PPP —
produces an inter-annual offset that looks exactly like glacier motion, so the
realization is recorded rather than assumed.

Deliberately just two columns. The source SRID is not stored: `geom` already
carries it. Nor is an observation epoch: RDN2008 is plate-fixed, so the
coordinate epoch is the frame's `datum_epoch` (2008.0) regardless of when a
campaign was observed, and the column would be NULL on every row. Add one if an
ITRF- or PPP-processed campaign ever turns up.

All campaigns 2015-2026 were tied to the Italian permanent network, so the
backfill is uniform.
"""

from django.db import migrations, models

BACKFILL = """
UPDATE measurements
   SET datum_realization = 'RDN2008',
       height_type = 'ellipsoidal'
 WHERE datum_realization IS NULL;
"""

UNFILL = """
UPDATE measurements SET datum_realization = NULL, height_type = NULL;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("surveys", "0022_rdn2008_srid"),
    ]

    operations = [
        migrations.AddField(
            model_name="measurement",
            name="datum_realization",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=32,
                choices=[
                    ("RDN2008", "RDN2008 (ETRF2000, epoch 2008.0)"),
                    ("ETRF2000", "ETRF2000"),
                    ("ITRF2014", "ITRF2014"),
                ],
                help_text="Reference frame realization the campaign was processed in.",
            ),
        ),
        migrations.AddField(
            model_name="measurement",
            name="height_type",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=16,
                choices=[
                    ("ellipsoidal", "ellipsoidal"),
                    ("orthometric", "orthometric"),
                ],
                help_text=(
                    "Should be 'ellipsoidal' everywhere; h_orto is computed "
                    "internally from h using ITALGEO05 geoid model."
                ),
            ),
        ),
        migrations.RunSQL(sql=BACKFILL, reverse_sql=UNFILL),
    ]
