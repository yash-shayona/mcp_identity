"""Frappe OAuth compatibility layer for RFC 8707 MCP resource binding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from frappe.integrations import oauth2 as frappe_oauth2
from frappe.oauth import OAuthWebRequestValidator
from frappe.utils import get_datetime, now_datetime
from oauthlib.oauth2 import InvalidRequestError, OAuth2Error
from oauthlib.openid.connect.core.endpoints.pre_configured import (
    Server as WebApplicationServer,
)

from mcp_identity.resource import MCPResourceError, canonicalize_mcp_resource

RESOURCE_FIELD = "custom_mcp_resource"
_BINDING_FLAG = "mcp_oauth_resource_binding"


class InvalidTargetError(OAuth2Error):
    """RFC 8707 error for a missing, malformed, or unacceptable resource."""

    error = "invalid_target"
    description = "The requested OAuth resource is invalid or unavailable."


@dataclass(frozen=True)
class _IssuanceBinding:
    grant_kind: str
    client: str
    resource: str
    source_name: str | None = None


class MCPResourceBindingOAuthValidator(OAuthWebRequestValidator):
    """Extend the installed Frappe validator only for explicitly bound clients."""

    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):
        if not super().validate_scopes(
            client_id, scopes, client, request, *args, **kwargs
        ):
            return False
        resource = _client_resource(client_id, request=request)
        if not resource:
            return True
        _validate_requested_resource(request, resource)
        if (
            not request.code_challenge
            or (request.code_challenge_method or "").upper() != "S256"
        ):
            raise InvalidRequestError(
                description="This resource requires a non-empty S256 PKCE challenge.",
                request=request,
            )
        _set_binding(_IssuanceBinding("authorization", client_id, resource))
        return True

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        client_resource = _client_resource(client_id, request=request)
        stored_resource = frappe.db.get_value(
            "OAuth Authorization Code", code, RESOURCE_FIELD
        )
        if not client_resource and not stored_resource:
            return super().validate_code(
                client_id, code, client, request, *args, **kwargs
            )

        record = frappe.db.get_value(
            "OAuth Authorization Code",
            {"name": code, "client": client_id, "validity": "Valid"},
            [
                "name",
                "client",
                "validity",
                "expiration_time",
                "user",
                "code_challenge",
                "code_challenge_method",
                RESOURCE_FIELD,
            ],
            as_dict=True,
            for_update=True,
        )
        if not record:
            return False
        expiration_time = _value(record, "expiration_time")
        if expiration_time and now_datetime() >= get_datetime(expiration_time):
            return False
        if not _valid_token_user(_value(record, "user")):
            return False
        resource = _canonical_persisted_resource(
            _value(record, RESOURCE_FIELD), request
        )
        if not client_resource or resource != client_resource:
            raise InvalidTargetError(request=request)
        _validate_requested_resource(request, resource)
        if (
            not _value(record, "code_challenge")
            or str(_value(record, "code_challenge_method") or "").upper() != "S256"
        ):
            return False
        if not getattr(request, "code_verifier", None):
            return False
        if not super().validate_code(client_id, code, client, request, *args, **kwargs):
            return False
        _set_binding(
            _IssuanceBinding(
                "authorization_code", client_id, resource, str(_value(record, "name"))
            )
        )
        return True

    def validate_refresh_token(self, refresh_token, client, request, *args, **kwargs):
        client_name = _client_name(client, request)
        preliminary_source = frappe.db.get_value(
            "OAuth Bearer Token",
            {"refresh_token": refresh_token, "status": "Active"},
            ["name", "client", RESOURCE_FIELD],
            as_dict=True,
        )
        if not preliminary_source:
            return False
        stored_resource = _value(preliminary_source, RESOURCE_FIELD)
        client_resource = _client_resource(client_name, request=request)
        if not stored_resource and not client_resource:
            return super().validate_refresh_token(
                refresh_token, client, request, *args, **kwargs
            )

        source = frappe.db.get_value(
            "OAuth Bearer Token",
            {"refresh_token": refresh_token, "status": "Active"},
            ["name", "client", "user", "scopes", "status", RESOURCE_FIELD],
            as_dict=True,
            for_update=True,
        )
        if not source:
            return False
        stored_resource = _value(source, RESOURCE_FIELD)
        if str(_value(source, "client")) != client_name:
            return False
        resource = _canonical_persisted_resource(stored_resource, request)
        if not client_resource or resource != client_resource:
            raise InvalidTargetError(request=request)
        _validate_requested_resource(request, resource)
        if not _valid_token_user(_value(source, "user")):
            return False
        if not super().validate_refresh_token(
            refresh_token, client, request, *args, **kwargs
        ):
            return False
        _set_binding(
            _IssuanceBinding(
                "refresh_token", client_name, resource, str(_value(source, "name"))
            )
        )
        return True


def install_mcp_oauth_validator_for_request() -> None:
    """Install a fresh compatibility server in this Frappe request only."""
    _clear_binding()
    frappe.local.oauth_server = WebApplicationServer(MCPResourceBindingOAuthValidator())


def validate_oauth_client_resource(doc, method=None) -> None:
    """Canonicalize the optional site-controlled OAuth Client trust anchor."""
    value = (getattr(doc, RESOURCE_FIELD, None) or "").strip()
    if not value:
        setattr(doc, RESOURCE_FIELD, None)
        return
    try:
        setattr(doc, RESOURCE_FIELD, canonicalize_mcp_resource(value))
    except MCPResourceError as error:
        raise frappe.ValidationError(str(error)) from error


def bind_authorization_code_before_insert(doc, method=None) -> None:
    """Persist only a resource verified in the current authorization request."""
    client = str(getattr(doc, "client", "") or "")
    client_resource = _client_resource(client)
    if not client_resource:
        return
    state = _get_binding()
    if not state or state.grant_kind != "authorization" or state.client != client:
        raise frappe.ValidationError(
            "Bound OAuth authorization code lacks verified request resource state."
        )
    setattr(doc, RESOURCE_FIELD, state.resource)


def bind_bearer_token_before_insert(doc, method=None) -> None:
    """Bind the replacement token and consume its locked source atomically."""
    client = str(getattr(doc, "client", "") or "")
    client_resource = _client_resource(client)
    state = _get_binding()
    if not client_resource and not state:
        return
    if (
        not state
        or state.client != client
        or state.resource != client_resource
        or not state.source_name
    ):
        raise frappe.ValidationError(
            "Bound OAuth token issuance lacks verified source state."
        )

    if state.grant_kind == "authorization_code":
        source = frappe.db.get_value(
            "OAuth Authorization Code",
            {"name": state.source_name, "client": client, "validity": "Valid"},
            ["name", RESOURCE_FIELD],
            as_dict=True,
            for_update=True,
        )
        if not source or _canonical_stored_for_event(source) != state.resource:
            raise frappe.ValidationError(
                "Bound OAuth authorization code is no longer valid."
            )
        frappe.db.set_value(
            "OAuth Authorization Code",
            state.source_name,
            "validity",
            "Invalid",
            update_modified=False,
        )
    elif state.grant_kind == "refresh_token":
        source = frappe.db.get_value(
            "OAuth Bearer Token",
            {"name": state.source_name, "client": client, "status": "Active"},
            ["name", RESOURCE_FIELD],
            as_dict=True,
            for_update=True,
        )
        if not source or _canonical_stored_for_event(source) != state.resource:
            raise frappe.ValidationError(
                "Bound OAuth refresh token is no longer active."
            )
        frappe.db.set_value(
            "OAuth Bearer Token",
            state.source_name,
            "status",
            "Revoked",
            update_modified=False,
        )
    else:
        raise frappe.ValidationError("Unsupported bound OAuth grant state.")
    setattr(doc, RESOURCE_FIELD, state.resource)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def authorize(**kwargs):
    install_mcp_oauth_validator_for_request()
    return frappe_oauth2.authorize(**kwargs)


@frappe.whitelist(methods=["POST"])
def approve(*args, **kwargs):
    install_mcp_oauth_validator_for_request()
    return frappe_oauth2.approve(*args, **kwargs)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def get_token(*args, **kwargs):
    install_mcp_oauth_validator_for_request()
    return frappe_oauth2.get_token(*args, **kwargs)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def revoke_token(*args, **kwargs):
    install_mcp_oauth_validator_for_request()
    return frappe_oauth2.revoke_token(*args, **kwargs)


def _validate_requested_resource(request, expected: str) -> str:
    if "resource" in getattr(request, "duplicate_params", ()):
        raise InvalidTargetError(request=request)
    value = _request_resource_value(request)
    if not isinstance(value, str) or not value:
        raise InvalidTargetError(request=request)
    try:
        resource = canonicalize_mcp_resource(value)
    except MCPResourceError as error:
        raise InvalidTargetError(request=request) from error
    if resource != expected:
        raise InvalidTargetError(request=request)
    return resource


def _request_resource_value(request) -> Any:
    """Retain duplicate detection when Frappe passes a Werkzeug MultiDict.

    oauthlib preserves duplicates for raw authorization bodies and query
    strings, but Frappe's token endpoint passes ``request.form``. oauthlib
    treats that dict-like object as a normal dict and otherwise loses repeated
    keys before ``duplicate_params`` is built.
    """
    http_request = getattr(frappe, "request", None)
    form = getattr(http_request, "form", None)
    getlist = getattr(form, "getlist", None)
    if callable(getlist):
        values = getlist("resource")
        if len(values) > 1:
            raise InvalidTargetError(request=request)
        if len(values) == 1:
            return values[0]
    return getattr(request, "resource", None)


def _client_resource(client_name: str, *, request=None) -> str | None:
    raw = frappe.db.get_value("OAuth Client", client_name, RESOURCE_FIELD)
    if not raw:
        return None
    try:
        return canonicalize_mcp_resource(str(raw))
    except MCPResourceError as error:
        raise InvalidTargetError(request=request) from error


def _canonical_persisted_resource(value: Any, request) -> str:
    if not value:
        raise InvalidTargetError(request=request)
    try:
        return canonicalize_mcp_resource(str(value))
    except MCPResourceError as error:
        raise InvalidTargetError(request=request) from error


def _canonical_stored_for_event(record: Any) -> str | None:
    value = _value(record, RESOURCE_FIELD)
    if not value:
        return None
    try:
        return canonicalize_mcp_resource(str(value))
    except MCPResourceError as error:
        raise frappe.ValidationError(
            "Persisted OAuth resource binding is invalid."
        ) from error


def _valid_token_user(user_name: Any) -> bool:
    if not user_name or str(user_name).casefold() == "guest":
        return False
    return bool(frappe.db.exists("User", {"name": user_name, "enabled": 1}))


def _client_name(client: Any, request: Any) -> str:
    for candidate in (
        _value(client, "name"),
        _value(client, "client_id"),
        getattr(request, "client_id", None),
    ):
        if candidate:
            return str(candidate)
    return ""


def _value(record: Any, fieldname: str) -> Any:
    if isinstance(record, dict):
        return record.get(fieldname)
    return getattr(record, fieldname, None)


def _set_binding(binding: _IssuanceBinding) -> None:
    setattr(frappe.flags, _BINDING_FLAG, binding)


def _get_binding() -> _IssuanceBinding | None:
    return getattr(frappe.flags, _BINDING_FLAG, None)


def _clear_binding() -> None:
    frappe.flags.pop(_BINDING_FLAG, None)
