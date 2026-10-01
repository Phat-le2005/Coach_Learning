from abc import ABC, abstractmethod
from pathlib import Path

class TeacherMaterialStorage(ABC):
    @abstractmethod
    def save(self, storage_key: str, data: bytes) -> None: ...
    @abstractmethod
    def read(self, storage_key: str) -> bytes: ...
    @abstractmethod
    def delete(self, storage_key: str) -> None: ...
    @abstractmethod
    def exists(self, storage_key: str) -> bool: ...

class LocalTeacherMaterialStorage(TeacherMaterialStorage):
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or Path(key).is_absolute() or any(part in {"..", "."} for part in Path(key).parts):
            raise ValueError("Invalid storage key")
        result = (self.root / key).resolve()
        if self.root not in result.parents: raise ValueError("Storage path escapes configured root")
        return result

    def save(self, storage_key: str, data: bytes) -> None:
        path = self._path(storage_key); path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp"); temporary.write_bytes(data); temporary.replace(path)
    def read(self, storage_key: str) -> bytes: return self._path(storage_key).read_bytes()
    def delete(self, storage_key: str) -> None: self._path(storage_key).unlink(missing_ok=True)
    def exists(self, storage_key: str) -> bool: return self._path(storage_key).is_file()
