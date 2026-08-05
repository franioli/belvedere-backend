"""Export a frame's parameters to a file kept in version control.

The database must not be the only place the origin exists: the same numbers
have to be quotable in Metashape projects, processing scripts and reports.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from georef.constants import ENU_SRID
from georef.models import ReferenceFrame

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[3] / "frames"

FIELDS = (
    "srid",
    "name",
    "description",
    "origin_mark",
    "lat_0",
    "lon_0",
    "h_0",
    "ellps",
    "x_off",
    "y_off",
    "z_off",
    "base_srid",
    "datum_epoch",
    "valid_from",
    "frozen",
    "notes",
    "proj_pipeline",
)


class Command(BaseCommand):
    help = "Write a reference frame's frozen parameters to a JSON file."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--srid", type=int, default=ENU_SRID)
        parser.add_argument("--output", type=Path, default=None)

    def handle(self, *args, **options) -> None:
        srid = options["srid"]
        try:
            frame = ReferenceFrame.objects.get(srid=srid)
        except ReferenceFrame.DoesNotExist:
            raise CommandError(f"no reference frame with SRID {srid}") from None

        if not frame.frozen:
            self.stdout.write(
                self.style.WARNING(
                    "frame is not frozen — the exported parameters may still change"
                )
            )

        payload = {field: getattr(frame, field) for field in FIELDS}
        payload["valid_from"] = frame.valid_from.isoformat()
        payload["datum_epoch"] = (
            float(frame.datum_epoch) if frame.datum_epoch is not None else None
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT auth_name, proj4text, srtext FROM spatial_ref_sys WHERE srid = %s",
                [srid],
            )
            row = cursor.fetchone()
        payload["spatial_ref_sys"] = (
            {"auth_name": row[0], "proj4text": row[1], "srtext": row[2]}
            if row
            else None
        )

        destination = options["output"] or DEFAULT_DIRECTORY / f"{frame.name}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2) + "\n")
        self.stdout.write(self.style.SUCCESS(f"wrote {destination}"))
