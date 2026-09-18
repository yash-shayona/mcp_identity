# MCP Identity Auth-Mode and OAuth Architecture Audit

Audit date: 2026-09-17

## 1. Executive Summary

The target boundary is sound with one qualification: `mcp_identity` should own
all authentication and execution-identity resolution, including the configured
stdio identity, while `mcp_erpnext` should continue to own MCP transport
selection, Frappe runtime bootstrapping, ERPNext profiles/tools, and business
operations.

The recommended HTTP configuration boundary is
`MCP_HTTP_AUTH_MODE=trusted_header|oauth`, parsed and validated by
`mcp_identity`. It is deliberately HTTP-specific: the current MCP authorization
spec says HTTP transports should use its OAuth flow, while stdio should obtain
credentials from the environment. The backward-compatible default must be
`trusted_header` when the variable is absent.

Native Frappe OAuth 16.34.0 is a strong starting point, but it is not sufficient
as a direct MCP OAuth resource server. It supports authorization code, S256
PKCE, refresh tokens, metadata, optional dynamic client registration (DCR),
exact redirect matching, bearer-token expiry/revocation, scopes, and a native
token-to-Frappe-User association. The security-critical gap is resource/audience
binding: Frappe does not persist the RFC 8707 `resource` parameter on an
authorization code or access token and does not validate that a bearer token
was issued for the MCP resource. Its access tokens are opaque database records
with `client`, `user`, scopes, expiry, and status, but no audience/resource.

Therefore the recommended first OAuth design is **Option 2: a thin
`mcp_identity` compatibility layer over Frappe OAuth**. It should use the
installed MCP SDK's resource-server primitives for protected-resource metadata,
401 challenges, scope enforcement, and request-scoped access-token context; it
should validate Frappe opaque tokens against native Frappe state and add a real,
fail-closed resource-binding mechanism. It must not create a generic
Azure/Keycloak/Auth0 adapter framework now. A small provider selector with only
`frappe` is acceptable as a configuration seam, but provider interfaces should
wait for a second proven provider.

No production code, configuration, database records, or tests were changed by
this audit.

## 2. Repository / Version Context

### Repositories and versions

| Component | Branch | Commit/version | Working tree at start |
|---|---|---|---|
| `mcp_identity` | `main` | `5cc9fcbb49d0704bf0b7fb48a82a315e0d426246` | Pre-existing untracked `docs/tasks/` |
| `mcp_erpnext` | `master` | `12ef04ea69280b79b2849dda574d1290a613ade2` | Clean |
| Frappe | `version-16` | `c1f1e8ec3708750d7254f7f99d869ffb9886f19f`; source version `16.34.0` | Inspected read-only |
| ERPNext | `version-16` | `12cd563fb9a79731f75ae2a45b1446a0a2dd9e74`; source version `16.35.0` | Inspected read-only |
| Python MCP SDK | installed package | `mcp==1.29.0` | Inspected read-only |

Git required a command-local `safe.directory` override because the checkout
ownership differs from the process user. No global Git configuration was
changed. `sites/apps.txt` lists both `mcp_identity` and `mcp_erpnext`; this is a
bench-level source/install list, not proof of the effective state of any one
site.

### Principal files inspected

- `mcp_identity/README.md`
- `mcp_identity/docs/MCP_IDENTITY_V1_IMPLEMENTATION_TASK.md`
- `mcp_identity/mcp_identity/identity.py`
- `mcp_identity/mcp_identity/hooks.py`
- `mcp_identity/mcp_identity/tests/test_identity.py`
- `mcp_erpnext/.env.example`
- `mcp_erpnext/mcp_erpnext/settings.py`
- `mcp_erpnext/mcp_erpnext/http_transport.py`
- `mcp_erpnext/mcp_erpnext/runtime.py`
- `mcp_erpnext/mcp_erpnext/observability.py`
- `mcp_erpnext/mcp_erpnext/mcp_server.py`
- `mcp_erpnext/mcp_erpnext/hooks.py`
- `mcp_erpnext/mcp_erpnext/rest_client.py`
- `mcp_erpnext/mcp_erpnext/remote_api.py`
- `mcp_erpnext/mcp_erpnext/tests/test_http_transport.py`
- `mcp_erpnext/mcp_erpnext/tests/test_runtime.py`
- `mcp_erpnext/mcp_erpnext/tests/test_identity.py`
- Frappe `frappe/oauth.py`, `frappe/auth.py`,
  `frappe/integrations/oauth2.py`, `frappe/integrations/utils.py`, OAuth
  DocType controllers/JSON, request lifecycle, and local-context implementation
- Installed MCP SDK auth settings, bearer middleware, provider protocol,
  auth-context middleware, and FastMCP server assembly

Official material inspected on 2026-09-17:

- [OpenAI plugin MCP authentication guide](https://developers.openai.com/plugins/build/auth)
- [OpenAI ChatGPT developer mode and MCP apps](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt)
- [MCP Authorization specification, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [Frappe OAuth2 overview](https://docs.frappe.io/framework/oauth2)
- [Frappe OAuth 2 API guide](https://docs.frappe.io/framework/user/en/guides/integration/rest_api/oauth-2)

## 3. Current Architecture

### A. stdio call graph

```text
python -m mcp_erpnext.mcp_server
  -> mcp_server.py:create_mcp()
       -> MCPSettings.from_environment()
          reads MCP_BACKEND, MCP_FRAPPE_SITE, MCP_FRAPPE_USER,
          MCP_TRANSPORT (default stdio), profile/approval/backend settings
       -> FastMCP(...)
       -> register_tools(...)
  -> mcp_server.py:main()
       -> MCPSettings.from_environment()
       -> settings.validate()
       -> mcp.run(transport="stdio")
  -> registered tool wrapper
       -> runtime.execute_tool_with_context(ctx, tool_name, operation)
       -> no HTTP headers => _get_http_runtime_identity(ctx) returns None
       -> observability.execute_tool(...)
       -> runtime._run_stdio_tool(settings, operation)
       -> runtime._ensure_context(settings)
            -> resolve site from explicit argument / MCP_FRAPPE_SITE /
               existing frappe.local.site
            -> frappe.init(..., force=True) when needed
            -> frappe.connect(set_admin_as_user=False)
            -> configured_user = explicit user or settings.frappe_user
            -> frappe.set_user(configured_user), when present
            -> reject absent/Guest current user
       -> ERPNext service operation under frappe.session.user
       -> success result, or observability.execute_tool maps exceptions to a
          public error envelope and logs a reference
```

Evidence: `mcp_server.py:28-76`, `settings.py:51-77,101-121,177-185`,
`runtime.py:31-80,107-162`, and `observability.py:137-143,181-218`.

The stdio path does **not functionally use `mcp_identity` to resolve the user**.
It reads `MCP_FRAPPE_USER` in `mcp_erpnext.settings.MCPSettings` and applies it in
`mcp_erpnext.runtime._ensure_context`. Nevertheless, stdio imports
`mcp_identity` transitively and cannot start without it because:

- `settings.py:11-14` imports shared-secret helpers at module import time;
- `runtime.py:12-19` imports HTTP identity types/resolvers;
- `observability.py:16` imports `MCPIdentityError` for error mapping;
- `mcp_server.py:6` imports `http_transport`, which imports identity helpers;
- `hooks.py:11` declares `required_apps = ["erpnext", "mcp_identity"]`.

Stdio Frappe state is intentionally persistent rather than wrapped in
`_http_runtime_scope`. `_ensure_context` reapplies the configured user when one
is present; it does not destroy the context after each tool.

### B. Streamable HTTP trusted-header call graph

```text
python -m mcp_erpnext.mcp_server
  -> MCPSettings.from_environment()
       MCP_TRANSPORT=streamable-http plus host/port/path/allowed-hosts
  -> settings.validate()
       -> validate_transport()
       -> mcp_identity.get_http_shared_secret_from_environment()
       -> mcp_identity.validate_http_shared_secret_configuration()
  -> create_http_app(mcp, settings)
       -> mcp.streamable_http_app()
       -> add SharedSecretAuthenticationMiddleware
  -> uvicorn.run(...)

HTTP request to exact MCP path
  -> SharedSecretAuthenticationMiddleware.dispatch()
       -> mcp_identity.validate_bearer_secret(Authorization, shared_secret)
       -> missing/malformed/wrong secret: generic warning + HTTP 401
       -> valid secret: FastMCP request processing
  -> tool wrapper
       -> runtime.execute_tool_with_context(...)
       -> _get_http_runtime_identity(ctx)
       -> mcp_identity.get_http_identity_inputs(request.headers)
          copies Authorization and X-MCP-User-Email into HTTPIdentityInputs
       -> observability.execute_tool(...)
       -> _run_http_tool(...)
       -> _http_runtime_scope()
            -> frappe.destroy() before work
            -> _ensure_context(..., runtime_identity=...)
                 -> frappe.init(..., force=True)
                 -> frappe.connect(set_admin_as_user=False)
                 -> reload/validate MCP_HTTP_SHARED_SECRET
                 -> mcp_identity.resolve_frappe_user_from_http(...)
                      -> constant-time Bearer-secret validation again
                      -> normalized email validation
                      -> User lookup by email
                      -> reject absent, Guest, or disabled user
                 -> frappe.set_user(resolved_user)
                 -> reject absent/Guest session user
            -> ERPNext service operation under frappe.session.user
            -> frappe.destroy() in finally, including exception paths
       -> observability maps identity/permission/unexpected exceptions to safe
          MCP error envelopes and logs a correlation reference
```

Evidence: `http_transport.py:24-54`, `identity.py:46-104`,
`runtime.py:42-104,107-170`, `observability.py:21-40,137-143,181-218`, and
`test_runtime.py:26-98`.

Streamable HTTP therefore **does functionally use `mcp_identity` twice**: once
as transport authentication middleware and again as the request identity
resolver immediately before `frappe.set_user`.

Two details matter for the future implementation:

1. Transport selection currently depends on whether request headers were found
   (`runtime.py:69-75`) rather than directly on `settings.transport`. A real
   HTTP request has headers, but a missing/changed SDK request shape could route
   to `_run_stdio_tool` and reuse `MCP_FRAPPE_USER`. Task 02 should select the
   identity path from the configured transport/auth strategy and fail closed if
   HTTP auth context is absent.
2. HTTP cleanup is strong: `frappe.destroy()` runs before and in `finally` after
   each tool. Because `observability.execute_tool` catches outside that scope,
   failure logs may see the Frappe site/user already cleared. That is an
   observability limitation, not an identity leak.

## 4. Current Responsibility Matrix

| Responsibility | Current owner | Finding |
|---|---|---|
| Shared-secret environment read/strength validation | `mcp_identity` | Correct semantic owner |
| Trusted Bearer comparison | `mcp_identity` | Correct; uses `hmac.compare_digest` |
| HTTP email-header parsing and Frappe User resolution | `mcp_identity` | Correct; generic and fail-closed |
| HTTP authentication middleware assembly | `mcp_erpnext` | Coupled; should be supplied/configured by `mcp_identity` |
| Auth error HTTP response | `mcp_erpnext` middleware | Currently generic HTTP 401 for secret failure |
| Stdio configured-user read/resolution | `mcp_erpnext` | Move semantic ownership to `mcp_identity` |
| Transport selection and host/port/path/DNS-rebinding allowlist | `mcp_erpnext` | Keep |
| Frappe site init/connect/destroy and `frappe.set_user` | `mcp_erpnext` | Keep; identity app returns a verified user, consumer applies it |
| ERPNext backend (`direct|rest`) | `mcp_erpnext` | Keep |
| REST API token credentials | `mcp_erpnext` | Keep; backend credentials are not end-user identity |
| Profile/tool inventory and approval mode | `mcp_erpnext` | Keep |
| Identity exception classes | `mcp_identity` | Keep, extend with mode-neutral categories |
| Public MCP error mapping/logging | `mcp_erpnext` | Keep integration mapping; HTTP OAuth challenges belong at auth middleware |
| OAuth provider compatibility and token-to-user resolution | absent | Add to `mcp_identity` |

The dependency direction remains:

```text
Frappe
  -> mcp_identity
       -> consumed by mcp_erpnext
            -> ERPNext business modules
```

No production import in `mcp_identity` references `mcp_erpnext`, ERPNext,
LibreChat, ChatGPT, or a business profile. This direction must remain unchanged.

## 5. Environment Variable Ownership Matrix

“Owner” means the module that defines the variable's semantics and validation.
All values still enter one process environment; package-local `.env.example`
files do not create runtime namespaces.

| Variable | Current reader/documentation | Purpose/category | Sensitive | Recommended owner/action | Reason |
|---|---|---|---|---|---|
| `MCP_HTTP_SHARED_SECRET` | `mcp_identity.identity`; validated from `mcp_erpnext.settings` and `http_transport`; documented in both READMEs and `mcp_erpnext/.env.example` | Client authentication for trusted-header HTTP | Yes | `mcp_identity`; **keep name**, move authoritative docs | It authenticates the MCP client, not transport binding or ERP business behavior |
| `MCP_FRAPPE_USER` | `mcp_erpnext.settings`, applied by `runtime._ensure_context`; documented in `mcp_erpnext` | Configured stdio execution identity | Identity value, not a secret by itself | `mcp_identity`; **keep name**, move reader/validation behind identity API | Unifies identity resolution without breaking existing launchers |
| `MCP_TRANSPORT` | `mcp_erpnext.settings` | MCP connection transport | No | `mcp_erpnext`; keep | Transport selection is not authentication |
| `MCP_HTTP_HOST` | `mcp_erpnext.settings` | Listener bind host | No | `mcp_erpnext`; keep | HTTP server transport configuration |
| `MCP_HTTP_PORT` | `mcp_erpnext.settings` | Listener port | No | `mcp_erpnext`; keep | HTTP server transport configuration |
| `MCP_HTTP_PATH` | `mcp_erpnext.settings` | Streamable HTTP route | No | `mcp_erpnext`; keep | Transport routing; OAuth resource URL may incorporate it but must not own it |
| `MCP_HTTP_ALLOWED_HOSTS` | `mcp_erpnext.settings` / FastMCP transport security | DNS-rebinding host allowlist | No | `mcp_erpnext`; keep | Transport/network security, not identity |
| `MCP_BACKEND` | `mcp_erpnext.settings` | `direct` local Frappe versus fixed REST bridge | No | `mcp_erpnext`; keep | Backend execution topology |
| `MCP_FRAPPE_SITE` | `mcp_erpnext.settings` / runtime | Direct-backend site | Operationally sensitive | `mcp_erpnext`; keep | Site/runtime target; identity must receive site context but not own backend selection |
| `MCP_PROFILE` | `mcp_erpnext.settings` / registry | Sales/purchase/accounts tool inventory | No | `mcp_erpnext`; keep | Business capability selection |
| `MCP_APPROVAL_MODE` | `mcp_erpnext.settings` / approvals | Confirm-write trust policy | Security-sensitive | `mcp_erpnext`; keep | Business write-approval policy is separate from authentication |
| `MCP_FRAPPE_SITES_PATH` | `mcp_erpnext.runtime` and `observability` | Bench sites-directory override | Operationally sensitive | `mcp_erpnext`; keep, future-review naming | Runtime/bootstrap/log path, not identity |
| `FRAPPE_SITES_PATH` | `mcp_erpnext.runtime` and `observability` fallback | Framework-standard sites path | Operationally sensitive | Frappe/runtime; keep fallback | Existing framework deployment input |
| `MCP_REST_ALLOW_INSECURE_HTTP` | `mcp_erpnext.settings` | Loopback-only REST backend exception | Security-sensitive | `mcp_erpnext`; keep | Backend connection policy |
| `ERPNEXT_BASE_URL` | `mcp_erpnext.settings` / REST client | Remote backend origin | Operationally sensitive | `mcp_erpnext`; keep | Backend connection target, not end-user identity |
| `ERPNEXT_API_KEY` | `mcp_erpnext.settings` / REST client | Remote Frappe API principal credential | Yes | `mcp_erpnext`; keep | Backend connection credential; current REST mode executes as its owning user |
| `ERPNEXT_API_SECRET` | `mcp_erpnext.settings` / REST client | Remote Frappe API principal credential | Yes | `mcp_erpnext`; keep | Backend connection credential; not MCP end-user identity |

The current REST backend is restricted to stdio (`settings.py:113-118`) and
executes remotely as the API-key owner (`rest_client.py:54-63`,
`remote_api.py:35-43`). Unifying local stdio identity under `mcp_identity` must
not imply that `MCP_FRAPPE_USER` can override that remote principal.

## 6. STDIO Identity Boundary Decision

### Comparison

| Criterion | Design A: current split | Design B: unified identity boundary |
|---|---|---|
| Separation of concerns | HTTP-only identity app; stdio identity leaks into consumer settings | All execution-user resolution is in identity app; runtime application stays in consumer |
| Coupling | `mcp_erpnext` knows one identity variable and HTTP identity APIs | `mcp_erpnext` consumes one mode/transport-neutral verified-user result |
| Backward compatibility | No change | Preserve `MCP_FRAPPE_USER` name and stdio semantics; small internal move |
| Testability | Duplicate consumer/identity test boundaries | Central fail-closed tests for configured identity and HTTP identities |
| Security | Stdio accepts a configured string and relies on resulting session state | Identity layer can explicitly reject absent, disabled, deleted, and Guest users before execution |
| Future consumers/transports | Each consumer repeats stdio rules | Reusable configured-identity resolver |
| Over-engineering | Minimal now | Still small if limited to a resolver, not a transport framework |

### Decision

Adopt **Design B**. Add a narrow `mcp_identity` configured-identity resolver for
stdio; keep `MCP_FRAPPE_USER` unchanged. The resolver should verify the named
Frappe User is present, enabled, and not Guest. `mcp_erpnext` should still own
`frappe.init`, `frappe.connect`, `frappe.set_user`, and cleanup. This preserves
the useful boundary: identity selects a verified principal; the consumer creates
the Frappe execution context.

Do not apply the HTTP OAuth protocol to stdio. The current MCP specification
explicitly says stdio implementations should retrieve credentials from the
environment rather than follow the HTTP authorization specification.

## 7. Auth-Mode Architecture Decision

### Recommended abstraction

Use:

```text
MCP_HTTP_AUTH_MODE=trusted_header|oauth
```

This name is preferable to a transport-neutral `MCP_AUTH_MODE` because OAuth
discovery, bearer challenges, and protected-resource metadata apply to HTTP,
while stdio uses configured identity. It also makes clear that
`MCP_TRANSPORT=streamable-http` and HTTP authentication mode are independent
configuration dimensions.

### Ownership and behavior

- `mcp_identity` parses and validates `MCP_HTTP_AUTH_MODE` and all
  authentication/provider settings.
- `mcp_erpnext` parses `MCP_TRANSPORT` and asks `mcp_identity` to supply the
  selected HTTP auth integration. It should not branch on `frappe`, token
  claims, email headers, or provider-specific errors.
- Default absent value: `trusted_header` for backward compatibility.
- Unknown/blank explicit values: startup failure.
- `trusted_header` startup: require a shared secret of at least 32 characters.
- `oauth` startup: require HTTPS external issuer/resource URLs, non-empty
  required scopes, supported provider, and a usable resource-binding strategy;
  reject shared-secret/email-header fallback.
- Request time: the selected authenticator yields one verified Frappe username
  plus non-secret auth context, or stops the request with the correct HTTP
  challenge/status before tool execution.
- Tool runtime: `mcp_erpnext` initializes Frappe, calls `frappe.set_user` once
  with the verified username, runs native permission checks, and destroys the
  request context.

Auth mode must be immutable process configuration. Never select it from an MCP
tool argument or request header.

## 8. Trusted-Header Compatibility

The existing contract remains:

```http
Authorization: Bearer <MCP_HTTP_SHARED_SECRET>
X-MCP-User-Email: person@example.com
```

Task 02 must preserve:

- startup rejection of absent/short secrets (`identity.py:62-75`);
- constant-time comparison with `hmac.compare_digest` (`identity.py:78-86`);
- case-insensitive header lookup through Starlette/mapping behavior and the
  explicit canonical/lower-case email-header lookup (`identity.py:54-59`);
- generic HTTP 401 for missing, malformed, or incorrect Authorization without
  logging the credential (`http_transport.py:32-40`);
- stripped, syntactically checked email identity (`identity.py:107-117`);
- enabled existing User lookup, explicit Guest rejection, and no fallback
  (`identity.py:89-104`);
- no `MCP_FRAPPE_USER` fallback for any configured HTTP request;
- pre/post `frappe.destroy()` cleanup for all tool outcomes;
- no secret, Authorization value, or raw user email in logs.

The auth-mode refactor should remove duplicate shared-secret validation at
middleware and tool time only if the authenticated identity is carried in a
request-scoped, tamper-resistant context. It must not weaken defense in depth by
copying unverified headers deeper into the tool runtime.

## 9. ChatGPT / MCP OAuth Requirements

The following classifications use the OpenAI guide and MCP 2025-11-25
authorization specification current on the audit date.

| Requirement | Classification | Project consequence |
|---|---|---|
| OAuth 2.1 security model for authenticated remote MCP | Required | OAuth mode must conform; shared-secret mode is a separate compatibility mode |
| Authorization Code flow for user-delegated ChatGPT connections | Required | Browser login/consent, code exchange, and exact redirect allowlisting |
| PKCE with `S256` and metadata advertisement | Required | AS metadata must include `code_challenge_methods_supported: ["S256"]` |
| Protected Resource Metadata (RFC 9728) | Required | MCP server serves its own resource document with at least `resource` and `authorization_servers` |
| Authorization-server metadata (RFC 8414) or OIDC discovery | Required | AS discovery must expose correct endpoints/capabilities |
| `resource` on authorization and token requests | Required | AS must accept and bind the canonical MCP resource |
| Access-token audience/resource validation | Required | MCP server rejects a token not issued specifically for it |
| Bearer token on every HTTP request; never query-string token | Required | Middleware validates every MCP request |
| 401 plus `WWW-Authenticate`/resource metadata for missing/invalid/expired token | Required | Use SDK resource-server middleware behavior |
| 403 plus `insufficient_scope` challenge | Required/recommended by context | Use for authenticated tokens lacking required scopes |
| Client registration | One of preregistration, CIMD, or DCR required operationally | OpenAI supports all three; CIMD is preferred, DCR remains supported |
| CIMD | Recommended, not mandatory | Frappe lacks it; DCR or pre-registration can be used initially |
| DCR | Optional in current MCP spec | Frappe supports configurable DCR; live setting must be verified |
| Refresh token | Operationally recommended for ChatGPT continuity | OpenAI warns that absent refresh/offline access may require reauthentication |
| `offline_access` advertisement | Recommended for OIDC-style reliable refresh | Frappe metadata gap must be tested/remediated even though Frappe issues refresh tokens in source tests |
| Scopes | Required for authorization policy | Define a minimal MCP scope; enforce it at middleware and token validation |
| Authorization response `iss` | Optional if not advertised; recommended hardening | OpenAI uses callback-ID-specific redirects when issuer identification is absent |
| Dynamic step-up scopes | Optional for v1 | One server-wide minimum scope is sufficient initially |
| HTTPS endpoints | Required in production | External MCP and AS URLs must be HTTPS |

OpenAI's guide additionally states that ChatGPT currently uses
authorization-code + S256 PKCE, sends the resource on authorization and token
requests, attaches the bearer token to later MCP requests, and expects the
server to validate issuer, audience, expiry, and scopes on each request. It
supports CIMD, DCR, and predefined clients. ChatGPT does not use machine-to-
machine client-credentials authentication for this user-linking flow.

## 10. Frappe OAuth Capability Audit

### Supported native behavior

- **Authorization Code:** endpoints are declared in
  `frappe/integrations/oauth2.py:29-35`; `authorize`, `approve`, and `get_token`
  implement the browser/code/token flow at lines 66-185.
- **PKCE:** `frappe/oauth.py:87-89` persists challenge/method on the
  authorization code; lines 144-165 verify `S256` and `plain`. AS metadata
  advertises only `S256` at `oauth2.py:324-350`. Frappe tests exercise S256 at
  `test_oauth20.py:237-280`.
- **AS metadata:** `/.well-known/oauth-authorization-server` is served when
  enabled, and advertises code, refresh token, `none`/`client_secret_basic`,
  endpoints, and S256 (`oauth2.py:293-356`). The OAuth Settings field defaults
  metadata exposure on (`oauth_settings.json:67-82`). Live effective settings
  were not queried.
- **Protected-resource metadata:** Frappe can expose RFC 9728 metadata at its
  own origin (`oauth2.py:437-491`). This does not automatically describe the
  separately hosted `mcp_erpnext` Streamable HTTP resource.
- **DCR:** optional endpoint and setting exist (`oauth2.py:353-434`;
  `oauth_settings.json:91-95`). It accepts authorization-code/refresh grants,
  code response, secure redirects, and public `none` clients
  (`integrations/utils.py:17-47,206-274`).
- **Token-endpoint client authentication:** AS metadata advertises `none` and
  `client_secret_basic` (`oauth2.py:337-350`). The OAuth Client model/DCR code
  also recognizes `client_secret_post` (`oauth_client.json:194-200`,
  `integrations/utils.py:268-271`), but it is not advertised. The first ChatGPT
  path should use advertised public-client `none` plus PKCE rather than depend
  on the inconsistent method.
- **CIMD:** no support or metadata flag was found.
- **Access and refresh tokens:** `save_bearer_token` stores client, native
  Frappe user, granted scopes, access token, refresh token, and expiry
  (`frappe/oauth.py:187-214`). The authorization-code test asserts both access
  and refresh tokens (`test_oauth20.py:190-232`).
- **Scope validation:** requested scopes must be a subset of OAuth Client
  scopes (`frappe/oauth.py:49-59`). Token records store scopes. Native bearer
  validation checks current client scopes (`frappe/oauth.py:227-242`). MCP
  operation-level minimum scopes still need resource-server enforcement.
- **Token validation/user:** `validate_bearer_token` checks expiration, revoked
  status, and existence of an enabled `User`, then puts the token record's user
  on the OAuth request (`frappe/oauth.py:227-242`). Frappe WSGI auth then calls
  `frappe.set_user` from the token record (`frappe/auth.py:655-690`).
- **Revocation:** revocation marks access or refresh token records `Revoked`
  (`frappe/oauth.py:254-270`); native validation rejects revoked tokens.
- **Redirect URIs:** authorization validation requires an exact registered URI
  (`frappe/oauth.py:28-47,171-180`); DCR rejects non-HTTPS redirects except
  loopback HTTP outside developer mode (`integrations/utils.py:206-238`).
- **Request-local Frappe auth:** native WSGI bearer authentication is not
  automatically invoked by the standalone FastMCP/uvicorn process. A verifier
  in `mcp_identity` must resolve the opaque token using the initialized Frappe
  site and return SDK access-token context.

### Gaps and cautions

1. No authorization-code/token field or validation path records the RFC 8707
   `resource` parameter. Searches of `frappe/oauth.py`,
   `frappe/integrations/oauth2.py`, and `frappe/integrations/utils.py` find
   `resource` only in metadata generation, not grant processing.
2. `OAuth Bearer Token` has no audience/resource field
   (`oauth_bearer_token.json:9-78`). Native bearer validation consequently
   cannot prove the token was minted for the MCP resource.
3. The access token is opaque. Opaque tokens are acceptable if introspected or
   validated authoritatively, but this standalone server must perform the
   equivalent checks against Frappe state; it cannot apply JWT signature/issuer/
   audience checks that do not exist.
4. Frappe's AS metadata does not advertise `scopes_supported`, including
   `offline_access`. Its separate PRM can advertise administrator-configured
   scopes. ChatGPT refresh behavior therefore needs a real interoperability
   test.
5. The AS metadata does not advertise
   `authorization_response_iss_parameter_supported`; this is compatible with
   OpenAI's callback-ID path, but the stable callback/issuer hardening path is
   unavailable without more work.
6. `validate_bearer_token` rejects deleted/disabled users but does not explicitly
   reject Guest. Normal authorization redirects Guest to login, but the MCP
   compatibility verifier must independently reject Guest.
7. Frappe introspection reports active status from token status without the same
   expiry/user checks used by `validate_bearer_token`
   (`oauth2.py:251-290`). Do not treat `active: true` from this endpoint alone as
   sufficient; use authoritative record validation or harden introspection.

Where the Frappe documentation and source differ in detail, this audit treats
the installed 16.34.0 source as runtime authority. The official OAuth page also
warns that some linked pages may be outdated.

## 11. Compatibility Matrix

| Requirement | ChatGPT/MCP need | Frappe 16.34 support | Evidence | Gap? | Consequence |
|---|---|---|---|---|---|
| Authorization Code | Required | Yes | `oauth2.py:66-185`; `test_oauth20.py:190-232` | No | Reuse native login/consent/code issuance |
| PKCE S256 | Required | Yes when client sends it; metadata advertises S256 | `oauth.py:87-89,144-165`; `oauth2.py:350`; test lines 237-280 | No for ChatGPT flow | Reject any non-S256 MCP authorization flow in compatibility boundary |
| AS metadata | Required | Yes, setting-controlled | `oauth2.py:293-356` | Live setting unverified | Startup/deployment check must confirm public HTTPS metadata |
| MCP-server PRM | Required | Frappe can describe its own origin; FastMCP SDK can describe MCP resource | Frappe `oauth2.py:437-491`; SDK `AuthSettings`/FastMCP auth routes | Yes if using Frappe document directly | Serve MCP-specific PRM from the MCP endpoint/app |
| RFC 8707 resource on auth/token requests | Required | Unknown params may arrive, but not persisted or enforced | No grant-path reference in installed source | **Critical gap** | Compatibility layer/AS enhancement must bind and later validate resource |
| Audience/resource validation | Required | No audience/resource on opaque bearer record | `oauth_bearer_token.json:9-78`; `oauth.py:227-242` | **Critical gap** | Direct Frappe OAuth is insufficient |
| Bearer token validation | Required | Expiry, revocation, enabled user, client scopes | `oauth.py:227-242` | Partial | Reuse checks and add resource, expected client, Guest, required scope |
| Token-to-Frappe User | Required for this project | Native token `user` | `oauth.py:194-214,227-242` | No | Token record user is authoritative execution identity |
| Disabled/deleted user | Fail closed | Yes | `oauth.py:230-234` | No | Recheck every request |
| Guest rejection | Fail closed | Not explicit in bearer validator | `oauth.py:227-242` | Yes | Add explicit compatibility-layer rejection |
| Refresh tokens | Recommended for ChatGPT continuity | Issued and validated | `oauth.py:187-214,272-299`; test lines 224-229 | Partial interoperability gap | Verify ChatGPT refresh behavior and rotation policy |
| Refresh-token rotation | Required for public clients by current MCP security text | Refreshed token is newly saved, but old-token rotation/reuse behavior was not proven | `oauth.py:187-214,272-299` | Unverified | Add focused source/runtime tests before production |
| `offline_access` discovery | OpenAI-recommended | Not in AS metadata | `oauth2.py:324-356` | Yes | ChatGPT may require reauthentication; test/remediate metadata |
| DCR | Optional/supported by OpenAI | Yes, setting-controlled | `oauth2.py:353-434`; `utils.py:206-274` | Live setting unverified | Viable initial registration path |
| CIMD | Preferred current mechanism | No | No flag/handler in installed source | Non-blocking gap | Use DCR or a predefined client initially |
| Public token endpoint auth | ChatGPT supports `none` | Advertised and DCR-supported | `oauth2.py:344`; `utils.py:268-269` | No for chosen path | Use `none` with S256; do not send/store a client secret |
| Scopes | Required | Client/request/token scopes exist | `oauth.py:49-59,209,235-241` | MCP enforcement missing | SDK verifier/middleware enforces a minimal MCP scope |
| Exact redirect validation | Required | Yes | `oauth.py:28-47,171-180` | No | Register exact ChatGPT callback shown by management UI |
| Authorization response `iss` | Conditional/OpenAI hardening | Not advertised/proven | AS metadata lacks flag | Non-blocking | Use callback-ID-specific redirect initially |
| 401 `WWW-Authenticate` with PRM | Required | Frappe WSGI adds a Frappe-origin challenge; current MCP middleware returns bare 401; SDK supports correct challenge | `frappe/app.py:356-360`; `mcp_erpnext/http_transport.py:32-40`; SDK bearer middleware | Yes | OAuth mode must use SDK/resource-specific challenge |
| 403 insufficient scope | Required for scope failure | MCP SDK supports it; current app does not configure SDK auth | installed SDK bearer middleware lines 102-143 | Integration gap | Configure SDK auth in OAuth mode |
| HTTPS | Required | Deployment concern | MCP/OpenAI spec | Unverified | Reject non-HTTPS external OAuth URLs outside explicit tests |

## 12. OAuth Provider Architecture Decision

### Option 1: Direct Frappe OAuth — reject for now

Benefits are native user ownership, consent, token storage, revocation, and no
new identity database. It fails the current MCP requirement that tokens be
issued specifically for, and validated against, the MCP resource. It also does
not inject native Frappe WSGI authentication into the standalone ASGI process.

### Option 2: `mcp_identity` compatibility layer over Frappe OAuth — recommend

The layer should:

- expose/configure MCP-specific protected-resource metadata;
- use the installed SDK's `AuthSettings`, `TokenVerifier`, bearer middleware,
  and request-local access-token context rather than reimplementing HTTP OAuth
  plumbing;
- validate the opaque token against Frappe's token record, expiry, revocation,
  expected OAuth client, granted/required scopes, enabled non-Guest user, and a
  persisted canonical MCP resource binding;
- return the native token record's `user` as the verified Frappe execution user;
- provide the minimal Frappe authorization-server compatibility needed to
  preserve and enforce RFC 8707 `resource` through authorization code, token,
  refresh, and revocation lifecycle;
- fail startup or every OAuth request closed until real resource binding is
  available. A configured expected client ID alone is useful defense in depth,
  but is not a substitute for resource binding because OAuth client and resource
  server are different roles.

The implementation should reuse native Frappe records and controller behavior
where possible. It should not copy passwords, build a new login screen, trust
email claims, or mint an unrelated token format merely to avoid the native
provider.

### Option 3: generic provider interface now — defer

There is only one concrete provider requirement. A full adapter abstraction
would speculate about JWT/JWKS, introspection, tenant, issuer, subject mapping,
and client-registration differences that are not yet required. Keep modules and
contracts provider-neutral at the boundary, permit only `frappe` in a small
provider setting, and extract an interface only when a second provider is
approved.

## 13. Identity Mapping Decision

For the first Frappe OAuth implementation, the authoritative execution identity
is:

```text
validated OAuth Bearer Token record.user
  -> revalidate existing enabled Frappe User
  -> explicitly reject Guest
  -> return Frappe User name
```

This is superior to email mapping: the authorization code is created from
`frappe.session.user` (`frappe/oauth.py:76-92`), and token issuance persists
that native Frappe username (`frappe/oauth.py:187-214`). No external subject
mapping is needed for the first provider.

OAuth mode rules:

- Never trust or consult `X-MCP-User-Email`.
- Never fall back to `MCP_FRAPPE_USER`.
- Do not cross-check against another caller-controlled identity header.
- Recheck token validity and User enabled/existence on every request.
- Reject Guest explicitly.
- Deleted/disabled users fail as invalid credentials without revealing whether
  the user or token existed.
- A future external provider must use stable issuer+subject mapping, not email,
  unless a separately audited verified-email mapping policy is approved.

## 14. Request Isolation / Concurrency Findings

Frappe 16 uses a `ContextVar`-backed `frappe.local`
(`frappe/utils/local.py:1-59`). `frappe.init(..., force=True)` releases prior
local state, initializes the session as Guest, and `frappe.destroy()` closes the
database then releases local state (`frappe/__init__.py:144-227,330-336`).
`frappe.set_user` updates the request-local session and clears permission/user
caches (`frappe/__init__.py:382-395`).

The current HTTP wrapper destroys Frappe state before work and in `finally`
after every tool (`mcp_erpnext/runtime.py:97-104`). The concurrency unit test
uses independent `ContextVar` identities across two worker threads and expects
no crossing (`test_runtime.py:65-98`). This is good structural evidence, though
not a live multi-user ASGI stress test.

The installed MCP SDK's `AuthContextMiddleware` independently stores the
validated access token in a `ContextVar` and resets it in `finally`. OAuth mode
should consume that context, not retain token/user state in a module global or
FastMCP singleton.

Required Task 02 changes are narrow:

1. choose the path from configured transport/auth mode, never from presence of
   a header object;
2. authenticate at HTTP middleware before MCP execution;
3. carry only verified request-scoped principal/auth metadata into runtime;
4. keep pre/finally `frappe.destroy()` around the entire Frappe operation;
5. avoid holding a Frappe document/database connection across `await` points;
6. test two concurrent identities, exception-before-set-user, exception-after-
   set-user, and sequential context reuse.

Multiple processes/workers are safe only if OAuth truth is shared in Frappe's
database/cache and no process-local token authorization state is introduced.

## 15. Error Contract Recommendation

Authentication must be rejected before tool execution. Public responses should
not distinguish unknown user from unknown/revoked token.

| Condition | HTTP behavior | Internal/common category |
|---|---|---|
| Missing OAuth bearer token | 401 + Bearer `WWW-Authenticate` with `resource_metadata` | `MCP_AUTHENTICATION_MISSING` |
| Malformed/unknown/expired/revoked/wrong-resource token | 401 + same challenge; optional standard `invalid_token` | `MCP_AUTHENTICATION_INVALID` |
| Disabled/deleted/Guest token user | 401, same public invalid-credential shape | `MCP_AUTHENTICATION_INVALID` internally log reason safely |
| Insufficient scope | 403 + `WWW-Authenticate: Bearer error="insufficient_scope"`, required scope, PRM URL | `MCP_AUTHORIZATION_INSUFFICIENT_SCOPE` |
| Provider/config unavailable at startup | Refuse startup | `MCP_IDENTITY_CONFIGURATION_ERROR` |
| Provider becomes unavailable at request time | 503 or generic 401 only where validity cannot be established; never accept | `MCP_IDENTITY_PROVIDER_UNAVAILABLE`, retryable internally |
| Trusted-header missing/wrong secret | Preserve current generic 401 | Existing authentication codes |
| Trusted-header missing/malformed/unknown/disabled user | Preserve fail-closed behavior; Task 02 may move it to transport 401 only as a documented compatibility decision | Existing user identity codes |

Logs may include a correlation ID, mode, provider name, site, tool name, and a
one-way user/token fingerprint after parsing. They must never include access or
refresh tokens, Authorization headers, shared secrets, authorization codes,
client secrets, raw provider bodies, or unneeded user-identifying claims.

OAuth protocol errors belong in HTTP status/headers. Once authentication has
succeeded, ERPNext permission failures should remain the existing safe MCP
`ERP_PERMISSION_DENIED` envelope; authentication and ERP authorization must not
be conflated.

## 16. Proposed Future Configuration Contract

The following is a recommendation for Task 02; it is **not implemented by this
audit**.

```dotenv
# HTTP authentication selection. Absent means trusted_header for compatibility.
MCP_HTTP_AUTH_MODE=trusted_header

# trusted_header only
MCP_HTTP_SHARED_SECRET=<minimum-32-character-secret>

# oauth only; initially the only accepted provider value
MCP_OAUTH_PROVIDER=frappe

# Canonical public authorization-server issuer/origin.
MCP_OAUTH_ISSUER_URL=https://erp.example.com

# Canonical public MCP resource URL, including path when it identifies the server.
MCP_OAUTH_RESOURCE_SERVER_URL=https://mcp.example.com/mcp

# Space-delimited minimum scope set advertised/challenged/enforced by the MCP server.
MCP_OAUTH_REQUIRED_SCOPES=mcp:access

# Dedicated expected Frappe OAuth Client ID; not a secret, and not a replacement
# for resource binding.
MCP_OAUTH_FRAPPE_CLIENT_ID=<registered-client-id>
```

Do not add an OAuth client secret to the MCP resource server merely because the
authorization server has one. ChatGPT can use a public DCR client with PKCE, a
predefined client, or later CIMD. Frappe OAuth Settings and OAuth Client records
remain site-owned database configuration; environment variables should not
duplicate redirect URIs, client secrets, DCR enablement, or token lifetime.

Mode-specific validation:

- `trusted_header`: require `MCP_HTTP_SHARED_SECRET`; ignore/reject OAuth-only
  settings according to a documented strictness policy.
- `oauth`: require issuer, resource, provider, scopes, expected Frappe client,
  and an implemented resource-binding mechanism; do not require or use shared
  secret/email header/stdio user.
- `stdio`: `MCP_HTTP_AUTH_MODE` is irrelevant; configured identity remains
  `MCP_FRAPPE_USER` resolved by `mcp_identity`.

## 17. Proposed Code Ownership / File Changes

Minimum likely Task 02 surface (final paths may be adjusted after a focused
design spike):

### `mcp_identity`

- Update `mcp_identity/identity.py` or split only when warranted:
  common verified-principal/error types, configured stdio resolver, trusted-
  header resolver.
- Add `mcp_identity/settings.py`:
  `HTTPAuthMode`, identity-owned environment parsing, mode validation.
- Add `mcp_identity/http_auth.py`:
  construct trusted-header or SDK OAuth middleware/integration without importing
  `mcp_erpnext`.
- Add `mcp_identity/oauth/frappe.py` (or one equivalently narrow module):
  Frappe opaque-token verifier, native user resolution, expected-client/scope/
  expiry/revocation/Guest/resource checks.
- Add only the persistence/controller surface proven necessary to bind RFC 8707
  resource across authorization code, token, refresh, and revocation. Reuse
  Frappe OAuth records; do not create a generic external-identity mapping.
- Add/update focused tests under `mcp_identity/tests/`.
- Later update `mcp_identity/.env.example`, README, OAuth deployment guide, and
  exact site configuration instructions.

### `mcp_erpnext`

- `settings.py`: remove identity-owned parsing/validation; retain transport,
  backend, runtime, profile, and approval settings.
- `http_transport.py`: replace hard-coded shared-secret middleware with the
  `mcp_identity` HTTP auth integration.
- `mcp_server.py`: pass OAuth `AuthSettings`/`TokenVerifier` into FastMCP when
  selected and mount/retain correct public metadata routes.
- `runtime.py`: consume a verified principal for both stdio and HTTP; choose by
  configured transport/auth mode and preserve Frappe scope cleanup.
- `observability.py`: map any new common identity categories without provider
  details.
- Update `test_http_transport.py`, `test_runtime.py`, settings/startup tests,
  and dependency/import tests.
- Update `.env.example`, README, `docs/MCP_SETUP.md`,
  `docs/LIBRECHAT_MCP_HTTP_SETUP.md`, relevant testing docs, and
  `docs/COMMANDS.md` only if Task 02 introduces a reusable command.

Do not change ERPNext services, profiles, tool input contracts, approval policy,
or business permissions for OAuth.

## 18. Backward-Compatibility Risks

- **Trusted-header/LibreChat:** absent auth-mode must retain current secret +
  verified-email behavior. Renaming headers or secrets would break configured
  clients.
- **Stdio:** moving resolution must preserve `MCP_FRAPPE_USER`, direct-site
  initialization, and persistent stdio behavior. New validation may expose
  previously accepted disabled/unknown configured users earlier; that is an
  intentional fail-closed correction and needs tests/release notes.
- **REST backend:** it remains stdio-only and bound to the API-key owner. Do not
  apply local `MCP_FRAPPE_USER` or OAuth end-user identity to the remote bridge
  without a separate delegated-identity architecture audit.
- **HTTP error shape:** moving identity failures from a tool-level structured
  error to HTTP 401 may affect existing tests/clients. Preserve current behavior
  for trusted-header unless there is an explicit migration decision; OAuth must
  follow standard HTTP challenges.
- **FastMCP session identity:** authenticated principal must be tied to each
  request/session consistently; token switching within a stateful session must
  be rejected or handled according to SDK behavior.
- **Metadata URL/proxying:** external scheme/host/path must match what ChatGPT
  sees. Deriving issuer/resource solely from an internal uvicorn request can
  publish wrong URLs behind a reverse proxy.
- **Frappe DCR defaults:** schema defaults are not proof of migrated/live setting
  values. Enabling DCR creates OAuth Client records and requires an operator
  decision.
- **Scope changes:** tightening scopes can invalidate existing tokens or require
  reauthorization.

## 19. Security Risks and Required Controls

1. **Token confused-deputy/audience misuse (highest):** never accept a general
   Frappe bearer token merely because it is active. Bind it to the canonical MCP
   resource and expected authorization server/client policy.
2. **Header impersonation:** OAuth mode must entirely ignore
   `X-MCP-User-Email`; trusted-header mode must validate the shared secret before
   using the email.
3. **Fallback escalation:** no HTTP/OAuth failure may reach
   `MCP_FRAPPE_USER`, Administrator, Guest, or previous-request identity.
4. **Context leakage:** keep ContextVar-backed auth and Frappe state scoped with
   `finally` cleanup; never cache the active user globally.
5. **Overbroad Frappe token:** use a dedicated OAuth Client and minimal MCP
   scope. Native ERPNext permissions remain mandatory after authentication.
6. **Expired/revoked/disabled state:** check on every request, not only at MCP
   session initialization.
7. **Redirect/DCR abuse:** exact redirect validation, HTTPS/loopback rules,
   controlled DCR enablement, and rate/abuse controls are required. If CIMD is
   added later, protect its server-side fetch against SSRF.
8. **Secret/token leakage:** redact all authorization material and provider
   bodies; store no raw access token in logs, errors, approval payloads, or MCP
   results.
9. **Proxy-origin confusion:** configure canonical external issuer/resource
   URLs; do not blindly trust forwarded host/proto headers.
10. **Refresh replay:** confirm native rotation/reuse behavior before production;
    harden or shorten sessions if it does not meet public-client requirements.

OAuth authenticates the user; it does not replace Frappe/ERPNext record-level
permissions or the existing `CONFIRM_WRITE` approval guard.

## 20. Implementation Recommendation

1. Add common identity settings/result/error contracts in `mcp_identity` and
   centralize configured stdio resolution while preserving names and behavior.
2. Refactor trusted-header assembly behind the new HTTP auth-mode boundary with
   no behavior change; change `mcp_erpnext.runtime` to fail closed based on
   configured transport rather than header presence.
3. Add tests proving the refactor before adding OAuth.
4. Implement the Frappe OAuth resource-binding compatibility seam. Treat this
   as a prerequisite: do not enable OAuth mode with only client-ID checking.
5. Implement an async SDK `TokenVerifier` that performs bounded native Frappe
   lookups within a clean site context and returns `AccessToken` containing
   client ID, scopes, expiry, canonical resource, native user as subject, and
   issuer claim. Do not retain a Frappe document across awaits.
6. Configure FastMCP OAuth auth settings/PRM/challenges for OAuth mode and map
   the verified SDK subject to the Frappe runtime user.
7. Add documentation/config examples, leaving trusted-header as the default.
8. Run source/unit tests, then an operator-approved site test with a dedicated
   OAuth Client and settings, then MCP Inspector OAuth, and only then ChatGPT
   remote MCP linking.
9. Keep OAuth marked experimental/fail-closed until resource binding, refresh,
   multi-user isolation, revocation, and ChatGPT interoperability all pass.

## 21. Acceptance-Test Plan for the Future Implementation

### Configuration and startup

- absent auth mode defaults to `trusted_header`;
- unknown mode fails startup;
- trusted mode requires strong secret and does not require OAuth values;
- OAuth mode rejects missing/non-HTTPS issuer or resource, missing scopes,
  unsupported provider, and missing resource-binding capability;
- stdio ignores HTTP auth mode and still requires a valid configured user;
- REST backend remains stdio-only and API-principal-bound.

### Trusted-header regression

- valid secret + enabled email resolves exact Frappe User;
- missing/malformed/wrong secret returns 401 and never looks up a user;
- missing/malformed/unknown/disabled/Guest email fails closed;
- HTTP never consults `MCP_FRAPPE_USER`;
- two concurrent users and sequential reused worker contexts do not leak;
- no credential appears in logs/errors.

### Stdio unified boundary

- existing enabled `MCP_FRAPPE_USER` works;
- absent/unknown/disabled/Guest configured user fails before the operation;
- explicit runtime argument cannot bypass configured policy unless deliberately
  retained and tested as an internal-only seam;
- no OAuth/HTTP header logic executes.

### OAuth protocol/resource server

- unauthenticated and malformed/unknown/expired/revoked token => 401 with valid
  `WWW-Authenticate` and PRM URL;
- PRM resource exactly equals configured canonical MCP URL and points to the
  correct issuer;
- AS metadata is reachable and advertises authorization code, S256, supported
  token endpoint auth, and chosen registration mechanism;
- authorization and token requests carry the same canonical `resource`;
- altered/missing resource fails; token minted for another resource/client is
  rejected;
- insufficient scope => 403 standard challenge; correct scope succeeds;
- exact redirect URI is enforced;
- OAuth email header and `MCP_FRAPPE_USER` are ignored;
- token's native Frappe user is applied and native permission differences are
  observable with two users;
- Guest, disabled, and deleted token users fail closed;
- token refresh preserves user, scopes, and resource while rotating/rejecting
  replay as required;
- revocation takes effect on the next request;
- token switch within an existing MCP session cannot cross identities;
- concurrent users across tasks and multiple workers remain isolated.

### Compatibility/E2E

- DCR public-client (`token_endpoint_auth_method=none`) path with S256, or an
  explicitly chosen predefined-client path;
- MCP Inspector completes discovery, authorization, initialize, tools/list, and
  one permission-sensitive tool call;
- ChatGPT scans tools, completes OAuth, refreshes after short access-token
  expiry, and runs as the correct Frappe user;
- trusted-header LibreChat flow remains unchanged;
- authenticated write still requires the existing prepare/approval/confirm
  guard and normal Frappe permissions.

Run focused unit tests and the full established unittest suite separately. Live
OAuth tests require explicit authorization because they create OAuth records and
tokens; they were not run during this audit.

## 22. Limitations / Unverified Items

- No live `yob.localhost` database/site query was run. Effective OAuth Settings,
  installed schema, OAuth Client records, DCR enablement, scopes, proxy/public
  URLs, and per-site app versions are unverified.
- No OAuth Client, authorization code, bearer token, or refresh token was
  created, changed, or revoked.
- No local service was restarted and no live Streamable HTTP, MCP Inspector,
  LibreChat, or ChatGPT request was made.
- ChatGPT behavior is based on official current documentation; the product is
  beta and can change. Exact redirect URI/client-registration choice must be
  taken from the ChatGPT management UI during the approved live test.
- Frappe refresh-token rotation and replay semantics were not proven end-to-end.
- Whether an upstream Frappe change can provide resource binding with less code
  than an app-owned compatibility seam needs a focused Task 02 design spike.
  OAuth mode must remain disabled if neither route gives enforceable binding.
- Unit tests currently model concurrency but do not establish multi-worker/live
  ASGI and database isolation.

## 23. Exact Next Task

**Task 02 - MCP Identity Auth-Mode and Frappe OAuth Compatibility
Implementation**

Scope:

1. introduce `MCP_HTTP_AUTH_MODE=trusted_header|oauth` in `mcp_identity`, with
   absent value defaulting to `trusted_header`;
2. move `MCP_FRAPPE_USER` resolution (not Frappe runtime setup) behind the
   `mcp_identity` boundary without renaming it;
3. refactor current trusted-header integration with zero contract regression;
4. implement a Frappe-first OAuth compatibility/resource-server layer using the
   installed MCP SDK, including MCP-specific PRM and standard 401/403 challenges;
5. implement and prove RFC 8707 resource binding across authorization, token,
   refresh, and bearer validation before OAuth mode can start;
6. resolve OAuth execution identity only from the validated native Frappe OAuth
   token user, with no email-header or configured-user fallback;
7. preserve request-local Frappe cleanup, ERPNext native permissions, REST
   backend behavior, and existing approval guards;
8. add complete focused/full tests and operator-gated Inspector/ChatGPT
   acceptance steps; and
9. update identity-owned configuration/docs and consumer references without
   creating a speculative multi-provider framework.
