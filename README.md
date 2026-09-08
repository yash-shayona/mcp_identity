# MCP Identity

`mcp_identity` resolves the Frappe user for an authenticated MCP HTTP request.
It depends only on Frappe and owns no DocTypes, business permissions, provider
adapters, or MCP tool permissions.

## HTTP identity contract

The supported client sends both values with each request:

```http
Authorization: Bearer <MCP_HTTP_SHARED_SECRET>
X-MCP-User-Email: person@example.com
```

`MCP_HTTP_SHARED_SECRET` is server-only configuration and must be at least 32
characters. The secret authenticates the configured client; only after it
validates does the app resolve the supplied email to an existing, enabled
Frappe `User`. Missing, malformed, unknown, disabled, or unauthenticated
identities fail closed. No Guest, service-user, previous-request, or provider
mapping fallback is used for HTTP requests.

Consumers receive the resolved Frappe User and run their own request-scoped
context and native permission checks. The dependency direction is:

```text
Frappe -> mcp_identity -> mcp_erpnext / future MCP consumers
```

This app is not an ERPNext permission system and is not an adapter for any
specific MCP client or identity provider.
