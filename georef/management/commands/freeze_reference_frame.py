"""Freeze a reference frame — only if it passes every validation check."""

from django.core.management.base import BaseCommand, CommandError

from georef.constants import ENU_SRID
from georef.models import ReferenceFrame
from georef.validation import run_checks


class Command(BaseCommand):
    help = (
        "Mark a reference frame immutable. Refuses if any validation check "
        "fails. After this, corrections require a new SRID."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--srid", type=int, default=ENU_SRID)

    def handle(self, *args, **options) -> None:
        srid = options["srid"]
        try:
            frame = ReferenceFrame.objects.get(srid=srid)
        except ReferenceFrame.DoesNotExist:
            raise CommandError(f"no reference frame with SRID {srid}") from None

        if frame.frozen:
            self.stdout.write(f"{frame} is already frozen")
            return

        failed = [result for result in run_checks(srid) if not result.passed]
        for result in failed:
            self.stdout.write(
                self.style.ERROR(f"  FAIL  {result.name}  {result.detail}")
            )
        if failed:
            raise CommandError(f"refusing to freeze: {len(failed)} check(s) failed")

        ReferenceFrame.objects.filter(srid=srid).update(frozen=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"{frame} frozen. Export the parameters with "
                f"`manage.py dump_reference_frame` and commit them."
            )
        )
