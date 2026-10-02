from __future__ import annotations

import unittest
from unittest.mock import patch

from mcp_identity.setup.install import after_install
from mcp_identity.setup.custom_fields import (
	OAUTH_RESOURCE_BINDING_CUSTOM_FIELDS,
	ensure_oauth_resource_binding_custom_fields,
)
from mcp_identity.patches.v1_0.add_oauth_resource_binding_fields import execute


class OAuthResourceFieldProvisioningTests(unittest.TestCase):
	def test_shared_definition_contains_exactly_the_three_approved_fields(self):
		self.assertEqual(
			set(OAUTH_RESOURCE_BINDING_CUSTOM_FIELDS),
			{"OAuth Client", "OAuth Authorization Code", "OAuth Bearer Token"},
		)
		self.assertEqual(sum(len(fields) for fields in OAUTH_RESOURCE_BINDING_CUSTOM_FIELDS.values()), 3)
		for doctype, fields in OAUTH_RESOURCE_BINDING_CUSTOM_FIELDS.items():
			field = fields[0]
			self.assertEqual(field["fieldname"], "custom_mcp_resource")
			self.assertEqual(field["fieldtype"], "Small Text")
			self.assertEqual(field["insert_after"], "scopes")
			self.assertNotIn("unique", field)
			self.assertNotIn("search_index", field)
			self.assertNotIn("reqd", field)
			if doctype != "OAuth Client":
				for property_name in ("hidden", "read_only", "no_copy", "print_hide", "report_hide"):
					self.assertEqual(field[property_name], 1)

	@patch("mcp_identity.setup.custom_fields.create_custom_fields")
	def test_shared_helper_uses_native_idempotent_update_without_backfill(self, create_custom_fields):
		ensure_oauth_resource_binding_custom_fields()
		ensure_oauth_resource_binding_custom_fields()
		self.assertEqual(create_custom_fields.call_count, 2)
		create_custom_fields.assert_called_with(OAUTH_RESOURCE_BINDING_CUSTOM_FIELDS, update=True)

	@patch("mcp_identity.patches.v1_0.add_oauth_resource_binding_fields.ensure_oauth_resource_binding_custom_fields")
	def test_historical_patch_delegates_to_shared_helper(self, ensure_fields):
		execute()
		ensure_fields.assert_called_once_with()

	@patch("mcp_identity.setup.install.ensure_oauth_resource_binding_custom_fields")
	def test_after_install_delegates_to_shared_helper(self, ensure_fields):

		after_install()
		ensure_fields.assert_called_once_with()
