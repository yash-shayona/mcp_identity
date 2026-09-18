# Task 02 - MCP Identity Frappe OAuth RFC 8707 Resource-Binding Design Spike

## Status

Planned

## Target App

`mcp_identity`

## Task Type

Architecture / source-level design spike only.

**NO production-code changes are allowed in this task.**

The task must end with a concrete, implementation-ready design for the minimum safe compatibility layer required to use Frappe OAuth as the authorization server for an MCP Streamable HTTP resource server.

---

## 1. Scope

Audit and design the exact mechanism required to make native Frappe OAuth compatible with the MCP/OpenAI requirement that an OAuth access token be issued for, and validated against, one canonical MCP resource.

The design must cover the RFC 8707 `resource` value through the complete authorization lifecycle:

```text
authorization request
    -> authorization code
    -> access token
    -> refresh token
    -> refreshed access token
    -> revocation / validation
```

The task must determine the smallest Frappe-native or `mcp_identity`-owned extension needed to preserve and enforce that binding.

This task must also resolve the architecture ambiguity identified by Task 01:

- whether current Frappe extension points are sufficient;
- whether `mcp_identity` needs new persistence;
- whether a Frappe OAuth controller/DocType extension is required;
- whether an upstream/native Frappe mechanism exists that was missed;
- or whether OAuth mode must remain unavailable until such support exists.

Do not implement the complete OAuth mode in this task.

---

## 2. Objective

Produce an implementation-ready answer to this question:

> How can `mcp_identity` safely use Frappe OAuth while proving that every accepted access token was issued specifically for the configured MCP resource URL?

The result must be specific enough that the next coding task can implement the chosen design without inventing new architecture.

The design must:

1. preserve native Frappe login, consent, token ownership, expiry, revocation, scopes, and user association where possible;
2. preserve the canonical RFC 8707 `resource` value across authorization-code and refresh-token flows;
3. reject missing, altered, cross-resource, replayed, or unbound tokens fail-closed;
4. work with opaque Frappe bearer tokens;
5. avoid trusting `X-MCP-User-Email`;
6. avoid using `MCP_FRAPPE_USER` as any HTTP/OAuth fallback;
7. avoid introducing a generic multi-provider framework;
8. avoid unnecessary duplication of Frappe OAuth behavior;
9. remain compatible with multiple MCP server processes/workers;
10. define exact migration and rollback implications if persistence/schema changes are required.

---

## 3. Inputs

Use the following as the primary project inputs:

### Current repositories

- `mcp_identity`
- `mcp_erpnext`

### Prior audit

- `mcp_identity/docs/inspect/MCP_IDENTITY_AUTH_MODE_OAUTH_ARCHITECTURE_AUDIT.md`

Treat that report as the baseline architectural evidence.

### Installed framework/runtime

Inspect the exact installed versions in the current environment:

- Frappe `version-16`
- ERPNext `version-16`
- installed Python MCP SDK

Do not assume behavior from memory when source is available.

### Required official external references

Use only authoritative sources for protocol/framework claims:

- current MCP Authorization specification;
- RFC 8707 OAuth 2.0 Resource Indicators;
- RFC 9728 OAuth Protected Resource Metadata;
- current OpenAI MCP / ChatGPT OAuth documentation;
- official Frappe documentation;
- official `frappe/frappe` repository source for the installed branch/version;
- installed MCP Python SDK source.

Record exact versions/commit identifiers inspected.

---

## 4. Allowed Changes

Allowed:

- create/update the design report under `mcp_identity/docs/inspect/`;
- create supporting notes or diagrams inside that report;
- run read-only source inspection commands;
- run existing tests if they do not modify production state;
- inspect Frappe DocType JSON/controllers/hooks and MCP SDK auth code;
- create disposable local scratch analysis outside the production app if needed;
- write pseudocode and proposed schemas/hooks in the report.

Not allowed:

- changing production Python files;
- changing Frappe hooks;
- adding a DocType;
- adding Custom Fields;
- changing database schema;
- creating OAuth Client/OAuth Bearer Token records;
- creating authorization codes/tokens;
- enabling DCR;
- changing OAuth Settings;
- editing `.env`;
- changing Docker/service config;
- modifying `mcp_erpnext`;
- restarting services;
- performing live ChatGPT/LibreChat/Inspector OAuth authorization;
- silently patching Frappe core.

If a live/runtime mutation is genuinely required to prove a design point, document it as a future operator-approved verification step instead of performing it.

---

## 5. Required Investigation

### 5.1 Trace native Frappe OAuth persistence

Trace the installed Frappe implementation for:

- OAuth Client;
- OAuth Authorization Code;
- OAuth Bearer Token;
- refresh token handling;
- authorization request parsing;
- code creation;
- token exchange;
- refresh flow;
- revocation;
- introspection;
- protected-resource metadata;
- authorization-server metadata.

For each stage, identify:

- function/class/file;
- persisted fields;
- request parameters accepted;
- values copied forward;
- validation behavior;
- extension points available without modifying Frappe core.

Specifically verify whether `resource` is ignored, discarded, or retained anywhere.

---

### 5.2 Inspect Frappe-native extension mechanisms first

Before proposing custom persistence or controller replacement, inspect the relevant Frappe-native extension mechanisms.

At minimum evaluate whether the requirement can be satisfied through any combination of:

- hooks;
- controller extension/override mechanisms supported by the installed Frappe version;
- whitelisted-method override support;
- document events;
- permission/query hooks if relevant;
- standard app-owned DocTypes;
- Custom Fields;
- request hooks;
- authentication hooks;
- OAuth-specific settings/hooks if any exist;
- subclassing/extension mechanisms available in current Frappe.

For every candidate, answer:

- Can it capture the original authorization `resource` value?
- Can it bind that value to the authorization code?
- Can it copy/validate it during token exchange?
- Can it preserve it through refresh?
- Can it enforce it on bearer-token validation?
- Does it require replacing native Frappe behavior?
- Is it safe across workers/processes?
- Is it upgrade-safe?

Prefer the framework-native mechanism if it fully meets the requirement.

---

### 5.3 Evaluate concrete resource-binding designs

Compare at least these candidate families.

#### Candidate A - Extend native Frappe OAuth records

Example questions:

- Can the authorization-code/token DocTypes be safely extended with app-owned fields?
- Can native issuance paths populate them without Frappe-core edits?
- Can refresh copy the binding correctly?
- Are migrations required?
- Can existing non-MCP OAuth tokens coexist safely?

Do not assume Custom Fields are appropriate; prove or reject them.

#### Candidate B - `mcp_identity` sidecar binding persistence

Conceptually:

```text
authorization code/token identifier
    -> canonical MCP resource
    -> client/user/scopes metadata as needed
```

Determine:

- exact key;
- lifecycle;
- uniqueness;
- refresh behavior;
- revocation cleanup;
- race handling;
- transaction boundaries;
- worker/process safety;
- whether raw access/refresh tokens would need to be stored.

**Storing raw OAuth secrets in a new sidecar table should be treated as a major negative and avoided if possible.**

#### Candidate C - Frappe OAuth flow wrapper/compatibility endpoint

Determine whether `mcp_identity` can safely expose a compatibility authorization/token endpoint that delegates to native Frappe behavior while preserving `resource`.

Evaluate:

- login/consent reuse;
- authorization code ownership;
- redirect validation;
- PKCE validation;
- token issuance;
- refresh flow;
- revocation;
- metadata implications;
- amount of duplicated OAuth logic.

Reject any design that effectively reimplements the whole OAuth server unless no safer alternative exists.

#### Candidate D - Dedicated OAuth Client only

Explicitly prove why a dedicated Frappe OAuth Client ID is or is not sufficient as the MCP resource binding.

