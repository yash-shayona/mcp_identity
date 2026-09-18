# Task 03 - MCP Identity Auth-Mode Foundation and Trusted-Header / Stdio Refactor

## Status

Ready for implementation.

## Target Apps

Primary owner:

- `mcp_identity`

Consumer/integration changes allowed only where required:

- `mcp_erpnext`

## Task Type

Implementation + regression tests.

This task is a **boundary/refactor task**, not an OAuth implementation task.

---

## 1. Scope

Implement the common identity/authentication boundary established by the approved architecture audits while preserving all currently working stdio and trusted-header behavior.

The task must:

1. make `mcp_identity` the semantic owner of identity-related configuration and user resolution;
2. introduce `MCP_HTTP_AUTH_MODE=trusted_header|oauth` as an identity-owned HTTP setting;
3. preserve `trusted_header` as the backward-compatible default when `MCP_HTTP_AUTH_MODE` is absent;
4. move configured stdio Frappe-user validation behind `mcp_identity` while preserving the existing environment variable name `MCP_FRAPPE_USER`;
5. keep Frappe runtime initialization, connection, cleanup, and `frappe.set_user()` inside `mcp_erpnext`;
6. refactor trusted-header integration so `mcp_erpnext` no longer owns authentication semantics;
7. make runtime path selection depend on configured transport/auth mode, never on whether request headers happen to be present;
8. keep OAuth mode intentionally unavailable/fail-closed in this task;
9. preserve the existing REST backend behavior and its API-principal semantics;
10. add focused regression tests proving no current stdio/trusted-header behavior was weakened.

This task must **not** implement Frappe OAuth resource binding or expose OAuth to ChatGPT.

---

## 2. Objective

After this task, the architecture should be:

```text
mcp_erpnext
    |
    | MCP_TRANSPORT
    v
transport/runtime selection
    |
    +-----------------------------+
    |                             |
    | stdio                       | streamable-http
    |                             |
    v                             v
mcp_identity                  mcp_identity
configured identity           HTTP auth mode
MCP_FRAPPE_USER               trusted_header | oauth
    |                             |
    |                             +-- trusted_header -> existing secret + email flow
    |                             |
    |                             +-- oauth -> recognized but NOT AVAILABLE yet
    |                                      fail closed at startup
    |
    +---------------+-------------+
                    |
                    v
            verified Frappe user
                    |
                    v
              mcp_erpnext
          Frappe runtime scope
                    |
              frappe.set_user()
                    |
                    v
             existing ERPNext tools
```

The important boundary is:

```text
mcp_identity decides/validates WHO the execution principal is.

mcp_erpnext decides HOW the Frappe/ERPNext runtime is initialized and executes
business operations as that already-verified principal.
```

Do not move ERPNext business logic, Frappe runtime ownership, permissions, profiles, approval logic, or backend connection logic into `mcp_identity`.

---

## 3. Source of Truth / Inputs

Before changing code, inspect the **current checkout** rather than assuming paths/functions from this task still match exactly.

Required project inputs:

- current `mcp_identity` source;
- current `mcp_erpnext` source;
- `mcp_identity/docs/inspect/MCP_IDENTITY_AUTH_MODE_OAUTH_ARCHITECTURE_AUDIT.md`;
- `mcp_identity/docs/inspect/MCP_IDENTITY_FRAPPE_OAUTH_RESOURCE_BINDING_DESIGN.md`;
- existing tests in both apps;
- installed Frappe version source where needed to verify User lookup/runtime behavior.

The approved design decision from the resource-binding report is:

```text
Task 03 = auth-mode/settings/principal foundation only.
Task 04 = Frappe OAuth resource-binding compatibility.
Task 05 = FastMCP OAuth resource-server integration and E2E.
```

Do not pull Task 04 or Task 05 work into this task.

---

## 4. Mandatory Engineering Rule - Reuse Existing Logic First

This project follows a strict reuse rule.

Before introducing any new helper, class, settings object, middleware, error code, or module:

