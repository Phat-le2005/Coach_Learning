"""Storage abstraction for immutable question acquisition artifacts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import shutil


from uuid import uuid4


class QuestionAcquisitionStorage(ABC):
    @abstractmethod
    def save(self, storage_key: str, data: bytes) -> None:
        """Save raw bytes to storage key."""

    @abstractmethod
    def save_file(self, storage_key: str, src_path: Path) -> None:
        """Atomically move or copy a file to storage key."""

    @abstractmethod
    def read(self, storage_key: str) -> bytes:
        """Read artifact binary from storage key."""

    @abstractmethod
    def path(self, storage_key: str) -> Path:
        """Get absolute filesystem Path for storage key."""

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Check if artifact exists at storage key."""

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        """Delete artifact at storage key."""


class LocalQuestionAcquisitionStorage(QuestionAcquisitionStorage):
    """Filesystem storage with path traversal protection and atomic writes."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_storage_key(sha256: str) -> str:
        """Derive standard two-level directory storage key from content hash."""
        clean = sha256.strip().lower()
        if len(clean) != 64:
            raise ValueError("SHA-256 string must be 64 characters.")
        return f"{clean[:2]}/{clean}.pdf"

    def path(self, key: str) -> Path:
        if not key or Path(key).is_absolute() or any(part in {"..", "."} for part in Path(key).parts):
            raise ValueError("Invalid storage key")
        result = (self.root / key).resolve()
        if self.root not in result.parents and result != self.root:
            raise ValueError("Storage path escapes configured root")
        return result

    def save(self, storage_key: str, data: bytes) -> None:
        target = self.path(storage_key)
        if target.is_file():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.parent / f".{target.stem}.{uuid4().hex}.tmp"
        try:
            temp.write_bytes(data)
            temp.replace(target)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def save_file(self, storage_key: str, src_path: Path) -> None:
        target = self.path(storage_key)
        if target.is_file():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.parent / f".{target.stem}.{uuid4().hex}.tmp"
        try:
            shutil.copy2(src_path, temp)
            temp.replace(target)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def read(self, storage_key: str) -> bytes:
        return self.path(storage_key).read_bytes()

    def exists(self, storage_key: str) -> bool:
        return self.path(storage_key).is_file()

    def delete(self, storage_key: str) -> None:
        self.path(storage_key).unlink(missing_ok=True)
