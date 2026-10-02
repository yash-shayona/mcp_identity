"""Installation hooks for mcp_identity."""

from mcp_identity.setup.custom_fields import ensure_oauth_resource_binding_custom_fields


def after_install():
	"""Provision required OAuth schema after Frappe stamps historical patches."""
	ensure_oauth_resource_binding_custom_fields()
