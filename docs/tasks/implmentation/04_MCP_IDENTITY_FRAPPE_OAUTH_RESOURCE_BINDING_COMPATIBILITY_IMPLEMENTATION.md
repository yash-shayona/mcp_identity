# Task 04 - MCP Identity Frappe OAuth Resource-Binding Compatibility Implementation

## Status

Ready for implementation.

## Target App

Primary owner:

- `mcp_identity`

Consumer changes in `mcp_erpnext` are **not expected** in this task unless a compile/test compatibility fix is strictly required by an identity API already introduced in Task 03.

## Task Type

Implementation + focused security/regression tests.

This task implements the **authorization-server compatibility/resource-binding layer only**.

It must **not** expose FastMCP OAuth to ChatGPT yet.

---

## 1. Scope

Implement the Frappe OAuth resource-binding compatibility design approved in:

```text
mcp_identity/docs/inspect/
MCP_IDENTITY_FRAPPE_OAUTH_RESOURCE_BINDING_DESIGN.md
```

The task must add the minimum Frappe-native compatibility needed to bind an OAuth grant/token to one canonical MCP resource URL across:

```text
authorization request
    -> authorization code
    -> access token
    -> refresh token
    -> replacement access/refresh token
    -> revocation / bearer validation metadata
```

The implementation must:

1. reuse Frappe's native OAuth login, consent, redirect validation, PKCE, token generation, expiry, user ownership, scopes, and revocation behavior;
2. add only the missing MCP/RFC 8707 resource binding;
3. add the three approved `custom_mcp_resource` Custom Fields on Frappe's native OAuth records;
4. install the resource-aware validator only for the intended native OAuth grant endpoints/commands, without modifying Frappe core;
5. preserve native behavior for unrelated OAuth Clients whose resource field is blank;
6. bind the verified canonical resource to authorization codes and bearer-token records;
7. enforce the same resource at code exchange and refresh;
8. make authorization-code consumption and refresh-token rotation replay-safe using database row locking and one transaction boundary;
9. preserve native token/user/client/scope semantics;
10. add focused tests proving the compatibility layer cannot be bypassed through alternate supported Frappe RPC invocation forms;
11. keep OAuth mode unavailable to the MCP resource server until Task 05;
12. avoid building any new OAuth server, generic IdP framework, sidecar token store, or duplicate token database.

---

## 2. Objective

After Task 04, the Frappe Authorization Server side should behave conceptually as:

```text
ChatGPT / OAuth client
        |
        | authorization request
        | resource=https://mcp.example.com/mcp
        v
Native Frappe OAuth authorize / login / consent
        |
        | existing Frappe validation
        | + mcp_identity resource validation
        v
OAuth Authorization Code
        |
        | custom_mcp_resource
        v
Native Frappe token exchange
        |
        | same resource required
        | source code locked
        v
OAuth Bearer Token
        |
        | custom_mcp_resource
        v
Native refresh flow
        |
        | same resource required
        | source token locked
        | source pair revoked atomically
        v
Replacement OAuth Bearer Token
        |
        | same custom_mcp_resource
        v
Ready for Task 05 FastMCP resource-server verification
```

Important boundary:

```text
Frappe continues to implement OAuth.

mcp_identity only extends the native flow with the missing MCP resource-binding
and replay-safe consumption rules.
```

Do not duplicate functionality already implemented by Frappe.

---

## 3. Mandatory Engineering Rule - Reuse Native Frappe First

Before writing custom logic for any step:

1. inspect the installed Frappe `version-16` implementation actually present in the bench;
2. locate the native function/class/DocType behavior;
3. preserve and call native behavior where it is correct;
4. extend only the missing resource-binding/replay-protection responsibility;
5. avoid copying full Frappe OAuth endpoint implementations into `mcp_identity`;
6. avoid replacing login, consent, redirect, PKCE, token generation, scope validation, expiry, user association, or revocation unless the approved report explicitly identified a gap that must be closed for MCP-bound grants.

The approved design specifically selected a native-extension approach, not a second OAuth server.

---

## 4. Source of Truth / Required Inputs

Before editing, inspect the current checkout and verify Task 03 changes are present.

Required project inputs:

- current `mcp_identity` source after Task 03;
- current `mcp_erpnext` source after Task 03;
- `mcp_identity/docs/inspect/MCP_IDENTITY_AUTH_MODE_OAUTH_ARCHITECTURE_AUDIT.md`;
- `mcp_identity/docs/inspect/MCP_IDENTITY_FRAPPE_OAUTH_RESOURCE_BINDING_DESIGN.md`;
- `mcp_identity/docs/inspect/MCP_IDENTITY_TASK_03_AUTH_MODE_FOUNDATION_IMPLEMENTATION_REPORT.md`;
- current `mcp_identity/hooks.py`, tests, patches structure, and README/docs;
- installed Frappe `version-16` source;
- installed `oauthlib` source/version where callback semantics matter;
- existing OAuth DocType schemas/controllers;
- current Frappe hook semantics for `before_request`, `doc_events`, and Custom Field creation.

Record the exact Frappe/oAuthlib versions/commit inspected in the implementation report.

If the current source differs materially from the approved design, do not silently invent an alternative. Preserve the architectural goals and document the smallest native-compatible adjustment.

---

## 5. Explicitly Out of Scope

Do **not** implement any of the following in Task 04:

- FastMCP OAuth `TokenVerifier`;
- FastMCP `AuthSettings` wiring;
- MCP protected-resource metadata exposure;
- MCP 401/403 OAuth challenge integration;
- ChatGPT OAuth connection;
- MCP Inspector OAuth E2E;
- `MCP_OAUTH_ISSUER_URL` resource-server usage;
- `MCP_OAUTH_RESOURCE_SERVER_URL` resource-server verification;
- `MCP_OAUTH_REQUIRED_SCOPES` FastMCP enforcement;
- `MCP_OAUTH_FRAPPE_CLIENT_ID` FastMCP verifier logic;
- generic Azure / Entra / Keycloak / Auth0 / OIDC providers;
- DCR support for MCP-bound clients;
- CIMD support;
- new login or consent pages;
- new OAuth authorization/token/revocation endpoints;
- new token formats;
- JWT conversion;
- sidecar token database;
- new identity mapping DocType;
- email-header based OAuth identity;
- `MCP_FRAPPE_USER` fallback for OAuth;
- Frappe core edits;
- ERPNext business tool changes;
- approval-policy changes;
- REST backend identity delegation.

Task 04 prepares the Frappe authorization server for MCP-safe OAuth. Task 05 exposes it through FastMCP.

---

## 6. Approved Schema Change

Implement exactly three optional Custom Fields on Frappe native OAuth DocTypes.

### 6.1 `OAuth Client`

```text
fieldname: custom_mcp_resource
fieldtype: Small Text
required: no
unique: no
index: no
```

Purpose:

- site-controlled trust anchor for the one canonical MCP resource assigned to this OAuth Client;
- blank means the client remains a normal/unbound Frappe OAuth Client and keeps native behavior.

### 6.2 `OAuth Authorization Code`

```text
fieldname: custom_mcp_resource
fieldtype: Small Text
required: no
hidden: yes
read_only: yes
no_copy: yes
print/report hidden: yes
unique: no
index: no
```

Purpose:

- persist the verified resource associated with the authorization grant.

### 6.3 `OAuth Bearer Token`

```text
fieldname: custom_mcp_resource
fieldtype: Small Text
required: no
hidden: yes
read_only: yes
no_copy: yes
print/report hidden: yes
unique: no
index: no
```

Purpose:

- persist the verified resource on the native access/refresh token pair.

### 6.4 No additional schema

Do not add:

- another DocType;
- another token table;
- duplicate authorization/access/refresh secret storage;
- token hash sidecar mapping;
- generic External Identity mapping.

Existing Frappe OAuth records own the lifecycle.

---

## 7. Patch / Migration Requirements

Add an idempotent `mcp_identity` patch using Frappe's native Custom Field creation helper/pattern supported by the installed version.

Expected shape conceptually:

```text
mcp_identity/
  patches.txt
  mcp_identity/
    patches/
      ...resource_binding_fields....py
```

Exact path/version grouping should follow the current repository's established Frappe conventions.

Requirements:

1. use the native supported Custom Field creation mechanism, e.g. `create_custom_fields(..., update=True)` if confirmed for the installed Frappe version;
2. do not export broad Custom Field fixtures;
3. do not backfill resource values into existing OAuth Client/Code/Bearer Token records;
4. existing records remain blank/unbound;
5. patch must be idempotent;
6. unrelated OAuth clients remain valid;
7. patch must not create OAuth Clients, codes, tokens, or OAuth Settings records;
8. document that the patch only takes effect on sites where `mcp_identity` is installed and migrated.

### Operator-safety rule

Implement the patch file and tests, but **do not run `bench migrate` against a real/shared site unless explicit operator approval was already provided for this task**.

If migration is not run, record this clearly in the report.

---

## 8. Canonical MCP Resource Function

Implement one pure canonicalization function in `mcp_identity` and reuse it everywhere resource comparison is required.

Do not create multiple normalization implementations.

Required behavior from the approved design:

1. absolute URL required;
2. scheme + authority required;
3. reject userinfo;
4. reject query;
5. reject fragment;
6. reject control characters;
7. HTTPS required outside explicit test/development loopback policy;
8. HTTP may be permitted only for `localhost`, `*.localhost`, or loopback IPs under an explicit development/test allowance;
9. lowercase scheme and DNS host;
10. convert internationalized DNS host to ASCII IDNA form;
11. preserve valid IPv6 form;
12. remove default ports;
13. preserve explicit non-default ports;
14. include MCP path;
15. preserve path case;
16. reject dot-segment aliases;
17. reject repeated-slash aliases;
18. normalize percent-escape hex digits consistently without decoding path octets;
19. apply the approved trailing-slash policy consistently;
20. accept exactly one resource value for this implementation;
21. compare canonicalized values exactly;
22. never derive canonical resource from untrusted `Host`, `Forwarded`, or `X-Forwarded-*` headers.

The same function must be used for:

- OAuth Client field validation;
- authorization request resource;
- token request resource;
- refresh request resource;
- persisted values;
- tests.

---

## 9. OAuth Client Resource Validation

Add a narrowly scoped Frappe document validation hook for `OAuth Client`.

For blank `custom_mcp_resource`:

```text
preserve native Frappe OAuth behavior
```

For nonblank `custom_mcp_resource`:

1. canonicalize the value;
2. reject invalid/non-allowed resource URLs;
3. persist the canonical value;
4. do not infer the value from redirect URIs, Host headers, site URL, or environment;
5. do not auto-populate it on existing OAuth Clients.

A bound OAuth Client means:

```text
this client is eligible for the MCP resource-binding compatibility rules
```

It does **not** mean the client ID itself is the resource/audience.

---

## 10. Native OAuth Validator Extension

Implement the approved subclass of Frappe's native OAuth validator.

Conceptually:

```python
class MCPResourceBindingOAuthValidator(OAuthWebRequestValidator):
    ...
```

Do not copy the whole native validator implementation.

Requirements:

1. call/preserve native validation first where safe and appropriate;
2. for unbound OAuth Clients, behavior must remain native;
3. for bound OAuth Clients, add only the approved MCP resource checks and replay-hardening behavior;
4. use request-local state only;
5. never store the active validator or resource in a process-global variable;
6. do not log raw authorization codes, access tokens, refresh tokens, client secrets, or request bodies.

Likely overridden callbacks include the approved resource-binding points such as:

- scope/client authorization stage needed to validate authorization-request resource;
- `validate_code(...)`;
- `validate_refresh_token(...)`.

Confirm exact callback signatures against installed Frappe/oauthlib before implementing.

---

## 11. Critical Hook Routing / Bypass Guard

This is mandatory.

The compatibility validator must **not** be enabled/disabled solely by matching a literal raw URL path.

Frappe OAuth whitelisted methods may be reachable through more than one supported RPC route form.

Before implementing the hook:

1. inspect the installed Frappe request/RPC dispatch flow;
2. enumerate all supported invocation forms that can reach the relevant OAuth methods;
3. determine the authoritative resolved command/method signal available in `before_request` or another native request-local point;
4. install the compatibility validator for every supported invocation form that reaches the OAuth methods;
5. ensure an alternate route cannot call the same native OAuth method while bypassing `mcp_identity` resource binding;
6. add focused tests for each supported route form;
7. if one route form cannot be safely intercepted, explicitly reject/block that route for MCP-bound OAuth methods or choose a safer native extension point.

