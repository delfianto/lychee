"""Local-import configuration (Settings → Local import).

A singleton row (id ``default``) holding the enable toggle, the AVIF quality used
when transcoding imported pages, and the optional filename→metadata token pattern.
Consumed by the import job (PART G / G3); this module only manages the row.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.integrations.models import ImportConfig
from src.integrations.schema import ImportConfigOut, ImportConfigUpdate

IMPORT_CONFIG_ID = "default"


def _out(cfg: ImportConfig) -> ImportConfigOut:
    return ImportConfigOut(
        enabled=cfg.enabled, quality=cfg.quality, filename_pattern=cfg.filename_pattern
    )


def get_config_row(session: Session) -> ImportConfig:
    """The singleton config row; created on the fly if seeding hasn't run (never 500s)."""
    cfg = session.get(ImportConfig, IMPORT_CONFIG_ID)
    if cfg is None:
        cfg = ImportConfig(id=IMPORT_CONFIG_ID)
        session.add(cfg)
        session.commit()
    return cfg


def get_import_config(session: Session) -> ImportConfigOut:
    return _out(get_config_row(session))


def update_import_config(session: Session, data: ImportConfigUpdate) -> ImportConfigOut:
    cfg = get_config_row(session)
    if data.enabled is not None:
        cfg.enabled = data.enabled
    if data.quality is not None:
        cfg.quality = data.quality
    if data.filename_pattern is not None:
        cfg.filename_pattern = data.filename_pattern
    session.commit()
    return _out(cfg)
