"""The corpus harness must never rewrite library metadata or create a database."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from scripts.export_descriptions import export_corpus


def test_export_preserves_source_and_only_includes_nonempty_descriptions(tmp_path: Path) -> None:
    database = tmp_path / "library.db"
    text = "Unicode 漫画\r\n\r\n| Book 1 | Tags |\r\n|---|---|\r\n|Genre|drama|"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE series(id TEXT, title TEXT, kind TEXT, description TEXT)")
        connection.executemany(
            "INSERT INTO series VALUES (?,?,?,?)",
            [
                ("a", "One", "manga", text),
                ("b", "Two", "manga", text),
                ("c", "Empty", "manga", "  "),
                ("d", "Missing", "gallery", None),
            ],
        )
        connection.commit()
    before = database.read_bytes()
    output = tmp_path / "corpus.json"
    assert export_corpus(database, output) == {
        "totalSeries": 4,
        "descriptions": 2,
        "uniqueDescriptions": 1,
    }
    corpus = json.loads(output.read_text())
    assert corpus["version"] == 1
    assert [row["id"] for row in corpus["items"]] == ["a", "b"]
    assert corpus["items"][0]["description"] == text
    assert database.read_bytes() == before
    with pytest.raises(FileExistsError):
        export_corpus(database, database)
    assert database.read_bytes() == before
    with pytest.raises(FileExistsError):
        export_corpus(database, output)


def test_missing_database_is_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    output = tmp_path / "corpus.json"
    with pytest.raises(FileNotFoundError):
        export_corpus(missing, output)
    assert not missing.exists()
    assert not output.exists()