Do not rely on assumptions such as:

```text
request.path == /api/method/frappe.integrations.oauth2.get_token
```

unless the current Frappe source proves that no alternate invocation path exists.

This is a security acceptance criterion.

---

## 12. Request-Local OAuth Server / Validator Installation

Use the native request-local mechanism confirmed by the design report.

Expected approach:

```text
before_request hook
    -> detect relevant resolved OAuth method/command safely
    -> construct native oauthlib WebApplicationServer
       with MCPResourceBindingOAuthValidator
    -> assign to frappe.local.oauth_server
    -> native frappe.integrations.oauth2 endpoint continues unchanged
```

Requirements:

- request-local only;
- no process-global singleton;
- preserve native endpoints;
- preserve native login/consent pages;
- preserve native redirect handling;
- preserve native token generation;
- preserve native error semantics unless MCP/RFC 8707 requires `invalid_target` for the new check;
- unrelated Frappe requests and unrelated OAuth flows must not be affected.

---

## 13. Authorization Request Binding

For an OAuth Client whose `custom_mcp_resource` is blank:

```text
native Frappe behavior only
```

For an MCP-bound OAuth Client:

1. native client validation must succeed;
2. native redirect validation must succeed before redirectable OAuth errors are emitted;
3. require exactly one `resource` parameter;
4. canonicalize it with the shared function;
5. require exact equality with `OAuth Client.custom_mcp_resource`;
6. reject missing/blank/malformed/multiple/mismatched values with standards-appropriate `invalid_target` behavior;
7. require non-empty PKCE challenge;
8. require PKCE method `S256` for the MCP-bound client;
9. preserve the validated canonical resource in request-local state only;
10. do not trust cookies, caller email headers, Host/Forwarded headers, or process globals;
11. ensure the value survives Frappe login/consent continuation and is revalidated at the continuation/approval stage.

Add tests for both direct logged-in/consent and login-continuation flows where testable without operator-created live records.

---

## 14. Authorization Code Persistence

Add a Frappe `doc_events` handler for `OAuth Authorization Code` insertion.

For unbound clients:

```text
leave custom_mcp_resource blank
preserve native behavior
```

For a validated MCP-bound authorization request:

1. retrieve only the request-local verified client/resource metadata;
2. verify document client matches the request-local client;
3. write the canonical resource to `custom_mcp_resource` before insert;
4. never derive the value again from raw request Host/header state;
5. fail closed if a bound-client code is being created without the expected verified request-local binding.

Do not create a second record/table.

---

## 15. Authorization-Code Token Exchange

For an MCP-bound client, the code-exchange path must be replay-safe and resource-bound.

Required behavior:

1. locate the authorization code using the installed Frappe-native lookup semantics;
2. acquire a database row lock using the native DB API supported by the installed version (`for_update=True` or exact equivalent confirmed in source);
3. require the code is still valid;
4. require code client matches the authenticated client;
5. require persisted `custom_mcp_resource` is nonblank and valid;
6. require exactly one token-request `resource`;
7. canonicalize it;
8. require exact equality with the code's persisted resource;
9. preserve native redirect/PKCE/user/scope/code validation;
10. require S256 for MCP-bound grant;
11. store only source record name/client/resource/grant kind in request-local state; never raw code/token values;
12. the new bearer token must receive the same canonical resource;
13. source authorization code must become invalid in the same transaction that inserts the new bearer token;
14. native later invalidation must remain safe/idempotent;
15. a second concurrent code exchange must block and then fail after the first transaction commits.

Do not weaken native PKCE or redirect verification while adding the lock.

---

## 16. Bearer Token Persistence Event

Add a `before_insert` handler for `OAuth Bearer Token` with grant-aware request-local state.

For a new token resulting from an MCP-bound authorization-code exchange:

- copy the exact verified canonical resource;
- consume/invalidate the locked authorization-code source before final transaction commit.

