from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from frappe import _dict
from frappe.oauth import OAuthWebRequestValidator
from oauthlib.oauth2 import InvalidRequestError

import mcp_identity.hooks as app_hooks
from mcp_identity.oauth_compat import (
	InvalidTargetError,
	MCPResourceBindingOAuthValidator,
	_IssuanceBinding,
	bind_authorization_code_before_insert,
	bind_bearer_token_before_insert,
	install_mcp_oauth_validator_for_request,
	validate_oauth_client_resource,
)

RESOURCE = "https://mcp.example.com/mcp"


class FakeValidationError(Exception):
	pass


class FakeDB:
	def __init__(self):
		self.get_value = Mock()
		self.exists = Mock(return_value=True)
		self.set_value = Mock()


class OAuthCompatibilityTestCase(unittest.TestCase):
	def setUp(self):
		self.fake_frappe = SimpleNamespace(
			db=FakeDB(), flags=_dict(), local=SimpleNamespace(), request=None,
			ValidationError=FakeValidationError,
		)
		self.frappe_patch = patch("mcp_identity.oauth_compat.frappe", self.fake_frappe)
		self.frappe_patch.start()
		self.addCleanup(self.frappe_patch.stop)

	def request(self, **values):
		defaults = {
			"resource": RESOURCE,
			"duplicate_params": [],
			"code_challenge": "challenge",
			"code_challenge_method": "S256",
			"client_id": "client-a",
			"redirect_uri": "https://client.example.com/callback",
			"scopes": ["all"],
			"response_type": "code",
			"response_mode": None,
			"grant_type": "authorization_code",
			"state": None,
		}
		defaults.update(values)
		return SimpleNamespace(**defaults)


class OAuthClientValidationTests(OAuthCompatibilityTestCase):
	def test_blank_binding_remains_allowed(self):
		doc = SimpleNamespace(custom_mcp_resource="  ")
		validate_oauth_client_resource(doc)
		self.assertIsNone(doc.custom_mcp_resource)

	def test_binding_is_canonicalized_and_invalid_value_fails(self):
		doc = SimpleNamespace(custom_mcp_resource="HTTPS://MCP.Example.com:443/mcp/")
		validate_oauth_client_resource(doc)
		self.assertEqual(doc.custom_mcp_resource, RESOURCE)
		with self.assertRaises(FakeValidationError):
			validate_oauth_client_resource(SimpleNamespace(custom_mcp_resource="http://example.com/mcp"))