The Task 01 audit concluded that client binding alone is not a substitute for resource binding. Re-verify this conclusion against the protocol and installed source.

#### Candidate E - Native/upstream capability

Search the installed Frappe source and current official Frappe repository/docs for a newer or existing native mechanism that supports RFC 8707 resource indicators.

If available:

- identify exact version/commit;
- determine whether upgrading is enough;
- determine whether backporting or app-owned compatibility is still needed.

---

## 6. Canonical Resource Definition

Define precisely what the MCP resource identifier should be for this project.

For example:

```text
https://mcp.example.com/mcp
```

The report must decide:

- whether the path is part of the canonical resource;
- trailing-slash normalization policy;
- scheme/host case handling;
- explicit/default port handling;
- query/fragment rejection;
- reverse-proxy/public-origin handling;
- multiple domains/aliases policy;
- whether one process can serve more than one resource;
- whether the configured value is compared byte-for-byte after validation or normalized once at startup.

Do not derive the canonical value from untrusted `Host` or forwarded headers.

The canonical public resource must come from trusted deployment configuration.

---

## 7. Required Security Analysis

For the chosen design, analyze at minimum:

### Token confusion / confused deputy

A token valid for:

```text
https://erp.example.com
```

must not automatically be valid for:

```text
https://mcp.example.com/mcp
```

unless the authorization flow explicitly bound it to that MCP resource.

### Cross-resource replay

A token issued for MCP Resource A must fail at MCP Resource B.

### Cross-client behavior

Determine the relationship between:

- OAuth client ID;
- MCP resource;
- Frappe user;
- scopes.

Do not use client ID as the sole audience substitute.

### Refresh

The refreshed token must preserve the original resource binding.

An attacker must not be able to change the resource during refresh.

### Revocation

Revoked access or refresh tokens must not retain valid sidecar/resource state that can later re-enable access.

### Authorization-code interception/replay

Preserve native PKCE S256, exact redirect validation, code expiry, and one-time code semantics.

### Request-local identity

Verified auth state must remain request-scoped and safe across:

- async tasks;
- sequential request reuse;
- multiple threads;
- multiple processes/workers.

### Secret handling

Do not log/store unnecessarily:

- access tokens;
- refresh tokens;
- authorization codes;
- Authorization headers;
- shared secrets;
- client secrets.

If token-derived database lookups require a key, explain how the native Frappe token record is located without introducing a second raw-secret store.

---

## 8. Required Data / Schema Decision

The report must explicitly state one of:

### Outcome A - No new schema required

Explain exactly how binding is persisted and enforced with current Frappe records/extensions.

or

### Outcome B - Frappe-native record extension required

Specify:

- DocType(s);
- exact proposed field(s);
- field type;
- required/index/unique behavior;
- migration mechanism;
- compatibility with non-MCP OAuth records;
- upgrade risk.

or

### Outcome C - New `mcp_identity` DocType required

Specify exact proposed DocType design, including:

- name;
- fields;
- indexes;
- uniqueness;
- ownership/permissions;
- creation/update/delete lifecycle;
- relationship to Frappe OAuth records;
- cleanup/revocation behavior;
- whether any token secrets are stored;
- multi-site behavior.

Do **not** create the schema in this task.

---

## 9. Required API / Code Boundary Decision

Define the exact ownership boundary for the future implementation.

The report must provide proposed callable contracts, for example conceptually:

```python
resolve_configured_frappe_user(...)
get_http_auth_mode(...)
build_http_auth_integration(...)
verify_frappe_oauth_access_token(...)
validate_resource_binding(...)
```

Names may differ, but the report must identify:

- which functions live in `mcp_identity`;
- which values are returned to `mcp_erpnext`;
- which code initializes Frappe site context;
- where database access occurs;
- where FastMCP `AuthSettings`/`TokenVerifier` are constructed;
- where standard 401/403 challenges are generated;
- where `frappe.set_user()` remains;
- how no provider-specific logic leaks into ERPNext business code.

