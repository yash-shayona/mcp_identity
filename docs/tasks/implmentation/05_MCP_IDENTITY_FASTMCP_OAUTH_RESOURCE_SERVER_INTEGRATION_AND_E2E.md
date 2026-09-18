# Task 05 - FastMCP OAuth Resource-Server Integration and End-to-End Verification

## Status

Ready for implementation.

## Target Apps

Primary identity/auth owner:

- `mcp_identity`

Consumer / MCP server integration:

- `mcp_erpnext`

## Task Type

Implementation + regression tests + live local OAuth verification + external ChatGPT verification when a public HTTPS MCP endpoint is available.

This task activates the OAuth **resource-server side** only after the Task 04/04V/04F authorization-server resource binding has been proven live.

---

## 1. Scope

Implement OAuth authentication for `MCP_TRANSPORT=streamable-http` by wiring the already-proven Frappe OAuth authorization server into the FastMCP/Python MCP SDK resource-server authentication boundary.

The implementation must:

1. make `MCP_HTTP_AUTH_MODE=oauth` usable for Streamable HTTP;
2. validate Frappe opaque OAuth access tokens on every protected MCP HTTP request;
3. require the token to belong to the configured OAuth Client;
4. require exact canonical MCP resource binding;
5. require configured scopes from the token's recorded scopes;
6. require an Active, unexpired token;
7. require the native token owner to be an existing enabled non-Guest Frappe User;
8. return a verified request-scoped principal to the MCP SDK;
9. configure FastMCP/Python MCP SDK auth settings and token verifier using installed SDK-native APIs;
10. expose RFC 9728 protected-resource metadata through the SDK-native route where supported;
11. return standards-safe 401/403 bearer challenges;
12. make `mcp_erpnext` execute each OAuth-authenticated request as the exact verified Frappe token user;
13. preserve native Frappe/ERPNext permissions;
14. preserve existing trusted-header, stdio, REST, profile, approval, and business-tool behavior;
15. verify the complete local OAuth resource-server flow on the approved local/testing-only site;
16. verify ChatGPT OAuth end-to-end only when an actual public HTTPS MCP endpoint and exact ChatGPT callback/client details are available.

Do not implement a second authorization server inside FastMCP.

Frappe remains the Authorization Server.
The MCP HTTP process becomes only the Resource Server.

---

## 2. Objective

Final architecture:

```text
                         ChatGPT / MCP Client
                                  |
                                  | GET protected-resource metadata
                                  v
                    FastMCP Streamable HTTP Resource Server
                                  |
                                  | authorization_servers
                                  v
                     Frappe OAuth Authorization Server
                                  |
                         Frappe login / consent
                                  |
                     authorization code + PKCE S256
                                  |
                          Frappe access token
                                  |
                                  | Authorization: Bearer <token>
                                  v
                    FastMCP bearer authentication
                                  |
                                  v
                     mcp_identity TokenVerifier
                                  |
               +------------------+-------------------+
               | status / expiry / client / scopes   |
               | token resource / client resource    |
               | configured resource                 |
               | native Frappe token user            |
               +------------------+-------------------+
                                  |
                           Verified Principal
                                  |
                                  v
                             mcp_erpnext
                                  |
                      fresh Frappe runtime scope
                                  |
                    frappe.set_user(token.user)
                                  |
                                  v
                    existing ERPNext permissions
                                  |
                                  v
                         existing MCP tool
```

The important boundary remains:

```text
mcp_identity
    authenticates and verifies WHO the request is.

mcp_erpnext
    initializes Frappe/ERPNext and executes AS that verified User.
```

---

## 3. Preconditions Already Proven

Do not repeat architecture discovery unless current source has materially changed.

Task 04/04V/04F already proved on the local test site:

- exactly three `custom_mcp_resource` fields exist;
- migration is idempotent;
- Frappe OAuth endpoint overrides are active across supported dispatch paths;
- bound authorization requires canonical `resource`;
- S256 PKCE is enforced;
- resource persists from OAuth Client -> Authorization Code -> OAuth Bearer Token;
- code exchange is replay-safe;
- refresh rotation is replay-safe;
- revocation works;
- unbound clients retain native Frappe OAuth behavior;
- real two-connection code replay tests pass;
- real two-connection refresh replay tests pass;
- OAuth token user remains the native Frappe User;
- Guest/missing user paths fail closed.

Task 05 must consume this proven authorization-server behavior rather than redesign it.

---

## 4. Required Inputs / Source of Truth

Before editing, inspect the current checkout.

Required project material:

- current `mcp_identity`;
- current `mcp_erpnext`;
- Task 03 implementation report;
- Task 04 implementation report;
- Task 04V live verification report;
- Task 04F fix + rerun report;
- current installed Frappe OAuth source;
- current installed Python MCP SDK source (`mcp==1.29.0` in the verified environment);
- current FastMCP/MCP server construction code in `mcp_erpnext`.

