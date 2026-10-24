"""Local pyturso adapter for SQLAlchemy's SQLite SQL/compiler layer.

Turso implements the DB-API but does not expose pysqlite's Python UDF hooks or
check_same_thread argument. It supplies regexp/floor natively. Keep this driver
separate from libSQL: pyturso runs the newer local Turso/MVCC engine.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy.dialects.sqlite.pysqlite import SQLiteDialect_pysqlite
from sqlalchemy.engine import URL


class TursoDialect(SQLiteDialect_pysqlite):
    driver = "turso"
    supports_statement_cache = True

    @classmethod
    def import_dbapi(cls) -> Any:
        import turso

        return turso

    def create_connect_args(self, url: URL) -> Any:
        args, options = super().create_connect_args(url)
        options.pop("check_same_thread", None)
        options["experimental_features"] = "index_method"
        return args, options

    def connect(self, *args: Any, **kwargs: Any) -> Any:
        connection = super().connect(*args, **kwargs)
        # Configure before SQLAlchemy's first-connect schema/isolation probes.
        # Opening an MVCC file in WAL mode first can hide its transaction log.
        cursor = connection.cursor()
        try:
            for pragma in (
                "journal_mode=mvcc",
                "foreign_keys=ON",
                "busy_timeout=30000",
                "synchronous=NORMAL",
            ):
                cursor.execute("PRAGMA " + pragma)
                cursor.fetchall()
        finally:
            cursor.close()
        return connection

    def on_connect(self) -> Callable[[Any], None]:
        # pysqlite registers regexp/floor with create_function(), which pyturso
        # intentionally does not provide. Turso has both built-in SQL functions.
        return lambda _connection: None
