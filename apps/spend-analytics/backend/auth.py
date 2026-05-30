"""On-behalf-of authentication for Databricks Apps.

Apps injects per-request user identity via forwarded headers when the app is
configured for user authorization (user_api_scopes in resources/apps.yml):

    X-Forwarded-Access-Token   OAuth access token for the calling user
    X-Forwarded-Email          User email
    X-Forwarded-Preferred-Username
    X-Forwarded-User           Workspace SCIM ID

The token is used as the bearer for all Databricks API calls (SQL, serving),
so Unity Catalog row/column security applies as the actual user.

Local dev: set APP_DEV_ALLOW_ANONYMOUS=1 to bypass OBO and boot without the
Apps proxy. Routes that open a warehouse connection will still raise 500 —
to exercise UC paths locally, deploy to a dev workspace.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from .config import get_settings


@dataclass(frozen=True)
class CallerIdentity:
    email: str
    user_id: str | None
    access_token: str | None  # None only in local-dev anonymous mode

    @property
    def is_anonymous(self) -> bool:
        return self.access_token is None

    @property
    def display_name(self) -> str:
        return self.email.split("@")[0].replace(".", " ").title()

    @property
    def initials(self) -> str:
        parts = self.display_name.split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[-1][0]}".upper()
        return self.display_name[:2].upper()


def caller_identity(request: Request) -> CallerIdentity:
    settings = get_settings()
    headers = request.headers

    token = headers.get("x-forwarded-access-token")
    email = headers.get("x-forwarded-email") or headers.get(
        "x-forwarded-preferred-username"
    )
    user_id = headers.get("x-forwarded-user")

    if token and email:
        return CallerIdentity(email=email, user_id=user_id, access_token=token)

    if settings.dev_allow_anonymous:
        return CallerIdentity(
            email=settings.dev_user_email, user_id=None, access_token=None
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=(
            "Missing user identity. This route requires a Databricks Apps "
            "OBO context (X-Forwarded-Access-Token + X-Forwarded-Email)."
        ),
    )