1. inspect the existing implementation;
2. identify whether equivalent behavior already exists;
3. reuse or move/refactor the existing behavior when sound;
4. add new code only for the responsibility that genuinely does not exist;
5. do not build a second/parallel authentication framework beside the existing one.

In particular, the current trusted-header behavior already exists and must be **refactored, not reinvented**.

Examples of existing behavior that should remain the basis of the implementation:

- shared-secret environment lookup;
- minimum shared-secret strength validation;
- constant-time secret comparison;
- Authorization Bearer parsing;
- `X-MCP-User-Email` parsing/normalization;
- Frappe User existence/enabled/Guest validation;
- identity exception/error mapping;
- Frappe request cleanup;
- existing HTTP middleware behavior;
- existing runtime/tool wrapper behavior.

If a proposed new abstraction would duplicate those functions, do not add it.

---

## 5. Explicitly Out of Scope

Do **not** implement any of the following in Task 03:

- Frappe OAuth login flow;
- ChatGPT OAuth connection;
- FastMCP OAuth `TokenVerifier`;
- FastMCP OAuth `AuthSettings` exposure;
- OAuth protected-resource metadata;
- OAuth 401/403 challenge integration;
- RFC 8707 `resource` persistence;
- `custom_mcp_resource` fields;
- Custom Fields of any kind;
- new DocTypes;
- DocType schema changes;
- `patches.txt` changes;
- migrations;
- `before_request` OAuth hooks;
- OAuth validator subclass;
- OAuth authorization-code/token document events;
- refresh-token rotation changes;
- DCR/CIMD;
- OAuth Client creation;
- database record creation for OAuth;
- live MCP Inspector OAuth tests;
- live ChatGPT OAuth tests;
- Frappe core modifications;
- generic Azure/Keycloak/Auth0 provider abstraction;
- generic provider plugin architecture.

**No hooks, fields, DocTypes, patches, or OAuth persistence changes belong in this task.**

---

## 6. Current Behavior That Must Be Preserved

### 6.1 Stdio

Current external contract:

```dotenv
MCP_TRANSPORT=stdio
MCP_FRAPPE_USER=user@example.com
```

The operation ultimately runs as:

```python
frappe.set_user(validated_user)
```

Task 03 may move **validation/identity ownership** into `mcp_identity`, but must preserve:

- environment variable name `MCP_FRAPPE_USER`;
- stdio as the default transport if that is the current contract;
- existing Frappe site initialization semantics;
- existing direct-backend behavior;
- existing persistent stdio runtime behavior unless current tests prove otherwise;
- no HTTP Authorization/header requirement for stdio;
- no OAuth protocol flow for stdio.

### 6.2 Streamable HTTP trusted-header mode

Current external contract must remain:

```http
Authorization: Bearer <MCP_HTTP_SHARED_SECRET>
X-MCP-User-Email: person@example.com
```

Preserve:

- `MCP_HTTP_SHARED_SECRET` name;
- minimum 32-character strength validation;
- constant-time secret comparison;
- generic 401 behavior for missing/malformed/wrong shared secret;
- no credential leakage in logs;
- exact current user-email header name;
- email normalization/validation;
- existing enabled-user lookup;
- explicit Guest rejection;
- no fallback to `MCP_FRAPPE_USER` for HTTP;
- request-scoped Frappe cleanup before/after tool execution;
- native Frappe/ERPNext permissions after `frappe.set_user()`.

### 6.3 REST backend

The REST backend remains:

- stdio-only;
- authenticated to remote Frappe/ERPNext by the existing API-key owner;
- not delegated to a local `MCP_FRAPPE_USER` or future OAuth end user.

Do not change REST identity semantics.

---

## 7. Configuration Ownership

### 7.1 Identity-owned environment variables

After Task 03, semantic ownership must be:

```text
mcp_identity
    MCP_HTTP_AUTH_MODE
    MCP_HTTP_SHARED_SECRET
    MCP_FRAPPE_USER
```

