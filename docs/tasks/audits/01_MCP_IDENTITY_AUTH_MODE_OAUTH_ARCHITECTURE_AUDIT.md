# Task 01 - MCP Identity Auth-Mode and OAuth Architecture Audit

## Task Type

**Audit / architecture decision only**

## Status

**Ready for execution**

## Target App

```text
mcp_identity
```

## Required Task File Location

Place this task file at:

```text
mcp_identity/docs/tasks/01_MCP_IDENTITY_AUTH_MODE_OAUTH_ARCHITECTURE_AUDIT.md
```

Create the `docs/tasks/` directory if it does not already exist.

## Required Audit Report Location

The only repository file that this task is allowed to create is:

```text
mcp_identity/docs/inspect/MCP_IDENTITY_AUTH_MODE_OAUTH_ARCHITECTURE_AUDIT.md
```

Create the `docs/inspect/` directory if it does not already exist.

---

# 1. Scope

Audit the current `mcp_identity` and `mcp_erpnext` implementation to determine the correct architecture for:

```text
1. current trusted-header Streamable HTTP authentication
2. current stdio execution identity
3. future OAuth-based Streamable HTTP authentication
4. ChatGPT remote MCP authentication
5. Frappe OAuth as the first OAuth provider candidate
6. future provider-neutral OAuth/OIDC support without redesigning mcp_erpnext
7. environment-variable ownership between mcp_identity and mcp_erpnext
```

This is an **inspection and architecture task only**.

The task must produce evidence-backed recommendations before any implementation task is written.

---

# 2. Objective

Determine the cleanest production architecture in which `mcp_identity` owns authentication and identity concerns while `mcp_erpnext` remains focused on MCP transport, ERPNext operations, Frappe runtime execution, profiles, tools, and business capabilities.

The audit must answer whether the desired long-term boundary should become conceptually:

```text
MCP request / execution
        |
        v
mcp_identity
        |
        +-- stdio configured identity
        |
        +-- trusted_header
        |      +-- shared secret
        |      +-- X-MCP-User-Email
        |
        +-- oauth
               +-- first provider: Frappe OAuth, if compatible
               +-- future provider adapters only if genuinely needed
        |
        v
Verified Frappe execution user
        |
        v
mcp_erpnext
        |
        v
Frappe / ERPNext native permissions and business logic
```

Do **not** assume this target architecture is correct merely because it is proposed here. Verify it against the current code and official protocol/framework behavior.

---

# 3. Inputs

Inspect the current local source trees for both apps.

Primary app:

```text
mcp_identity
```

Consumer app:

```text
mcp_erpnext
```

At minimum inspect all relevant files discovered in the repository, including the current equivalents of:

```text
mcp_identity/README.md
mcp_identity/docs/MCP_IDENTITY_V1_IMPLEMENTATION_TASK.md
mcp_identity/mcp_identity/identity.py
mcp_identity/mcp_identity/hooks.py
mcp_identity/mcp_identity/tests/test_identity.py

mcp_erpnext/.env.example
mcp_erpnext/mcp_erpnext/settings.py
mcp_erpnext/mcp_erpnext/http_transport.py
mcp_erpnext/mcp_erpnext/runtime.py
mcp_erpnext/mcp_erpnext/observability.py
mcp_erpnext/mcp_erpnext/hooks.py
mcp_erpnext/mcp_erpnext/mcp_server.py
relevant transport/runtime tests
relevant profile/server startup tests
```

Do not assume these exact paths if the repository layout differs. Find the actual implementation first.

Also search both apps for every reference to at least:

```text
MCP_HTTP_SHARED_SECRET
MCP_FRAPPE_USER
MCP_TRANSPORT
MCP_HTTP_HOST
MCP_HTTP_PORT
MCP_HTTP_PATH
MCP_HTTP_ALLOWED_HOSTS
MCP_BACKEND
MCP_FRAPPE_SITE
ERPNEXT_BASE_URL
ERPNEXT_API_KEY
ERPNEXT_API_SECRET
Authorization
Bearer
X-MCP-User-Email
frappe.set_user
frappe.session.user
get_http_shared_secret_from_environment
validate_http_shared_secret_configuration
validate_bearer_secret
resolve_frappe_user_from_http
HTTPIdentityInputs
```

---

# 4. Allowed Changes

## Allowed

Only create/update the audit report:

```text
mcp_identity/docs/inspect/MCP_IDENTITY_AUTH_MODE_OAUTH_ARCHITECTURE_AUDIT.md
```

Read-only inspection commands are allowed.

Examples:

```text
git status
git log
git grep / rg / grep
find / tree / ls
cat / sed
Python import/source inspection when read-only
```

Use official source documentation/repository code when external verification is required.

## Strictly Forbidden

Do **not** modify production code.

Do not modify:

```text
mcp_identity Python code
mcp_erpnext Python code
.env.example files
Docker/Compose files
Frappe site configuration
hooks.py
pyproject.toml
requirements/dependencies
tests
DocTypes
database records
OAuth Client records
OAuth Bearer Token records
site_config.json
common_site_config.json
```

Do not:

```text
implement MCP_HTTP_AUTH_MODE
implement OAuth
move environment variables
rename environment variables
create authenticators
change middleware
change runtime identity logic
change stdio behavior
change Streamable HTTP behavior
run migrations
clear cache
restart services
install/uninstall apps
install packages
create OAuth clients on a live site
```

**NO PRODUCTION CODE CHANGES.**

If a live-runtime experiment would require configuration or database changes, document the proposed experiment instead of performing it.

---

# 5. Current Baseline That Must Be Verified

The following are observations from the current source snapshot. Treat them as hypotheses to verify, not unquestionable facts.

## 5.1 Current trusted HTTP identity

Current behavior appears to use:

```http
Authorization: Bearer <MCP_HTTP_SHARED_SECRET>
X-MCP-User-Email: person@example.com
```

`mcp_identity` appears to:

```text
validate the shared secret
validate/normalize the supplied email
resolve an existing enabled Frappe User
reject Guest/unknown/disabled users
return the resolved Frappe username
```

## 5.2 Current stdio identity

Current stdio behavior appears to use:

```text
MCP_FRAPPE_USER
```

from `mcp_erpnext` settings/runtime rather than using `mcp_identity` as the identity resolver.

Verify the complete current call path.

## 5.3 Current Streamable HTTP coupling

Current `mcp_erpnext` HTTP startup/middleware/runtime appears to import shared-secret and HTTP identity helpers directly from `mcp_identity`.

Verify exactly which responsibility is owned by each app today.

---

# 6. Required Audit Work

## 6.1 Build the Exact Current Identity Call Graph

Document separate call graphs for:

```text
A. stdio
B. streamable-http trusted-header mode
```

For each flow show:

```text
entry point
settings/config reads
transport-specific branch
identity/authentication validation
Frappe context initialization
frappe.set_user location
operation/tool execution
context cleanup/reset behavior
error mapping
observability/logging touchpoints
```

The report must clearly answer:

```text
Does stdio currently use mcp_identity functionally?
Does streamable-http currently use mcp_identity functionally?
Which imports make mcp_identity a required package even where its resolver is not executed?
```

Do not use vague statements. Name actual files/functions/classes.

---

## 6.2 Environment Variable Ownership Audit

Inventory every environment variable relevant to transport, backend access, authentication, and execution identity.

For each variable record:

```text
name
current reader(s)
current documented location(s)
actual purpose
security sensitivity
recommended semantic owner
keep / move-ownership / deprecate / future-review
reason
```

At minimum decide the ownership of:

```text
MCP_HTTP_SHARED_SECRET
MCP_FRAPPE_USER
MCP_TRANSPORT
MCP_HTTP_HOST
MCP_HTTP_PORT
MCP_HTTP_PATH
MCP_HTTP_ALLOWED_HOSTS
MCP_BACKEND
MCP_FRAPPE_SITE
MCP_PROFILE
MCP_APPROVAL_MODE
MCP_FRAPPE_SITES_PATH
MCP_REST_ALLOW_INSECURE_HTTP
ERPNEXT_BASE_URL
ERPNEXT_API_KEY
ERPNEXT_API_SECRET
```

Explicitly distinguish:

```text
end-user / execution identity
client authentication
OAuth/provider configuration
HTTP transport configuration
backend connection credentials
business/profile configuration
```

Do not classify a variable as identity-owned merely because it contains a credential.

Example distinction to verify:

```text
ERPNEXT_API_KEY / ERPNEXT_API_SECRET
= backend connection credentials
!= MCP end-user identity
```

---

## 6.3 Decide Whether STDIO Identity Belongs in mcp_identity

Compare at least these two designs.

### Design A - current split

```text
stdio identity          -> mcp_erpnext
HTTP identity/auth      -> mcp_identity
```

### Design B - unified identity boundary

```text
stdio configured identity -> mcp_identity
trusted-header identity    -> mcp_identity
oauth identity             -> mcp_identity
```

Evaluate:

```text
separation of concerns
coupling
backward compatibility
clarity of ownership
testability
security/fail-closed behavior
consumer reuse
future MCP clients
future non-HTTP transports
risk of over-engineering
amount of required change
```

