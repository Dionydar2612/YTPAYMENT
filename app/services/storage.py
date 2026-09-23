"""Storage layer, kept separate from business logic so the backing store can
be swapped (local disk today, S3-compatible object storage later) without
touching routers or the calculation service.

To add S3 support: implement a `S3Storage` class with the same interface
and select it in `get_storage()` based on settings.STORAGE_TYPE.
"""
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from fastapi import UploadFile

from app.config import get_settings

settings = get_settings()

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class StorageError(Exception):
    pass


class BaseStorage(ABC):
    @abstractmethod
    def save(self, file: UploadFile, subdir: str) -> str:
        """Persist the file, return a relative path usable by `open_path`/`url_for`."""

    @abstractmethod
    def path_on_disk(self, relative_path: str) -> str:
        """Resolve a relative path to a readable local filesystem path."""


class LocalStorage(BaseStorage):
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, file: UploadFile, subdir: str) -> str:
        _validate_upload(file)
        target_dir = self.base_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            ext = ".jpg"
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = target_dir / filename

        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        size = 0
        with open(dest, "wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    out.close()
                    os.remove(dest)
                    raise StorageError(
                        f"ไฟล์ใหญ่เกินกำหนด (สูงสุด {settings.MAX_UPLOAD_SIZE_MB} MB)"
                    )
                out.write(chunk)

        return f"{subdir}/{filename}"

    def path_on_disk(self, relative_path: str) -> str:
        # Prevent path traversal outside the upload directory.
        full = (self.base_dir / relative_path).resolve()
        if not str(full).startswith(str(self.base_dir.resolve())):
            raise StorageError("Invalid path")
        return str(full)


def _validate_upload(file: UploadFile) -> None:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise StorageError("รองรับเฉพาะไฟล์ JPG, JPEG, PNG, WEBP เท่านั้น")
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise StorageError("ประเภทไฟล์ไม่ถูกต้อง")


_storage_instance: BaseStorage = None


def get_storage() -> BaseStorage:
    global _storage_instance
    if _storage_instance is None:
        if settings.STORAGE_TYPE == "local":
            _storage_instance = LocalStorage(settings.UPLOAD_DIR)
        else:
            raise StorageError(f"Unsupported STORAGE_TYPE: {settings.STORAGE_TYPE}")
    return _storage_instance