Ownership means:

- defines meaning;
- reads/parses where appropriate;
- validates;
- exposes a narrow API to consumers;
- documents behavior.

All variables still exist in one process environment. Do not invent package-specific runtime environment namespaces.

### 7.2 `mcp_erpnext`-owned configuration remains unchanged

Keep these with `mcp_erpnext`:

```text
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
FRAPPE_SITES_PATH
MCP_REST_ALLOW_INSECURE_HTTP
ERPNEXT_BASE_URL
ERPNEXT_API_KEY
ERPNEXT_API_SECRET
```

Do not move them into `mcp_identity` merely because some are security-sensitive.

They belong to transport/runtime/backend/business configuration, not caller identity.

---

## 8. `MCP_HTTP_AUTH_MODE` Contract

Introduce:

```dotenv
MCP_HTTP_AUTH_MODE=trusted_header
```

Accepted values:

```text
trusted_header
oauth
```

Required behavior:

### Variable absent

For `streamable-http`:

```text
absent -> trusted_header
```

This preserves existing deployments such as LibreChat.

### Explicit `trusted_header`

Use the current shared-secret + verified-email flow.

A valid `MCP_HTTP_SHARED_SECRET` remains required.

### Explicit `oauth`

Task 03 must recognize the value as a valid future mode, but **must not allow an HTTP OAuth server to start successfully yet**.

Fail startup closed with the project's identity-configuration error contract.

The public/internal error should clearly mean:

```text
OAuth auth mode is not available until the Frappe OAuth resource-binding capability is installed/implemented.
```

Do not silently fall back to trusted-header.

Do not silently use a shared secret.

Do not silently use `MCP_FRAPPE_USER`.

### Blank or unknown explicit value

Examples:

```dotenv
MCP_HTTP_AUTH_MODE=
MCP_HTTP_AUTH_MODE=basic
MCP_HTTP_AUTH_MODE=frappe_oauth
```

must fail configuration validation.

### Stdio

`MCP_HTTP_AUTH_MODE` is HTTP-only.

For:

```dotenv
MCP_TRANSPORT=stdio
```

stdio must not require or execute HTTP-auth validation.

Do not make stdio fail just because an HTTP-only mode/secret is absent.

If the current configuration loader happens to see the variable, it must not change stdio semantics.

---

## 9. `mcp_identity` Implementation Boundary

Inspect the existing module structure first.

Prefer the smallest change consistent with clear ownership.

A likely target shape is:

```text
mcp_identity/
  mcp_identity/
    identity.py
    settings.py        # only if separation is justified by current code size/responsibility
    ...
```

Do not split code into many modules merely to match an architecture diagram.

### 9.1 Identity settings

Provide a narrow identity-owned API for HTTP auth-mode parsing/validation.

Conceptual behavior, not mandatory exact names:

```python
get_http_auth_mode(...)
validate_http_auth_configuration(...)
```

If a typed enum/value object improves correctness, a small `HTTPAuthMode` type is acceptable.

Do not add a generic provider abstraction.

Do not add `MCP_OAUTH_PROVIDER`; the approved design removed it from the first implementation contract.

### 9.2 Configured stdio identity

Move configured-user resolution/validation into `mcp_identity`.

Conceptual contract:

```python
resolve_configured_frappe_user(...)
```

The exact API should reuse current identity helpers/patterns where possible.

The resolver must validate the configured Frappe User after a usable Frappe site context exists:

- value present where required by current stdio policy;
- Frappe User exists;
- User is enabled;
- User is not `Guest`;
- return canonical Frappe User name.

It must not call `frappe.set_user()`.

It must not own `frappe.init()`.

It must not own `frappe.connect()`.

It must not own Frappe cleanup.

Those remain `mcp_erpnext` runtime responsibilities.

### 9.3 Trusted-header authentication

Reuse the current implementation for:

- reading/validating `MCP_HTTP_SHARED_SECRET`;
- Bearer parsing;
- constant-time comparison;
- HTTP identity extraction;
- Frappe User resolution.

