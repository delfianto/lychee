"""Export a read-only SQLite description corpus for the frontend preview/audit harness.

No application startup, provider requests, metadata edits, or library scans.
"""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def export_corpus(database: Path, output: Path) -> dict[str, int]:
    database = database.resolve(strict=True)
    # mode=ro also prevents a misspelled database path from creating an empty DB.
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("PRAGMA query_only = ON")
        total = connection.execute("SELECT COUNT(*) FROM series").fetchone()[0]
        items = [
            dict(zip(("id", "title", "kind", "description"), row, strict=True))
            for row in connection.execute(
                "SELECT id,title,kind,description FROM series "
                "WHERE description IS NOT NULL AND TRIM(description) != '' ORDER BY id"
            )
        ]
    # Never overwrite the database, an earlier export, or another existing file.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(
            {"version": 1, "totalSeries": total, "items": items},
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")
    return {
        "totalSeries": total,
        "descriptions": len(items),
        "uniqueDescriptions": len({item["description"] for item in items}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export_corpus(args.database, args.output)))


if __name__ == "__main__":
    main()