For a new token resulting from an MCP-bound refresh:

- copy the exact persisted resource from the locked source bearer-token record;
- revoke the source access/refresh pair before final transaction commit.

For unrelated native flows:

```text
preserve native behavior
```

The handler must fail closed if MCP-bound token issuance is occurring but the expected request-local verified source/binding is missing or inconsistent.

---

## 17. Refresh-Token Enforcement and Rotation

For an MCP-bound refresh token:

1. locate the active native bearer-token source record using native Frappe lookup semantics;
2. lock the source row;
3. require source status is Active;
4. require authenticated client equals source client;
5. require source `custom_mcp_resource` is nonblank;
6. require current OAuth Client's `custom_mcp_resource` still matches the source binding;
7. require exactly one refresh-request `resource`;
8. canonicalize it;
9. require exact equality with source resource;
10. revalidate the native user exists, is enabled, and is not Guest;
11. preserve/restore the native scopes from the source token;
12. preserve native token generation;
13. insert the replacement bearer-token record with the same binding;
14. mark the source bearer-token record Revoked in the same transaction as replacement insertion;
15. sequential reuse of the old refresh token must fail;
16. concurrent reuse of the old refresh token must serialize and only one request may succeed;
17. caller may not switch resource during refresh.

Do not implement RFC 8707 resource subset switching in this project. One grant = one canonical MCP resource.

---

## 18. Revocation / Cleanup

Preserve native Frappe revocation as the authority.

Because the resource binding lives on the native bearer-token record:

- revoking access token revokes the bound pair according to native semantics;
- revoking refresh token revokes the bound pair according to native semantics;
- deletion/cleanup of the native token automatically deletes the binding;
- no sidecar cleanup job is needed;
- no stale binding may reactivate a Revoked token.

Do not change native revocation endpoint behavior unless a compatibility fix is strictly required for the resource-bound row and is explicitly justified by the installed source.

---

## 19. Identity Rules

Task 04 still does **not** authenticate MCP HTTP requests.

However, its authorization-server binding logic must preserve the identity policy needed by Task 05:

```text
OAuth Bearer Token.user
    -> native Frappe User
```

For MCP-bound refresh/grant validation where user state is checked:

- User must exist;
- User must be enabled;
- User must not be Guest.

Never use:

- `X-MCP-User-Email`;
- `MCP_FRAPPE_USER`;
- arbitrary email claim;
- caller-provided username;
- ChatGPT account email.

OAuth execution identity later comes from the native Frappe token owner.

---

## 20. Installation / Deployment Boundary

This Task 04 design means:

```text
The Frappe site acting as the OAuth Authorization Server
must have mcp_identity installed and migrated.
```

Having `mcp_identity` source merely present in the bench is not sufficient for the schema/hooks to be active on a site.

Document this explicitly in `mcp_identity` README/setup docs.

Do not generalize this into a requirement for non-Frappe future systems. It is the requirement for the current Frappe OAuth compatibility implementation.

---

## 21. Environment Configuration in Task 04

Do not make Task 05 resource-server environment variables active yet.

Task 04's trusted policy anchor on the Authorization Server is:

```text
OAuth Client.custom_mcp_resource
```

Task 04 may document the future resource-server variables for context, but must mark them as not active until Task 05.

Do not add `MCP_OAUTH_PROVIDER`.

Do not change Task 03 contracts:

```text
MCP_HTTP_AUTH_MODE=trusted_header|oauth
MCP_HTTP_SHARED_SECRET=...
MCP_FRAPPE_USER=...
```

`oauth` must remain unavailable from the MCP Streamable HTTP server in Task 04.

---

## 22. Allowed Changes

### `mcp_identity`

Allowed:

- narrowly scoped resource canonicalization helper;
- OAuth compatibility validator subclass;
- request hook function;
- OAuth Client validation function;
- authorization-code `doc_events` handler;
- bearer-token `doc_events` handler;
- Custom Field patch;
- `patches.txt` entry if repository convention requires it;
- hooks.py entries strictly needed for this compatibility layer;
- focused unit/integration tests;
- README/setup/security documentation;
- implementation report.

New modules are allowed only when they separate real responsibilities and avoid bloating the existing Task 03 files.