class AuthorizationBindingTests(OAuthCompatibilityTestCase):
	def setUp(self):
		super().setUp()
		self.validator = MCPResourceBindingOAuthValidator()

	@patch.object(OAuthWebRequestValidator, "validate_scopes", return_value=True)
	def test_bound_authorization_requires_one_matching_resource_and_s256(self, native):
		self.fake_frappe.db.get_value.return_value = RESOURCE
		request = self.request()
		self.assertTrue(self.validator.validate_scopes("client-a", ["all"], {}, request))
		native.assert_called_once()
		state = self.fake_frappe.flags.mcp_oauth_resource_binding
		self.assertEqual(state, _IssuanceBinding("authorization", "client-a", RESOURCE))

		for overrides in (
			{"resource": None},
			{"resource": ""},
			{"resource": "https://other.example.com/mcp"},
			{"resource": "not-a-url"},
			{"duplicate_params": ["resource"]},
		):
			with self.subTest(overrides=overrides), self.assertRaises(InvalidTargetError):
				self.validator.validate_scopes("client-a", ["all"], {}, self.request(**overrides))
		for overrides in ({"code_challenge": None}, {"code_challenge_method": "plain"}):
			with self.subTest(overrides=overrides), self.assertRaises(InvalidRequestError):
				self.validator.validate_scopes("client-a", ["all"], {}, self.request(**overrides))

		self.fake_frappe.request = SimpleNamespace(
			form=SimpleNamespace(getlist=lambda key: [RESOURCE, RESOURCE] if key == "resource" else [])
		)
		with self.assertRaises(InvalidTargetError):
			self.validator.validate_scopes("client-a", ["all"], {}, self.request())

	@patch.object(OAuthWebRequestValidator, "validate_scopes", return_value=True)
	def test_unbound_authorization_is_native(self, native):
		self.fake_frappe.db.get_value.return_value = None
		self.assertTrue(self.validator.validate_scopes("client-a", ["all"], {}, self.request(resource=None)))
		native.assert_called_once()
		self.assertNotIn("mcp_oauth_resource_binding", self.fake_frappe.flags)

	@patch.object(OAuthWebRequestValidator, "validate_scopes", return_value=False)
	def test_native_scope_failure_wins_before_resource_checks(self, native):
		self.assertFalse(self.validator.validate_scopes("client-a", ["bad"], {}, self.request()))
		self.fake_frappe.db.get_value.assert_not_called()

	def test_authorization_code_event_binds_only_verified_matching_state(self):
		self.fake_frappe.db.get_value.return_value = RESOURCE
		doc = SimpleNamespace(client="client-a")
		self.fake_frappe.flags.mcp_oauth_resource_binding = _IssuanceBinding(
			"authorization", "client-a", RESOURCE
		)
		bind_authorization_code_before_insert(doc)
		self.assertEqual(doc.custom_mcp_resource, RESOURCE)

		del self.fake_frappe.flags.mcp_oauth_resource_binding
		with self.assertRaises(FakeValidationError):
			bind_authorization_code_before_insert(SimpleNamespace(client="client-a"))

	def test_unbound_authorization_code_event_is_noop(self):
		self.fake_frappe.db.get_value.return_value = None
		doc = SimpleNamespace(client="client-a")
		bind_authorization_code_before_insert(doc)
		self.assertFalse(hasattr(doc, "custom_mcp_resource"))


