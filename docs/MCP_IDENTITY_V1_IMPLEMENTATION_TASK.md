# MCP Identity v1 — Implementation Task

> Current foundation note (Task 03): `mcp_identity` now also owns exact parsing
> of `MCP_HTTP_AUTH_MODE=trusted_header|oauth` and configured stdio identity
> validation for `MCP_FRAPPE_USER`. Missing HTTP auth mode defaults to
> `trusted_header`. `oauth` is recognized but intentionally unavailable until
> the separately approved Frappe resource-binding work is implemented. This
> does not add an OAuth flow, schema, hook, or token verifier.

## Status

Architecture: **Frozen**

This task implements the agreed generic MCP identity layer and removes the existing LibreChat-specific identity mapping path.

---

# 1. Objective

Create a new standalone Frappe app:

```text
mcp_identity
```

Its only v1 responsibility is:

```text
Authenticated MCP HTTP request
        +
verified user email supplied by the trusted MCP client
        ↓
resolve existing Frappe User
        ↓
make that Frappe User available to the consuming MCP app
```

The identity layer must be generic and must not know about LibreChat, ERPNext, HRMS, Google, or any other business/integration domain.

For the current `mcp_erpnext` integration, once a Frappe User is resolved, ERPNext/Frappe's existing permission model remains the source of truth.

---

# 2. Frozen Architecture

```text
Any supported MCP HTTP client
        ↓
Authorization: Bearer <shared-secret>
        +
generic verified-user-email header
        ↓
      mcp_identity
        ↓
validate trusted request
        ↓
resolve Frappe User by email
        ↓
ensure User exists and is enabled
        ↓
return/set resolved Frappe User
        ↓
consuming MCP app
        ↓
ERPNext / HRMS / future integration
        ↓
downstream system's native permissions
```

Current first consumer:

```text
mcp_erpnext
```

Future consumers may include other MCP apps. They must be able to reuse `mcp_identity` without importing `mcp_erpnext`.

---

# 3. Explicitly Out of Scope

Do **not** implement any of the following in v1:

```text
OAuth
OIDC
Continue with Frappe
redirect-based login
pairing pages
pairing codes
per-user MCP URLs
External User Identity DocType
MCP credential DocType
provider/platform mapping
LibreChat-specific mapping
LibreChat-specific identity resolver
custom MCP permission system
tool-level permission system
ERPNext permission duplication
HRMS permission duplication
Google permission duplication
service-user fallback
Guest fallback
email-only unauthenticated access
```

Do not create a DocType merely to justify the new app.

---

# 4. Important Security Model

The shared secret and email solve different problems.

```text
Shared secret
= Is this request coming from a trusted configured MCP client/server?

Verified user email
= Which Frappe User should this request run as?
```

Both are required for the current HTTP identity mode.

A request must never be trusted only because it contains an email address.

Example unsafe request:

```text
X-MCP-User-Email: administrator@example.com
```

This must not establish identity unless the request has first passed the configured shared-secret validation.

---

# 5. Generic HTTP Contract

Keep the current shared-secret concept, but make all identity naming generic.

Preferred request contract:

```http
Authorization: Bearer <MCP_HTTP_SHARED_SECRET>
X-MCP-User-Email: sagar@company.com
```

Use the existing environment/config mechanism for `MCP_HTTP_SHARED_SECRET` unless inspection finds a strong reason to relocate it.

Do not introduce a LibreChat-named environment variable or header.

The user email header must be generic:

```text
X-MCP-User-Email
```

If the local code already has a generic equivalent with established usage, preserve it only if it is genuinely platform-neutral and document the decision.

---

# 6. Fail-Closed Rules

The resolver must reject the request when any of these are true:

```text
shared secret missing
shared secret malformed
shared secret incorrect
user email missing
user email blank
user email malformed enough that it cannot identify a valid Frappe User
Frappe User does not exist
Frappe User is disabled
Frappe context cannot be safely initialized
```

Never fall back to:

```text
Administrator
Guest
service user
environment-configured Frappe user
previous request user
LibreChat mapping
```

Unknown/untrusted requests must fail closed.

---

# 7. New App Boundary

Create a standard Frappe app:

```text
mcp_identity
```

Suggested responsibility boundary:

```text
mcp_identity
├── request authentication helpers
├── identity validation
├── Frappe User resolution
├── request user-context helpers
└── tests
```

It must not import:

```text
mcp_erpnext
erpnext
hrms
yob_core
yob_auth
yob_storefront
future business MCP apps
```

It should depend only on Frappe unless local implementation requirements prove otherwise.

Do not add empty hypothetical modules or folders.

---

# 8. Pre-Implementation Inspection — Mandatory

Before changing code, inspect the actual current local state.

At minimum inspect:

```text
Frappe version
site name
installed apps
current git status
mcp_erpnext/hooks.py
mcp_erpnext/settings.py
mcp_erpnext/http_transport.py
mcp_erpnext/mcp_server.py
current LibreChat user-mapping implementation
current shared-secret validation
current HTTP identity-header handling
current request-scoped Frappe context setup/cleanup
current tests related to Task 05/06 identity mapping and HTTP transport
```

Also locate all references to terms such as:

```text
LibreChat User Mapping
librechat_user_mapping
librechat user
librechat_user
MCP_HTTP_SHARED_SECRET
identity headers
frappe.set_user
service user fallback
```

Do not assume file names if the actual local tree differs.

Before modification, report briefly:

```text
Current identity flow
Current shared-secret flow
LibreChat-specific files/references found
Files proposed for creation
Files proposed for modification
Files proposed for deletion/removal
Any compatibility risk
```

Then proceed unless a destructive ambiguity is discovered.

---

# 9. Create `mcp_identity`

Use the standard Frappe app scaffold from the actual bench environment.

Example only:

```bash
bench new-app mcp_identity
```

Use the project's existing publisher/email/license conventions where available.

Do not manually invent a non-Frappe Python package.

Do not rebuild Docker images for normal Python/Frappe app code unless inspection proves it is required.

---

# 10. Identity Resolver Contract

The implementation must expose one clear reusable contract to consumers.

Conceptually:

```text
trusted HTTP request identity inputs
        ↓
validate shared secret
        ↓
normalize/validate user email
        ↓
resolve Frappe User
        ↓
verify enabled
        ↓
return resolved Frappe User identity
```

Exact function names and internal decomposition are implementation choices for the coding agent.

Do not hardcode users or platforms.

Do not create mappings such as:

```text
librechat_user_123 → sagar@company.com
```

Do not maintain a platform/provider list.

---

# 11. Frappe User Resolution

The final internal identity is the existing Frappe `User`.

Expected behavior:

```text
incoming verified email
        ↓
look up User using Frappe's standard APIs
        ↓
User exists?
        ↓
User enabled?
        ↓
resolved Frappe User
```

Use standard Frappe APIs and preserve Frappe's existing user semantics.

Do not duplicate role, company, DocType, or user permissions inside `mcp_identity`.

---

# 12. Request User Context

The consuming MCP operation must execute under the resolved Frappe User.

The implementation must preserve request isolation:

```text
request starts
↓
Frappe context initialized
↓
identity resolved
↓
resolved user set for this request
↓
MCP tool executes
↓
context cleaned up
```

A user's identity must never leak into the next request.

Reuse the safe request-scoped context lifecycle already established in the current HTTP transport where correct.

Do not introduce global/process-level current-user state.

---

# 13. Integrate `mcp_erpnext`

After `mcp_identity` exists:

```text
mcp_erpnext
        ↓
depends on mcp_identity
        ↓
uses generic identity resolver
        ↓
receives Frappe User
        ↓
executes ERPNext tools as that user
```

Update `mcp_erpnext` dependency declaration appropriately using Frappe's normal `required_apps` pattern if applicable to the current app structure.

Preserve actual ERPNext dependencies already required by `mcp_erpnext`.

Do not move ERPNext tool logic into `mcp_identity`.

---

# 14. Remove LibreChat-Specific Identity Implementation Completely

There is no production data and no migration requirement.

Therefore:

```text
LibreChat User Mapping migration       NO
compatibility layer                    NO
deprecation period                     NO
dual resolver                          NO
fallback to old mapping                NO
```

Completely remove the old LibreChat-specific mapping implementation.

Remove as applicable:

```text
LibreChat User Mapping DocType
its Python/JSON files
references/imports
lookup helpers
mapping-specific tests
fixtures/config referencing it
LibreChat-specific identity header names
LibreChat-specific fallback logic
Task 05 mapping code that is no longer used
```

Do not remove unrelated LibreChat configuration or documentation merely because its name contains LibreChat. Only remove the identity-mapping-specific implementation that is superseded by `mcp_identity`.

