# Task 04V - MCP Identity Frappe OAuth Resource-Binding Live Verification

## Status

Ready for execution on a local/testing-only Frappe site.

## Target App

Primary:

- `mcp_identity`

Consumer regression only where needed:

- `mcp_erpnext`

## Task Type

Local-site migration + DB-backed integration/security verification.

This is a **verification task**, not a production implementation task.

---

## 1. Scope

Verify the Task 04 Frappe OAuth resource-binding compatibility implementation against a real local Frappe site and real database behavior.

The user has explicitly confirmed that the current site/environment is local and used for testing, so this task may perform local test-site mutations required for verification, including:

- installing `mcp_identity` on the selected local test site if it is not already installed;
- running `bench migrate` on that local test site;
- creating disposable OAuth Client / OAuth Authorization Code / OAuth Bearer Token records;
- creating disposable local test users if required;
- executing authorization-code, token, refresh, revocation, and replay tests;
- running two-connection database concurrency tests;
- clearing cache / restarting the local development process if genuinely required by Frappe after migration/hook changes;
- deleting/revoking disposable test data after verification where safe and appropriate.

Do not hard-code a site name in production code, tests, documentation, or commands committed to the repository. Resolve the local test site from the current project/runtime configuration or explicit bench/site context.

This task must verify Task 04 as implemented. It must **not** implement Task 05 FastMCP OAuth resource-server support.

---

## 2. Objective

Prove with a migrated local site and real database transactions that the Task 04 authorization-server compatibility layer actually provides durable, replay-safe MCP resource binding.

The verification must establish that:

```text
OAuth Client.custom_mcp_resource
        -> Authorization Code.custom_mcp_resource
        -> Bearer Token.custom_mcp_resource
        -> refresh preserves the same resource
        -> old refresh/code cannot be replayed successfully
```

and that:

```text
native Frappe OAuth behavior
+ mcp_identity resource-binding extension
```

works without replacing Frappe login, consent, PKCE, redirect checks, token generation, scopes, user ownership, expiry, or native revocation.

The result must answer one question unambiguously:

> Is Task 04 safe and proven enough on a real local Frappe site to unblock Task 05 FastMCP OAuth resource-server integration?

---

## 3. Inputs / Source of Truth

Use the current checkout, not assumptions from earlier task text.

Required inputs:

- current `mcp_identity` source including Task 03 and Task 04 changes;
- current `mcp_erpnext` source including Task 03 changes;
- `mcp_identity/docs/inspect/MCP_IDENTITY_FRAPPE_OAUTH_RESOURCE_BINDING_DESIGN.md`;
- `mcp_identity/docs/inspect/MCP_IDENTITY_TASK_04_FRAPPE_OAUTH_RESOURCE_BINDING_IMPLEMENTATION_REPORT.md`;
- `mcp_identity/mcp_identity/tests/test_oauth_replay_integration.py`;
- Task 04 OAuth compatibility/resource/patch tests;
- installed Frappe `version-16` source;
- installed oauthlib version;
- the current local Frappe bench/site configuration.

Before executing any migration or DB-writing verification, inspect the current working tree and record existing changes. Do not overwrite or clean unrelated work.

---

## 4. Mandatory Engineering Rule - Verify Existing Implementation, Do Not Rebuild It

Do not create a second OAuth flow, alternate token store, custom login, custom authorization endpoint, or parallel validation framework for this verification.

Use the implementation already produced by Task 04 and Frappe's native OAuth machinery.

Prefer existing project tests and native Frappe helpers/endpoints over writing ad-hoc verification logic.

If a missing test harness is required only to exercise an existing production path, test-only code may be added under the existing test suite, but:

- do not change production behavior;
- do not add a workaround merely to make a failing test pass;
- document any new test helper clearly;
- if verification exposes a production bug, stop and report it as a blocker rather than silently fixing it in this task.

---

## 5. Site Selection and Safety Boundary

The user has authorized writes on the **local testing site only**.

Required selection logic:

1. inspect current bench sites and current MCP/Frappe site configuration;
2. prefer the site already configured for the local MCP test environment;
3. if the app/test harness already specifies the local site through environment/config, use that;
4. do not embed that resolved site name into production code;
5. record the selected site in the report;
6. verify that the selected site is local/testing before performing writes.

Do not run this task against a production or externally managed site.

If multiple local sites are present, use the one already configured for this project/test runtime rather than inventing a new hard-coded default.

---

## 6. Allowed Changes / Actions

