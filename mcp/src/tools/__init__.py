# Import-for-side-effect: each module registers its functions on `server.mcp`
# via the @mcp.tool decorator.
from . import downloads, libraries, series, taxonomy  # noqa: F401
