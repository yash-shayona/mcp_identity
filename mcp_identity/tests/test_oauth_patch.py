from __future__ import annotations

import unittest
from unittest.mock import patch

from mcp_identity.patches.v1_0.add_oauth_resource_binding_fields import CUSTOM_FIELDS, execute


class OAuthResourceFieldPatchTests(unittest.TestCase):
	def test_patch_defines_exactly_the_three_approved_fields(self):
		self.assertEqual(
			set(CUSTOM_FIELDS),
			{"OAuth Client", "OAuth Authorization Code", "OAuth Bearer Token"},
		)
		self.assertEqual(sum(len(fields) for fields in CUSTOM_FIELDS.values()), 3)
		for doctype, fields in CUSTOM_FIELDS.items():
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

	@patch("mcp_identity.patches.v1_0.add_oauth_resource_binding_fields.create_custom_fields")
	def test_patch_uses_native_idempotent_update_without_backfill(self, create_custom_fields):
		execute()
		execute()
		self.assertEqual(create_custom_fields.call_count, 2)
		create_custom_fields.assert_called_with(CUSTOM_FIELDS, update=True)
