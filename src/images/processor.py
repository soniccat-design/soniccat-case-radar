from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional

from src.collectors.http import HttpClient


def download_image_bytes(url: str, timeout: int = 20) -> bytes:
    client = HttpClient(timeout=timeout, retries=0)
    response = client.get(url, accept="image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8")
    return response.content


def inspect_image_bytes(image_bytes: bytes) -> Dict[str, object]:
    if not image_bytes:
        return {"ok": False, "reason": "empty image"}
    try:
        from PIL import Image, ImageStat  # type: ignore

        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size
            gray = image.convert("L").resize((96, 96))
            stat = ImageStat.Stat(gray)
            clarity = float(stat.var[0])
            return {
                "ok": True,
                "width": int(width),
                "height": int(height),
                "clarity": clarity,
                "image_hash": perceptual_hash(image_bytes),
            }
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def perceptual_hash(image_bytes: bytes) -> str:
    try:
        from PIL import Image  # type: ignore
        import imagehash  # type: ignore

        with Image.open(BytesIO(image_bytes)) as image:
            return str(imagehash.phash(image))
    except Exception:
        try:
            from PIL import Image  # type: ignore

            with Image.open(BytesIO(image_bytes)) as image:
                gray = image.convert("L").resize((8, 8))
                pixels = list(gray.getdata())
            avg = sum(pixels) / len(pixels)
            bits = "".join("1" if pixel >= avg else "0" for pixel in pixels)
            return "%016x" % int(bits, 2)
        except Exception:
            return hashlib.sha256(image_bytes).hexdigest()[:16]


def save_webp(
    image_bytes: bytes,
    output_path: Path,
    max_long_edge: int = 1400,
    target_max_kb: int = 250,
) -> Optional[Path]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image  # type: ignore

        with Image.open(BytesIO(image_bytes)) as image:
            image = image.convert("RGB")
            width, height = image.size
            long_edge = max(width, height)
            if long_edge > max_long_edge:
                scale = max_long_edge / float(long_edge)
                image = image.resize((int(width * scale), int(height * scale)))
            for quality in (86, 80, 74, 68, 62, 56, 50):
                buffer = BytesIO()
                image.save(buffer, format="WEBP", quality=quality, method=6)
                data = buffer.getvalue()
                if len(data) <= target_max_kb * 1024 or quality == 50:
                    output_path.write_bytes(data)
                    return output_path
    except Exception:
        return None
    return None
