from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont, ImageOps

from image_index.models import Image
from image_index.s3_utils import build_s3_client, get_object_bytes, put_object_bytes

PREVIEW_SIZE = (1280, 960)
THUMBNAIL_SIZE = (160, 120)
PREVIEW_QUALITY = 80
THUMBNAIL_QUALITY = 60
DEFAULT_WORKERS = 2  # Keep low to run on vps

PREVIEW_FOLDER = "previews/"
THUMBNAIL_FOLDER = "thumbnails/"


class Command(BaseCommand):
    help = "Generate preview and thumbnail JPEG files for indexed images and upload them to S3"

    def add_arguments(self, parser):
        parser.add_argument(
            "--camera-id", type=int, help="Process only one camera by ID"
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate even if preview_object_key is already set",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=DEFAULT_WORKERS,
            help=f"Parallel threads (default: {DEFAULT_WORKERS})",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        if not settings.S3_ENDPOINT_URL:
            raise CommandError("S3_ENDPOINT_URL is not configured")

        s3 = build_s3_client()
        workers = max(1, options["workers"])

        qs = Image.objects.select_related("camera").order_by("id")
        if options["camera_id"]:
            qs = qs.filter(camera_id=options["camera_id"])
        if not options["force"]:
            qs = qs.filter(preview_object_key__isnull=True)

        total = qs.count()
        self.stdout.write(
            f"Images to process: {total} (force={options['force']}, dry_run={options['dry_run']})"
        )

        if options["dry_run"] or total == 0:
            return

        done = 0
        errors = 0

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_process_image, s3, img): img for img in qs.iterator()
            }

            for future in as_completed(futures):
                img = futures[future]
                preview_key = f"{PREVIEW_FOLDER}{img.object_key}"
                thumb_key = f"{THUMBNAIL_FOLDER}{img.object_key}"

                try:
                    preview_bytes, thumb_bytes = future.result()
                    put_object_bytes(
                        s3, img.bucket, preview_key, preview_bytes, "image/jpeg"
                    )
                    put_object_bytes(
                        s3, img.bucket, thumb_key, thumb_bytes, "image/jpeg"
                    )
                    Image.objects.filter(pk=img.pk).update(
                        preview_object_key=preview_key,
                        thumbnail_object_key=thumb_key,
                    )
                    done += 1
                    if done % 50 == 0:
                        self.stdout.write(f"  {done}/{total} done, {errors} errors")
                except Exception as exc:
                    errors += 1
                    self.stderr.write(f"  ERROR {img.object_key}: {exc}")

        self.stdout.write(
            self.style.SUCCESS(f"Done: {done} generated, {errors} errors")
        )


def _make_preview(image_bytes: bytes, camera_name: str, dt_str: str) -> bytes:
    """Resize to PREVIEW_SIZE, add watermark with camera name and datetime."""
    with PILImage.open(BytesIO(image_bytes)) as src:
        img = ImageOps.exif_transpose(src)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail(PREVIEW_SIZE, PILImage.Resampling.LANCZOS)

        _draw_watermark(img, camera_name, dt_str)

        logo_path = getattr(settings, "PREVIEW_LOGO_PATH", "")
        if logo_path and Path(logo_path).is_file():
            _composite_logo(img, logo_path)

        out = BytesIO()
        img.save(out, format="JPEG", quality=PREVIEW_QUALITY, optimize=True)
        return out.getvalue()


def _make_thumbnail(image_bytes: bytes) -> bytes:
    """Resize to THUMBNAIL_SIZE, no watermark."""
    with PILImage.open(BytesIO(image_bytes)) as src:
        img = ImageOps.exif_transpose(src)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail(THUMBNAIL_SIZE, PILImage.Resampling.LANCZOS)

        out = BytesIO()
        img.save(out, format="JPEG", quality=THUMBNAIL_QUALITY, optimize=True)
        return out.getvalue()


def _draw_watermark(img: PILImage.Image, camera_name: str, dt_str: str) -> None:
    """Draw a semi-transparent dark band at the bottom with camera name and datetime."""
    w, h = img.size
    band_h = max(20, h // 14)

    # Semi-transparent overlay
    overlay = PILImage.new("RGBA", (w, band_h), (0, 0, 0, 160))
    if img.mode != "RGBA":
        img_rgba = img.convert("RGBA")
        img_rgba.paste(overlay, (0, h - band_h), overlay)
        rgb = img_rgba.convert("RGB")
        img.paste(rgb)
    else:
        img.paste(overlay, (0, h - band_h), overlay)

    draw = ImageDraw.Draw(img)
    font_size = max(10, band_h - 6)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size
        )
    except OSError:
        font = ImageFont.load_default()

    text = f"{camera_name}  |  {dt_str}"
    draw.text((6, h - band_h + 3), text, fill=(255, 255, 255), font=font)


def _composite_logo(img: PILImage.Image, logo_path: str) -> None:
    """Paste a logo at the bottom-right, scaled to ~60px tall."""
    with PILImage.open(logo_path) as logo_src:
        logo = logo_src.convert("RGBA")
    target_h = min(60, img.size[1] // 8)
    scale = target_h / logo.size[1]
    target_w = int(logo.size[0] * scale)
    logo = logo.resize((target_w, target_h), PILImage.Resampling.LANCZOS)

    x = img.size[0] - target_w - 8
    y = img.size[1] - target_h - 8
    if img.mode != "RGBA":
        img_rgba = img.convert("RGBA")
        img_rgba.paste(logo, (x, y), logo)
        img.paste(img_rgba.convert("RGB"))
    else:
        img.paste(logo, (x, y), logo)


def _process_image(s3, image: Image) -> tuple[bytes, bytes]:
    """Fetch original and return (preview_bytes, thumbnail_bytes)."""
    raw, _ = get_object_bytes(s3, image.bucket, image.object_key)
    dt_str = image.datetime.strftime("%Y-%m-%d %H:%M") if image.datetime else "—"
    preview = _make_preview(raw, image.camera.camera_name, dt_str)
    thumbnail = _make_thumbnail(raw)
    return preview, thumbnail