class CodeExchangeTests(OAuthCompatibilityTestCase):
	def setUp(self):
		super().setUp()
		self.validator = MCPResourceBindingOAuthValidator()

	def _db_lookup(self, doctype, filters, fieldname="name", **kwargs):
		if doctype == "OAuth Client":
			return RESOURCE
		if isinstance(filters, str) and fieldname == "custom_mcp_resource":
			return RESOURCE
		return {
			"name": "code-record", "client": "client-a", "validity": "Valid",
			"expiration_time": None, "user": "user@example.com",
			"code_challenge": "challenge", "code_challenge_method": "s256",
			"custom_mcp_resource": RESOURCE,
		}

	@patch.object(OAuthWebRequestValidator, "validate_code", return_value=True)
	def test_bound_code_is_locked_validated_and_records_source_state(self, native):
		self.fake_frappe.db.get_value.side_effect = self._db_lookup
		self.assertTrue(
			self.validator.validate_code("client-a", "code-record", {}, self.request(code_verifier="v"))
		)
		locked = [item for item in self.fake_frappe.db.get_value.call_args_list if item.kwargs.get("for_update")]
		self.assertEqual(len(locked), 1)
		self.assertEqual(
			self.fake_frappe.flags.mcp_oauth_resource_binding,
			_IssuanceBinding("authorization_code", "client-a", RESOURCE, "code-record"),
		)

	@patch.object(OAuthWebRequestValidator, "validate_code", return_value=True)
	def test_code_resource_change_and_non_s256_are_rejected(self, native):
		self.fake_frappe.db.get_value.side_effect = self._db_lookup
		with self.assertRaises(InvalidTargetError):
			self.validator.validate_code(
				"client-a", "code-record", {}, self.request(resource="https://other.example.com/mcp", code_verifier="v")
			)
		native.assert_not_called()

		def plain_lookup(doctype, filters, fieldname="name", **kwargs):
			result = self._db_lookup(doctype, filters, fieldname, **kwargs)
			if isinstance(result, dict):
				result["code_challenge_method"] = "plain"
			return result

		self.fake_frappe.db.get_value.side_effect = plain_lookup
		self.assertFalse(
			self.validator.validate_code("client-a", "code-record", {}, self.request(code_verifier="v"))
		)

	@patch.object(OAuthWebRequestValidator, "validate_code", return_value=True)
	def test_code_missing_or_duplicate_resource_and_expiry_fail_before_native_issuance(self, native):
		self.fake_frappe.db.get_value.side_effect = self._db_lookup
		for request in (
			self.request(resource=None, code_verifier="v"),
			self.request(duplicate_params=["resource"], code_verifier="v"),
		):
			with self.subTest(request=request), self.assertRaises(InvalidTargetError):
				self.validator.validate_code("client-a", "code-record", {}, request)

		def expired_lookup(doctype, filters, fieldname="name", **kwargs):
			result = self._db_lookup(doctype, filters, fieldname, **kwargs)
			if isinstance(result, dict):
				result["expiration_time"] = datetime.now() - timedelta(minutes=1)
			return result

		self.fake_frappe.db.get_value.side_effect = expired_lookup
		with patch("mcp_identity.oauth_compat.now_datetime", return_value=datetime.now()):
			self.assertFalse(
				self.validator.validate_code("client-a", "code-record", {}, self.request(code_verifier="v"))
			)
		native.assert_not_called()

	@patch.object(OAuthWebRequestValidator, "validate_code", return_value=True)
	def test_unbound_code_path_delegates_unchanged(self, native):
		self.fake_frappe.db.get_value.return_value = None
		self.assertTrue(self.validator.validate_code("client-a", "code", {}, self.request(resource=None)))
		native.assert_called_once()

	def test_bearer_event_invalidates_code_before_native_commit(self):
		self.fake_frappe.db.get_value.side_effect = [
			RESOURCE,
			{"name": "code-record", "custom_mcp_resource": RESOURCE},
		]
		self.fake_frappe.flags.mcp_oauth_resource_binding = _IssuanceBinding(
			"authorization_code", "client-a", RESOURCE, "code-record"
		)
		doc = SimpleNamespace(client="client-a")
		bind_bearer_token_before_insert(doc)
		self.assertEqual(doc.custom_mcp_resource, RESOURCE)
		self.fake_frappe.db.set_value.assert_called_once_with(
			"OAuth Authorization Code", "code-record", "validity", "Invalid", update_modified=False
		)

	def test_bearer_event_fails_closed_when_locked_code_was_already_consumed(self):
		self.fake_frappe.db.get_value.side_effect = [RESOURCE, None]
		self.fake_frappe.flags.mcp_oauth_resource_binding = _IssuanceBinding(
			"authorization_code", "client-a", RESOURCE, "code-record"
		)
		with self.assertRaises(FakeValidationError):
			bind_bearer_token_before_insert(SimpleNamespace(client="client-a"))
		self.fake_frappe.db.set_value.assert_not_called()