External protocol references may be consulted, but implementation must match the actual installed SDK.

### Important SDK version rule

Current upstream MCP Python SDK documentation may contain APIs added after installed `mcp==1.29.0`.

Therefore:

- inspect installed `1.29.0` source first;
- use installed-native APIs;
- do not upgrade the MCP SDK merely to make this task easier;
- do not copy newer-only settings blindly;
- if a newer SDK feature is truly required for correctness, stop and report that as a separate dependency decision rather than silently upgrading.

In particular, exact resource validation is mandatory even if installed SDK does not provide a dedicated `validate_token_resource` setting.

---

## 5. Mandatory Engineering Rule - Native / Existing Logic First

Before adding any helper or middleware:

1. inspect the current Task 03 identity boundary;
2. inspect installed MCP SDK `AuthSettings`, `TokenVerifier`, bearer backend, auth context, protected-resource routes, and challenge middleware;
3. inspect existing `mcp_erpnext` FastMCP/ASGI construction;
4. reuse those extension points;
5. write custom logic only for the Frappe-specific opaque-token verification that the SDK cannot know.

Do **not** create:

- a second bearer middleware if SDK middleware already covers it;
- a second protected-resource metadata router if SDK provides it;
- custom OAuth login/authorize/token endpoints;
- a JWT layer for opaque Frappe tokens;
- custom session identity storage;
- process-global principal state;
- generic provider abstraction.

---

## 6. Existing Modes That Must Remain

### Stdio

```dotenv
MCP_TRANSPORT=stdio
MCP_FRAPPE_USER=user@example.com
```

Must remain unchanged.

No OAuth header/token processing for stdio.

### Streamable HTTP trusted-header

```dotenv
MCP_TRANSPORT=streamable-http
MCP_HTTP_AUTH_MODE=trusted_header
MCP_HTTP_SHARED_SECRET=...
```

Request:

```http
Authorization: Bearer <shared-secret>
X-MCP-User-Email: user@example.com
```

Must remain unchanged.

### REST backend

Existing REST/API-key principal semantics remain unchanged.

OAuth must not reinterpret the REST API-key owner as an OAuth end-user.

---

## 7. OAuth Environment Contract

Activate the previously approved configuration:

```dotenv
MCP_TRANSPORT=streamable-http
MCP_HTTP_AUTH_MODE=oauth

MCP_OAUTH_ISSUER_URL=https://erp.example.com
MCP_OAUTH_RESOURCE_SERVER_URL=https://mcp.example.com/mcp
MCP_OAUTH_REQUIRED_SCOPES=mcp:access
MCP_OAUTH_FRAPPE_CLIENT_ID=<pre-registered-frappe-oauth-client-id>
```

### Ownership

`mcp_identity` owns parsing and validation of:

```text
MCP_HTTP_AUTH_MODE
MCP_OAUTH_ISSUER_URL
MCP_OAUTH_RESOURCE_SERVER_URL
MCP_OAUTH_REQUIRED_SCOPES
MCP_OAUTH_FRAPPE_CLIENT_ID
```

Existing identity ownership remains:

```text
MCP_HTTP_SHARED_SECRET
MCP_FRAPPE_USER
```

### Do not add

Do not add:

```text
MCP_OAUTH_PROVIDER
```

for the first implementation.

Frappe is the only approved OAuth Authorization Server in this version.

### OAuth mode ignores

When:

```dotenv
MCP_HTTP_AUTH_MODE=oauth
```

the HTTP path must ignore:

```text
MCP_HTTP_SHARED_SECRET
X-MCP-User-Email
MCP_FRAPPE_USER
```

A stale shared secret may remain in the process environment, but it must grant no OAuth access.

---

## 8. OAuth Startup Validation

For Streamable HTTP + OAuth, fail startup closed unless all required conditions are satisfied.

At minimum verify:

1. issuer URL is valid according to approved Task 02 rules;
2. MCP resource URL canonicalizes successfully;
3. required scope list is non-empty and deterministic;
4. configured Frappe OAuth Client ID is non-empty;
5. local Frappe site/backend required for authoritative token verification is available;
6. Task 04 Custom Fields exist;
7. configured OAuth Client exists;
8. OAuth Client has nonblank canonical `custom_mcp_resource`;
9. OAuth Client resource exactly equals configured MCP resource;
10. OAuth Client configuration is compatible with the approved authorization-code/PKCE flow;
11. no OAuth mode fallback to trusted-header or stdio occurs.

Do not infer public resource URL from:

- `Host`;
- `Forwarded`;
- `X-Forwarded-*`;
- incoming request origin.

Use the trusted configured URL only.

If local/direct Frappe database access is unavailable, OAuth mode must fail closed rather than silently using REST/API credentials as the end-user identity source.

---

## 9. Frappe Opaque Token Verification

Implement the smallest identity-owned verifier around the native Frappe OAuth Bearer Token truth.