Give a clear recommendation, but do not implement it.

---

## 6.4 Define the Auth-Mode Boundary

Audit whether a future configuration such as:

```text
MCP_HTTP_AUTH_MODE=trusted_header
```

and:

```text
MCP_HTTP_AUTH_MODE=oauth
```

is the correct abstraction.

Determine:

```text
where the setting should be parsed
which app owns validation
which app selects the authenticator
what mcp_erpnext should know about auth modes, if anything
whether auth-mode selection should be HTTP-specific or transport-neutral
startup validation behavior by mode
request-time validation behavior by mode
backward-compatible default behavior
```

Do not freeze an environment-variable name merely because it is suggested here. Recommend the final name only after the audit.

---

## 6.5 Trusted-Header Backward Compatibility

The current working mode must not be casually broken.

Audit the future compatibility requirements for:

```http
Authorization: Bearer <shared-secret>
X-MCP-User-Email: person@example.com
```

Confirm how a future auth-mode implementation can preserve the current trusted-client behavior for LibreChat or other clients that can inject the verified user email.

Address:

```text
shared-secret startup validation
constant-time secret comparison
header normalization
missing/malformed Authorization
missing/malformed email
unknown Frappe User
disabled Frappe User
Guest rejection
no service-user fallback
no MCP_FRAPPE_USER fallback for HTTP requests
request-scoped identity isolation
```

---

## 6.6 ChatGPT Remote MCP OAuth Requirements Audit

Using only current official OpenAI documentation and, when needed, the official MCP authorization specification, document the authentication requirements that matter for connecting ChatGPT to a remote Streamable HTTP MCP server.

Verify current requirements rather than relying on memory.

At minimum determine whether the relevant flow requires/supports:

```text
OAuth 2.1-style authorization
Authorization Code flow
PKCE
authorization-server metadata
protected-resource metadata
resource parameter/resource indicators
audience/resource binding
access-token validation
refresh tokens, if applicable
dynamic client registration, if applicable
scopes
WWW-Authenticate behavior
401 behavior
```

Do not reproduce unnecessary protocol theory. Record only requirements that affect this project.

For each requirement classify:

```text
required
recommended
optional
not applicable
uncertain / must verify further
```

Cite official sources in the audit report.

---

## 6.7 Frappe OAuth Compatibility Audit

Using the actual Frappe version used by this project and official Frappe documentation/repository source, inspect Frappe's current OAuth provider implementation.

At minimum verify support/behavior for:

```text
Authorization Code flow
PKCE and supported methods
OAuth server metadata / discovery
protected-resource metadata, if present
dynamic client registration, if present
access-token issuance
refresh tokens
scope validation
bearer-token validation
token-to-Frappe-User association
frappe.set_user behavior for bearer tokens
resource parameter handling
audience/resource binding
aud claim or equivalent enforcement
token revocation/expiry behavior
OAuth Client configuration requirements
redirect URI handling
```

Where docs and repository code differ, state the difference and use repository code for actual runtime behavior.

The report must produce a compatibility matrix:

| Requirement | ChatGPT/MCP need | Frappe support | Evidence | Gap? | Consequence |
|---|---|---|---|---|---|

Do not conclude that native Frappe OAuth is sufficient until every security-critical requirement has been checked.

---

## 6.8 Decide the First OAuth Provider Architecture

Evaluate at least these designs.

### Option 1 - Direct Frappe OAuth

```text
ChatGPT
  -> Frappe OAuth authorization
  -> access token
  -> MCP server validates/uses Frappe-native token
  -> resolved Frappe User
```

### Option 2 - mcp_identity compatibility layer over Frappe OAuth

```text
ChatGPT
  -> Frappe OAuth authorization
  -> token
  -> mcp_identity performs MCP-specific validation/compatibility checks
  -> resolved Frappe User
```

### Option 3 - Separate generic OAuth/OIDC provider abstraction now

```text
mcp_identity
  -> provider interface
      -> Frappe
      -> future Azure/Keycloak/Auth0/etc.
```

Determine which option is justified **now**, not merely theoretically elegant.

Prefer the smallest architecture that:

```text
meets ChatGPT/MCP security requirements
preserves Frappe native capabilities
keeps mcp_erpnext provider-agnostic
allows future extension without a rewrite
avoids speculative provider frameworks
```

---

## 6.9 Identity Mapping Semantics

For OAuth mode, determine what should become the authoritative execution identity.

Compare possibilities such as:

```text
Frappe OAuth Bearer Token.user
OAuth subject -> explicit mapping -> Frappe User
verified email claim -> Frappe User
provider-specific username
```

