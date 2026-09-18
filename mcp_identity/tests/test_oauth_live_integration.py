"""Live-site integration coverage for the Task 04 Frappe OAuth extension.

These tests use Frappe's real RPC dispatch, oauthlib server, document events,
and database records. Run them only on an explicitly approved local test site.
"""

from __future__ import annotations

import base64
import hashlib
import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlparse

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_test_client

from mcp_identity.oauth_compat import MCPResourceBindingOAuthValidator

RUN_DB_TESTS = os.environ.get("MCP_IDENTITY_RUN_OAUTH_DB_TESTS") == "1"
RESOURCE = "https://mcp.example.invalid/mcp"
REDIRECT_URI = "https://client.example.invalid/callback"
SCOPE = "mcp:access"
VERIFIER = "mcp-identity-live-verification-code-verifier-0123456789"


def _s256_challenge(verifier: str) -> str:
	return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def _make_request(*, target, args, kwargs, site):
	result = []

	def run():
		with patch("frappe.app.get_site_name", return_value=site):
			result.append(target(*args, **kwargs))

	thread = threading.Thread(target=run)
	thread.start()
	thread.join()
	return result[0]


@unittest.skipUnless(RUN_DB_TESTS, "requires an explicitly approved isolated Frappe test site")
class OAuthLiveIntegrationTests(IntegrationTestCase):
	site = getattr(frappe.local, "site", None)

	def setUp(self):
		super().setUp()
		self.test_client = get_test_client()
		self.form_header = {"content-type": "application/x-www-form-urlencoded"}
		self.client_name = self._create_client(bound=True)
		frappe.db.commit()
		self.test_client.set_cookie(key="sid", value=self._administrator_sid())

	def tearDown(self):
		frappe.db.delete("OAuth Authorization Code", {"client": self.client_name})
		frappe.db.delete("OAuth Bearer Token", {"client": self.client_name})
		frappe.db.delete("OAuth Client", self.client_name)
		frappe.db.commit()
		super().tearDown()

	def _create_client(self, *, bound: bool) -> str:
		client = frappe.get_doc(
			{
				"doctype": "OAuth Client",
				"app_name": "MCP Task 04V live verification",
				"scopes": SCOPE,
				"redirect_uris": REDIRECT_URI,
				"default_redirect_uri": REDIRECT_URI,
				"grant_type": "Authorization Code",
				"response_type": "Code",
				"token_endpoint_auth_method": "None",
				"skip_authorization": 1,
				"custom_mcp_resource": RESOURCE if bound else None,
			}
		).insert(ignore_permissions=True)
		return client.name

	def _administrator_sid(self) -> str:
		from frappe.auth import CookieManager, LoginManager
		from frappe.utils import set_request

		set_request(path="/")
		frappe.local.cookie_manager = CookieManager()
		frappe.local.login_manager = LoginManager()
		frappe.local.login_manager.login_as("Administrator")
		return frappe.session.sid

	def _get(self, path: str, params: dict | None = None):
		response = _make_request(
			target=self.test_client.get,
			args=(path,),
			kwargs={"data": params},
			site=self.site,
		)
		frappe.db.commit()
		return response

	def _post(self, path: str, data):
		response = _make_request(
			target=self.test_client.post,
			args=(path,),
			kwargs={"data": data, "headers": self.form_header},
			site=self.site,
		)
		frappe.db.commit()
		return response

	def _authorization_params(self, **overrides):
		params = {
			"client_id": self.client_name,
			"scope": SCOPE,
			"response_type": "code",
			"redirect_uri": REDIRECT_URI,
			"resource": RESOURCE,
			"code_challenge_method": "S256",
			"code_challenge": _s256_challenge(VERIFIER),
		}
		params.update(overrides)
		return params

	def _authorize(self, **overrides) -> tuple[str, dict]:
		response = self._get(
			"/api/method/frappe.integrations.oauth2.authorize",
			self._authorization_params(**overrides),
		)
		query = parse_qs(urlparse(response.location).query)
		return query["code"][0], query

	def _exchange(self, code: str, **overrides):
		data = {
			"grant_type": "authorization_code",
			"code": code,
			"redirect_uri": REDIRECT_URI,
			"client_id": self.client_name,
			"scope": SCOPE,
			"resource": RESOURCE,
			"code_verifier": VERIFIER,
		}
		data.update(overrides)
		return self._post("/api/method/frappe.integrations.oauth2.get_token", data)

	def test_bound_code_exchange_refresh_and_native_revocation(self):
		code, _query = self._authorize()
		code_row = frappe.db.get_value(
			"OAuth Authorization Code",
			code,
			["user", "client", "scopes", "validity", "code_challenge_method", "custom_mcp_resource"],
			as_dict=True,
		)
		self.assertEqual(
			code_row,
			{
				"user": "Administrator",
				"client": self.client_name,
				"scopes": SCOPE,
				"validity": "Valid",
				"code_challenge_method": "s256",
				"custom_mcp_resource": RESOURCE,
			},
		)

		token_response = self._exchange(code)
		self.assertEqual(token_response.status_code, 200)
		first = token_response.json
		self.assertTrue(first.get("access_token"))
		self.assertTrue(first.get("refresh_token"))
		self.assertEqual(frappe.db.get_value("OAuth Authorization Code", code, "validity"), "Invalid")
		first_row = frappe.db.get_value(
			"OAuth Bearer Token",
			first["access_token"],
			["user", "client", "scopes", "status", "custom_mcp_resource"],
			as_dict=True,
		)
		self.assertEqual(
			first_row,
			{
				"user": "Administrator",
				"client": self.client_name,
				"scopes": SCOPE,
				"status": "Active",
				"custom_mcp_resource": RESOURCE,
			},
		)

		reused_code = self._exchange(code)
		self.assertEqual(reused_code.status_code, 400)
		self.assertEqual(reused_code.json.get("error"), "invalid_grant")

		refresh_response = self._post(
			"/api/method/frappe.integrations.oauth2.get_token",
			{
				"grant_type": "refresh_token",
				"refresh_token": first["refresh_token"],
				"client_id": self.client_name,
				"resource": RESOURCE,
			},
		)
		self.assertEqual(refresh_response.status_code, 200)
		replacement = refresh_response.json
		self.assertTrue(replacement.get("access_token"))
		self.assertTrue(replacement.get("refresh_token"))
		self.assertNotEqual(replacement["access_token"], first["access_token"])
		self.assertEqual(frappe.db.get_value("OAuth Bearer Token", first["access_token"], "status"), "Revoked")
		replacement_row = frappe.db.get_value(
			"OAuth Bearer Token",
			replacement["access_token"],
			["user", "client", "scopes", "status", "custom_mcp_resource"],
			as_dict=True,
		)
		self.assertEqual(
			replacement_row,
			{
				"user": "Administrator",
				"client": self.client_name,
				"scopes": SCOPE,
				"status": "Active",
				"custom_mcp_resource": RESOURCE,
			},
		)

		reused_refresh = self._post(
			"/api/method/frappe.integrations.oauth2.get_token",
			{
				"grant_type": "refresh_token",
				"refresh_token": first["refresh_token"],
				"client_id": self.client_name,
				"resource": RESOURCE,
			},
		)
		self.assertEqual(reused_refresh.status_code, 400)
		self.assertEqual(reused_refresh.json.get("error"), "invalid_grant")

		revoke_response = self._post(
			"/api/method/frappe.integrations.oauth2.revoke_token",
			{"token": replacement["access_token"], "token_type_hint": "access_token"},
		)
		self.assertEqual(revoke_response.status_code, 200)
		self.assertEqual(
			frappe.db.get_value("OAuth Bearer Token", replacement["access_token"], "status"), "Revoked"
		)

	def test_bound_requests_fail_closed(self):
		cases = (
			("missing resource", {"resource": None}, "invalid_target"),
			("wrong resource", {"resource": "https://other.example.invalid/mcp"}, "invalid_target"),
			("malformed resource", {"resource": "https://user@mcp.example.invalid/mcp"}, "invalid_target"),
			("missing challenge", {"code_challenge": None}, "invalid_request"),
			("plain challenge", {"code_challenge_method": "plain"}, "invalid_request"),
		)
		for label, overrides, expected_error in cases:
			params = {key: value for key, value in self._authorization_params(**overrides).items() if value is not None}
			with self.subTest(label=label):
				response = self._get("/api/method/frappe.integrations.oauth2.authorize", params)
				self.assertEqual(response.status_code, 400)
				self.assertEqual(response.json.get("error"), expected_error)

		duplicate_query = urlencode(self._authorization_params()) + f"&resource={RESOURCE}"
		response = self._get(f"/api/method/frappe.integrations.oauth2.authorize?{duplicate_query}")
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json.get("error"), "invalid_target")
		self.assertFalse(frappe.db.exists("OAuth Authorization Code", {"client": self.client_name}))

	def test_supported_rpc_dispatchers_apply_the_override(self):
		params = self._authorization_params()
		params.pop("resource")
		paths = (
			"/api/method/frappe.integrations.oauth2.authorize",
			"/api/v2/method/frappe.integrations.oauth2.authorize",
		)
		for path in paths:
			with self.subTest(path=path):
				response = self._get(path, params)
				self.assertEqual(response.status_code, 400)
				self.assertEqual(response.json.get("error"), "invalid_target")

		root_params = dict(params, cmd="frappe.integrations.oauth2.authorize")
		response = self._get("/", root_params)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.json.get("error"), "invalid_target")

	def test_unbound_client_retains_native_behavior_without_resource(self):
		frappe.db.set_value("OAuth Client", self.client_name, "custom_mcp_resource", None)
		frappe.db.commit()
		params = self._authorization_params()
		params.pop("resource")
		params.pop("code_challenge")
		params.pop("code_challenge_method")
		response = self._get("/api/method/frappe.integrations.oauth2.authorize", params)
		query = parse_qs(urlparse(response.location).query)
		code = query["code"][0]
		self.assertIsNone(frappe.db.get_value("OAuth Authorization Code", code, "custom_mcp_resource"))
		token_response = self._post(
			"/api/method/frappe.integrations.oauth2.get_token",
			{
				"grant_type": "authorization_code",
				"code": code,
				"redirect_uri": REDIRECT_URI,
				"client_id": self.client_name,
				"scope": SCOPE,
			},
		)
		self.assertEqual(token_response.status_code, 200)
		access_token = token_response.json["access_token"]
		self.assertIsNone(
			frappe.db.get_value("OAuth Bearer Token", access_token, "custom_mcp_resource")
		)

	def test_bound_refresh_rejects_invalid_native_users(self):
		validator = MCPResourceBindingOAuthValidator()
		self.assertEqual(
			frappe.db.get_value("OAuth Client", self.client_name, "custom_mcp_resource"), RESOURCE
		)
		for label, user in (
			("guest", "Guest"),
			("deleted", f"missing-{frappe.generate_hash(length=8)}@example.invalid"),
		):
			access_token = frappe.generate_hash(length=24)
			refresh_token = frappe.generate_hash(length=24)
			frappe.get_doc(
				{
					"doctype": "OAuth Bearer Token",
					"access_token": access_token,
					"refresh_token": refresh_token,
					"client": self.client_name,
					"user": user,
					"scopes": SCOPE,
					"expires_in": 3600,
					"status": "Active",
					"custom_mcp_resource": RESOURCE,
				}
			).db_insert()
			frappe.db.commit()
			request = SimpleNamespace(
				resource=RESOURCE,
				duplicate_params=[],
				client_id=self.client_name,
				body={"refresh_token": refresh_token},
				redirect_uri=None,
			)
			with self.subTest(label=label):
				self.assertFalse(
					validator.validate_refresh_token(
						refresh_token, {"name": self.client_name}, request
					)
				)


def cleanup_verification_fixtures() -> list[str]:
	"""Remove only the disposable OAuth Clients created by Task 04V tests."""
	client_names = frappe.get_all(
		"OAuth Client",
		filters={
			"app_name": [
				"in",
				["MCP Task 04V live verification", "MCP replay lock integration test"],
			]
		},
		pluck="name",
	)
	for client_name in client_names:
		frappe.db.delete("OAuth Authorization Code", {"client": client_name})
		frappe.db.delete("OAuth Bearer Token", {"client": client_name})
		frappe.delete_doc("OAuth Client", client_name, ignore_permissions=True, force=True)
	frappe.db.commit()
	return client_names