### Allowed on the local test site

- `bench --site <resolved-local-site> install-app mcp_identity` if required;
- `bench --site <resolved-local-site> migrate`;
- Frappe cache clear/restart if required after hooks/schema migration;
- creation of disposable Frappe Users required only for OAuth verification;
- creation/update/deletion of a dedicated disposable OAuth Client;
- creation/consumption/revocation/deletion of OAuth codes/tokens through the native flow/tests;
- database transaction and two-connection concurrency tests;
- execution of the already implemented gated replay tests;
- local HTTP/Frappe OAuth requests if needed to prove the native endpoint lifecycle;
- test-only records/configuration required for the isolated local flow;
- test-only code additions if strictly required to exercise production behavior.

### Allowed repository changes

Only:

- this verification report;
- narrowly scoped test-only changes if a missing integration harness is required;
- test documentation if necessary.

### Not allowed

- production behavior changes;
- modifying Frappe core;
- changing the Task 04 resource-binding design during verification;
- adding FastMCP `TokenVerifier`;
- enabling `MCP_HTTP_AUTH_MODE=oauth` in the MCP server;
- adding protected-resource metadata/challenges;
- ChatGPT MCP connection;
- generic OAuth provider abstraction;
- DCR/CIMD implementation;
- broad unrelated test fixes;
- changing approval/business tools;
- changing REST backend identity semantics.

If a production defect is found, produce a blocker/fix recommendation and stop the affected verification path.

---

## 7. Preflight Inspection

Before mutation, record:

- bench path;
- selected local test site;
- `mcp_identity` branch/commit/worktree state;
- `mcp_erpnext` branch/commit/worktree state;
- Frappe branch/commit/version;
- ERPNext version;
- oauthlib version;
- Python MCP SDK version;
- Python version;
- installed apps on the selected site;
- whether `mcp_identity` is already installed;
- whether the three Custom Fields already exist;
- current relevant OAuth Settings without exposing secrets;
- whether any pre-existing test OAuth Client with the intended test identifier exists.

Do not assume Task 04 migration has been applied merely because the code exists.

---

## 8. Install / Migration Verification

### 8.1 Ensure `mcp_identity` is installed

If `mcp_identity` is not installed on the selected local test site, install it using the standard Frappe app installation mechanism.

Do not install or modify unrelated apps.

### 8.2 Apply migrations

Run the standard site migration for the selected local test site.

After migration, verify through Frappe metadata and database/schema inspection that exactly these Task 04 fields exist:

```text
OAuth Client.custom_mcp_resource
OAuth Authorization Code.custom_mcp_resource
OAuth Bearer Token.custom_mcp_resource
```

Verify expected properties from Task 04:

- type `Small Text`;
- optional;
- code/token fields hidden/read-only/no-copy/report/print hidden as designed;
- no new MCP token/identity DocType;
- no duplicate token table;
- no backfill into unrelated existing records.

Run migration a second time or otherwise prove the patch is idempotent and does not duplicate fields or corrupt metadata.

---

## 9. Hook / Override Registration Verification

Verify on the migrated local site that Task 04 hooks are loaded and resolve as intended.

The implementation report states that `override_whitelisted_methods` is used rather than raw-path `before_request` gating.

Prove that the compatibility wrapper/validator seam is active for all supported native OAuth RPC invocation forms applicable to the installed Frappe version, including where supported:

```text
legacy/root cmd dispatch
/api/method/<method>
/api/v2/method/<method>
```

The test must prove there is no alternate supported route that invokes the native OAuth method while bypassing the `mcp_identity` compatibility validator.

Do not merely inspect hook configuration; execute or integration-test the dispatch resolution where practical.

---

## 10. Disposable OAuth Test Fixture

Create a dedicated disposable OAuth test fixture on the local site using native Frappe records/APIs.

Use a clearly test-only client identifier/title.

The bound client must be configured as the Task 04 design requires:

- Authorization Code flow;
- Code response type;
- public client / token endpoint auth method compatible with the tested native path;
- exact test redirect URI;
- S256 PKCE;
- minimal MCP test scope, for example `mcp:access` if that is the implemented expected scope;
- one canonical MCP resource binding.

Use a canonical HTTPS test resource that requires no external service, for example a reserved test domain such as:

```text
https://mcp.example.invalid/mcp
```

or another deterministic canonical HTTPS test URL accepted by the current implementation.

Do not use a real external production MCP endpoint for this verification.

