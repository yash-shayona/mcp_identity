"""Idempotent schema setup for MCP OAuth resource binding fields."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

OAUTH_RESOURCE_BINDING_CUSTOM_FIELDS = {
    "OAuth Client": [
        {
            "fieldname": "custom_mcp_resource",
            "label": "MCP Resource",
            "fieldtype": "Small Text",
            "insert_after": "scopes",
        }
    ],
    "OAuth Authorization Code": [
        {
            "fieldname": "custom_mcp_resource",
            "label": "MCP Resource",
            "fieldtype": "Small Text",
            "insert_after": "scopes",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "print_hide": 1,
            "report_hide": 1,
        }
    ],
    "OAuth Bearer Token": [
        {
            "fieldname": "custom_mcp_resource",
            "label": "MCP Resource",
            "fieldtype": "Small Text",
            "insert_after": "scopes",
            "hidden": 1,
            "read_only": 1,
            "no_copy": 1,
            "print_hide": 1,
            "report_hide": 1,
        }
    ],
}


def ensure_oauth_resource_binding_custom_fields():
    """Create or update the MCP-owned OAuth fields without backfilling records."""
    create_custom_fields(OAUTH_RESOURCE_BINDING_CUSTOM_FIELDS, update=True)