class RefreshRotationTests(OAuthCompatibilityTestCase):
	def setUp(self):
		super().setUp()
		self.validator = MCPResourceBindingOAuthValidator()

	def _db_lookup(self, doctype, filters, fieldname="name", **kwargs):
		if doctype == "OAuth Client":
			return RESOURCE
		return {
			"name": "old-token", "client": "client-a", "user": "user@example.com",
			"scopes": "all", "status": "Active", "custom_mcp_resource": RESOURCE,
		}

	@patch.object(OAuthWebRequestValidator, "validate_refresh_token", return_value=True)
	def test_bound_refresh_locks_and_preserves_authoritative_identity(self, native):
		self.fake_frappe.db.get_value.side_effect = self._db_lookup
		request = self.request()
		client = {"name": "client-a", "client_id": "client-a"}
		self.assertTrue(self.validator.validate_refresh_token("secret", client, request))
		self.fake_frappe.db.exists.assert_called_once_with(
			"User", {"name": "user@example.com", "enabled": 1}
		)
		self.assertEqual(
			self.fake_frappe.flags.mcp_oauth_resource_binding,
			_IssuanceBinding("refresh_token", "client-a", RESOURCE, "old-token"),
		)

	@patch.object(OAuthWebRequestValidator, "validate_refresh_token", return_value=True)
	def test_refresh_rejects_resource_client_and_user_changes(self, native):
		self.fake_frappe.db.get_value.side_effect = self._db_lookup
		with self.assertRaises(InvalidTargetError):
			self.validator.validate_refresh_token(
				"secret", {"name": "client-a"}, self.request(resource="https://other.example.com/mcp")
			)

		self.fake_frappe.db.get_value.side_effect = self._db_lookup
		self.assertFalse(
			self.validator.validate_refresh_token("secret", {"name": "client-b"}, self.request())
		)

		self.fake_frappe.db.get_value.side_effect = self._db_lookup
		self.fake_frappe.db.exists.return_value = False
		self.assertFalse(
			self.validator.validate_refresh_token("secret", {"name": "client-a"}, self.request())
		)

		def guest_lookup(doctype, filters, fieldname="name", **kwargs):
			result = self._db_lookup(doctype, filters, fieldname, **kwargs)
			if isinstance(result, dict):
				result["user"] = "Guest"
			return result

		self.fake_frappe.db.get_value.side_effect = guest_lookup
		self.assertFalse(
			self.validator.validate_refresh_token("secret", {"name": "client-a"}, self.request())
		)

		def changed_client_binding(doctype, filters, fieldname="name", **kwargs):
			if doctype == "OAuth Client":
				return "https://other.example.com/mcp"
			return self._db_lookup(doctype, filters, fieldname, **kwargs)

		self.fake_frappe.db.get_value.side_effect = changed_client_binding
		with self.assertRaises(InvalidTargetError):
			self.validator.validate_refresh_token("secret", {"name": "client-a"}, self.request())

	@patch.object(OAuthWebRequestValidator, "validate_refresh_token", return_value=True)
	def test_refresh_missing_or_duplicate_resource_fails_and_unbound_refresh_stays_native(self, native):
		for request in (self.request(resource=None), self.request(duplicate_params=["resource"])):
			self.fake_frappe.db.get_value.side_effect = self._db_lookup
			with self.subTest(request=request), self.assertRaises(InvalidTargetError):
				self.validator.validate_refresh_token("secret", {"name": "client-a"}, request)

		self.fake_frappe.db.get_value.reset_mock()
		self.fake_frappe.db.get_value.side_effect = [
			{
				"name": "old-token", "client": "client-a", "user": "user@example.com",
				"scopes": "all", "status": "Active", "custom_mcp_resource": None,
			},
			None,
		]
		self.assertTrue(
			self.validator.validate_refresh_token("secret", {"name": "client-a"}, self.request(resource=None))
		)
		native.assert_called_once()
		self.assertFalse(
			any(call.kwargs.get("for_update") for call in self.fake_frappe.db.get_value.call_args_list)
		)

	def test_bearer_event_revokes_refresh_source_before_native_commit(self):
		self.fake_frappe.db.get_value.side_effect = [
			RESOURCE,
			{"name": "old-token", "custom_mcp_resource": RESOURCE},
		]
		self.fake_frappe.flags.mcp_oauth_resource_binding = _IssuanceBinding(
			"refresh_token", "client-a", RESOURCE, "old-token"
		)
		doc = SimpleNamespace(client="client-a")
		bind_bearer_token_before_insert(doc)
		self.assertEqual(doc.custom_mcp_resource, RESOURCE)
		self.fake_frappe.db.set_value.assert_called_once_with(
			"OAuth Bearer Token", "old-token", "status", "Revoked", update_modified=False
		)

	def test_bearer_event_requires_matching_request_local_state(self):
		self.fake_frappe.db.get_value.return_value = RESOURCE
		with self.assertRaises(FakeValidationError):
			bind_bearer_token_before_insert(SimpleNamespace(client="client-a"))
		self.fake_frappe.db.set_value.assert_not_called()