Create/use a disposable enabled non-Guest Frappe test user where needed. Negative tests may use a disposable disabled user if current test utilities support clean creation/removal.

Record exact fixture values except secrets/tokens/passwords.

---

## 11. Canonical Resource Verification

Exercise the production `canonicalize_mcp_resource()` behavior with real Task 04 tests and confirm at minimum:

- valid HTTPS URL accepted;
- scheme/host normalization behaves as designed;
- default port removal;
- non-default port preservation;
- path case preservation;
- trailing slash policy;
- query rejected;
- fragment rejected;
- userinfo rejected;
- dot segments rejected;
- repeated slash aliases rejected;
- malformed percent escapes rejected;
- multiple/duplicate resource values rejected;
- domain aliases remain distinct;
- resource is never inferred from Host/Forwarded headers.

Do not loosen canonicalization during this task merely to make an integration fixture easier.

---

## 12. DB-Backed Authorization-Code Lifecycle

Prove on the migrated site using native Frappe/oauthlib behavior plus the Task 04 compatibility extension:

```text
bound OAuth Client
    -> authorization request with exact resource + S256 PKCE
    -> native authorization code
    -> OAuth Authorization Code.custom_mcp_resource populated
```

Required positive checks:

- native client validation runs;
- exact redirect URI behavior remains native;
- S256 challenge required for the bound client;
- exactly one correct resource accepted;
- persisted authorization-code resource equals the canonical client binding;
- native user ownership is preserved;
- native scopes are preserved.

Required negative checks:

- missing resource -> fail closed;
- wrong resource -> `invalid_target`/equivalent standards-safe failure;
- malformed resource -> fail;
- duplicate/multiple resource -> fail;
- missing PKCE challenge -> fail for bound client;
- non-S256/plain PKCE -> fail for bound client;
- unbound OAuth Client continues native behavior and receives no inferred MCP binding.

Where browser login/consent is practical locally, exercise the native flow through those endpoints. Otherwise use the closest Frappe-native integration harness that still executes the real endpoint/validator/document-event/database path and document the limitation precisely.

---

## 13. DB-Backed Token Exchange

Using the real authorization-code record:

```text
code(resource=A)
    + token request(resource=A)
    -> bearer token(resource=A)
    -> code becomes Invalid
```

Verify:

- source authorization code is selected with row locking in the production path;
- request resource must exactly equal stored/client resource;
- native PKCE verifier logic still runs;
- bearer token gets the same `custom_mcp_resource`;
- native token user/client/scopes remain correct;
- code invalidation and bearer insertion commit atomically for the bound flow;
- missing/wrong/multiple token-request resource fails without issuing a usable token;
- sequential code reuse fails.

Do not print/log raw authorization codes or access/refresh tokens in the report.

---

## 14. Mandatory Two-Connection Authorization-Code Replay Test

Run the already implemented operator-gated authorization-code replay integration test against the migrated local site.

Set the project's explicit test gate as required by the current test implementation, including:

```text
MCP_IDENTITY_RUN_OAUTH_DB_TESTS=1
```

and any current site/test environment value required by the test harness after inspecting the test source.

Use **two independent database connections/transactions**, not two mocks sharing one transaction.

Expected property:

```text
same still-valid authorization code
request A -----------------> exactly one succeeds
request B -----------------> the other blocks/then fails
```

Record:

- runner/command;
- site;
- database engine;
- result;
- which assertion proves only one success;
- whether row blocking/serialization was actually observed/proven by the integration test.

This test is mandatory for Task 04V pass status.

---

## 15. DB-Backed Refresh Lifecycle

Using a real bound bearer/refresh pair:

```text
old token(resource=A)
    + refresh(resource=A)
    -> replacement token(resource=A)
    -> old pair Revoked
```

Verify:

- source bearer row is locked;
- authenticated client equals source client;
- source binding equals current OAuth Client binding;
- exactly one matching resource is required;
- enabled non-Guest source user is revalidated;
- replacement preserves user/client/scopes/resource;
- old access/refresh pair becomes Revoked in the same transaction as replacement insertion;
- changed/missing/multiple resource fails;
- resource switching is impossible;
- sequential old-refresh reuse fails;
- disabled/deleted/Guest user path fails closed where safely testable.

---

## 16. Mandatory Two-Connection Refresh Replay Test

Run the already implemented operator-gated refresh replay integration test using two independent database connections/transactions.

Expected property:

```text
same active refresh token
request A -----------------> exactly one succeeds
request B -----------------> the other blocks/then fails
```

