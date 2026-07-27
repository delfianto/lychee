"""Entrypoint. Deliberately lives *outside* `src/`, not `src/server.py` —
`fastmcp run`/`call`/`dev` load whatever file they're pointed at as a raw
script (no package context), so a file living inside `src/` doing relative
imports (`from . import tools`) fails with "attempted relative import with
no known parent package". Living here, `mcp/` (this file's own directory) is
what Python puts on `sys.path`, so the plain absolute imports below resolve
`src` as a normal top-level package — and since this file is never itself
part of the `src` package, there's no risk of `src.app` getting imported
twice under two identities (once here, once from within `src/tools/*.py`'s
relative `from ..app import mcp`) — both resolve to the same cached
`sys.modules["src.app"]`. See notes/plan.md PART J.
"""

# Imported for side effect: each tools/*.py module registers its functions
# onto `src.app.mcp` via `@mcp.tool` — the same object `mcp` below refers to
# (cached in sys.modules once either import runs; ruff's import sort puts
# this line first, but the actual order doesn't matter for correctness).
import src.tools  # noqa: E402,F401
from src.app import mcp


def main() -> None:
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
