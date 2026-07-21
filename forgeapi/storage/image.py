from __future__ import annotations

import asyncio
import io
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.datastructures import UploadFile


class _ImagePipeline:
    """Fluent builder for image transformations.

    Created by :meth:`ImageProcessor.process` — do not instantiate directly.

    Chain operations and finish with :meth:`to_bytes` or :meth:`store`::

        from forgeapi import Storage
        from forgeapi.storage import ImageProcessor

        path = await ImageProcessor.process(upload.file.read()) \\
            .resize(1200, 800) \\
            .quality(85) \\
            .store("posts/cover.jpg")

        thumb_path = await ImageProcessor.process(data) \\
            .thumbnail(200) \\
            .store("posts/thumb.jpg")
    """

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._ops: list[tuple] = []
        self._fmt: str = "JPEG"
        self._quality: int = 85

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def resize(self, width: int, height: int, *, crop: bool = False) -> "_ImagePipeline":
        """Resize to at most *width* × *height*, preserving aspect ratio.

        Args:
            width:  Target width in pixels.
            height: Target height in pixels.
            crop:   If ``True``, crop to exact dimensions (centre-crop).
        """
        self._ops.append(("resize", width, height, crop))
        return self

    def thumbnail(self, size: int) -> "_ImagePipeline":
        """Fit inside a *size* × *size* bounding box (no upscaling)."""
        self._ops.append(("thumbnail", size))
        return self

    def quality(self, q: int) -> "_ImagePipeline":
        """JPEG/WebP quality (1–95). Default 85."""
        self._quality = max(1, min(q, 95))
        return self

    def convert(self, fmt: str) -> "_ImagePipeline":
        """Convert to *fmt* (``"JPEG"``, ``"PNG"``, ``"WEBP"``)."""
        self._fmt = fmt.upper()
        return self

    def grayscale(self) -> "_ImagePipeline":
        """Convert to grayscale."""
        self._ops.append(("grayscale",))
        return self

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """Apply all operations and return the result as bytes.

        Raises:
            ImportError: If Pillow is not installed.
        """
        try:
            from PIL import Image, ImageOps
        except ImportError:
            raise ImportError(
                "ImageProcessor requires Pillow. "
                "Install it: pip install forge-kits[images]"
            )

        img = Image.open(io.BytesIO(self._data))

        # Normalise: strip EXIF rotation, convert palette/RGBA for JPEG
        img = ImageOps.exif_transpose(img)

        for op in self._ops:
            if op[0] == "resize":
                _, w, h, crop = op
                if crop:
                    img = ImageOps.fit(img, (w, h), Image.LANCZOS)
                else:
                    img.thumbnail((w, h), Image.LANCZOS)
            elif op[0] == "thumbnail":
                img.thumbnail((op[1], op[1]), Image.LANCZOS)
            elif op[0] == "grayscale":
                img = ImageOps.grayscale(img)

        if self._fmt == "JPEG" and img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        buf = io.BytesIO()
        save_kwargs: dict = {"format": self._fmt, "optimize": True}
        if self._fmt in ("JPEG", "WEBP"):
            save_kwargs["quality"] = self._quality

        img.save(buf, **save_kwargs)
        return buf.getvalue()

    async def store(
        self,
        path: str | None = None,
        *,
        directory: str = "images",
        extension: str | None = None,
        disk: str | None = None,
    ) -> str:
        """Process and store the image, returning the stored path.

        Args:
            path:      Full path including filename. If ``None``, a UUID
                       filename is generated under *directory*.
            directory: Used when *path* is ``None``.
            extension: File extension when auto-generating filename.
                       Defaults to the format (``".jpg"`` for JPEG).
            disk:      Named disk registered via ``Storage.add_disk()``.
                       Omit to use the default disk.

        Returns:
            The path where the file was stored.
        """
        from .storage import Storage

        if path is None:
            ext = extension or _FMT_EXT.get(self._fmt, ".jpg")
            path = f"{directory.rstrip('/')}/{uuid.uuid4().hex}{ext}"

        data = await asyncio.to_thread(self.to_bytes)
        driver = Storage.disk(disk) if disk else Storage
        return await driver.put(path, data)


_FMT_EXT = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
}


class ImageProcessor:
    """Entry point for image processing.

    Usage::

        from forgeapi.storage import ImageProcessor

        # From raw bytes:
        pipeline = ImageProcessor.process(file_bytes)

        # From a FastAPI UploadFile:
        pipeline = await ImageProcessor.from_upload(upload_file)

        # Chain operations:
        path = await pipeline.resize(800, 600).quality(80).store("avatars/")
    """

    @staticmethod
    def process(data: bytes) -> _ImagePipeline:
        """Create a pipeline from raw image bytes."""
        return _ImagePipeline(data)

    @staticmethod
    async def from_upload(upload: "UploadFile") -> _ImagePipeline:
        """Create a pipeline from a FastAPI ``UploadFile``.

        Reads the file content and resets the cursor so the upload object
        can still be used afterwards.
        """
        data = await upload.read()
        await upload.seek(0)
        return _ImagePipeline(data)