Conceptual API, exact naming may follow current code:

```python
class FrappeOAuthTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        ...
```

or a narrow pure verifier plus SDK adapter.

### Per-request verification

For every bearer token:

1. accept the raw token only from SDK bearer authentication input;
2. perform authoritative lookup using the installed Frappe token lookup/storage convention;
3. do not assume forever that document name equals token if installed native helper says otherwise;
4. require native token record exists;
5. require `status == "Active"`;
6. require token is not expired;
7. require `token.client == MCP_OAUTH_FRAPPE_CLIENT_ID`;
8. load the OAuth Client;
9. require OAuth Client still exists;
10. canonicalize/validate stored client resource;
11. require token resource is nonblank;
12. require token resource equals current OAuth Client resource;
13. require both equal configured `MCP_OAUTH_RESOURCE_SERVER_URL`;
14. parse scopes from the **token record**;
15. require every configured MCP scope;
16. current OAuth Client scopes may narrow policy but must never expand token-record scopes;
17. require token native User exists;
18. require User is enabled;
19. reject `Guest`;
20. return only verified immutable principal/access-token data.

### Authoritative execution user

The execution user is only:

```text
OAuth Bearer Token.user
```

Never:

```text
X-MCP-User-Email
ChatGPT account email
MCP_FRAPPE_USER
OAuth userinfo email
caller-supplied subject
```

---

## 10. Frappe Runtime Safety in the Verifier

Token verification may need a local Frappe site context.

Keep this boundary:

```text
mcp_identity verifier
    -> short auth-only Frappe context
    -> read native OAuth/User truth
    -> return immutable verified data
    -> destroy auth context in finally
```

Then separately:

```text
mcp_erpnext
    -> fresh business Frappe context
    -> frappe.set_user(verified_subject)
    -> execute tool
    -> cleanup
```

Do not pass:

- Frappe Document objects;
- DB connection objects;
- mutable `frappe.local`;
- session objects

across an `await` boundary.

If the verifier is async while Frappe access is synchronous, use the installed/project-native worker-thread approach where appropriate.

Each worker must initialize/connect/destroy its own Frappe context safely.

---

## 11. SDK `AccessToken` Mapping

Inspect installed SDK `1.29.0` exact `AccessToken` fields.

Populate only supported fields.

Conceptually return:

```text
token        = raw token only because SDK contract requires it
client_id    = native OAuth token client
scopes       = scopes recorded on native OAuth Bearer Token
expires_at   = native expiration converted correctly
resource     = canonical persisted MCP resource
subject      = native Frappe token User
claims       = safe non-secret issuer/context if supported
```

Important:

- do not expose raw token in tool results;
- do not log it;
- do not put it in approval state;
- do not serialize it into observability payloads;
- do not add reversible token fingerprints.

If installed SDK does not support one conceptual field, adapt to installed contract instead of inventing one.

---

## 12. Exact Resource Enforcement

Task 04 already proves the Authorization Server issues resource-bound tokens.

Task 05 must independently enforce the Resource Server side.

Before verifier success:

```text
configured MCP resource
        ==
OAuth Client.custom_mcp_resource
        ==
OAuth Bearer Token.custom_mcp_resource
```

must be true after canonicalization.

Also require configured expected client ID.

Client ID is defense in depth, **not** a replacement for resource/audience validation.

If installed MCP SDK `1.29.0` itself does not compare `AccessToken.resource` with `resource_server_url`, the Frappe verifier must enforce equality before returning success.

If installed SDK has a native resource-validation switch, use it as an additional defense only after confirming its exact behavior in installed source.

---

## 13. FastMCP / MCP SDK Auth Assembly

Use installed SDK-native Resource Server integration.

Conceptual result:

```text
FastMCP / MCPServer
    auth = AuthSettings(
        issuer_url=...,
        resource_server_url=...,
        required_scopes=[...],
        ...
    )
    token_verifier = FrappeOAuthTokenVerifier(...)
```

Exact constructor/location must follow current installed `mcp_erpnext` server code and SDK `1.29.0`.

Do not mount an MCP SDK authorization-server provider.

Frappe remains the external Authorization Server.

Do not use `auth_server_provider` merely because the SDK exposes it.

---

## 14. Protected Resource Metadata

OAuth Streamable HTTP must expose RFC 9728 protected-resource metadata through the SDK-native route where installed SDK supports it.

For resource:

```text
https://mcp.example.com/mcp
```

metadata resource must be exactly the same canonical value.

It must point to the configured Frappe OAuth issuer in:

```text
authorization_servers
```

and advertise the configured required scopes where supported.

Verify the actual installed SDK route.

For a path resource such as `/mcp`, expected well-known routing should follow installed SDK/RFC 9728 behavior, not a hand-written guessed path.

Do not publish OAuth metadata in stdio.

