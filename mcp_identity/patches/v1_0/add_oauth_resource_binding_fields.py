"""Historical upgrade patch for MCP OAuth resource-binding fields."""

from mcp_identity.setup.custom_fields import ensure_oauth_resource_binding_custom_fields


def execute():
	ensure_oauth_resource_binding_custom_fields()
