"""Config for the lychee MCP server.

Local-only per notes/plan.md PART J — this server talks to the backend over
plain HTTP on localhost, and (today, on stdio transport) has no network
listener of its own, so there is nothing here to authenticate. If this ever
grows an HTTP/SSE transport, that is also the point to add an API key setting
guarding *this* server's listener — see PART J's "Transport + auth" section
before doing that.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base URL of the lychee backend's REST API.
    lychee_api_url: str = "http://127.0.0.1:8000"


settings = Settings()
