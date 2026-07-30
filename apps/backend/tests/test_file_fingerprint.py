import hashlib
from io import BytesIO

import pytest

from assistant.application.file_fingerprint import FileFingerprintService
from assistant.domain.file_fingerprint import FileFingerprint, InvalidFileFingerprint


class CountingStream(BytesIO):
    def __init__(self, value: bytes) -> None:
        super().__init__(value)
        self.read_sizes: list[int | None] = []

    def read(self, size: int | None = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


def test_sha256_fingerprint_is_streamed_counts_exact_bytes_and_rewinds_seekable_stream():
    content = bytes(range(256)) * 10
    stream = CountingStream(content)
    service = FileFingerprintService(read_buffer_size=127)

    fingerprint = service.calculate_sha256(stream)

    assert fingerprint == FileFingerprint(
        algorithm="sha256",
        checksum=hashlib.sha256(content).hexdigest(),
        file_size_bytes=len(content),
    )
    assert len(stream.read_sizes) > 2
    assert set(stream.read_sizes) == {127}
    assert stream.tell() == 0
    assert not stream.closed


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
        ("Zażółć gęślą".encode(), hashlib.sha256("Zażółć gęślą".encode()).hexdigest()),
    ],
)
def test_sha256_fingerprint_matches_known_and_binary_safe_vectors(content: bytes, expected: str):
    first = FileFingerprintService().calculate_sha256(BytesIO(content))
    second = FileFingerprintService().calculate_sha256(BytesIO(content))

    assert first.checksum == second.checksum == expected
    assert first.file_size_bytes == len(content)
    assert first.checksum == first.checksum.lower()


def test_fingerprint_service_propagates_stream_read_failure_without_closing_caller_stream():
    class BrokenStream(BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            raise OSError("storage unavailable")

    stream = BrokenStream(b"content")

    with pytest.raises(OSError, match="storage unavailable"):
        FileFingerprintService().calculate_sha256(stream)

    assert not stream.closed


@pytest.mark.parametrize(
    ("algorithm", "checksum", "size"),
    [
        ("md5", "a" * 64, 1),
        ("sha256", "a" * 63, 1),
        ("sha256", "g" * 64, 1),
        ("sha256", "A" * 64, 1),
        ("sha256", "a" * 64, -1),
    ],
)
def test_fingerprint_rejects_unsupported_or_malformed_integrity_metadata(
    algorithm: str, checksum: str, size: int
):
    with pytest.raises(InvalidFileFingerprint):
        FileFingerprint(algorithm, checksum, size)