Do not create a large framework solely for architectural symmetry.

### `mcp_erpnext`

Production changes are not expected.

If a change becomes necessary, it must be:

- minimal;
- directly caused by Task 04 compatibility;
- not FastMCP OAuth integration;
- fully documented in the implementation report.

---

## 23. Forbidden Changes

Do not:

- modify Frappe core;
- copy Frappe OAuth endpoints into `mcp_identity`;
- create parallel login/consent pages;
- create a second OAuth authorization server;
- create a token sidecar DocType;
- store duplicate raw authorization/access/refresh tokens;
- add generic provider abstractions;
- enable OAuth mode in FastMCP;
- expose PRM/401/403 MCP OAuth behavior;
- connect ChatGPT;
- change trusted-header behavior;
- change stdio behavior;
- change REST backend identity semantics;
- change ERPNext tools/profiles/services;
- change approval rules;
- silently fix unrelated test failures;
- rely only on raw request path to decide whether the OAuth validator is installed;
- allow DCR-created unbound clients to become MCP-bound implicitly;
- backfill existing OAuth records with a guessed resource;
- run `bench migrate` or create live OAuth records on a shared/real site without explicit operator approval.

---

## 24. Required Tests - Schema / Patch

Add tests proving:

1. patch definition contains exactly the three approved fields;
2. patch is idempotent;
3. field metadata matches the approved design;
4. existing records are not backfilled;
5. blank client binding remains permitted;
6. invalid bound-client resource fails validation;
7. canonical bound-client resource persists canonical form;
8. no extra DocType/token storage is created.

If repository conventions allow safe isolated test-site migration tests, add them. Do not mutate a shared site without approval.

---

## 25. Required Tests - Canonicalization

At minimum cover:

- valid HTTPS origin + path;
- scheme/host case normalization;
- IDNA hostname;
- IPv6;
- default port removal;
- non-default port preservation;
- root path behavior;
- non-root trailing slash behavior;
- path case preservation;
- percent-escape normalization policy;
- reject relative URL;
- reject userinfo;
- reject query;
- reject fragment;
- reject controls;
- reject dot segments;
- reject repeated slash aliases;
- reject non-loopback HTTP;
- explicit loopback/test HTTP allowance only when enabled;
- aliases treated as distinct resources;
- multiple resource values rejected.

---

## 26. Required Tests - Native OAuth Routing / Hook Bypass

This section is mandatory.

Enumerate every supported Frappe route/dispatch form capable of invoking the native OAuth methods relevant to:

- authorization;
- approval/consent continuation;
- token exchange;
- refresh;
- revocation where applicable.

For each supported form:

- prove the `mcp_identity` compatibility validator is installed for the intended MCP-bound flow;
- prove an alternate invocation cannot reach the native validator without the resource-binding checks;
- prove unrelated non-OAuth methods are unaffected.

If the installed Frappe version exposes both `/api/method/...` and another command form for the same whitelisted method, cover both or explicitly block the unsafe alternate form.

A raw-path-only unit test is insufficient.

---

## 27. Required Tests - Authorization Lifecycle

For bound clients, cover:

- correct resource accepted;
- missing resource rejected;
- blank resource rejected;
- malformed resource rejected;
- mismatched resource rejected;
- duplicate/multiple resource rejected;
- plain PKCE rejected;
- missing PKCE rejected;
- S256 accepted;
- native exact redirect validation remains effective;
- native scope/client/role checks remain effective;
- login/consent continuation preserves and revalidates resource;
- authorization-code record stores canonical resource;
- unbound client remains native and blank-binding compatible.

---

## 28. Required Tests - Token Exchange / Code Replay

Cover:

- correct code + resource succeeds;
- changed resource fails;
- missing resource fails;
- multiple resources fail;
- wrong client fails;
- invalid/expired/consumed code fails;
- native PKCE verifier mismatch still fails;
- created bearer-token record receives exact code resource;
- code becomes invalid atomically with replacement token insertion;
- sequential code replay fails;
- concurrent code replay allows exactly one success.

### Concurrency requirement

The automated test suite should include a real transaction/locking integration test where practical.

The strongest proof is two independent DB connections attempting the same code concurrently.

