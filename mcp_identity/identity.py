"""Generic trusted HTTP request identity resolution for Frappe consumers."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from email.headerregistry import Address
from typing import Any, Mapping

import frappe

USER_EMAIL_HEADER = "X-MCP-User-Email"
MIN_SHARED_SECRET_LENGTH = 32


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
class HTTPIdentityInputs:
	"""Identity material copied from one HTTP request and never retained globally."""

	authorization: str | None
	user_email: str | None


def get_http_identity_inputs(headers: Mapping[str, str]) -> HTTPIdentityInputs:
	"""Read the generic identity inputs from a request header mapping."""
	return HTTPIdentityInputs(
		authorization=headers.get("authorization"),
		user_email=headers.get(USER_EMAIL_HEADER) or headers.get(USER_EMAIL_HEADER.lower()),
	)


def get_http_shared_secret_from_environment() -> str | None:
	"""Return the server-only shared secret without logging or exposing it."""
	import os

	return os.environ.get("MCP_HTTP_SHARED_SECRET")


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
	user = frappe.db.get_value("User", {"email": email}, ["name", "enabled"], as_dict=True)
	if not user or not _field_value(user, "name") or _is_guest(_field_value(user, "name")):
		raise MCPUserNotFoundError()
	if not _is_enabled(_field_value(user, "enabled")):
		raise MCPUserDisabledError()
	return str(_field_value(user, "name"))


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


def _is_enabled(value: Any) -> bool:
	return value not in {None, "", 0, "0", False, "false", "False"}


def _is_guest(value: Any) -> bool:
	return str(value).casefold() == "guest"