Do not implement the functions.

---

## 10. Environment / Configuration Decision

Review and finalize the proposed future config from Task 01:

```dotenv
MCP_HTTP_AUTH_MODE=trusted_header|oauth
MCP_HTTP_SHARED_SECRET=...
MCP_OAUTH_PROVIDER=frappe
MCP_OAUTH_ISSUER_URL=https://erp.example.com
MCP_OAUTH_RESOURCE_SERVER_URL=https://mcp.example.com/mcp
MCP_OAUTH_REQUIRED_SCOPES=mcp:access
MCP_OAUTH_FRAPPE_CLIENT_ID=...
```

For each variable decide:

- keep/remove/rename;
- semantic owner;
- required in which mode;
- sensitive or non-sensitive;
- startup validation;
- canonicalization;
- whether it duplicates site-owned Frappe OAuth configuration.

Do not add configuration that is not necessary.

`MCP_FRAPPE_USER` must remain the stdio configured identity name unless the report finds a concrete breaking/security reason.

---

## 11. Migration / Backward Compatibility

The chosen design must preserve:

### Stdio

```text
MCP_TRANSPORT=stdio
MCP_FRAPPE_USER=<user>
```

No OAuth flow must be introduced into stdio.

### Existing Streamable HTTP trusted-header mode

Existing behavior must remain available:

```http
Authorization: Bearer <MCP_HTTP_SHARED_SECRET>
X-MCP-User-Email: person@example.com
```

The future absence of `MCP_HTTP_AUTH_MODE` should continue to mean:

```text
trusted_header
```

unless the design report identifies a compelling security reason otherwise.

### REST backend

Do not accidentally imply that a local configured/OAuth identity can replace the remote ERPNext API-key owner.

REST backend identity delegation is outside this task.

### Existing OAuth users/integrations

Any schema/flow change must not invalidate unrelated existing Frappe OAuth clients/tokens.

---

## 12. Implementation Sequence Recommendation

The final report must provide a staged implementation plan.

At minimum decide whether the safe order is:

```text
1. identity settings + stdio resolver refactor
2. trusted-header refactor with zero behavior change
3. resource-binding persistence/compatibility seam
4. Frappe opaque-token verifier
5. FastMCP OAuth resource-server integration
6. MCP runtime verified-principal consumption
7. docs/config
8. unit tests
9. live Frappe OAuth verification
10. MCP Inspector verification
11. ChatGPT verification
```

If a different order is safer, explain why.

The report must identify which of those should be separate coding tasks versus one implementation task.

---

## 13. Required Tests for the Future Implementation

Design the exact tests needed for the selected resource-binding mechanism.

At minimum include:

### Resource lifecycle

- authorization request with correct resource;
- missing resource;
- malformed resource;
- unsupported resource;
- authorization code stores/binds correct resource;
- token exchange preserves the resource;
- changed resource during token exchange fails;
- refresh preserves original resource;
- changed resource during refresh fails;
- access token for Resource A rejected at Resource B;
- revoked token rejected;
- expired token rejected.

### Identity

- native token user resolved;
- disabled user rejected;
- deleted user rejected;
- Guest rejected;
- email header ignored in OAuth mode;
- `MCP_FRAPPE_USER` ignored in OAuth mode.

### Client / scope

- wrong client rejected if expected-client policy is retained;
- missing required scope rejected;
- insufficient scope produces standard 403 challenge;
- correct scope succeeds.

### Concurrency

- two users concurrently;
- two resources concurrently where testable;
- sequential reused worker;
- multiple process-safe persistence model;
- exception before/after principal application.

### Regression

- current trusted-header behavior unchanged;
- current stdio behavior unchanged;
- REST backend unchanged;
- ERPNext native permissions still enforced;
- existing approval/confirm guards still enforced.

---

## 14. Acceptance Criteria

This task is complete only when the report:

