"""Generic trusted HTTP request identity resolution for Frappe consumers."""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from email.headerregistry import Address
from enum import StrEnum
from typing import Any, Mapping
from urllib.parse import urlsplit

import frappe

USER_EMAIL_HEADER = "X-MCP-User-Email"
MIN_SHARED_SECRET_LENGTH = 32
HTTP_AUTH_MODE_ENV_VAR = "MCP_HTTP_AUTH_MODE"
HTTP_SHARED_SECRET_ENV_VAR = "MCP_HTTP_SHARED_SECRET"
FRAPPE_USER_ENV_VAR = "MCP_FRAPPE_USER"
OAUTH_ISSUER_ENV_VAR = "MCP_OAUTH_ISSUER_URL"
OAUTH_RESOURCE_ENV_VAR = "MCP_OAUTH_RESOURCE_SERVER_URL"
OAUTH_SCOPES_ENV_VAR = "MCP_OAUTH_REQUIRED_SCOPES"
OAUTH_CLIENT_ID_ENV_VAR = "MCP_OAUTH_FRAPPE_CLIENT_ID"


class HTTPAuthMode(StrEnum):
    """Supported HTTP authentication strategies."""

    TRUSTED_HEADER = "trusted_header"
    OAUTH = "oauth"


class MCPIdentityError(RuntimeError):
    """Base failure whose public code does not expose request details."""

    public_code = "MCP_IDENTITY_ERROR"


class MCPAuthenticationMissingError(MCPIdentityError):
    public_code = "MCP_AUTHENTICATION_MISSING"


class MCPAuthenticationInvalidError(MCPIdentityError):
    public_code = "MCP_AUTHENTICATION_INVALID"


class MCPUserIdentityMissingError(MCPIdentityError):
    public_code = "MCP_USER_IDENTITY_MISSING"


class MCPUserNotFoundError(MCPIdentityError):
    public_code = "MCP_USER_NOT_FOUND"


class MCPUserDisabledError(MCPIdentityError):
    public_code = "MCP_USER_DISABLED"


class MCPIdentityConfigurationError(MCPIdentityError):
    public_code = "MCP_IDENTITY_CONFIGURATION_ERROR"


@dataclass(frozen=True)
class OAuthResourceServerSettings:
    """The non-secret configuration for the Frappe-backed MCP resource server."""

    issuer_url: str
    resource_server_url: str
    required_scopes: tuple[str, ...]
    frappe_client_id: str
    frappe_site: str


def get_oauth_resource_server_settings(*, frappe_site: str | None = None) -> OAuthResourceServerSettings:
    """Read OAuth resource-server settings without consulting request headers."""
    from .resource import MCPResourceError, canonicalize_mcp_resource

    issuer = os.environ.get(OAUTH_ISSUER_ENV_VAR, "").strip()
    resource = os.environ.get(OAUTH_RESOURCE_ENV_VAR, "").strip()
    client_id = os.environ.get(OAUTH_CLIENT_ID_ENV_VAR, "").strip()
    site = (frappe_site or os.environ.get("MCP_FRAPPE_SITE", "")).strip()
    if not issuer or not resource or not client_id or not site:
        raise MCPIdentityConfigurationError(
            "OAuth mode requires MCP_OAUTH_ISSUER_URL, MCP_OAUTH_RESOURCE_SERVER_URL, "
            "MCP_OAUTH_FRAPPE_CLIENT_ID, and MCP_FRAPPE_SITE."
        )
    try:
        issuer_resource = canonicalize_mcp_resource(issuer)
        resource = canonicalize_mcp_resource(resource)
    except MCPResourceError as error:
        raise MCPIdentityConfigurationError(str(error)) from error
    issuer_parts = urlsplit(issuer_resource)
    if (
        not issuer_resource.rstrip("/")
        or issuer_parts.path not in {"", "/"}
    ):
        raise MCPIdentityConfigurationError("MCP_OAUTH_ISSUER_URL must be a canonical URL.")
    raw_scopes = os.environ.get(OAUTH_SCOPES_ENV_VAR, "")
    scopes: list[str] = []
    for scope in raw_scopes.replace(",", " ").split():
        if scope not in scopes:
            scopes.append(scope)
    if not scopes or any(any(ord(char) < 0x20 for char in scope) for scope in scopes):
        raise MCPIdentityConfigurationError(
            "MCP_OAUTH_REQUIRED_SCOPES must contain at least one valid scope."
        )
    return OAuthResourceServerSettings(
        issuer_url=issuer_resource,
        resource_server_url=resource,
        required_scopes=tuple(scopes),
        frappe_client_id=client_id,
        frappe_site=site,
    )