Confirm the winning transaction creates one replacement pair and revokes the source pair.

Confirm the losing transaction cannot mint another active replacement.

This test is mandatory for Task 04V pass status.

---

## 17. Native Revocation / Cleanup Verification

Using the native Frappe revocation path, verify that a bound token remains a normal native OAuth Bearer Token record with extra resource metadata.

Confirm:

- revoking access or refresh token marks the native pair Revoked according to Frappe behavior;
- the resource binding does not create a sidecar cleanup requirement;
- revoked token state cannot become active again due to stale resource metadata;
- cleanup/deletion of native OAuth records naturally removes the attached custom field value.

Do not implement a second revocation path.

---

## 18. Identity / Permission Boundary Verification

Task 04 does not yet expose FastMCP OAuth, but the authorization-server records must retain the correct Frappe user.

Verify that:

```text
OAuth Authorization Code.user
        -> OAuth Bearer Token.user
```

remains the native authenticated Frappe User.

Prove for bound flows:

- enabled user succeeds;
- disabled/deleted/Guest user fails in the Task 04 compatibility checks where designed;
- no `X-MCP-User-Email` participates;
- no `MCP_FRAPPE_USER` participates;
- no caller header can override token ownership.

Do not test FastMCP `frappe.set_user()` OAuth consumption yet; that is Task 05.

---

## 19. Regression Verification

Run the established suites after migration/integration verification.

At minimum:

### `mcp_identity`

- full current identity test suite;
- gated DB replay integration tests enabled.

### `mcp_erpnext`

Run at least the Task 03 focused consumer regression suite:

- identity integration;
- HTTP transport;
- runtime;
- REST backend.

Also run the established full `mcp_erpnext` test suite and compare the same five previously documented unrelated approval-policy failures.

If failure count/type changes, investigate before declaring Task 04V successful.

Do not silently repair unrelated approval tests in this task.

---

## 20. Static / Repository Verification

After verification:

- run Python compile/static syntax verification for both apps;
- run `git diff --check` for both apps;
- confirm no Frappe core file changed;
- confirm no Task 05 FastMCP OAuth implementation appeared;
- confirm no production source was modified by this verification unless explicitly documented as an accidental/problematic deviation;
- list any new test-only files/changes.

Do not install new lint/development dependencies solely for this task unless the repository already requires them.

---

## 21. Test Data Cleanup

After evidence is captured:

- revoke disposable active OAuth tokens;
- remove disposable OAuth Client/test users only if removal does not invalidate evidence needed by the test suite/report;
- otherwise leave clearly named test-only records and document them;
- do not remove the three Custom Fields or Task 04 migration result;
- do not reverse Task 04 production code on a passing local test site.

The report must state exactly what test records remain.

Never include raw token/code/password values in the report.

---

## 22. Pass / Fail Rules

### PASS

Task 04V passes only if all of the following are true:

1. `mcp_identity` is installed on the selected local OAuth Authorization Server site;
2. site migration completes successfully;
3. all three expected Custom Fields exist with the intended metadata;
4. repeated migration/patch application is idempotent;
5. OAuth override/hook routing cannot be bypassed through supported RPC dispatch forms;
6. bound authorization request persists the canonical resource;
7. missing/wrong/duplicate resource fails closed;
8. S256 PKCE is enforced for the bound client;
9. code exchange preserves the exact resource;
10. code consumption/token insertion behavior is proven with real DB state;
11. two-connection authorization-code replay allows at most one success;
12. refresh preserves exact user/client/scopes/resource;
13. source refresh pair is revoked during rotation;
14. two-connection refresh replay allows at most one success;
15. native revocation still works;
16. unbound/non-MCP OAuth Client remains compatible with native behavior;
17. no alternate identity header/config is used by OAuth issuance;
18. Task 03 stdio/trusted-header/REST regressions still pass;
19. no new Task 04-caused full-suite regression remains;
20. no Frappe core modification exists;
21. OAuth is still not enabled in FastMCP/ChatGPT at the end of this task.

### FAIL / BLOCKED

Mark Task 04V blocked if any of these occurs:

- migration/patch fails;
- expected field metadata is wrong;
- route bypass exists;
- resource can be omitted/switched/replayed;
- authorization-code concurrency permits two successful exchanges;
- refresh concurrency permits two successful replacements;
- old refresh remains reusable after a successful rotation;
- resource/client/user/scope integrity is not preserved;
- Task 03 trusted-header/stdio semantics regress;
- verification requires patching Frappe core;
- production code must be changed to make the test pass.

