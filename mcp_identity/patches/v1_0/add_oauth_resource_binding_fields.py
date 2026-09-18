"""Add the optional resource binding fields to native Frappe OAuth records."""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
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


def execute():
    create_custom_fields(CUSTOM_FIELDS, update=True)