After completion, a code search for the removed mapping name should return no active implementation references.

---

# 15. Preserve Shared Secret Protection

`MCP_HTTP_SHARED_SECRET` is **not** part of the obsolete LibreChat mapping and must not be removed merely because the mapping is removed.

For HTTP mode, keep shared-secret validation as the trusted-client gate.

Generic target behavior:

```text
Authorization: Bearer <shared secret>
        ↓
valid?
        ↓
read generic MCP user-email header
        ↓
resolve Frappe User
```

Use constant-time secret comparison where appropriate.

Never log the secret.

Never return the secret in errors.

---

# 16. Existing Transport Modes

Do not break existing transport support.

If `mcp_erpnext` currently supports:

```text
stdio
streamable-http
```

preserve both.

The shared-secret + email identity contract applies to HTTP mode where request headers exist.

For `stdio`, preserve the existing safe development/testing behavior unless it currently relies on the LibreChat mapping. If identity semantics for stdio require a decision, keep the smallest non-breaking behavior and document it rather than inventing a new v1 authentication system.

Do not weaken HTTP authentication to make stdio easier.

---

# 17. No Permission Duplication

`mcp_identity` answers only:

```text
Who is the caller in Frappe?
```

It must not answer:

```text
Can this user create Quotation?
Can this user submit Sales Order?
Can this user access HRMS?
Can this user call Google Calendar?
Which MCP tools are allowed?
```

For ERPNext/Frappe operations:

```text
resolved Frappe User
        ↓
normal Frappe / ERPNext permissions
```

Do not use `ignore_permissions=True` to bypass the resolved user's permissions except where pre-existing code has a separately justified internal reason; if found, report it as a security review item.

---

# 18. Error Behavior

Use concise machine-safe failures.

Minimum distinct cases should be testable:

```text
MCP authentication missing
MCP authentication invalid
MCP user identity missing
Frappe User not found
Frappe User disabled
```

Do not expose:

```text
raw secrets
tracebacks
internal configuration values
unnecessary personal details
```

Do not make errors LibreChat-specific.

---

# 19. Configuration

Keep configuration minimal.

Required HTTP configuration should remain approximately:

```text
MCP_HTTP_SHARED_SECRET=<strong-secret>
```

The existing minimum secret-length validation should be preserved if already implemented and still appropriate.

Document the generic user identity header expected from supported clients:

```text
X-MCP-User-Email
```

Do not add provider-specific configuration in v1.

---

# 20. Tests — `mcp_identity`

Add focused tests for the new app.

At minimum verify:

### Shared secret

```text
missing secret → rejected
incorrect secret → rejected
correct secret → continues
```

### User email

```text
missing email → rejected
blank email → rejected
unknown Frappe User → rejected
disabled Frappe User → rejected
enabled existing Frappe User → resolved
```

### Generic behavior

```text
no LibreChat-specific provider required
no mapping DocType required
no hardcoded user mapping
```

### Isolation

```text
request A user does not leak into request B
failed request does not leave a user context behind
```

---

# 21. Tests — `mcp_erpnext`

Update/remove old mapping tests and add integration coverage.

At minimum verify:

```text
valid shared secret + valid enabled Frappe email → ERPNext MCP request runs as that user
invalid shared secret → tool is not executed
missing email → tool is not executed
unknown user → tool is not executed
disabled user → tool is not executed
normal Frappe permissions still apply
```

Use at least two Frappe users with different permissions where feasible to prove the current user context is actually respected.

Do not fake success merely by checking that `frappe.set_user()` was called; verify permission-sensitive behavior where practical.

---

# 22. Existing LibreChat End-to-End Verification

LibreChat is the current test client, but it must now consume the generic contract.

Configure it to send:

```text
Authorization: Bearer <MCP_HTTP_SHARED_SECRET>
X-MCP-User-Email: <current logged-in user's verified email>
```

Then verify:

```text
LibreChat user A → Frappe User A
LibreChat user B → Frappe User B
```

No `LibreChat User Mapping` record must exist or be required.

The server implementation must not branch on `LibreChat`.

---

# 23. Security Checks

Explicitly verify:

```text
email header without valid shared secret cannot impersonate a Frappe User
Administrator email cannot be spoofed without trusted-client authentication
shared secret is never logged
unknown identity fails closed
no service-user fallback remains in HTTP mode
request user context is always cleaned up
old LibreChat mapping cannot be used as a bypass
```