Refactor ownership so the HTTP authentication integration is supplied/defined by `mcp_identity` rather than having `mcp_erpnext` implement identity semantics itself.

This does **not** require creating a large generic middleware framework.

If the existing middleware can be moved or wrapped with a small identity-owned factory/helper, prefer that.

Do not weaken the existing two-stage defense unless a verified request-scoped principal is introduced safely and tests prove equivalent or stronger behavior.

---

## 10. `mcp_erpnext` Integration Changes

Only change `mcp_erpnext` where required to consume the cleaned identity boundary.

Likely affected files must be confirmed from the current checkout before editing:

- `mcp_erpnext/settings.py`;
- `mcp_erpnext/http_transport.py`;
- `mcp_erpnext/runtime.py`;
- `mcp_erpnext/mcp_server.py` only if auth integration construction requires it;
- `mcp_erpnext/observability.py` only if identity error mapping needs a minimal adjustment;
- corresponding tests/docs.

### 10.1 Settings

`mcp_erpnext.settings` should keep transport/runtime/backend/business settings.

Remove direct semantic ownership of:

- `MCP_HTTP_SHARED_SECRET` validation;
- `MCP_FRAPPE_USER` identity validation;
- HTTP auth-mode semantics.

If a value must still be carried internally for compatibility, it should be obtained through the identity API rather than reimplementing validation.

### 10.2 Runtime path selection

This is a mandatory security fix.

Current audit found that HTTP-vs-stdio tool execution can depend on whether HTTP headers were discovered.

After Task 03, choose execution path from configured transport, not incidental request shape.

Required logic conceptually:

```text
if transport == stdio:
    use configured stdio identity path

elif transport == streamable-http:
    use configured HTTP auth-mode path
    if required authenticated HTTP identity/context is absent:
        fail closed

else:
    reject unsupported transport
```

Never do:

```text
headers missing -> maybe stdio fallback
```

for a process configured as Streamable HTTP.

### 10.3 `frappe.set_user()`

Keep this in `mcp_erpnext`.

Correct separation:

```text
mcp_identity
    -> returns verified Frappe username

mcp_erpnext
    -> opens/owns Frappe runtime context
    -> frappe.set_user(verified_username)
    -> executes ERPNext operation
    -> destroys context
```

### 10.4 HTTP fallback prohibition

For any `streamable-http` request:

- never consult `MCP_FRAPPE_USER` as fallback;
- never reuse a previous request user;
- never default to Administrator;
- never default to Guest for tool execution;
- never bypass auth because SDK/request headers are absent.

---

## 11. Error Contract

Reuse existing `mcp_identity` error classes/codes when they already express the condition.

Add the smallest new mode-neutral configuration error only if the existing hierarchy cannot represent invalid/unavailable auth configuration.

Do not expose secrets or detailed credential/user existence information.

Required categories/behavior:

### Invalid configuration

Examples:

- blank/unknown `MCP_HTTP_AUTH_MODE`;
- OAuth selected before Task 04 capability exists;
- trusted-header selected with missing/weak shared secret.

Must fail startup/config validation.

### Stdio configured identity invalid

Examples:

- missing when current runtime requires one;
- unknown User;
- disabled User;
- Guest.

Must fail before business operation executes.

### Trusted-header authentication invalid

Preserve existing public behavior and error mapping.

Do not change existing client-visible shapes unless current code makes a change unavoidable; if unavoidable, document and test it explicitly.

---

## 12. Environment Documentation

Identity-owned documentation should clearly show:

```dotenv
# HTTP only. Missing means trusted_header for backward compatibility.
MCP_HTTP_AUTH_MODE=trusted_header

# Required only for trusted_header HTTP mode.
MCP_HTTP_SHARED_SECRET=<minimum-32-character-secret>

# Configured stdio Frappe execution identity.
MCP_FRAPPE_USER=user@example.com
```