Do not accidentally change trusted-header behavior unless the current HTTP app necessarily exposes a harmless route; if behavior changes, document and test it.

---

## 15. 401 / 403 Challenge Contract

Prefer installed MCP SDK middleware.

Verify actual responses.

### Missing / malformed / unknown / expired / revoked / wrong-client / wrong-resource / invalid-user token

Expected public behavior:

```text
401 Unauthorized
WWW-Authenticate: Bearer ...
```

Challenge must include the protected-resource metadata reference required by the installed MCP/OpenAI flow.

Do not reveal which private validation check failed.

### Valid token but missing required scope

Expected:

```text
403 Forbidden
error = insufficient_scope
```

Include required scope information where the applicable MCP/OpenAI authorization contract requires it.

### Provider/database unavailable

Fail closed.

Prefer a temporary/server failure distinction rather than misrepresenting a backend outage as a valid token rejection if current architecture cleanly supports that distinction.

Never accept on verifier exception.

### No unnecessary custom challenge layer

If installed SDK already emits a standards-compliant challenge, use it.

Add a narrow wrapper only if a verified required field is absent and the current client/spec actually requires it.

---

## 16. Request-Scoped Principal Consumption

In OAuth HTTP mode, `mcp_erpnext` runtime must obtain the already-verified SDK auth context.

Inspect installed SDK's request-context API.

Conceptually:

```text
get_access_token()
    -> verified SDK AccessToken
    -> subject/native Frappe User
```

Then:

```text
mcp_erpnext
    -> fresh Frappe business context
    -> frappe.set_user(subject)
    -> existing operation
    -> cleanup
```

Mandatory rules:

- missing SDK auth context in OAuth mode -> fail closed;
- never parse `X-MCP-User-Email`;
- never use `MCP_FRAPPE_USER`;
- never default to Administrator;
- never default to Guest;
- never trust a previous stateful MCP session user;
- every HTTP request uses the currently verified bearer token.

---

## 17. Stateful Session / Identity Switching

Explicitly test one HTTP/MCP process receiving:

```text
request 1 -> token for User A
request 2 -> token for User B
request 3 -> token for User A
```

The business runtime identity must be exactly:

```text
A -> B -> A
```

No session-sticky user.

Also test concurrent requests for two different users.

Frappe context and SDK auth ContextVar must not cross between requests.

---

## 18. Native ERPNext Permission Proof

Use at least two real/disposable Frappe Users with meaningfully different permissions on the local test site.

Prove:

```text
OAuth token for User A
    -> tool executes as User A
    -> User A permissions apply

OAuth token for User B
    -> same MCP server/tool
    -> executes as User B
    -> User B permissions apply
```

Do not bypass permissions with `Administrator`.

Prefer an existing read capability with safe, deterministic permission differences.

For write verification, use only a disposable/local record and preserve existing MCP approval rules.

OAuth authentication must never bypass:

- Frappe Role permissions;
- User Permissions;
- document permissions;
- existing profile allowlists;
- confirmation/approval gates.

---

## 19. ChatGPT Client Registration Strategy

First release remains **pre-registered OAuth Client**.

Do not enable MCP DCR/CIMD binding in Frappe for this task.

For ChatGPT live verification:

1. use the exact client identifier/callback details shown by the current ChatGPT MCP/plugin management UI;
2. do not invent or hard-code a redirect URI from memory;
3. configure a dedicated Frappe OAuth Client for the public MCP resource;
4. use Authorization Code flow;
5. use S256 PKCE;
6. use public-client token auth method compatible with the current ChatGPT mode and Frappe capability;
7. set exact required scopes;
8. set `custom_mcp_resource` to the exact public MCP resource URL;
9. set `MCP_OAUTH_FRAPPE_CLIENT_ID` to that client ID for the public deployment.

Do not reuse an Inspector/local client with a different client/resource pair.

---

## 20. ChatGPT Compatibility Gate

Current OpenAI MCP authentication behavior may evolve.

Before live ChatGPT verification, check the current official OpenAI MCP authentication documentation and compare it with installed MCP SDK `1.29.0`.

Particularly inspect:

- protected-resource metadata discovery;
- `resource` propagation;
- PKCE S256;
- supported client registration mode;
- exact redirect URI shown for the connection;
- bearer challenge behavior;
- tool-level OAuth metadata / `securitySchemes`;
- `_meta["mcp/www_authenticate"]` requirements, if applicable to the current ChatGPT linking UI.

### Native-first rule for tool security metadata

Inspect whether the installed Python MCP SDK / current server abstraction has a native way to express the ChatGPT-required tool security metadata.

If it does:

- use the native feature.

If it does not:

- do **not** invent a private/non-standard tool schema hack;
- first prove whether server-level HTTP bearer auth + protected-resource discovery is sufficient for the actual ChatGPT connection being tested;
- if ChatGPT specifically requires a feature unavailable in installed SDK, report a focused SDK compatibility blocker and propose a separate dependency-upgrade task.

