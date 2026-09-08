from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from mcp_identity.identity import (
	HTTPIdentityInputs,
	MCPAuthenticationInvalidError,
	MCPAuthenticationMissingError,
	MCPUserDisabledError,
	MCPUserIdentityMissingError,
	MCPUserNotFoundError,
	resolve_frappe_user_from_http,
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

	def test_missing_or_blank_email_is_rejected_after_authentication(self):
		for email in (None, "   "):
			with self.subTest(email=email), self.assertRaises(MCPUserIdentityMissingError):
				self._resolve(email=email)
		self.frappe.db.get_value.assert_not_called()

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
