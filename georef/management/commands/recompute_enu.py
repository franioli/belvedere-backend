"""Recompute the materialised ENU geometries from their source coordinates.

The triggers keep these columns current on every write; this command exists
for the initial backfill and for the rare case where the frame row changed
before it was frozen.
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from georef.constants import ENU_SRID
from georef.sql import (
    COUNT_MISSING_CAMERAS_ENU,
    COUNT_MISSING_MEASUREMENTS_ENU,
    RECOMPUTE_CAMERAS_ENU,
    RECOMPUTE_MEASUREMENTS_ENU,
)

TARGETS = {
    "measurements": RECOMPUTE_MEASUREMENTS_ENU,
    "cameras": RECOMPUTE_CAMERAS_ENU,
}

COUNTS = {
    "measurements": COUNT_MISSING_MEASUREMENTS_ENU,
    "cameras": COUNT_MISSING_CAMERAS_ENU,
}


class Command(BaseCommand):
    help = "Recompute geom_enu / location_enu from the source coordinates."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--target",
            choices=[*TARGETS, "all"],
            default="all",
        )
        parser.add_argument("--srid", type=int, default=ENU_SRID)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many rows are missing an ENU geometry, change nothing.",
        )

    def handle(self, *args, **options) -> None:
        targets = list(TARGETS) if options["target"] == "all" else [options["target"]]

        if options["dry_run"]:
            with connection.cursor() as cursor:
                for target in targets:
                    cursor.execute(COUNTS[target])
                    self.stdout.write(
                        f"{target}: {cursor.fetchone()[0]} row(s) without an ENU geometry"
                    )
            return

        with transaction.atomic(), connection.cursor() as cursor:
            for target in targets:
                cursor.execute(TARGETS[target], [options["srid"]])
                self.stdout.write(
                    self.style.SUCCESS(f"{target}: {cursor.rowcount} row(s) updated")
                )
