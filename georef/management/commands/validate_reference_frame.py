"""Run the frame validation suite against whatever database is configured."""

from django.core.management.base import BaseCommand, CommandError

from georef.constants import ENU_SRID
from georef.models import ReferenceFrame
from georef.validation import run_checks


class Command(BaseCommand):
    help = "Validate a local reference frame (round trip, scale, positivity, ...)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--srid", type=int, default=ENU_SRID)

    def handle(self, *args, **options) -> None:
        srid = options["srid"]
        try:
            frame = ReferenceFrame.objects.get(srid=srid)
        except ReferenceFrame.DoesNotExist:
            raise CommandError(f"no reference frame with SRID {srid}") from None

        self.stdout.write(f"{frame}  origin {frame.origin_mark}  frozen={frame.frozen}")

        results = run_checks(srid)
        width = max(len(result.name) for result in results)
        for result in results:
            mark = "PASS" if result.passed else "FAIL"
            style = self.style.SUCCESS if result.passed else self.style.ERROR
            self.stdout.write(
                style(f"  {mark}  {result.name:<{width}}  {result.detail}")
            )

        failed = [result.name for result in results if not result.passed]
        if failed:
            raise CommandError(f"{len(failed)} check(s) failed: {', '.join(failed)}")
        self.stdout.write(self.style.SUCCESS(f"all {len(results)} checks passed"))