For the first Frappe OAuth implementation, prefer native authoritative identity if it is secure and sufficient.

Explicitly answer:

```text
Should OAuth mode ever trust X-MCP-User-Email?
Should OAuth mode accept MCP_FRAPPE_USER fallback?
Should a token's user be cross-checked against another header?
How should disabled/deleted Frappe users behave?
How should Guest behave?
```

The expected security direction is fail-closed, but verify the best implementation boundary.

---

## 6.10 Request-Scoped Identity and Concurrency Audit

Because Streamable HTTP may serve multiple users concurrently, inspect whether the current Frappe context handling safely isolates identities per request/tool execution.

Audit:

```text
frappe.init/connect lifecycle
frappe.set_user
frappe.session.user
frappe.local/request-local state
cleanup/destroy/reset behavior
exceptions before cleanup
concurrent requests
multiple workers/processes
reuse of any global/module-level identity state
observability context
```

Do not redesign unrelated runtime code. Only identify changes required for safe auth-mode/OAuth support.

---

## 6.11 Error Contract Audit

Inventory current public identity/auth error codes and HTTP responses.

Determine which errors can remain common across auth modes and which may need OAuth-specific handling.

At minimum consider:

```text
missing credentials
invalid credentials
invalid server configuration
missing identity
unknown user
disabled user
expired token
revoked token
invalid audience/resource
insufficient scope
provider unavailable
```

Recommendations must avoid leaking:

```text
secrets
tokens
raw Authorization headers
sensitive provider response bodies
unnecessary user existence details
```

---

## 6.12 Dependency Direction Audit

Verify that the desired dependency direction remains:

```text
Frappe
  -> mcp_identity
       -> consumed by mcp_erpnext
```

`mcp_identity` must not become dependent on:

```text
mcp_erpnext
ERPNext business modules
sales/accounts/purchase profiles
LibreChat
ChatGPT-specific business logic
```

A protocol adapter may know about OAuth/MCP authentication requirements, but the identity app must remain independent of ERPNext business capabilities.

---

## 6.13 Configuration Documentation Strategy

Recommend where identity-owned settings should be documented after implementation.

Evaluate a structure such as:

```text
mcp_identity/.env.example
mcp_identity/README.md
mcp_identity/docs/...
```

while remembering that actual environment variables are injected into the running process/container, not physically scoped by application package.

Determine how `mcp_erpnext/.env.example` should reference identity-owned configuration without creating two conflicting sources of truth.

Do not implement the documentation changes in this audit.

---

# 7. Required Report Structure

The report must be written to:

```text
mcp_identity/docs/inspect/MCP_IDENTITY_AUTH_MODE_OAUTH_ARCHITECTURE_AUDIT.md
```

Use this structure.

## 1. Executive Summary

State the recommended direction in concise terms.

## 2. Repository / Version Context

Record:

```text
mcp_identity commit/branch if available
mcp_erpnext commit/branch if available
Frappe version
ERPNext version when relevant
working-tree status
files inspected
```

Do not modify a dirty worktree.

## 3. Current Architecture

Include exact stdio and Streamable HTTP call graphs.

## 4. Current Responsibility Matrix

Show what `mcp_identity` and `mcp_erpnext` each own today.

## 5. Environment Variable Ownership Matrix

Include all variables required by Section 6.2.

## 6. STDIO Identity Boundary Decision

Compare Design A vs Design B and recommend one.

## 7. Auth-Mode Architecture Decision

State the recommended abstraction, owner, default, and startup/request behavior.

## 8. Trusted-Header Compatibility

Document how the existing mode must remain compatible.

## 9. ChatGPT / MCP OAuth Requirements

Evidence-backed current requirements with official citations.

## 10. Frappe OAuth Capability Audit

Document exact native support and source evidence.

## 11. Compatibility Matrix

Use the required table.

## 12. OAuth Provider Architecture Decision

Recommend Direct Frappe OAuth, compatibility layer, or another minimal justified approach.

## 13. Identity Mapping Decision

State the authoritative user source and forbidden fallbacks.

## 14. Request Isolation / Concurrency Findings

Identify any issues relevant to OAuth/auth-mode work.

## 15. Error Contract Recommendation

Describe public-safe error behavior.

## 16. Proposed Future Configuration Contract

Show proposed environment/config names, but clearly mark them as **recommended for the implementation task**, not implemented by this audit.

Example only:

```text
MCP_HTTP_AUTH_MODE=trusted_header|oauth
MCP_HTTP_SHARED_SECRET=...
MCP_OAUTH_PROVIDER=frappe
...
```

