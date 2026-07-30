from dataclasses import dataclass
from enum import Enum
from re import fullmatch


class InvalidFileFingerprint(ValueError):
    """Raised when persisted file-integrity metadata is not trustworthy."""


class ContentStatus(str, Enum):
    new_content = "NEW_CONTENT"
    duplicate_content = "DUPLICATE_CONTENT"
    modified_content = "MODIFIED_CONTENT"
    forced_reindex = "FORCED_REINDEX"


@dataclass(frozen=True)
class FileFingerprint:
    algorithm: str
    checksum: str
    file_size_bytes: int

    def __post_init__(self) -> None:
        if self.algorithm != "sha256":
            raise InvalidFileFingerprint("Only sha256 file fingerprints are supported.")
        if fullmatch(r"[0-9a-f]{64}", self.checksum) is None:
            raise InvalidFileFingerprint(
                "A SHA-256 checksum must be 64 lowercase hexadecimal characters."
            )
        if self.file_size_bytes < 0:
            raise InvalidFileFingerprint("File size cannot be negative.")
