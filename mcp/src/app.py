"""The bare FastMCP instance. Kept free of any other project import so it has
exactly one identity in `sys.modules` (`src.app`) no matter whether it's
reached via the top-level `server.py` entrypoint or a tool module's relative
import — the thing that broke before this split (see server.py's docstring).
"""

from fastmcp import FastMCP

mcp = FastMCP(
    name="lychee",
    instructions=(
        "Tools for lychee, a self-hosted manga/comic/gallery library server. "
        "Use list_series / find_untagged_series / find_unmatched_series to locate "
        "candidate series, list_taxonomy to resolve tag names to ids, then "
        "bulk_tag_series / bulk_set_favorite / bulk_set_library_status / "
        "bulk_queue_downloads to act on a batch of them in one call instead of "
        "one series at a time."
    ),
)
