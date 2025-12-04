from __future__ import annotations

from pathlib import Path

from infra.file_processing.extract_text import extract_text


def test_extract_text_from_txt(tmp_path: Path):
    p = tmp_path / "sample.txt"
    p.write_text("hello world")
    assert extract_text(p) == "hello world"
