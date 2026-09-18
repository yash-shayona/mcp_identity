# MCP Identity Task 05 FastMCP OAuth Resource-Server Implementation Report

Implementation date: 2026-09-18

## Result

Implemented the OAuth resource-server boundary for Streamable HTTP. Frappe
remains the authorization server; FastMCP only verifies native opaque Frappe
bearer tokens. External ChatGPT E2E and public HTTPS deployment were not run.

## Inspected environment

- Bench: `/home/frappe/frappe-bench`.
- Frappe `16.34.0`, ERPNext `16.35.0`, oauthlib `3.3.1`.
- Bench Python `3.14`.
- Installed MCP SDK: `1.29.0` (source inspected in the Bench environment).
- Existing Task 04/04V/04F binding implementation and reports.

## SDK APIs used

The implementation uses the installed SDK's `AuthSettings`, `TokenVerifier`,
`AccessToken`, `BearerAuthBackend`, `AuthContextMiddleware`,
`RequireAuthMiddleware`, `get_access_token()`, and
`create_protected_resource_routes()` through `FastMCP.streamable_http_app()`.
No `auth_server_provider` or SDK upgrade was added.

## Changed responsibility and files

`mcp_identity` owns OAuth environment parsing, canonical configuration, startup
trust-anchor validation, and `FrappeOAuthTokenVerifier` in:

- `mcp_identity/identity.py`
- `mcp_identity/oauth_resource_server.py`
- `mcp_identity/tests/test_oauth_resource_server.py`
- updated identity regression tests, README, and this report

`mcp_erpnext` only assembles the SDK auth settings, selects OAuth versus
trusted-header transport, and consumes the SDK principal in:

- `mcp_erpnext/mcp_server.py`
- `mcp_erpnext/http_transport.py`
- `mcp_erpnext/runtime.py`
- focused HTTP/runtime tests and `.env.example`/command documentation

Business tools, profiles, approvals, REST semantics, and Frappe core were not
changed.

## Configuration and startup

OAuth requires `MCP_TRANSPORT=streamable-http`, `MCP_HTTP_AUTH_MODE=oauth`,
`MCP_FRAPPE_SITE`, `MCP_OAUTH_ISSUER_URL`,
`MCP_OAUTH_RESOURCE_SERVER_URL`, non-empty deterministic
`MCP_OAUTH_REQUIRED_SCOPES`, and `MCP_OAUTH_FRAPPE_CLIENT_ID`. The issuer and
resource are canonicalized; issuer paths are rejected. Startup then requires
the three migrated `custom_mcp_resource` Custom Fields, an existing configured
OAuth Client, and exact client/resource equality. No Host, Forwarded, shared
secret, email header, or stdio identity is used for OAuth startup or requests.

Absent auth mode still selects trusted-header and still requires the strong
shared secret. Stdio does not validate HTTP OAuth settings.

## Token verification

The verifier reads the native `OAuth Bearer Token` row by the presented opaque
access-token document name, then the native `OAuth Client` and `User` rows. It
requires Active status, unexpired `expiration_time`, the configured client,
existing client record, nonblank valid token/client resources, exact equality of
token resource, client resource, and configured MCP resource, every configured
scope in the token-record scopes, and an enabled non-Guest native User. Native
client scopes cannot expand token-record scopes. Any lookup or database error
fails closed without logging the raw token or Authorization header.

The SDK `AccessToken` maps the raw token only to the SDK-required `token` field,
native client name to `client_id`, token-record scopes to `scopes`, native expiry
to `expires_at`, canonical resource to `resource`, native User name to
`subject`, and configured issuer to a safe `iss` claim. No token is placed in
tool output, approval state, or logs.

The verifier performs its short synchronous Frappe lookup in the request's
Frappe context and returns only immutable SDK data; no Frappe Document, DB
connection, session, or `frappe.local` crosses an await boundary. A temporary
Frappe context created by startup/verification is destroyed in `finally`.

## FastMCP behavior

OAuth construction passes `AuthSettings` and the Frappe verifier to FastMCP.
The SDK supplies the bearer backend, request-scoped auth ContextVar, required
scope checks, challenges, and protected-resource metadata. The metadata route
is the SDK-native RFC 9728 route derived from the exact configured resource and
advertises the configured issuer and scopes.

Missing, malformed, unknown, expired, revoked, wrong-client, wrong-resource,
or invalid-user tokens are handled by the SDK as `401 Unauthorized` with a
Bearer challenge and resource metadata reference. A valid token missing a
required scope is `403 Forbidden` with `insufficient_scope`.

`mcp_erpnext.runtime` reads only SDK `get_access_token().subject` in OAuth mode,
requires it to exist, creates a fresh business Frappe scope, calls
`frappe.set_user(subject)`, executes the existing tool, and cleans up. It never
reads `X-MCP-User-Email` or `MCP_FRAPPE_USER` in this mode. Sequential or
concurrent two-user live permission proof remains unrun in this implementation
turn.

## Verification evidence

Passed compile and focused tests:

```text
/home/frappe/frappe-bench/env/bin/python -m compileall -q \
  apps/mcp_identity/mcp_identity apps/mcp_erpnext/mcp_erpnext
```

```text
/home/frappe/frappe-bench/env/bin/python -m unittest \
  apps.mcp_identity.mcp_identity.tests.test_oauth_resource_server \
  apps.mcp_identity.mcp_identity.tests.test_identity \
  apps.mcp_erpnext.mcp_erpnext.tests.test_http_transport \
  apps.mcp_erpnext.mcp_erpnext.tests.test_runtime
```

The final focused run passed 45 tests. A separate SDK assembly/metadata run
passed 17 tests. The existing Pydantic `lifespan` incomplete-definition warning
was emitted and did not fail tests.

The tests cover canonical settings, duplicate scope normalization, startup
configuration gates, SDK OAuth assembly, metadata route presence, token status,
expiry, client/resource/scope/user checks, database failure, exact subject
consumption, trusted-header regression, stdio regression, and runtime cleanup.

Task 04 live authorization-server lifecycle, refresh rotation, revocation, and
two-connection replay evidence remains the previously recorded 04V/04F result.
This turn did not create live OAuth fixtures, migrate a site, start a live MCP
process, execute a local browser/authorization flow, or test ERPNext
permission differences between two real users.

## External ChatGPT and security metadata

No public HTTPS endpoint, ChatGPT client identifier, callback, login/consent,
revocation reconnect, or external E2E was available or authorized. Those checks
are deferred to Task 05V. The installed SDK-native metadata/challenge path was
used; no tool `securitySchemes` or `_meta["mcp/www_authenticate"]` override was
added because the resource-server HTTP contract is supplied by the SDK route and
middleware.

## Readiness and limitations

The server-side source/unit implementation is ready for authorized local live
verification. Full Task 05 acceptance is not claimed: local live MCP OAuth,
native ERPNext two-user permission proof, sequential/concurrent live identity
switching, and public ChatGPT E2E remain unverified. DCR/CIMD, external IdPs,
remote REST-backed OAuth verification, token caching, and public tunnel/TLS
infrastructure remain out of scope.
