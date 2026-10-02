from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from mcp_identity.identity import (
    HTTPAuthMode,
    HTTPIdentityInputs,
    MCPAuthenticationInvalidError,
    MCPAuthenticationMissingError,
    MCPIdentityConfigurationError,
    MCPUserDisabledError,
    MCPUserIdentityMissingError,
    MCPUserNotFoundError,
    get_http_auth_mode_from_environment,
    resolve_configured_frappe_user,
    resolve_frappe_user_from_http,
    validate_bearer_secret,
    validate_http_auth_configuration,
)


SECRET = "this-is-a-development-only-secret-with-32-chars"


class HTTPIdentityResolutionTests(unittest.TestCase):
	def setUp(self) -> None:
		self.frappe = Mock()
		self.frappe_patch = patch("mcp_identity.identity.frappe", self.frappe)
		self.frappe_patch.start()
		self.addCleanup(self.frappe_patch.stop)

	def _resolve(self, authorization: str | None = None, email: str | None = "sales@example.com") -> str:
		return resolve_frappe_user_from_http(
			HTTPIdentityInputs(f"Bearer {SECRET}" if authorization is None else authorization, email),
			shared_secret=SECRET,
		)

	def test_missing_secret_is_rejected_before_any_user_lookup(self):
		with self.assertRaises(MCPAuthenticationMissingError):
			self._resolve(authorization="")
		self.frappe.db.get_value.assert_not_called()

	def test_wrong_secret_is_rejected_before_any_user_lookup(self):
		with self.assertRaises(MCPAuthenticationInvalidError):
			self._resolve(authorization="Bearer wrong-secret")
		self.frappe.db.get_value.assert_not_called()

	def test_malformed_secret_is_rejected_before_any_user_lookup(self):
		with self.assertRaises(MCPAuthenticationInvalidError):
			self._resolve(authorization="Basic value")
		self.frappe.db.get_value.assert_not_called()

	def test_missing_or_blank_email_is_rejected_after_authentication(self):
		for email in (None, "   "):
			with self.subTest(email=email), self.assertRaises(MCPUserIdentityMissingError):
				self._resolve(email=email)
		self.frappe.db.get_value.assert_not_called()

	def test_malformed_email_is_rejected_after_authentication(self):
		for email in ("not-an-email", "Name <sales@example.com>"):
			with self.subTest(email=email), self.assertRaises(MCPUserIdentityMissingError):
				self._resolve(email=email)
		self.frappe.db.get_value.assert_not_called()

	def test_email_whitespace_is_normalized_before_lookup(self):
		self.frappe.db.get_value.return_value = SimpleNamespace(name="sales@example.com", enabled=1)
		self.assertEqual(self._resolve(email=" sales@example.com "), "sales@example.com")
		self.frappe.db.get_value.assert_called_once_with(
			"User", {"email": "sales@example.com"}, ["name", "enabled"], as_dict=True
		)

	def test_unknown_user_is_rejected(self):
		self.frappe.db.get_value.return_value = None
		with self.assertRaises(MCPUserNotFoundError):
			self._resolve()

	def test_disabled_user_is_rejected(self):
		self.frappe.db.get_value.return_value = SimpleNamespace(name="sales@example.com", enabled=0)
		with self.assertRaises(MCPUserDisabledError):
			self._resolve()

	def test_enabled_user_is_resolved_from_the_generic_email_header_value(self):
		self.frappe.db.get_value.return_value = SimpleNamespace(name="sales@example.com", enabled=1)
		self.assertEqual(self._resolve(), "sales@example.com")
		self.assertEqual(
			self.frappe.db.get_value.call_args,
			call("User", {"email": "sales@example.com"}, ["name", "enabled"], as_dict=True),
		)

	def test_guest_is_rejected(self):
		self.frappe.db.get_value.return_value = SimpleNamespace(name="Guest", enabled=1)
		with self.assertRaises(MCPUserNotFoundError):
			self._resolve(email="guest@example.com")


