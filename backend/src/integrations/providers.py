"""Metadata-provider configuration — enable, language, auto-match, and download quality.

These are the settings rows for content/metadata providers (currently MangaDex).
The OAuth account + follows import for a provider live in ``src/providers/`` (e.g.
``mangadex_account``); this module only manages the config row itself.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.exceptions import NotFoundError
from src.integrations.models import Provider
from src.integrations.schema import ProviderOut, ProviderUpdate


def provider_out(p: Provider) -> ProviderOut:
    return ProviderOut(
        id=p.id,
        name=p.name,
        enabled=p.enabled,
        language=p.language,
        auto_match=p.auto_match,
        fetch_covers=p.fetch_covers,
        data_saver=p.data_saver,
        connected=bool(p.client_id and p.refresh_token_enc),
        account_name=p.account_name,
    )


def get_provider_row(session: Session, provider_id: str) -> Provider:
    provider = session.get(Provider, provider_id)
    if provider is None:
        raise NotFoundError(f"provider {provider_id!r} not found")
    return provider


def list_providers(session: Session) -> list[ProviderOut]:
    return [provider_out(p) for p in session.scalars(select(Provider).order_by(Provider.name))]


def update_provider(session: Session, provider_id: str, data: ProviderUpdate) -> ProviderOut:
    provider = get_provider_row(session, provider_id)
    if data.enabled is not None:
        provider.enabled = data.enabled
    if data.language is not None:
        provider.language = data.language
    if data.auto_match is not None:
        provider.auto_match = data.auto_match
    if data.fetch_covers is not None:
        provider.fetch_covers = data.fetch_covers
    if data.data_saver is not None:
        provider.data_saver = data.data_saver
    session.commit()
    return provider_out(provider)