class RequestRoutingTests(OAuthCompatibilityTestCase):
	def test_all_native_oauth_commands_are_overridden_by_thin_wrappers(self):
		expected = {
			"frappe.integrations.oauth2.authorize": "mcp_identity.oauth_compat.authorize",
			"frappe.integrations.oauth2.approve": "mcp_identity.oauth_compat.approve",
			"frappe.integrations.oauth2.get_token": "mcp_identity.oauth_compat.get_token",
			"frappe.integrations.oauth2.revoke_token": "mcp_identity.oauth_compat.revoke_token",
		}
		self.assertEqual(app_hooks.override_whitelisted_methods, expected)

	def test_each_supported_rpc_dispatcher_resolves_whitelisted_overrides(self):
		frappe_root = Path(inspect.getfile(OAuthWebRequestValidator)).parent
		handler_source = (frappe_root / "handler.py").read_text()
		v1_source = (frappe_root / "api" / "v1.py").read_text()
		v2_source = (frappe_root / "api" / "v2.py").read_text()
		self.assertIn("override_whitelisted_method(cmd)", handler_source)
		self.assertIn("frappe.handler.handle()", v1_source)
		self.assertIn("override_whitelisted_method(method)", v2_source)

	def test_request_installation_is_local_fresh_and_clears_prior_state(self):
		self.fake_frappe.flags.mcp_oauth_resource_binding = "old"
		self.fake_frappe.flags.unrelated = "preserve"
		install_mcp_oauth_validator_for_request()
		first = self.fake_frappe.local.oauth_server
		self.assertNotIn("mcp_oauth_resource_binding", self.fake_frappe.flags)
		self.assertEqual(self.fake_frappe.flags.unrelated, "preserve")
		install_mcp_oauth_validator_for_request()
		self.assertIsNot(first, self.fake_frappe.local.oauth_server)

	def test_clear_missing_real_frappe_dict_binding_is_idempotent(self):
		from mcp_identity.oauth_compat import _clear_binding

		self.fake_frappe.flags.unrelated = "preserve"
		self.assertTrue(hasattr(self.fake_frappe.flags, "mcp_oauth_resource_binding"))
		_clear_binding()
		_clear_binding()
		self.assertNotIn("mcp_oauth_resource_binding", self.fake_frappe.flags)
		self.assertEqual(self.fake_frappe.flags.unrelated, "preserve")

	def test_each_endpoint_wrapper_installs_fresh_state_before_delegating(self):
		from mcp_identity import oauth_compat

		for name in ("authorize", "approve", "get_token", "revoke_token"):
			with self.subTest(name=name):
				self.fake_frappe.flags.mcp_oauth_resource_binding = "stale"
				with patch.object(
					oauth_compat.frappe_oauth2,
					name,
					return_value=name,
				) as native:
					with patch.object(
						oauth_compat,
						"install_mcp_oauth_validator_for_request",
						wraps=oauth_compat.install_mcp_oauth_validator_for_request,
					) as install:
						self.assertEqual(getattr(oauth_compat, name)(value="x"), name)
					install.assert_called_once_with()
					native.assert_called_once_with(value="x")
					self.assertNotIn("mcp_oauth_resource_binding", self.fake_frappe.flags)

	@patch("mcp_identity.oauth_compat.frappe_oauth2.get_token", return_value="native")
	@patch("mcp_identity.oauth_compat.install_mcp_oauth_validator_for_request")
	def test_endpoint_wrapper_installs_then_delegates(self, install, native):
		from mcp_identity.oauth_compat import get_token

		self.assertEqual(get_token(example="value"), "native")
		self.assertEqual([install.mock_calls, native.mock_calls], [[call()], [call(example="value")]])
