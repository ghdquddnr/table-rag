"""중복 업로드 방지(백로그 #7) — 파일 해시 헬퍼 테스트. DB 없이 동작해야 한다."""
import hashlib
from pathlib import Path

from src.index.ingest import file_sha256


def test_file_sha256_matches_hashlib(tmp_path: Path):
    f = tmp_path / "sample.pdf"
    content = b"%PDF-1.4 fake content \xea\xb0\x80\xeb\x82\x98"
    f.write_bytes(content)
    assert file_sha256(f) == hashlib.sha256(content).hexdigest()


def test_file_sha256_same_content_different_name(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"identical bytes")
    b.write_bytes(b"identical bytes")
    assert file_sha256(a) == file_sha256(b)


def test_file_sha256_differs_on_content_change(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(b"content v1")
    b.write_bytes(b"content v2")
    assert file_sha256(a) != file_sha256(b)
