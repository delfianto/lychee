"""Write the app's OpenAPI schema to backend/openapi.json.

Feeds the frontend client generator (`bun run api:gen`). Run after changing the
API surface::

    uv run python scripts/dump_openapi.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.main import app  # noqa: E402

_OUT = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> None:
    _OUT.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"wrote {_OUT} ({_OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