Use different names if the audit finds better ones.

## 17. Proposed Code Ownership / File Changes

List the minimum files/modules that a later implementation task should change or add.

Do not edit them during this task.

## 18. Backward-Compatibility Risks

Include stdio, LibreChat/trusted-header, REST backend mode, and existing tests.

## 19. Security Risks and Required Controls

Prioritize actual risks; do not produce generic security filler.

## 20. Implementation Recommendation

Give a precise recommended implementation sequence.

## 21. Acceptance-Test Plan for the Future Implementation

List concrete tests that Task 02 should require.

## 22. Limitations / Unverified Items

Clearly identify anything that could not be confirmed.

## 23. Exact Next Task

End with the proposed title and scope for **Task 02**, but do not create or implement Task 02.

---

# 8. Required Evidence Standard

Every important conclusion must be traceable to one of:

```text
current mcp_identity source
current mcp_erpnext source
official Frappe documentation
official Frappe GitHub repository
official OpenAI documentation
official MCP authorization specification when needed
```

Do not use:

```text
third-party blogs
Stack Overflow
forum speculation
AI-generated assumptions
unofficial forks
```

For code findings, cite exact:

```text
file
function/class
relevant line range if practical
```

For protocol/framework findings, include the official source URL and the date/version inspected where useful.

---

# 9. Acceptance Criteria

This audit is complete only if all of the following are true.

1. No production source file was changed.
2. Only the required audit report was added/updated.
3. Current stdio identity flow is documented end-to-end.
4. Current Streamable HTTP trusted-header flow is documented end-to-end.
5. Actual current use of `mcp_identity` in both transports is explicitly stated.
6. All relevant environment variables are inventoried and assigned a recommended semantic owner.
7. `MCP_HTTP_SHARED_SECRET` ownership is explicitly decided.
8. `MCP_FRAPPE_USER` ownership is explicitly decided or intentionally deferred with a concrete reason.
9. Auth-mode ownership and configuration boundary are explicitly decided.
10. Existing trusted-header behavior has a backward-compatibility plan.
11. Current ChatGPT/MCP OAuth requirements are verified from official sources.
12. Current Frappe OAuth capabilities are verified from official docs/repository code.
13. A ChatGPT/MCP vs Frappe OAuth compatibility matrix is present.
14. Resource/audience binding is explicitly investigated rather than assumed.
15. Token-to-Frappe-user resolution is explicitly investigated.
16. Request-scoped user isolation/concurrency is inspected.
17. OAuth mode's forbidden fallbacks are specified.
18. The minimum future code-change surface is identified.
19. A concrete future implementation test plan is included.
20. The report ends with an exact Task 02 recommendation.

---

# 10. Tests / Verification for This Audit Task

Because this is an audit-only task, verification is structural and read-only.

Before finishing, verify:

```text
git status
```

Expected repository change:

```text
only mcp_identity/docs/inspect/MCP_IDENTITY_AUTH_MODE_OAUTH_ARCHITECTURE_AUDIT.md
```

If the repository was already dirty before the audit, record the pre-existing changes and do not alter them.

Run no state-changing Frappe/bench command merely to satisfy this task.

If an existing safe unit test can be run without changing site/database state, it may be used only as supporting evidence; it is not required.

---

# 11. Expected Result

At the end of this task we should know, with evidence:

```text
what mcp_identity owns today
what mcp_erpnext owns today
whether stdio identity should be unified under mcp_identity
where auth_mode should live
which environment variables belong to identity vs transport/backend
how the existing trusted-header mode stays backward-compatible
whether native Frappe OAuth directly satisfies ChatGPT/MCP requirements
whether mcp_identity needs a thin OAuth compatibility layer
how OAuth resolves the authoritative Frappe User
what exact code/files Task 02 should change
```

There must be enough detail to write Task 02 without another architecture-guessing round.

---

# 12. Limitations

This task does **not**:

```text
implement OAuth
implement OIDC
implement ChatGPT connection setup
create Frappe OAuth Client records
change Docker configuration
change LibreChat configuration
change stdio behavior
change Streamable HTTP behavior
move environment variables
add new dependencies
write provider adapters
change ERPNext business tools
```

The audit may recommend such changes for Task 02 only when evidence shows they are necessary.

---

# 13. Exact Next Task

After this audit report is reviewed and the architecture is accepted, create a separate implementation task tentatively titled:

```text
Task 02 - MCP Identity Auth-Mode and OAuth Implementation
```

Its exact scope must be derived from the audit findings rather than pre-decided here.

Do not start Task 02 during this task.