1. traces the exact Frappe OAuth code and persistence lifecycle;
2. identifies the precise point where RFC 8707 `resource` is currently lost;
3. evaluates Frappe-native extension points before custom logic;
4. compares at least the required candidate designs;
5. chooses one design and rejects the others with concrete reasons;
6. defines canonical MCP resource normalization/comparison;
7. defines persistence/schema requirements exactly;
8. proves how resource binding survives authorization, token, refresh, and revocation;
9. defines how opaque access tokens are authoritatively validated;
10. defines exact `mcp_identity` vs `mcp_erpnext` code ownership;
11. finalizes the required environment-variable contract;
12. addresses multi-worker/process safety;
13. preserves trusted-header, stdio, REST backend, ERPNext permissions, and approval behavior;
14. provides an implementation sequence;
15. provides a complete future-test matrix;
16. identifies every remaining unverified item;
17. ends with the exact next coding task(s);
18. makes **no production-code or database change**.

---

## 15. Expected Result

The report must result in one explicit architecture decision, such as:

```text
Chosen design:
<exact mechanism>

Resource source:
MCP_OAUTH_RESOURCE_SERVER_URL

Authorization binding:
<exact storage/extension point>

Token exchange:
<exact enforcement point>

Refresh:
<exact preservation/enforcement point>

Bearer verification:
<exact lookup + validation path>

Execution identity:
validated native Frappe OAuth token user

Schema:
none | exact existing-record extension | exact new mcp_identity DocType

OAuth mode can be implemented:
YES | NO
```

A vague recommendation such as "add resource validation" is not acceptable.

---

## 16. Limitations

This task does not:

- implement `MCP_HTTP_AUTH_MODE`;
- move `MCP_FRAPPE_USER`;
- refactor trusted-header middleware;
- implement OAuth middleware;
- create FastMCP `TokenVerifier`;
- add OAuth endpoints;
- add/modify DocTypes;
- migrate the database;
- change OAuth Settings;
- create OAuth clients/tokens;
- connect ChatGPT;
- modify LibreChat;
- modify ERPNext business tools;
- modify Frappe core.

---

## 17. Deliverable

Create exactly:

```text
mcp_identity/docs/inspect/
MCP_IDENTITY_FRAPPE_OAUTH_RESOURCE_BINDING_DESIGN.md
```

The report should contain:

1. Executive Summary
2. Repository / Version Context
3. Native Frappe OAuth Lifecycle Trace
4. Where `resource` Is Lost Today
5. Frappe-Native Extension Points
6. Candidate Design Comparison
7. Chosen Resource-Binding Architecture
8. Canonical Resource Definition
9. Persistence / Schema Decision
10. OAuth Authorization-Code Binding
11. Token Exchange Enforcement
12. Refresh-Token Enforcement
13. Revocation / Cleanup
14. Opaque Bearer Verification
15. Identity Mapping
16. MCP SDK / FastMCP Integration Boundary
17. `mcp_identity` / `mcp_erpnext` Ownership
18. Environment Variable Contract
19. Request Isolation / Multi-Worker Safety
20. Error / Challenge Contract
21. Migration / Backward Compatibility
22. Security Risks / Controls
23. Future Test Matrix
24. Recommended Implementation Sequence
25. Limitations / Unverified Items
26. Exact Next Task(s)

---

## 18. Exact Next Task

Do not pre-decide the implementation task number beyond this task.

The report must end by proposing the exact next coding task(s) based on its result.

Expected direction if a safe binding design is proven:

```text
Task 03 - MCP Identity Auth-Mode Foundation and Trusted-Header / Stdio Refactor
Task 04 - Frappe OAuth Resource-Binding Compatibility Implementation
Task 05 - FastMCP OAuth Resource-Server Integration and E2E Verification
```

The report may merge or reorder these only if it demonstrates that doing so is safer and simpler.

If no safe resource-binding mechanism can be implemented without patching Frappe core or violating project constraints, the report must say so explicitly and the next task must not enable OAuth mode.
