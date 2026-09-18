"""Operator-gated database proof for the row-lock replay boundary.

Run only on an isolated test site that has ``mcp_identity`` installed and
migrated. The ordinary unit suite skips this module's tests.
"""

from __future__ import annotations

import os
import threading
import unittest

import frappe

RUN_DB_TESTS = os.environ.get("MCP_IDENTITY_RUN_OAUTH_DB_TESTS") == "1"


@unittest.skipUnless(RUN_DB_TESTS, "requires an explicitly approved isolated Frappe test site")
class OAuthReplayLockIntegrationTests(unittest.TestCase):
	def setUp(self):
		self.site = frappe.local.site
		self.sites_path = frappe.local.sites_path
		self.client_name = f"mcp-replay-test-{frappe.generate_hash(length=12)}"
		client = frappe.get_doc(
			{
				"doctype": "OAuth Client",
				"name": self.client_name,
				"app_name": "MCP replay lock integration test",
				"scopes": "all",
				"redirect_uris": "https://client.example.com/callback",
				"default_redirect_uri": "https://client.example.com/callback",
				"grant_type": "Authorization Code",
				"response_type": "Code",
				"token_endpoint_auth_method": "None",
				"custom_mcp_resource": "https://mcp.example.com/mcp",
			}
		)
		client.insert(ignore_permissions=True)
		self.client_name = client.name
		frappe.db.commit()

	def tearDown(self):
		frappe.db.delete("OAuth Authorization Code", {"client": self.client_name})
		frappe.db.delete("OAuth Bearer Token", {"client": self.client_name})
		frappe.db.delete("OAuth Client", self.client_name)
		frappe.db.commit()

	def test_authorization_code_lock_serializes_replay(self):
		name = frappe.generate_hash(length=24)
		doc = frappe.get_doc(
			{
				"doctype": "OAuth Authorization Code",
				"authorization_code": name,
				"client": self.client_name,
				"user": "Administrator",
				"scopes": "all",
				"validity": "Valid",
				"code_challenge": "challenge",
				"code_challenge_method": "s256",
				"custom_mcp_resource": "https://mcp.example.com/mcp",
			}
		)
		doc.db_insert()
		frappe.db.commit()
		self._assert_only_first_connection_can_claim(
			"OAuth Authorization Code", name, "validity", "Valid", "Invalid"
		)

	def test_refresh_token_lock_serializes_replay(self):
		name = frappe.generate_hash(length=24)
		doc = frappe.get_doc(
			{
				"doctype": "OAuth Bearer Token",
				"access_token": name,
				"refresh_token": frappe.generate_hash(length=24),
				"client": self.client_name,
				"user": "Administrator",
				"scopes": "all",
				"expires_in": 3600,
				"status": "Active",
				"custom_mcp_resource": "https://mcp.example.com/mcp",
			}
		)
		doc.db_insert()
		frappe.db.commit()
		self._assert_only_first_connection_can_claim(
			"OAuth Bearer Token", name, "status", "Active", "Revoked"
		)

	def _assert_only_first_connection_can_claim(
		self, doctype: str, name: str, state_field: str, active: str, consumed: str
	):
		first_locked = threading.Event()
		release_first = threading.Event()
		second_finished = threading.Event()
		results: list[tuple[str, str | None]] = []
		errors: list[BaseException] = []

		def claim(label: str, hold_lock: bool):
			try:
				frappe.init(site=self.site, sites_path=self.sites_path)
				frappe.connect()
				found = frappe.db.get_value(
					doctype,
					{"name": name, state_field: active},
					"name",
					for_update=True,
				)
				results.append((label, found))
				if hold_lock:
					first_locked.set()
					if not release_first.wait(timeout=5):
						raise TimeoutError("test did not release first transaction")
					frappe.db.set_value(doctype, name, state_field, consumed, update_modified=False)
				frappe.db.commit()
			except BaseException as error:
				errors.append(error)
				frappe.db.rollback()
			finally:
				if not hold_lock:
					second_finished.set()
				frappe.destroy()

		first = threading.Thread(target=claim, args=("first", True), daemon=True)
		second = threading.Thread(target=claim, args=("second", False), daemon=True)
		first.start()
		self.assertTrue(first_locked.wait(timeout=5))
		second.start()
		self.assertFalse(second_finished.wait(timeout=0.2), "second claim did not block on row lock")
		release_first.set()
		first.join(timeout=5)
		second.join(timeout=5)

		self.assertFalse(first.is_alive() or second.is_alive())
		self.assertEqual(errors, [])
		self.assertEqual(dict(results), {"first": name, "second": None})