class HTTPAuthConfigurationTests(unittest.TestCase):
	@patch.dict(os.environ, {}, clear=True)
	def test_absent_mode_defaults_to_trusted_header(self):
		self.assertEqual(get_http_auth_mode_from_environment(), HTTPAuthMode.TRUSTED_HEADER)

	@patch.dict(os.environ, {"MCP_HTTP_AUTH_MODE": "trusted_header"}, clear=True)
	def test_explicit_trusted_header_mode_is_accepted(self):
		self.assertEqual(get_http_auth_mode_from_environment(), HTTPAuthMode.TRUSTED_HEADER)

	@patch.dict(os.environ, {"MCP_HTTP_AUTH_MODE": "oauth"}, clear=True)
	def test_oauth_is_recognized_and_requires_its_configuration(self):
		self.assertEqual(get_http_auth_mode_from_environment(), HTTPAuthMode.OAUTH)
		with patch("mcp_identity.identity.get_http_shared_secret_from_environment") as get_secret:
			with self.assertRaisesRegex(MCPIdentityConfigurationError, "MCP_OAUTH_ISSUER_URL"):
				validate_http_auth_configuration()
		get_secret.assert_not_called()

	def test_blank_unknown_case_and_whitespace_variants_fail(self):
		for value in ("", "basic", "frappe_oauth", "TRUSTED_HEADER", " trusted_header"):
			with self.subTest(value=value), patch.dict(
				os.environ, {"MCP_HTTP_AUTH_MODE": value}, clear=True
			), self.assertRaisesRegex(MCPIdentityConfigurationError, "MCP_HTTP_AUTH_MODE"):
				get_http_auth_mode_from_environment()

	def test_trusted_header_requires_a_strong_secret(self):
		for secret in (None, "too-short"):
			environment = {"MCP_HTTP_AUTH_MODE": "trusted_header"}
			if secret is not None:
				environment["MCP_HTTP_SHARED_SECRET"] = secret
			with self.subTest(secret=secret), patch.dict(
				os.environ, environment, clear=True
			), self.assertRaisesRegex(MCPIdentityConfigurationError, "MCP_HTTP_SHARED_SECRET"):
				validate_http_auth_configuration()

	@patch.dict(
		os.environ,
		{"MCP_HTTP_AUTH_MODE": "trusted_header", "MCP_HTTP_SHARED_SECRET": SECRET},
		clear=True,
	)
	def test_trusted_header_with_a_strong_secret_is_valid(self):
		self.assertEqual(validate_http_auth_configuration(), HTTPAuthMode.TRUSTED_HEADER)


class BearerSecretTests(unittest.TestCase):
	def test_comparison_uses_constant_time_helper(self):
		with patch("mcp_identity.identity.hmac.compare_digest", return_value=True) as compare:
			validate_bearer_secret(f"Bearer {SECRET}", SECRET)
		compare.assert_called_once_with(SECRET, SECRET)


class ConfiguredFrappeUserTests(unittest.TestCase):
	def setUp(self) -> None:
		self.frappe = Mock()
		self.frappe_patch = patch("mcp_identity.identity.frappe", self.frappe)
		self.frappe_patch.start()
		self.addCleanup(self.frappe_patch.stop)

	def test_enabled_user_returns_canonical_name_without_setting_user(self):
		self.frappe.db.get_value.return_value = SimpleNamespace(
			name="canonical@example.com", enabled=1
		)
		self.assertEqual(
			resolve_configured_frappe_user(" configured@example.com "),
			"canonical@example.com",
		)
		self.frappe.db.get_value.assert_called_once_with(
			"User", "configured@example.com", ["name", "enabled"], as_dict=True
		)
		self.frappe.set_user.assert_not_called()

	def test_missing_unknown_disabled_and_guest_users_fail_closed(self):
		cases = (
			(None, None, MCPUserIdentityMissingError),
			("unknown@example.com", None, MCPUserNotFoundError),
			("disabled@example.com", SimpleNamespace(name="disabled@example.com", enabled=0), MCPUserDisabledError),
			("Guest", SimpleNamespace(name="Guest", enabled=1), MCPUserNotFoundError),
		)
		for configured_user, record, error_type in cases:
			with self.subTest(configured_user=configured_user):
				self.frappe.db.get_value.reset_mock()
				self.frappe.db.get_value.return_value = record
				with self.assertRaises(error_type):
					resolve_configured_frappe_user(configured_user)

	@patch.dict(os.environ, {}, clear=True)
	def test_stdio_resolver_does_not_require_http_configuration(self):
		self.frappe.db.get_value.return_value = SimpleNamespace(name="stdio@example.com", enabled=1)
		self.assertEqual(resolve_configured_frappe_user("stdio@example.com"), "stdio@example.com")
