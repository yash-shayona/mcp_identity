from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mcp_identity.identity import MCPIdentityConfigurationError, get_oauth_resource_server_settings
from mcp_identity.oauth_resource_server import FrappeOAuthTokenVerifier


RESOURCE = "https://mcp.example.com/mcp"


class Record(dict):
	__getattr__ = dict.__getitem__


class OAuthResourceSettingsTests(unittest.TestCase):
	@patch.dict(
		"os.environ",
		{
			"MCP_OAUTH_ISSUER_URL": "https://erp.example.com/",
			"MCP_OAUTH_RESOURCE_SERVER_URL": "HTTPS://MCP.Example.com:443/mcp/",
			"MCP_OAUTH_REQUIRED_SCOPES": "mcp:access, mcp:read mcp:access",
			"MCP_OAUTH_FRAPPE_CLIENT_ID": "client-a",
			"MCP_FRAPPE_SITE": "yob.localhost",
		},
		clear=True,
	)
	def test_oauth_settings_are_canonical_and_scopes_are_deterministic(self):
		settings = get_oauth_resource_server_settings()
		self.assertEqual(settings.issuer_url, "https://erp.example.com")
		self.assertEqual(settings.resource_server_url, RESOURCE)
		self.assertEqual(settings.required_scopes, ("mcp:access", "mcp:read"))

	@patch.dict("os.environ", {"MCP_OAUTH_ISSUER_URL": "not-a-url"}, clear=True)
	def test_missing_oauth_settings_fail_closed(self):
		with self.assertRaises(MCPIdentityConfigurationError):
			get_oauth_resource_server_settings()


class OAuthResourceVerifierTests(unittest.TestCase):
	def setUp(self):
		self.settings = SimpleNamespace(
			issuer_url="https://erp.example.com",
			resource_server_url=RESOURCE,
			required_scopes=("mcp:access",),
			frappe_client_id="client-a",
			frappe_site="yob.localhost",
		)
		self.db = SimpleNamespace(get_value=Mock())
		self.fake_frappe = SimpleNamespace(
			local=SimpleNamespace(initialised=True), db=self.db,
			utils=SimpleNamespace(get_datetime=lambda value: value), destroy=Mock(),
		)
		self.patch = patch("mcp_identity.oauth_resource_server.frappe", self.fake_frappe)
		self.patch.start()
		self.addCleanup(self.patch.stop)

	def _verifier(self, **changes):
		values = {**self.settings.__dict__, **changes}
		return FrappeOAuthTokenVerifier(SimpleNamespace(**values))

	def _rows(self, *, token_resource=RESOURCE, client_resource=RESOURCE, scopes="mcp:access", status="Active", user="sales@example.com", expires=None):
		self.db.get_value.side_effect = [
			Record(name="token", client="client-a", user=user, scopes=scopes, status=status, expiration_time=expires, custom_mcp_resource=token_resource),
			Record(name="client-a", client_id="client-a", custom_mcp_resource=client_resource),
			Record(name=user, enabled=1),
		]

	def test_valid_token_returns_native_user_and_recorded_scopes(self):
		self._rows()
		result = asyncio.run(self._verifier().verify_token("opaque-token"))
		self.assertEqual(result.subject, "sales@example.com")
		self.assertEqual(result.client_id, "client-a")
		self.assertEqual(result.resource, RESOURCE)

	def test_token_must_match_client_resource_and_required_scopes(self):
		for changes in (
			{"token_resource": "https://other.example.com/mcp"},
			{"client_resource": "https://other.example.com/mcp"},
			{"scopes": "openid"},
			{"status": "Revoked"},
			{"user": "Guest"},
		):
			with self.subTest(changes=changes):
				self._rows(**changes)
				self.assertIsNone(asyncio.run(self._verifier().verify_token("opaque-token")))
				self.db.get_value.reset_mock()

	def test_expired_token_and_database_errors_fail_closed(self):
		self._rows(expires=datetime.now(timezone.utc) - timedelta(seconds=1))
		self.assertIsNone(asyncio.run(self._verifier().verify_token("opaque-token")))
		self.db.get_value.reset_mock(side_effect=True)
		self.db.get_value.side_effect = RuntimeError("database unavailable")
		self.assertIsNone(asyncio.run(self._verifier().verify_token("opaque-token")))