Review any existing `ignore_permissions=True`, `frappe.set_user`, environment-user fallback, or direct DB access found in the affected path and report anything that could bypass the intended permission model.

---

# 24. Installation / Migration

Because `mcp_identity` is a new Frappe app:

1. Install it on the actual development site using the existing bench/container workflow.
2. Update dependencies.
3. Run migration as required by the new installed app/removal of the old DocType.

There is **no LibreChat mapping data migration**.

Do not preserve the old DocType for data safety; it contains only test/development data and is intentionally being removed.

Do not wipe or recreate the site.

Do not use destructive database commands.

---

# 25. Documentation

Add concise documentation to `mcp_identity` covering only:

```text
purpose
identity contract
required shared-secret config
generic email header
fail-closed behavior
consumer integration boundary
what the app deliberately does not own
```

Document the dependency direction:

```text
Frappe
   ↓
mcp_identity
   ↓
mcp_erpnext / future MCP consumers
```

Make it explicit that `mcp_identity` is not an ERPNext permission system and not a LibreChat adapter.

---

# 26. Acceptance Criteria

The task is complete only when all of the following are true:

- [ ] Standard Frappe app `mcp_identity` exists.
- [ ] `mcp_identity` has no DocTypes in v1.
- [ ] Shared-secret validation remains active for HTTP MCP requests.
- [ ] Generic user-email header is used.
- [ ] Existing enabled Frappe User can be resolved directly from the trusted email.
- [ ] Missing/invalid secret fails closed.
- [ ] Missing email fails closed.
- [ ] Unknown Frappe User fails closed.
- [ ] Disabled Frappe User fails closed.
- [ ] No Guest/service-user fallback exists in HTTP mode.
- [ ] Request user context is isolated and cleaned after each request.
- [ ] `mcp_erpnext` consumes `mcp_identity` rather than LibreChat mapping code.
- [ ] `LibreChat User Mapping` is completely removed.
- [ ] No compatibility/deprecation/migration path for the old mapping remains.
- [ ] No LibreChat-specific identity logic remains in the generic identity path.
- [ ] ERPNext operations continue to use native Frappe permissions.
- [ ] No MCP-specific tool permission system is introduced.
- [ ] Existing stdio support remains working unless a documented pre-existing limitation prevents it.
- [ ] Existing streamable-HTTP MCP transport remains working.
- [ ] Tests for `mcp_identity` pass.
- [ ] Updated `mcp_erpnext` tests pass.
- [ ] LibreChat end-to-end test works using the generic shared-secret + email contract.

---

# 27. Expected Final Architecture

```text
                      Frappe
                        │
                        ▼
                  mcp_identity
        shared-secret + user resolution
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
       mcp_erpnext            future MCP apps
            │
            ▼
          ERPNext
            │
            ▼
   native Frappe permissions
```

Current LibreChat becomes only one client:

```text
LibreChat
   ↓
shared secret + verified email
   ↓
common MCP endpoint
   ↓
mcp_identity
```

The server must behave the same for any future supported client that sends the same trusted generic contract.

---

# 28. Final Report Required From Agent

After implementation, report only the information useful for review:

## Architecture

Show the final dependency flow.

## Created

List files/app created in `mcp_identity`.

## Modified

List affected `mcp_erpnext` files and why.

## Removed

List all LibreChat User Mapping files/references removed.

## Configuration Required From User

State exactly what must be configured, including:

```text
MCP_HTTP_SHARED_SECRET
client Authorization header
generic user-email header
app installation/migrate commands if required
```

## Tests

List commands run and exact pass/fail result.

## Security Verification

Confirm:

```text
fail-closed behavior
no service-user fallback
no email-only trust
no user-context leakage
native Frappe permission enforcement preserved
```

## Limitations

List only real remaining limitations, especially clients that cannot send the agreed trusted identity contract.

Do not include speculative future architecture unless it blocks the current v1.

---

# 29. Exact Next Task After This One

After this task passes, the next task is **not** to add OAuth or provider mapping.

The next task should be:

```text
MCP Identity Client Compatibility Verification
```

Verify the frozen generic HTTP identity contract against the actual clients we intend to support next (LibreChat first, then other MCP clients) and only introduce an additional authentication adapter if a real client cannot satisfy the shared-secret + verified-email contract.

Do not pre-build unused authentication systems.
