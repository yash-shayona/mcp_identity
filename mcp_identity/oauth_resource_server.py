"""Frappe-native opaque bearer verification for the MCP resource server."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import frappe
from mcp.server.auth.provider import AccessToken, TokenVerifier

from .identity import (
    MCPIdentityConfigurationError,
    OAuthResourceServerSettings,
    get_oauth_resource_server_settings,
)
from .resource import MCPResourceError, canonicalize_mcp_resource

RESOURCE_FIELD = "custom_mcp_resource"
OAUTH_FIELDS = ("OAuth Client", "OAuth Authorization Code", "OAuth Bearer Token")


def _split_scopes(value: Any) -> list[str]:
    return list(dict.fromkeys(str(value or "").replace(",", " ").split()))


def _sites_path() -> str:
    return os.environ.get("MCP_FRAPPE_SITES_PATH") or os.environ.get(
        "FRAPPE_SITES_PATH"
    ) or str(Path(__file__).resolve().parents[3] / "sites")


def _timestamp(value: Any) -> int | None:
    if not value:
        return None
    if isinstance(value, datetime):
        current = value
    else:
        current = frappe.utils.get_datetime(value)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return int(current.timestamp())


class FrappeOAuthTokenVerifier(TokenVerifier):
    """Verify every opaque token against the current native Frappe rows."""

    def __init__(self, settings: OAuthResourceServerSettings | None = None) -> None:
        self.settings = settings or get_oauth_resource_server_settings()

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token or not isinstance(token, str):
            return None
        # Frappe's DB API is synchronous and its request-local state is
        # ContextVar-backed. Keep the short authoritative lookup in this
        # request context rather than leaking Frappe objects across await
        # boundaries or relying on an executor with a separate site context.
        return self._verify_in_frappe(token)

    def _verify_in_frappe(self, token: str) -> AccessToken | None:
        initialized_here = False
        try:
            if not getattr(frappe.local, "initialised", False):
                frappe.init(site=self.settings.frappe_site, sites_path=_sites_path(), force=True)
                frappe.connect(set_admin_as_user=False)
                initialized_here = True
            row = frappe.db.get_value(
                "OAuth Bearer Token",
                token,
                ["name", "client", "user", "scopes", "status", "expiration_time", RESOURCE_FIELD],
                as_dict=True,
            )
            if not row or row.status != "Active":
                return None
            expires_at = _timestamp(row.expiration_time)
            if expires_at is not None and expires_at <= int(datetime.now(timezone.utc).timestamp()):
                return None
            client = frappe.db.get_value(
                "OAuth Client", self.settings.frappe_client_id,
                ["name", "client_id", "scopes", RESOURCE_FIELD], as_dict=True,
            )
            if not client:
                client = frappe.db.get_value(
                    "OAuth Client", {"client_id": self.settings.frappe_client_id},
                    ["name", "client_id", "scopes", RESOURCE_FIELD], as_dict=True,
                )
            if not client or str(client.name) != str(row.client):
                return None
            try:
                token_resource = canonicalize_mcp_resource(str(row.get(RESOURCE_FIELD) or ""))
                client_resource = canonicalize_mcp_resource(str(client.get(RESOURCE_FIELD) or ""))
            except MCPResourceError:
                return None
            if not (token_resource == client_resource == self.settings.resource_server_url):
                return None
            token_scopes = _split_scopes(row.scopes)
            if any(scope not in token_scopes for scope in self.settings.required_scopes):
                return None
            user = frappe.db.get_value("User", row.user, ["name", "enabled"], as_dict=True)
            if not user or str(user.name).casefold() == "guest" or not user.enabled:
                return None
            return AccessToken(
                token=token,
                client_id=str(row.client),
                scopes=token_scopes,
                expires_at=expires_at,
                resource=token_resource,
                subject=str(user.name),
                claims={"iss": self.settings.issuer_url},
            )
        except Exception:
            # Authentication infrastructure failures are fail-closed and are not
            # exposed as token-specific diagnostics.
            return None
        finally:
            if initialized_here:
                frappe.destroy()


def validate_oauth_resource_server_startup(
    settings: OAuthResourceServerSettings | None = None,
) -> OAuthResourceServerSettings:
    """Validate the local Frappe trust anchor before exposing HTTP."""
    settings = settings or get_oauth_resource_server_settings()
    initialized_here = False
    try:
        if not getattr(frappe.local, "initialised", False):
            frappe.init(site=settings.frappe_site, sites_path=_sites_path(), force=True)
            frappe.connect(set_admin_as_user=False)
            initialized_here = True
        for doctype in OAUTH_FIELDS:
            if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": RESOURCE_FIELD}):
                raise MCPIdentityConfigurationError(
                    f"OAuth resource binding field is missing on {doctype}. Migrate mcp_identity first."
                )
        client = frappe.db.get_value(
            "OAuth Client", settings.frappe_client_id,
            ["name", "client_id", "grant_type", "response_type", RESOURCE_FIELD], as_dict=True,
        )
        if not client:
            client = frappe.db.get_value(
                "OAuth Client", {"client_id": settings.frappe_client_id},
                ["name", "client_id", "grant_type", "response_type", RESOURCE_FIELD], as_dict=True,
            )
        if not client:
            raise MCPIdentityConfigurationError("Configured OAuth Client does not exist.")
        if "authorization code" not in str(client.get("grant_type") or "").casefold():
            raise MCPIdentityConfigurationError(
                "Configured OAuth Client must allow the authorization-code flow."
            )
        if "code" not in str(client.get("response_type") or "").casefold():
            raise MCPIdentityConfigurationError(
                "Configured OAuth Client must allow the code response type."
            )
        try:
            client_resource = canonicalize_mcp_resource(str(client.get(RESOURCE_FIELD) or ""))
        except MCPResourceError as error:
            raise MCPIdentityConfigurationError("Configured OAuth Client resource is invalid.") from error
        if client_resource != settings.resource_server_url:
            raise MCPIdentityConfigurationError("Configured OAuth Client resource does not match MCP resource.")
        return settings
    finally:
        if initialized_here:
            frappe.destroy()
