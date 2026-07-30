from hashlib import sha256
from typing import BinaryIO

from assistant.domain.file_fingerprint import FileFingerprint


class FileFingerprintService:
    """Calculate a SHA-256 digest without taking ownership of the caller's stream."""

    def __init__(self, *, read_buffer_size: int = 1024 * 1024) -> None:
        if read_buffer_size < 1:
            raise ValueError("Fingerprint read buffer size must be positive.")
        self._read_buffer_size = read_buffer_size

    def calculate_sha256(self, stream: BinaryIO) -> FileFingerprint:
        initial_position: int | None = None
        if stream.seekable():
            initial_position = stream.tell()
            stream.seek(0)

        digest = sha256()
        file_size_bytes = 0
        try:
            while True:
                chunk = stream.read(self._read_buffer_size)
                if not chunk:
                    break
                digest.update(chunk)
                file_size_bytes += len(chunk)
        finally:
            if initial_position is not None:
                stream.seek(initial_position)

        return FileFingerprint("sha256", digest.hexdigest(), file_size_bytes)