Do not silently upgrade the SDK inside Task 05.

---

## 21. Local Live Verification Environment

The user has explicitly authorized the current local/testing-only environment for writes, migrations, OAuth test records, and test configuration.

Therefore Task 05 may:

- run `bench migrate`;
- create disposable OAuth Clients;
- create disposable test Users;
- create authorization codes/tokens through native Frappe OAuth;
- refresh/revoke;
- start the local Streamable HTTP MCP server;
- run local MCP/OAuth client tests;
- use MCP Inspector if installed/available;
- change local test environment variables for OAuth-mode runs;
- restore them afterward;
- clean all disposable records.

Do not hard-code `yob.localhost` in production code.

The implementation/report may record the actual test site used.

---

## 22. Local Resource URL

For purely local verification, a loopback MCP resource is allowed only according to the existing approved development canonicalization rules.

Example conceptually:

```text
http://127.0.0.1:<port>/mcp
```

or supported localhost form.

The local OAuth Client binding and:

```text
MCP_OAUTH_RESOURCE_SERVER_URL
```

must match exactly after canonicalization.

Do not treat the local URL as the future public ChatGPT resource.

Public deployment must use HTTPS.

---

## 23. Local End-to-End OAuth Verification

Before ChatGPT, prove the full Resource Server locally.

At minimum:

1. start Streamable HTTP in OAuth mode;
2. GET protected-resource metadata;
3. verify exact resource;
4. verify Frappe issuer listed;
5. call MCP endpoint without token -> 401;
6. inspect `WWW-Authenticate`;
7. obtain a real bound Frappe OAuth token through the native authorization flow;
8. call MCP endpoint with valid token;
9. initialize MCP;
10. `tools/list`;
11. invoke at least one permission-sensitive read tool;
12. verify exact Frappe token user was applied;
13. missing scope -> 403;
14. wrong-resource token -> 401;
15. wrong-client token -> 401;
16. expired token -> 401;
17. revoked token -> 401 immediately;
18. unbound ordinary Frappe OAuth token -> rejected by MCP;
19. disabled user -> rejected;
20. Guest/missing user -> rejected;
21. email header cannot override token user;
22. `MCP_FRAPPE_USER` cannot override token user;
23. two-user sequential identity switch works;
24. two-user concurrent isolation works;
25. exception cleanup does not leak identity.

---

## 24. OAuth Refresh Resource-Server Check

Task 04 proved Frappe refresh rotation.

Task 05 must prove the Resource Server observes it correctly:

```text
old access token
    -> valid before revocation/rotation as appropriate

refresh
    -> replacement access token accepted
    -> old revoked pair rejected immediately
```

Do not cache token validity in-process in a way that delays revocation.

The authoritative native Frappe token row must be checked on each protected request unless a future separately approved cache design safely preserves immediate revocation semantics.

---

## 25. FastMCP OAuth vs Trusted-Header Construction

HTTP app construction should select one auth strategy from config.

Conceptually:

```text
streamable-http
    |
    +-- trusted_header
    |      -> existing Task 03 middleware
    |
    +-- oauth
           -> SDK AuthSettings + Frappe TokenVerifier
```

Do not stack both authentications on the same request.

OAuth request must not need the shared secret.

Trusted-header request must not be interpreted as a Frappe OAuth token.

---

## 26. Configuration Validation Tests

At minimum cover:

- absent HTTP auth mode -> trusted-header as before;
- `trusted_header` still requires strong secret;
- OAuth requires issuer/resource/scopes/client ID;
- malformed issuer fails;
- malformed resource fails;
- empty scopes fail;
- duplicate scopes normalize deterministically;
- missing client ID fails;
- OAuth Client missing -> startup fail;
- OAuth Client unbound -> startup fail;
- configured resource/client binding mismatch -> startup fail;
- required Custom Fields missing -> startup fail;
- OAuth ignores stale shared secret;
- OAuth ignores `MCP_FRAPPE_USER`;
- stdio does not require OAuth config.

---

## 27. Token Verifier Unit Tests

Cover every verifier rejection independently:

- unknown token;
- inactive/revoked token;
- expired token;
- wrong client;
- missing OAuth Client;
- blank token resource;
- blank client resource;
- token/client resource mismatch;
- configured resource mismatch;
- malformed persisted resource;
- missing required scope;
- multiple required scopes;
- current client scope cannot expand token-record scopes;
- missing User;
- disabled User;
- Guest;
- database exception -> fail closed;
- correct token -> exact principal returned.

Also prove:

- raw token not logged;
- raw Authorization header not logged;
- Frappe context always destroyed in `finally`.

---

## 28. HTTP / SDK Integration Tests

Using the actual installed MCP SDK HTTP app where practical, verify:

- auth settings + verifier assembly succeeds;
- OAuth app includes the protected MCP route;
- protected-resource metadata route exists;
- metadata exact resource;
- metadata correct issuer;
- metadata expected scopes;
- no token -> 401;
- invalid token -> 401;
- insufficient scopes -> 403;
- valid token reaches MCP handler;
- SDK auth context contains the verified principal;
- handler/runtime applies exact subject;
- auth failure prevents tool execution.

Do not rely only on mocked verifier unit tests.

---

## 29. Regression Tests

### `mcp_identity`

Run full established tests.

### `mcp_erpnext`

Run focused Task 03 identity/http/runtime/rest tests.

Run full established suite.

The known approval-policy baseline may remain, but:

- count/type must not worsen;
- no new unrelated failures;
- document it separately.

### Trusted-header live smoke test

Run at least one HTTP trusted-header request after OAuth implementation to prove backward compatibility.

### Stdio live smoke test

Run at least one stdio path under configured Frappe User.

---

## 30. ChatGPT External E2E Preconditions

ChatGPT cannot connect to a localhost-only MCP URL.

Do **not** automatically create a public tunnel, reverse proxy, DNS record, TLS certificate, firewall rule, or internet exposure in this task unless the operator separately provides/authorizes that environment.

For real ChatGPT E2E, require an already available or explicitly authorized:

```text
https://<public-mcp-host>/<mcp-path>
```

Then:

- `MCP_OAUTH_RESOURCE_SERVER_URL` must equal that exact public URL;
- Frappe OAuth Client `custom_mcp_resource` must equal it;
- protected-resource metadata must advertise it;
- ChatGPT must request the same resource;
- token must store the same resource.

If public HTTPS is unavailable, complete all local implementation/E2E and report:

```text
ChatGPT external E2E deferred only for public connectivity/callback setup.
```

Do not call that an OAuth implementation failure if every local protocol/resource-server test passes.

---

## 31. ChatGPT External E2E Steps

When public HTTPS and exact ChatGPT connection details are available:

1. configure a dedicated Frappe OAuth Client from the actual ChatGPT management UI values;
2. use the exact current callback URI;
3. bind client to the exact public MCP resource;
4. configure MCP process with matching issuer/resource/scopes/client ID;
5. start Streamable HTTP OAuth mode;
6. add/connect the MCP server in ChatGPT;
7. trigger a protected tool;
8. verify Frappe login page appears if no active Frappe session;
9. login as a real test Frappe User;
10. approve native consent if shown;
11. verify ChatGPT completes authorization-code + PKCE exchange;
12. verify Frappe OAuth Bearer Token.user equals that logged-in Frappe User;
13. verify stored token resource equals public MCP URL;
14. invoke a read tool;
15. verify result obeys that User's ERPNext permissions;
16. invoke a permitted write only if safe/disposable and preserve approval rules;
17. revoke token in Frappe;
18. verify the old token can no longer call MCP;
19. verify ChatGPT requires/re-enters authorization appropriately;
20. clean disposable test data, but preserve intentionally configured client if needed for continued development.

Never identify the ERPNext execution user from the ChatGPT account email.

---

## 32. ChatGPT-Specific Security Metadata

Current ChatGPT behavior may require tool-level security metadata in addition to server-level OAuth discovery.

Inspect the exact current OpenAI requirement and installed SDK capability.

If supported natively, add the minimal per-tool/server metadata necessary **without changing tool business schemas or descriptions**.

If not supported by installed SDK:

- do not hand-edit protocol payloads with undocumented fields;
- document the exact missing SDK capability;
- keep generic MCP OAuth resource-server behavior correct;
- make ChatGPT E2E a blocker for completion only if ChatGPT genuinely cannot link without it.

No broad tool-registry refactor belongs in this task.

---

## 33. Logging / Observability

Allowed log dimensions:

- auth mode;
- correlation/request ID;
- site;
- non-secret configured client identifier or safe fingerprint if current observability policy permits;
- generic failure category;
- verified username only where current project logging policy already allows it and it is operationally necessary.

Never log:

- Authorization header;
- access token;
- refresh token;
- authorization code;
- client secret;
- shared secret;
- DB password;
- raw request body containing OAuth secrets.

Public errors must not reveal whether a particular user/token/client exists.

---

## 34. Allowed Changes

### `mcp_identity`

Allowed:

- OAuth identity settings parsing/validation;
- opaque token verifier;
- verified-principal / SDK adapter;
- auth integration factory/helper;
- focused tests;
- docs.

Reuse existing Task 03/04 modules where responsibility fits.

Do not split into many modules solely to match diagrams.

### `mcp_erpnext`

Allowed only for integration:

- settings consumption;
- FastMCP/MCP server auth assembly;
- HTTP transport construction;
- runtime verified-principal consumption;
- minimal observability/error mapping;
- tests/docs/.env examples.

Do not change business services/tools.

---

## 35. Forbidden Changes

Do not:

- modify Frappe core;
- redesign Task 04 resource binding;
- add more OAuth Custom Fields;
- add token sidecar storage;
- add new identity DocTypes;
- add JWT conversion;
- use email header in OAuth mode;
- use `MCP_FRAPPE_USER` in OAuth HTTP mode;
- use Administrator fallback;
- alter ERPNext permission rules;
- alter tool schemas for business reasons;
- alter profile membership;
- alter approval semantics;
- alter REST API principal semantics;
- enable DCR/CIMD resource binding;
- add generic provider abstraction;
- upgrade MCP SDK without separate explicit decision;
- expose public internet infrastructure without explicit operator authorization.

---

## 36. Documentation Updates

Update docs to clearly show all three identity modes:

### Stdio

```dotenv
MCP_TRANSPORT=stdio
MCP_FRAPPE_USER=user@example.com
```

### HTTP trusted-header

```dotenv
MCP_TRANSPORT=streamable-http
MCP_HTTP_AUTH_MODE=trusted_header
MCP_HTTP_SHARED_SECRET=...
```

### HTTP OAuth

```dotenv
MCP_TRANSPORT=streamable-http
MCP_HTTP_AUTH_MODE=oauth
MCP_OAUTH_ISSUER_URL=...
MCP_OAUTH_RESOURCE_SERVER_URL=...
MCP_OAUTH_REQUIRED_SCOPES=mcp:access
MCP_OAUTH_FRAPPE_CLIENT_ID=...
```

Explain:

- OAuth execution user comes from native Frappe bearer token;
- `X-MCP-User-Email` is not trusted in OAuth;
- `MCP_FRAPPE_USER` is stdio-only;
- Frappe Authorization Server site must have `mcp_identity` installed and migrated;
- OAuth MCP process needs authoritative local Frappe access in this version;
- first release uses a pre-registered OAuth Client;
- exact public callback values come from the MCP client/ChatGPT UI;
- localhost is for local testing only;
- ChatGPT needs a reachable HTTPS MCP endpoint.

---

## 37. Test / Verification Order

Use this order:

### Phase A - Source / configuration

1. inspect current code and installed SDK;
2. implement settings/verifier;
3. unit tests;
4. startup validation tests.

### Phase B - FastMCP integration

5. wire SDK auth;
6. metadata tests;
7. 401/403 tests;
8. SDK auth-context tests;
9. runtime identity tests.

### Phase C - Local live OAuth

10. migrate test site if needed;
11. create disposable local bound client;
12. start OAuth-mode Streamable HTTP;
13. run full local OAuth MCP flow;
14. test revoked/expired/wrong-resource/wrong-client/scopes;
15. test two users and concurrency;
16. trusted-header/stdin regression;
17. cleanup.

### Phase D - External ChatGPT

18. only if public HTTPS is available/authorized;
19. use exact ChatGPT UI callback/client values;
20. connect;
21. login/consent;
22. permission-sensitive tool;
23. revocation/reconnect;
24. cleanup/report.

Do not skip local verification and jump directly to ChatGPT.

---

## 38. Acceptance Criteria

Task 05 server-side implementation is complete only when all applicable mandatory items below pass:

1. `MCP_HTTP_AUTH_MODE=oauth` starts only with valid OAuth configuration;
2. trusted-header default remains unchanged when mode is absent;
3. stdio remains unchanged;
4. OAuth uses installed SDK-native Resource Server integration;
5. Frappe remains the only Authorization Server;
6. no embedded FastMCP authorization-server provider is added;
7. opaque token verifier uses authoritative native Frappe data;
8. token status is enforced;
9. token expiry is enforced;
10. configured client ID is enforced;
11. token resource is enforced;
12. OAuth Client resource is enforced;
13. configured resource is enforced;
14. all three resources match exactly;
15. token-record scopes are authoritative;
16. all required scopes are enforced;
17. native token User exists/enabled/non-Guest;
18. OAuth identity cannot be overridden by email header;
19. OAuth identity cannot be overridden by stdio config;
20. verifier cleanup is request-safe;
21. no Frappe object crosses async boundaries unsafely;
22. protected-resource metadata exists in OAuth HTTP mode;
23. metadata advertises exact resource/issuer/scopes;
24. no/invalid token returns safe 401;
25. insufficient scopes return safe 403;
26. valid token reaches MCP only after verification;
27. `mcp_erpnext` applies exact verified User using `frappe.set_user()`;
28. native ERPNext permissions differ correctly between two users;
29. stateful/sequential identity switching does not leak;
30. concurrent identity isolation passes;
31. revoked token is rejected immediately;
32. refreshed replacement token is accepted;
33. old revoked pair is rejected;
34. wrong-resource token is rejected;
35. wrong-client token is rejected;
36. unbound ordinary Frappe token is rejected by MCP;
37. Task 03 trusted-header regression passes;
38. stdio regression passes;
39. REST semantics remain unchanged;
40. full relevant suites pass or known unrelated baseline is unchanged;
41. raw OAuth secrets never appear in logs/results;
42. disposable live fixtures are cleaned;
43. no Frappe core modification exists;
44. no generic provider framework exists;
45. no DCR/CIMD binding is added;
46. no silent MCP SDK upgrade occurs.