If such DB-writing integration cannot be run without explicit operator approval:

- implement the test;
- do not run it against the shared site;
- mark it as operator-gated in the report;
- do not falsely claim replay locking is live-proven.

---

## 29. Required Tests - Refresh / Replay

Cover:

- valid refresh preserves user/client/scopes/resource;
- changed resource fails;
- missing resource fails;
- multiple resources fail;
- authenticated client mismatch fails;
- source resource vs current OAuth Client resource mismatch fails;
- disabled/deleted/Guest source user fails;
- replacement token receives exact resource;
- source token pair becomes Revoked atomically;
- sequential reuse of old refresh token fails;
- concurrent reuse allows exactly one success;
- no resource switching/subset escalation;
- unrelated unbound native refresh behavior remains unchanged.

Use the same operator-gating rule for live DB concurrency tests.

---

## 30. Required Regression Tests

Prove Task 04 does not regress Task 03:

### Stdio

- `MCP_TRANSPORT=stdio` behavior unchanged;
- `MCP_FRAPPE_USER` behavior unchanged;
- no OAuth hook/resource logic participates in stdio MCP execution.

### Trusted-header HTTP

- existing shared-secret + `X-MCP-User-Email` flow unchanged;
- missing auth mode still defaults to trusted-header;
- no new schema dependency is required to use trusted-header unless the site is intentionally acting as OAuth Authorization Server.

### OAuth still unavailable in MCP server

```text
MCP_HTTP_AUTH_MODE=oauth
```

must still fail closed from Task 03 because Task 05 resource-server integration does not exist yet.

### Existing unrelated Frappe OAuth

- OAuth Clients with blank `custom_mcp_resource` keep native behavior;
- existing unbound codes/tokens are not magically treated as MCP tokens;
- no existing OAuth record is backfilled.

### ERPNext / approvals / REST

- no business tool changes;
- no permission bypass;
- no approval-policy changes;
- REST backend unchanged.

---

## 31. Static / Source Verification

Run repository-appropriate checks, including:

- Python compilation;
- current unit tests for `mcp_identity`;
- relevant existing `mcp_erpnext` Task 03 regression tests;
- diff whitespace checks;
- any repository-native linter if already installed/configured.

Do not install new tooling merely to satisfy this task unless the repository already requires it.

Record exact commands/results in the report.

---

## 32. Acceptance Criteria

Task 04 is complete only when all of the following are true:

1. exactly three approved Custom Fields are defined through an idempotent `mcp_identity` migration/patch;
2. no new token/identity DocType exists;
3. no raw OAuth secret is duplicated outside native Frappe OAuth records;
4. bound OAuth Client resource values are canonicalized and validated;
5. unbound clients preserve native behavior;
6. the compatibility validator extends native Frappe behavior rather than replacing the OAuth endpoints;
7. validator installation is request-local, not global;
8. validator routing cannot be bypassed through an alternate supported Frappe RPC invocation form;
9. bound authorization requests require exactly one correct resource;
10. bound authorization requests require S256 PKCE;
11. authorization codes persist the verified canonical resource;
12. code exchange locks the source code and requires the same resource;
13. bearer token receives the same resource;
14. code consumption and token insertion are atomic for MCP-bound grants;
15. concurrent authorization-code replay permits at most one success;
16. refresh locks the source bearer-token row;
17. refresh requires same client/resource and enabled non-Guest user;
18. replacement token inherits the same resource;
19. source token pair is revoked atomically with replacement insertion;
20. concurrent refresh replay permits at most one success;
21. native revocation/cleanup continue to own the token lifecycle;
22. no OAuth email/header/stdio fallback is introduced;
23. Task 03 stdio and trusted-header contracts remain unchanged;
24. `MCP_HTTP_AUTH_MODE=oauth` is still unavailable to FastMCP after Task 04;
25. no Frappe core modifications exist;
26. no generic provider abstraction exists;
27. no DCR/CIMD MCP binding is introduced;
28. focused tests pass;
29. full relevant suites pass, or unrelated pre-existing failures are separately evidenced;
30. live migration/token/concurrency tests are either explicitly operator-approved and reported, or clearly left unexecuted without false claims;
31. deployment docs state that the Frappe OAuth Authorization Server site must have `mcp_identity` installed and migrated;
32. implementation report contains all deviations/limitations and exact Task 05 readiness.

