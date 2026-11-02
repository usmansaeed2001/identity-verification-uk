"""Checks and cleans uploaded photos: must be a real image; EXIF (including GPS) is dropped."""

import io

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 1600
# The browser converts camera photos to JPEG before upload; MPO is what some phones call a JPEG.
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}


class InvalidImage(ValueError):
    pass


def clean_photo(upload) -> bytes:
    """Return the photo as a JPEG with no metadata, at most MAX_SIDE pixels on its longest side."""
    if upload.size > settings.MAX_UPLOAD_BYTES:
        raise InvalidImage("That photo is too large. The limit is 8 MB.")
    upload.seek(0)  # DRF's ImageField already read it once
    raw = upload.read()
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise InvalidImage("Upload a JPEG, PNG or WebP photo.")
        with Image.open(io.BytesIO(raw)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            if min(image.size) < 200:
                raise InvalidImage("That photo is too small. Take it again closer up.")
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise InvalidImage("That file isn't a photo we can read. Take the photo again.") from exc