@dataclass(frozen=True)
class HTTPIdentityInputs:
    """Identity material copied from one HTTP request and never retained globally."""

    authorization: str | None
    user_email: str | None


def get_http_identity_inputs(headers: Mapping[str, str]) -> HTTPIdentityInputs:
    """Read the generic identity inputs from a request header mapping."""
    return HTTPIdentityInputs(
        authorization=headers.get("authorization"),
        user_email=headers.get(USER_EMAIL_HEADER)
        or headers.get(USER_EMAIL_HEADER.lower()),
    )


def get_http_shared_secret_from_environment() -> str | None:
    """Return the server-only shared secret without logging or exposing it."""
    return os.environ.get(HTTP_SHARED_SECRET_ENV_VAR)


def get_configured_frappe_user_from_environment() -> str | None:
    """Return the identity-owned stdio Frappe User configuration."""
    return os.environ.get(FRAPPE_USER_ENV_VAR)


def get_http_auth_mode_from_environment() -> HTTPAuthMode:
    """Parse the exact HTTP auth mode, defaulting only when it is absent."""
    if HTTP_AUTH_MODE_ENV_VAR not in os.environ:
        return HTTPAuthMode.TRUSTED_HEADER
    value = os.environ[HTTP_AUTH_MODE_ENV_VAR]
    try:
        return HTTPAuthMode(value)
    except ValueError as error:
        raise MCPIdentityConfigurationError(
            "MCP_HTTP_AUTH_MODE must be either 'trusted_header' or 'oauth'."
        ) from error


def validate_http_auth_configuration() -> HTTPAuthMode:
    """Validate the selected HTTP authentication mode for server startup."""
    mode = get_http_auth_mode_from_environment()
    if mode is HTTPAuthMode.OAUTH:
        get_oauth_resource_server_settings()
        return mode
    validate_http_shared_secret_configuration(get_http_shared_secret_from_environment())
    return mode


def validate_http_shared_secret_configuration(shared_secret: str | None) -> str:
    """Require the existing minimum secret strength before serving HTTP."""
    if not shared_secret or len(shared_secret) < MIN_SHARED_SECRET_LENGTH:
        raise MCPIdentityConfigurationError(
            "MCP_HTTP_SHARED_SECRET must be at least 32 characters for Streamable HTTP."
        )
    return shared_secret


def validate_bearer_secret(authorization: str | None, shared_secret: str) -> None:
    """Validate a complete Bearer credential using constant-time comparison."""
    if not authorization:
        raise MCPAuthenticationMissingError()
    if not authorization.startswith("Bearer "):
        raise MCPAuthenticationInvalidError()
    presented_secret = authorization.removeprefix("Bearer ")
    if not presented_secret or not hmac.compare_digest(presented_secret, shared_secret):
        raise MCPAuthenticationInvalidError()


def resolve_frappe_user_from_http(
    inputs: HTTPIdentityInputs, *, shared_secret: str
) -> str:
    """Authenticate one HTTP request and resolve its enabled Frappe User.

    The lookup intentionally happens before ``frappe.set_user`` because the
    request has not yet acquired a Frappe execution identity.
    """
    validate_bearer_secret(inputs.authorization, shared_secret)
    email = _normalized_email(inputs.user_email)
    user = frappe.db.get_value(
        "User", {"email": email}, ["name", "enabled"], as_dict=True
    )
    return _validated_user_name(user)


def resolve_configured_frappe_user(configured_user: str | None) -> str:
    """Resolve the configured stdio identity without applying it to Frappe."""
    user_name = (configured_user or "").strip()
    if not user_name:
        raise MCPUserIdentityMissingError()
    user = frappe.db.get_value("User", user_name, ["name", "enabled"], as_dict=True)
    return _validated_user_name(user)


def _normalized_email(value: str | None) -> str:
    email = (value or "").strip()
    if not email:
        raise MCPUserIdentityMissingError()
    try:
        parsed = Address(addr_spec=email)
    except (TypeError, ValueError) as error:
        raise MCPUserIdentityMissingError() from error
    if parsed.addr_spec != email or "@" not in email:
        raise MCPUserIdentityMissingError()
    return email


def _field_value(record: Any, fieldname: str) -> Any:
    if isinstance(record, dict):
        return record.get(fieldname)
    return getattr(record, fieldname, None)


def _validated_user_name(user: Any) -> str:
    user_name = _field_value(user, "name")
    if not user or not user_name or _is_guest(user_name):
        raise MCPUserNotFoundError()
    if not _is_enabled(_field_value(user, "enabled")):
        raise MCPUserDisabledError()
    return str(user_name)


def _is_enabled(value: Any) -> bool:
    return value not in {None, "", 0, "0", False, "false", "False"}


def _is_guest(value: Any) -> bool:
    return str(value).casefold() == "guest"