Do not document OAuth issuer/resource/client/scope variables as active/usable in Task 03.

They belong to later tasks.

If they are mentioned at all, mark them clearly as future/not yet supported.

The actual process environment may still contain both identity and `mcp_erpnext` variables together.

Do not imply separate `.env` runtime namespaces.

---

## 13. Required Tests - `mcp_identity`

Inspect existing tests and extend them rather than creating redundant parallel suites.

At minimum cover:

### 13.1 HTTP auth-mode parsing

- absent value -> `trusted_header`;
- explicit `trusted_header` -> accepted;
- explicit `oauth` -> recognized as a known mode;
- blank explicit value -> configuration failure;
- unknown value -> configuration failure;
- case/whitespace policy is deterministic and documented; do not silently accept unintended aliases.

### 13.2 Trusted-header configuration

- trusted mode + valid >=32-char secret -> accepted;
- missing secret -> startup/config failure;
- too-short secret -> startup/config failure;
- OAuth-only behavior is not accidentally triggered.

### 13.3 Existing Bearer secret behavior

Preserve tests for:

- correct secret;
- incorrect secret;
- malformed Authorization;
- missing Authorization;
- constant-time comparison path;
- no credential leakage.

### 13.4 Existing HTTP user resolution

Preserve/add tests for:

- valid enabled User;
- missing email;
- malformed email;
- unknown User;
- disabled User;
- Guest;
- normalized/canonical user result;
- no fallback identity.

### 13.5 Configured stdio user resolver

Add focused tests for:

- existing enabled User -> canonical username returned;
- unknown User -> fail closed;
- disabled User -> fail closed;
- Guest -> fail closed;
- resolver never calls `frappe.set_user()` itself;
- no HTTP header/shared-secret behavior is required for this resolver.

### 13.6 OAuth unavailable gate

For the Task 03 state:

- HTTP + `MCP_HTTP_AUTH_MODE=oauth` must fail startup/configuration;
- error must be deterministic and safe;
- must not fall back to trusted-header;
- must not read `X-MCP-User-Email` as OAuth identity;
- must not use `MCP_FRAPPE_USER` as OAuth identity.

---

## 14. Required Tests - `mcp_erpnext`

Update existing tests rather than discarding useful coverage.

At minimum prove:

### 14.1 Stdio regression

- existing stdio launch/config still works;
- `MCP_FRAPPE_USER` retains its name and expected behavior;
- verified user is passed to `frappe.set_user()` by `mcp_erpnext`;
- HTTP shared secret is not required;
- HTTP auth mode does not trigger HTTP auth logic;
- ERPNext operation remains under the configured User's native permissions.

### 14.2 REST regression

- REST backend remains stdio-only;
- remote API-key owner semantics do not change;
- local configured user is not incorrectly applied to remote REST execution.

### 14.3 Streamable HTTP trusted-header regression

- valid secret + valid enabled email -> tool executes as exact Frappe User;
- bad/missing secret -> rejected before business tool execution;
- bad/missing/disabled/Guest user -> fail closed according to preserved contract;
- HTTP never falls back to `MCP_FRAPPE_USER`;
- pre/finally Frappe cleanup remains in place;
- native ERPNext permissions still apply.

### 14.4 Transport-path fail-closed behavior

Critical tests:

```text
configured transport = streamable-http
request/auth context missing
```

must **not** execute `_run_stdio_tool` or use `MCP_FRAPPE_USER`.

Also prove:

```text
configured transport = stdio
```

never executes HTTP identity logic.

### 14.5 Context isolation

Retain/extend current tests proving:

- sequential HTTP users do not leak;
- concurrent HTTP users do not cross;
- exception before user application cleans state;
- exception after user application cleans state;
- no previous-request user can become the next request identity.

---

## 15. Test Execution

Run focused tests first, then the established full suites for both apps.

Do not invent bench commands without checking the current project/test setup.

Use the repository's existing test runner conventions.

Record in the implementation report:

- exact commands used;
- focused test results;
- full test results;
- skipped tests and reason;
- pre-existing failures separately from task-caused failures.

No live OAuth record-creating test is needed in Task 03.

---

## 16. Allowed Changes

Allowed production changes are limited to what is necessary for the above boundary/refactor.

### In `mcp_identity`

Allowed examples after inspecting current code:

- existing `identity.py` refactor;
- one small identity settings module if justified;
- existing/new focused tests;
- README/config documentation;
- an identity-owned `.env.example` if useful and consistent with repository conventions;
- minimal error-contract additions where existing types are insufficient.

### In `mcp_erpnext`

Allowed examples:

- settings integration cleanup;
- HTTP transport integration cleanup;
- runtime transport/auth-path selection fix;
- minimal MCP server wiring if required by the new identity API;
- minimal observability mapping updates;
- relevant tests/docs/config examples.

Do not change ERPNext service/tool implementations.

---

## 17. Forbidden Changes

Do not:

- rename public environment variables;
- rename `X-MCP-User-Email`;
- change the shared-secret minimum-strength policy unless an existing official/native project rule proves it should change;
- alter business tool schemas;
- alter profile membership;
- alter approval rules;
- alter Frappe/ERPNext permission logic;
- alter REST API credential semantics;
- add OAuth database fields;
- add patches;
- add DocTypes;
- add hooks for OAuth grant interception;
- modify Frappe core;
- introduce generic IdP/provider abstractions;
- add ChatGPT-specific logic to `mcp_erpnext` business code;
- make OAuth mode usable;
- silently fix unrelated code discovered during implementation.

If unrelated issues are found, document them separately without expanding scope.

---

## 18. Backward Compatibility Requirements

After Task 03:

### Existing stdio configuration

```dotenv
MCP_TRANSPORT=stdio
MCP_FRAPPE_USER=user@example.com
```

must continue to work with equivalent behavior.

### Existing LibreChat / trusted-header configuration

Existing deployments that do not define `MCP_HTTP_AUTH_MODE` must continue to behave as:

```dotenv
MCP_HTTP_AUTH_MODE=trusted_header
```

and use:

```http
Authorization: Bearer <shared-secret>
X-MCP-User-Email: user@example.com
```

without client-side configuration changes.

### Future OAuth configuration

If someone sets:

```dotenv
MCP_HTTP_AUTH_MODE=oauth
```

Task 03 must fail closed and clearly state that OAuth resource-binding capability is not yet installed/available.

This is intentional.

---

## 19. Acceptance Criteria

Task 03 is complete only when all of the following are true:

1. `mcp_identity` owns the semantics/validation of `MCP_HTTP_AUTH_MODE`.
2. Missing HTTP auth mode defaults to `trusted_header`.
3. Unknown/blank explicit auth mode fails configuration.
4. OAuth is a recognized future mode but cannot start HTTP successfully in Task 03.
5. `mcp_identity` owns configured stdio Frappe-user validation.
6. `MCP_FRAPPE_USER` name is unchanged.
7. `mcp_erpnext` still owns Frappe runtime init/connect/set-user/cleanup.
8. Current trusted-header secret validation and email-user resolution are reused, not duplicated/reinvented.
9. `mcp_erpnext` no longer chooses HTTP vs stdio execution based on presence/absence of request headers.
10. Streamable HTTP missing auth context fails closed and never falls back to stdio identity.
11. Stdio does not require HTTP auth configuration.
12. REST backend behavior is unchanged.
13. Existing trusted-header external contract is unchanged.
14. Existing stdio external contract is unchanged.
15. No OAuth field/hook/patch/DocType/token-verifier implementation exists in this task.
16. No Frappe core modification exists.
17. No generic provider abstraction was added.
18. Focused identity tests pass.
19. Focused `mcp_erpnext` integration/runtime tests pass.
20. Established full test suites pass, or any pre-existing unrelated failures are explicitly documented with evidence.
21. Logs/errors expose no shared secret, Authorization value, or unnecessary raw user identity data.
22. Documentation clearly distinguishes identity-owned variables from transport/backend variables.