If blocked, do not proceed to Task 05. Document the smallest root-cause fix as the next task.

---

## 23. Acceptance Criteria

This verification task is complete only when the final report contains:

1. selected local site and why it is safe for test writes;
2. preflight repository/framework versions;
3. installed-app state before/after;
4. exact migration/install commands and results;
5. proof of all three Custom Fields and metadata;
6. idempotent migration proof;
7. RPC override/bypass verification;
8. canonical resource test results;
9. real DB-backed authorization-code binding proof;
10. real DB-backed token exchange proof;
11. two-connection authorization-code replay result;
12. real DB-backed refresh/rotation proof;
13. two-connection refresh replay result;
14. native revocation proof;
15. user/identity-boundary proof;
16. stdio/trusted-header/REST regression results;
17. full suite results and comparison to the known unrelated failures;
18. static verification results;
19. test data cleanup/remaining-record statement;
20. explicit PASS / FAIL / BLOCKED verdict;
21. exact Task 05 readiness or exact blocker/fix task.

---

## 24. Expected Result

Expected successful evidence:

```text
Local test site
    -> mcp_identity installed
    -> bench migrate succeeds
    -> 3 resource fields exist

Bound OAuth Client(resource=A)
    -> authorization(resource=A, S256)
    -> Authorization Code(resource=A)
    -> token exchange(resource=A)
    -> Bearer Token(resource=A)

Concurrent same-code exchange
    -> ONE success only

Refresh(resource=A)
    -> replacement(resource=A)
    -> source pair Revoked

Concurrent same-refresh reuse
    -> ONE success only

Wrong/missing Resource B
    -> rejected

Unbound normal Frappe OAuth client
    -> native compatibility preserved

Task 03 stdio/trusted-header/REST
    -> unchanged

FastMCP OAuth
    -> still disabled
```

If all pass, Task 04 authorization-server compatibility is considered live-verified on the local test environment and Task 05 may begin.

---

## 25. Limitations

Even after Task 04V passes:

- this proves the local Frappe authorization-server compatibility layer, not production deployment hardening;
- ChatGPT OAuth is not yet connected;
- FastMCP has not yet verified opaque bearer tokens;
- protected-resource metadata and 401/403 challenges are still absent;
- reverse-proxy public issuer/resource URL behavior is still Task 05/deployment work;
- real production multi-worker infrastructure is not proven by a local test alone;
- DCR/CIMD remain out of scope;
- external OAuth providers remain out of scope.

---

## 26. Deliverable

Create:

```text
mcp_identity/docs/inspect/
MCP_IDENTITY_TASK_04V_FRAPPE_OAUTH_RESOURCE_BINDING_LIVE_VERIFICATION_REPORT.md
```

The report must include:

1. Result / PASS-FAIL-BLOCKED
2. Environment and selected local site
3. Repository / framework versions
4. Install / migration result
5. Custom Field verification
6. Hook / RPC override verification
7. Test fixture summary
8. Canonical resource verification
9. Authorization-code lifecycle
10. Token exchange lifecycle
11. Authorization-code concurrency replay proof
12. Refresh lifecycle
13. Refresh concurrency replay proof
14. Revocation / cleanup proof
15. Identity boundary proof
16. Regression suite results
17. Static verification
18. Test data cleanup / records remaining
19. Deviations / limitations
20. Task 05 readiness or blocker

Do not include raw OAuth codes, access tokens, refresh tokens, passwords, client secrets, or Authorization headers.

---

## 27. Exact Next Task

If Task 04V passes completely, the next task is:

**Task 05 - FastMCP OAuth Resource-Server Integration and E2E Verification**

Task 05 may then:

- make `MCP_HTTP_AUTH_MODE=oauth` start successfully when configuration/resource-binding prerequisites are valid;
- add Frappe opaque bearer-token verification;
- add FastMCP `AuthSettings` and `TokenVerifier` integration;
- expose MCP protected-resource metadata;
- implement standards-compliant 401/403 challenges;
- consume only the verified native Frappe token user;
- preserve native Frappe/ERPNext permissions;
- run MCP Inspector OAuth verification;
- finally run ChatGPT remote MCP OAuth verification;
- preserve stdio and trusted-header compatibility.

If Task 04V fails or is blocked, do **not** start Task 05. The verification report must instead define the smallest root-cause Task 04 fix required.