### ChatGPT external acceptance

If an authorized public HTTPS endpoint is available, additionally require:

47. ChatGPT discovers protected-resource metadata;
48. ChatGPT uses exact configured resource;
49. ChatGPT opens Frappe login/authorization flow;
50. native Frappe logged-in User becomes token owner;
51. ChatGPT completes bearer-authenticated MCP call;
52. ERPNext permissions apply to that exact User;
53. token revocation blocks subsequent access;
54. reconnect/reauthorization works.

If public HTTPS is not available, items 47-54 are explicitly deferred to a follow-up public-connectivity verification task and must not be falsely claimed.

---

## 39. Expected Result

### Local OAuth mode

```text
MCP HTTP request
    -> no token
    -> 401 + resource metadata

Client discovers Frappe issuer
    -> native Frappe OAuth
    -> User login
    -> PKCE S256
    -> resource-bound opaque token

MCP HTTP request
Authorization: Bearer <token>
    -> FastMCP bearer auth
    -> mcp_identity verifies native token
    -> exact resource/client/scopes/user
    -> AccessToken.subject = native Frappe User
    -> mcp_erpnext frappe.set_user(subject)
    -> native ERPNext permissions
```

### Identity example

```text
Frappe token.user = sales1@example.com

X-MCP-User-Email = Administrator
MCP_FRAPPE_USER = Administrator

OAuth mode result:
    sales1@example.com
```

The headers/configured stdio identity have no authority in OAuth HTTP mode.

---

## 40. Limitations After Task 05

Unless separately implemented and verified, this version still does not provide:

- generic external IdP provider abstraction;
- Azure/Keycloak/Auth0-specific verifier;
- DCR-bound MCP clients;
- CIMD-bound Frappe clients;
- remote REST-backed end-user OAuth verification;
- token-validity caching;
- multi-resource token issuance;
- multiple OAuth client allowlist in one process;
- automatic public tunnel/reverse proxy/DNS/TLS setup.

Do not add them opportunistically.

---

## 41. Implementation Report

Create:

```text
mcp_identity/docs/inspect/
MCP_IDENTITY_TASK_05_FASTMCP_OAUTH_RESOURCE_SERVER_IMPLEMENTATION_REPORT.md
```

The report must include:

1. repositories/versions inspected;
2. installed MCP SDK auth APIs actually used;
3. files changed in `mcp_identity`;
4. files changed in `mcp_erpnext`;
5. final responsibility boundary;
6. final environment contract;
7. startup validation behavior;
8. exact opaque token lookup path;
9. every token verification check;
10. `AccessToken` mapping;
11. Frappe verifier context lifecycle;
12. FastMCP auth construction;
13. protected-resource metadata route/result;
14. exact 401 result;
15. exact 403 result;
16. exact runtime principal flow;
17. proof email/stdin identity fallback is impossible;
18. two-user permission proof;
19. sequential identity-switch result;
20. concurrent isolation result;
21. refresh/revocation result;
22. wrong-resource/client/scope results;
23. local live MCP OAuth commands/results;
24. trusted-header regression;
25. stdio regression;
26. REST regression;
27. full test results;
28. logs/secrets verification;
29. live fixture cleanup;
30. current OpenAI/ChatGPT compatibility findings;
31. whether tool `securitySchemes` / `_meta["mcp/www_authenticate"]` were required and how native SDK support was handled;
32. public HTTPS availability status;
33. exact ChatGPT client/callback mode used, if tested;
34. ChatGPT E2E result, if tested;
35. deviations/limitations;
36. exact readiness verdict.

Do not state ChatGPT E2E passed unless it was actually performed against a reachable public HTTPS endpoint.

---

## 42. Exact Next Task

### If local Task 05 passes but public HTTPS is not available

Next task:

**Task 05V - Public HTTPS + ChatGPT OAuth End-to-End Verification**

That task should cover only:

- public/reverse-proxy MCP endpoint already authorized by the operator;
- exact ChatGPT callback/client configuration;
- public resource metadata;
- ChatGPT account linking;
- Frappe login/consent;
- permission-sensitive tool execution;
- revocation/reconnect verification.

Do not change the OAuth architecture unless live evidence requires it.

### If Task 05 including ChatGPT external E2E fully passes

`mcp_identity` OAuth v1 is complete.

Do not invent another identity feature automatically.

Return to the next approved `mcp_erpnext` business-capability / optimization roadmap item.

### If Task 05 exposes a production defect

Do not continue to deployment.

Create the smallest correction task for the first failing production point, then rerun the affected Task 05 verification.