---

## 33. Expected Result

At the end of Task 04, the authorization-server side should be ready for Task 05.

Example bound client:

```text
OAuth Client
  client_id = chatgpt-mcp-client
  custom_mcp_resource = https://mcp.example.com/mcp
```

Successful grant:

```text
authorization request
resource=https://mcp.example.com/mcp
        |
        v
OAuth Authorization Code
custom_mcp_resource=https://mcp.example.com/mcp
        |
        v
token request
resource=https://mcp.example.com/mcp
        |
        v
OAuth Bearer Token
custom_mcp_resource=https://mcp.example.com/mcp
```

Wrong resource:

```text
resource=https://other.example.com/mcp
        |
        v
invalid_target / fail closed
```

Refresh:

```text
old token bound to Resource A
        |
refresh requires Resource A
        |
        v
new token bound to Resource A
old pair Revoked
```

But this must still **not** work yet:

```text
ChatGPT bearer token
    -> FastMCP OAuth authentication
```

That is Task 05.

---

## 34. Limitations After Task 04

After Task 04:

- ChatGPT is not connected;
- MCP Inspector OAuth is not connected;
- FastMCP `TokenVerifier` is not implemented;
- FastMCP OAuth metadata/challenges are not exposed;
- `MCP_HTTP_AUTH_MODE=oauth` must still fail closed;
- DCR is not supported for bound MCP clients;
- CIMD is not supported;
- only a manually/pre-registered bound Frappe OAuth Client is the approved first-release model;
- live site migration and OAuth record creation may still be pending operator approval;
- live two-worker/two-connection replay proof may still be pending operator approval if not safely runnable in isolated infrastructure.

These limitations are intentional.

---

## 35. Implementation Report

After implementation, create exactly:

```text
mcp_identity/docs/inspect/
MCP_IDENTITY_TASK_04_FRAPPE_OAUTH_RESOURCE_BINDING_IMPLEMENTATION_REPORT.md
```

The report must include:

1. repository/version context;
2. exact files changed;
3. exact patch/Custom Fields added;
4. proof no other schema was added;
5. canonical resource behavior;
6. OAuth Client validation behavior;
7. exact Frappe native extension points reused;
8. exact validator subclass callbacks overridden and why;
9. exact hook registration and route/command-bypass analysis;
10. authorization-code binding flow;
11. token-exchange locking/transaction flow;
12. bearer-token insertion event behavior;
13. refresh locking/rotation flow;
14. revocation/cleanup behavior;
15. user/client/scope checks retained;
16. proof unbound clients preserve native behavior;
17. proof Task 03 stdio/trusted-header behavior remains unchanged;
18. proof OAuth FastMCP mode is still disabled;
19. exact test commands/results;
20. concurrent replay test design/results;
21. whether any live DB/migration test was run and under what operator approval;
22. any unexecuted operator-gated tests;
23. any unrelated pre-existing test failures;
24. deviations from the approved Task 02 design, if any;
25. security limitations/risks remaining;
26. Task 05 readiness/blockers.

Do not claim a live property was proven if only mocked/unit-tested.

---

## 36. Exact Next Task

If Task 04 passes the acceptance criteria, the next task is:

**Task 05 - FastMCP OAuth Resource-Server Integration and E2E Verification**

Task 05 will:

- activate OAuth mode in the MCP Streamable HTTP resource server;
- add Frappe opaque bearer-token verification;
- configure FastMCP `AuthSettings` / `TokenVerifier`;
- expose MCP protected-resource metadata;
- produce standards-compliant 401/403 challenges;
- enforce configured resource/client/scopes/token/user checks;
- consume only the verified native Frappe token user as execution identity;
- preserve `frappe.set_user()` / native ERPNext permissions;
- perform separately authorized live Frappe OAuth, MCP Inspector, and ChatGPT verification;
- keep trusted-header and stdio backward-compatible.

Do not start Task 05 until Task 04 proves that the authorization server has durable, enforceable MCP resource binding and replay-safe grant/refresh behavior.