---

## 20. Expected Result

Expected configuration after Task 03:

### Stdio

```dotenv
MCP_TRANSPORT=stdio
MCP_FRAPPE_USER=user@example.com
```

Flow:

```text
mcp_erpnext opens Frappe context
    -> mcp_identity validates configured User
    -> mcp_erpnext frappe.set_user(verified_user)
    -> existing tool executes
```

### Existing Streamable HTTP / LibreChat

```dotenv
MCP_TRANSPORT=streamable-http
MCP_HTTP_AUTH_MODE=trusted_header   # optional because this is the default
MCP_HTTP_SHARED_SECRET=<strong-secret>
```

Request:

```http
Authorization: Bearer <strong-secret>
X-MCP-User-Email: person@example.com
```

Flow:

```text
mcp_identity trusted-header authentication
    -> verified Frappe user
    -> mcp_erpnext Frappe runtime
    -> frappe.set_user(verified_user)
    -> existing tool executes under native permissions
```

### OAuth selected prematurely

```dotenv
MCP_TRANSPORT=streamable-http
MCP_HTTP_AUTH_MODE=oauth
```

Result:

```text
startup/config validation fails closed
because Task 04 resource-binding capability is not yet implemented
```

No fallback occurs.

---

## 21. Limitations After Task 03

After this task:

- ChatGPT OAuth is still not available;
- no OAuth token can be accepted by the MCP server;
- Frappe OAuth resource binding is still not implemented;
- there are no `custom_mcp_resource` fields;
- there is no OAuth validator hook;
- there is no authorization-code/resource persistence;
- there is no refresh-token rotation hardening;
- there is no FastMCP OAuth `TokenVerifier`;
- there is no MCP OAuth protected-resource metadata integration;
- there is no live ChatGPT connection.

This is expected.

The purpose of Task 03 is to make the identity boundary safe and clean **before** adding OAuth-specific capability.

---

## 22. Implementation Report

After implementation, create:

```text
mcp_identity/docs/inspect/
MCP_IDENTITY_TASK_03_AUTH_MODE_FOUNDATION_IMPLEMENTATION_REPORT.md
```

The report must include:

1. files changed in `mcp_identity`;
2. files changed in `mcp_erpnext`;
3. exact old vs new responsibility boundary;
4. exact `MCP_HTTP_AUTH_MODE` behavior;
5. exact stdio identity flow after refactor;
6. exact trusted-header flow after refactor;
7. proof HTTP cannot fall back to stdio identity;
8. proof OAuth mode remains unavailable;
9. proof REST semantics are unchanged;
10. test commands and results;
11. backward-compatibility notes;
12. any deviations from this task with reason;
13. exact next task readiness/blockers.

Do not hide implementation deviations. If current code makes one requested structure inappropriate, preserve the architectural boundary and explain the smaller/native alternative chosen.

---

## 23. Exact Next Task

After Task 03 passes all acceptance criteria, the next task is:

**Task 04 - Frappe OAuth Resource-Binding Compatibility Implementation**

Task 04 will implement only the already-approved resource-binding compatibility layer, including:

- the three `custom_mcp_resource` Custom Fields;
- idempotent Frappe migration/patch;
- canonical MCP resource validation;
- request-local native OAuth validator extension;
- authorization-code resource binding;
- token resource binding;
- row locking/atomic code consumption;
- refresh-token resource preservation and rotation/replay protection;
- focused compatibility/security tests.

Task 04 must still **not** expose FastMCP OAuth to ChatGPT; that remains Task 05.

Additional Task 04 guard from architecture review:

- do not protect the OAuth compatibility validator only by matching a raw URL path;
- inspect all supported Frappe RPC invocation forms for the OAuth methods;
- ensure no alternate route/method invocation can bypass the resource-binding validator;
- prove this with focused tests before considering the authorization-server compatibility layer complete.
