
"""Qikink LIVE authentication only. Order submission is disabled."""
import asyncio
import os
import httpx

LIVE_BASE = "https://api.qikink.com"

class QikinkLiveError(RuntimeError):
    """Contains no credentials or response bodies."""

class LiveClient:
    def __init__(self, client_id, client_secret, *, transport=None):
        if not client_id.strip() or not client_secret.strip():
            raise QikinkLiveError("Missing LIVE credentials")
        self._client_id = client_id.strip()
        self._secret = client_secret.strip()
        self._http = httpx.AsyncClient(
            timeout=30, follow_redirects=False, transport=transport
        )

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv("QIKINK_LIVE_CLIENT_ID", ""),
            os.getenv("QIKINK_LIVE_CLIENT_SECRET", ""),
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._http.aclose()

    async def authenticate(self):
        try:
            response = await self._http.post(
                LIVE_BASE + "/api/token",
                data={"ClientId": self._client_id, "client_secret": self._secret},
            )
            if response.status_code != 200:
                raise QikinkLiveError(
                    f"LIVE authentication failed: HTTP {response.status_code}"
                )
            data = response.json()
            token = data.get("Accesstoken")
            expires = data.get("expires_in")
            if (
                not isinstance(token, str) or not token.strip()
                or isinstance(expires, bool)
                or not isinstance(expires, (int, str))
                or int(expires) <= 0
                or str(data.get("ClientId")) != self._client_id
            ):
                raise ValueError
        except (httpx.HTTPError, ValueError, TypeError, AttributeError, OverflowError):
            raise QikinkLiveError("LIVE authentication unavailable or invalid response") from None
        return {
            "environment": "live",
            "authenticated": True,
            "expires_in": int(expires),
            "order_submission_enabled": False,
        }

    async def create_plain_order(self, *args, **kwargs):
        raise QikinkLiveError("LIVE order submission is disabled")

    async def create_printed_order(self, *args, **kwargs):
        raise QikinkLiveError("LIVE order submission is disabled")
