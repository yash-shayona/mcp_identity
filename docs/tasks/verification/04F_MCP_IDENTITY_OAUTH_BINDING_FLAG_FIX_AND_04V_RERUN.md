# Task 04F - MCP Identity OAuth Binding Flag Cleanup Fix and 04V Rerun

## Status

Ready for implementation and verification.

## Target App

Primary:

- `mcp_identity`

Consumer app:

- `mcp_erpnext` must not require production changes for this task.

## Task Type

Narrow production bug fix + regression test + full Task 04V rerun.

This is **not** an OAuth architecture task and **not** Task 05.

---

## 1. Scope

Fix the live Task 04 defect in the request-local OAuth resource-binding cleanup helper, then rerun the complete Task 04V live verification on the approved local/testing-only Frappe site.

The known failure is:

```text
install_mcp_oauth_validator_for_request()
  -> _clear_binding()
  -> hasattr(frappe.flags, "mcp_oauth_resource_binding") == True
  -> delattr(frappe.flags, "mcp_oauth_resource_binding")
  -> KeyError
  -> HTTP 500
```

The fix must be the smallest Frappe-compatible change necessary.

Do not redesign the OAuth compatibility layer.

Do not begin FastMCP OAuth resource-server integration.

---

## 2. Objective

After this task:

1. a fresh OAuth request must not fail while clearing absent request-local binding state;
2. binding cleanup must work correctly for real `frappe.flags`;
3. existing binding state must still be removable/reset safely;
4. request-local state must never leak across OAuth requests;
5. all existing Task 04 unit/source tests must pass;
6. all previously passing live migration/schema/hook/concurrency checks must still pass;
7. the complete native OAuth lifecycle in Task 04V must be rerun and pass;
8. only after the complete 04V report passes may Task 05 begin.

---

## 3. Inputs

Inspect the current checkout before editing.

Required project inputs:

- current `mcp_identity` source;
- current `mcp_erpnext` source;
- `mcp_identity/docs/inspect/MCP_IDENTITY_TASK_04_FRAPPE_OAUTH_RESOURCE_BINDING_IMPLEMENTATION_REPORT.md`;
- `mcp_identity/docs/inspect/MCP_IDENTITY_TASK_04V_FRAPPE_OAUTH_RESOURCE_BINDING_LIVE_VERIFICATION_REPORT.md`;
- current `mcp_identity/oauth_compat.py`;
- current tests, especially:
  - `test_oauth_compat.py`
  - `test_oauth_patch.py`
  - `test_oauth_replay_integration.py`
  - `test_oauth_live_integration.py`
  - resource canonicalization tests.

Installed/tested framework context from 04V:

- Frappe `16.34.0`
- ERPNext `16.35.0`
- oauthlib `3.3.1`
- MCP SDK `1.29.0`

Use the actual installed source as runtime authority.

---

## 4. Mandatory Engineering Rule - Reuse Existing Logic First

Do not introduce a new state container, request context abstraction, or OAuth framework.

The existing design remains:

```text
frappe.local / frappe.flags
    -> request-local binding state
```

Only correct the cleanup semantics for Frappe's real mapping-like `_dict` behavior.

Before editing, inspect the installed Frappe implementation of `_dict` / `frappe.flags` and confirm the supported mapping operations.

Prefer native dictionary-style removal such as:

```python
frappe.flags.pop(KEY, None)
```

or another installed-source-confirmed equivalent.

Do not choose an implementation merely because it works on a `SimpleNamespace` test fake.

---

## 5. Confirmed Root Cause

Task 04V proved that the current helper is incorrect:

```python
def _clear_binding() -> None:
    if hasattr(frappe.flags, _BINDING_FLAG):
        delattr(frappe.flags, _BINDING_FLAG)
```

The live `frappe.flags` object is Frappe `_dict`-like.

A missing attribute can resolve to `None`, so:

```python
hasattr(frappe.flags, key)
```

can return true even when the mapping key is absent.

Then:

```python
delattr(...)
```

can attempt to delete a nonexistent mapping key and raise `KeyError`.

This is a production bug proven by the live OAuth RPC test.

Do not change the architectural design to solve this.

---

## 6. Allowed Production Changes

Allowed only where required for this defect:

### `mcp_identity`

- `mcp_identity/oauth_compat.py`
  - fix `_clear_binding()` or the exact current equivalent;
- focused test files needed to prove real Frappe `_dict` behavior;
- test fake/helper updates if their semantics currently hide this defect;
- README/report only if needed to document the correction.

### `mcp_erpnext`

No production change expected or allowed unless the current checkout proves an unavoidable direct dependency on this exact fix.

If such a need appears, stop and document it rather than expanding scope silently.

---

## 7. Forbidden Changes

Do not:

- add/remove/change the three `custom_mcp_resource` fields;
- add a new DocType;
- add a sidecar table;
- change the approved OAuth Client -> Authorization Code -> Bearer Token resource-binding model;
- change resource canonicalization semantics;
- change PKCE requirements;
- change row-lock strategy;
- change code-consumption semantics;
- change refresh rotation semantics;
- change OAuth endpoint override architecture;
- change `override_whitelisted_methods`;
- add DCR/CIMD support;
- modify Frappe core;
- enable `MCP_HTTP_AUTH_MODE=oauth` in FastMCP;
- add FastMCP `TokenVerifier`;
- add protected-resource metadata;
- add ChatGPT integration;
- change stdio/trusted-header behavior;
- change ERPNext tools, permissions, profiles, approval logic, or REST behavior;
- silently fix unrelated issues.

---

## 8. Required Fix Behavior

The cleanup helper must satisfy all of these:

### Missing binding

Given a fresh real `frappe.flags` with no binding key:

```text
_clear_binding()
```

must:

- return normally;
- not raise `KeyError`;
- not create the key;
- not change unrelated flags.

### Existing binding

Given:

```text
frappe.flags["mcp_oauth_resource_binding"] = <state>
```

cleanup must:

- remove exactly that key;
- leave unrelated request-local flags untouched;
- be idempotent.

Calling cleanup twice must succeed.

### Request isolation

At wrapper entry:

```text
stale binding from current request context, if any
    -> removed
```

Then the native/compatibility validator may install fresh state.

No binding from a prior invocation may be reused.

### Exception paths

If native/compatibility OAuth validation fails:

- stale/partially created binding state must not become valid input for a later request;
- existing request-local lifecycle cleanup behavior must remain intact.

Do not introduce process-global cleanup.

---

## 9. Test-Fake Correction

Task 04V found that the old unit fake used `SimpleNamespace`, whose missing-attribute semantics differ from real `frappe._dict`.

Tests must no longer mask that difference.

Use one of these approaches, preferring the most native/current-project appropriate:

1. instantiate real `frappe._dict` for flags in focused unit tests; or
2. use a minimal fake that intentionally matches Frappe `_dict` missing-key behavior.

Do not keep a fake whose semantics make the production bug impossible to reproduce.

Add an explicit regression test for:

```text
missing key
hasattr-like semantics would previously mislead
cleanup must not raise
```

---

## 10. Required Focused Tests

At minimum add/prove:

### Cleanup unit tests

- missing binding key -> no exception;
- existing binding -> removed;
- cleanup called twice -> no exception;
- unrelated flags preserved;
- fresh real `frappe._dict` behavior is covered;
- stale binding does not survive wrapper initialization.

### Wrapper tests

For each wrapped native method:

```text
authorize
approve
get_token
revoke_token
```

prove:

- wrapper can start with no binding flag;
- wrapper installs fresh compatibility validator/state as intended;
- wrapper delegates to native function;
- no old binding is reused.

### Existing Task 04 regression

All current tests for:

- canonical resource handling;
- bound/unbound clients;
- S256 enforcement;
- code binding;
- token binding;
- refresh binding;
- route override coverage;
- code/refresh locks;
- Guest/disabled user handling

must remain passing.

---

## 11. Local Test Site Authorization

The user has explicitly confirmed the current environment is local/testing-only.

Therefore this task is authorized to use the current configured local test site for:

- `bench migrate`;
- test OAuth Client/User/code/token records;
- DB writes;
- refresh/revocation;
- operator-gated Frappe tests;
- two-connection concurrency tests;
- cleanup of disposable test records;
- service/cache operations only if the actual Frappe test flow requires them.

Do not hard-code a site name in production code.

The verification agent may resolve the current local test site from the repository/runtime configuration.

Record the site used in the final report.

Do not modify unrelated pre-existing OAuth clients.

---

## 12. Migration Verification

Task 04V already migrated successfully, but rerun the relevant safe checks.

Confirm:

- `mcp_identity` is installed on the OAuth Authorization Server test site;
- migration is clean/idempotent;
- the three approved Custom Fields exist exactly once;
- Patch Log is not duplicated;
- existing blank/unbound OAuth Clients remain unbound;
- no new sidecar/token DocType exists.

Do not add new schema for this fix.

---

## 13. Mandatory Full 04V Rerun

After the focused fix/tests pass, rerun the entire live verification, not only the previously failing first request.

The rerun must verify all of the following.

### A. Hook/dispatch coverage

All supported installed RPC invocation forms must reach the override seam for:

```text
authorize
approve
get_token
revoke_token
```

No raw-path-only protection.

### B. Bound authorization request

With a real bound OAuth Client:

```text
resource = canonical MCP resource
PKCE = S256
```

prove the native authorization flow proceeds rather than returning HTTP 500.

### C. Resource errors

Prove standards-safe failure for:

- missing resource;
- wrong resource;
- malformed resource;
- duplicate/multiple resource;
- non-S256/missing PKCE for a bound client.

Do not accept a server error as success.

### D. Authorization-code persistence

Prove a real native authorization code stores:

- native client;
- native user;
- scopes;
- PKCE values;
- exact canonical `custom_mcp_resource`.

### E. Token exchange

Prove:

```text
bound authorization code
    + same resource
    + correct verifier
    -> native OAuth Bearer Token
```

and verify:

- token user continuity;
- client continuity;
- scope continuity;
- resource continuity;
- code becomes invalid atomically.

### F. Sequential code replay

Reuse the consumed code through the real token endpoint.

It must fail.

### G. Concurrent code replay

Run the existing two-connection gated test.

Exactly one claim/success must occur.

### H. Refresh lifecycle

Prove through the real refresh flow:

- same client required;
- same resource required;
- user continuity;
- scope continuity;
- replacement receives same resource;
- old access/refresh pair becomes Revoked.

### I. Sequential refresh replay

Reuse old refresh token through the real token endpoint.

It must fail.

### J. Concurrent refresh replay

Run the existing two-connection gated test.

Exactly one claim/success must occur.

### K. Revocation

Use the wrapped native revoke endpoint and prove the record becomes unusable.

### L. Unbound native Frappe OAuth compatibility

A client with blank `custom_mcp_resource` must continue native Frappe OAuth behavior.

The MCP compatibility layer must not force MCP resource binding on unrelated OAuth clients.

### M. Identity safety

For bound flows:

- token user is the actual native Frappe User;
- Guest fails;
- disabled User fails;
- deleted/missing User fails;
- `X-MCP-User-Email` does not participate;
- `MCP_FRAPPE_USER` does not participate.

---

## 14. Mandatory DB Concurrency Command

Use the repository's corrected gated integration test, adapting only if the current checkout differs:

```bash
MCP_IDENTITY_RUN_OAUTH_DB_TESTS=1 \
  ./env/bin/bench --site <resolved-local-test-site> run-tests \
  --app mcp_identity \
  --module mcp_identity.tests.test_oauth_replay_integration
```

The report must record exact output/result.

Both tests must pass:

```text
authorization-code replay serialization
refresh-token replay serialization
```

---

## 15. Regression Tests

Run:

### `mcp_identity`

Focused tests plus full established suite.

### `mcp_erpnext`

At minimum Task 03 focused identity/HTTP/runtime/REST suite.

Then run the full established consumer suite.

Previously documented unrelated approval-policy test failures may remain, but:

- their count/type must not worsen;
- report them separately;
- do not modify approval behavior in this task.

---

## 16. Cleanup

All disposable live OAuth test data must be cleaned after verification.

At minimum remove test-created:

- OAuth Clients;
- authorization codes;
- bearer tokens;
- child roles;
- disposable test Users if created.

Preserve:

- Task 04 Custom Fields;
- Patch Log entry;
- unrelated pre-existing OAuth Clients;
- unrelated users/settings.

Restore temporary testing configuration such as `allow_tests` to its prior value.

Report exact cleanup state.

---

## 17. Acceptance Criteria

Task 04F + rerun is complete only when all are true:

1. `_clear_binding()` no longer fails on fresh real `frappe.flags`;
2. the fix uses Frappe-compatible mapping semantics confirmed from installed source;
3. cleanup is idempotent;
4. unrelated flags remain untouched;
5. test fakes no longer hide Frappe `_dict` behavior;
6. no OAuth architecture/schema/resource-model change was introduced;
7. all ordinary `mcp_identity` tests pass except explicitly justified gates;
8. migration/schema checks still pass;
9. all supported OAuth RPC routes reach the override seam;
10. real bound authorization proceeds successfully;
11. resource/PKCE invalid cases fail safely;
12. real authorization code stores correct resource;
13. real token exchange preserves user/client/scopes/resource;
14. real consumed-code replay fails;
15. concurrent code replay permits only one claim/success;
16. real refresh preserves user/client/scopes/resource;
17. old token pair is revoked during rotation;
18. sequential old-refresh replay fails;
19. concurrent refresh replay permits only one claim/success;
20. native revocation works;
21. unbound client native compatibility is preserved;
22. Guest/disabled/deleted users fail safely;
23. stdio/trusted-header/REST behavior is unchanged;
24. `MCP_HTTP_AUTH_MODE=oauth` remains disabled at FastMCP startup;
25. no Frappe core modification exists;
26. no Task 05 feature was implemented;
27. test fixtures are cleaned;
28. final report contains exact commands/results and blockers.

If any lifecycle item fails, Task 05 remains blocked.

---

## 18. Expected Result

Expected fix conceptually:

```text
before:
hasattr(frappe.flags, key)
    -> misleading True
delattr(...)
    -> KeyError

after:
Frappe mapping-safe removal
    -> missing key: no-op
    -> existing key: removed
    -> idempotent
```

Then:

```text
real OAuth authorize
    -> wrapper starts
    -> binding cleanup succeeds
    -> native Frappe OAuth continues
    -> resource binding verified
```

And complete lifecycle:

```text
Authorize
  -> Code(resource)
  -> Token(resource)
  -> Refresh(resource)
  -> old pair Revoked
  -> Revoke
```

with replay protection proven.

---

## 19. Limitations

This task still does not:

- enable OAuth in the Streamable HTTP MCP resource server;
- add FastMCP `TokenVerifier`;
- expose RFC 9728 MCP protected-resource metadata;
- add MCP OAuth 401/403 challenges;
- connect ChatGPT;
- add DCR/CIMD;
- add external IdP support;
- change ERPNext permissions;
- change approval policy.

Those remain Task 05 or later.

---

## 20. Implementation / Verification Report

Create:

```text
mcp_identity/docs/inspect/
MCP_IDENTITY_TASK_04F_OAUTH_BINDING_FLAG_FIX_AND_04V_RERUN_REPORT.md
```

The report must include:

1. exact root cause;
2. exact production diff;
3. why the chosen deletion operation matches Frappe `_dict`;
4. tests added/changed;
5. test-fake correction;
6. site used;
7. migration/schema state;
8. hook/dispatch verification;
9. native bound authorization result;
10. invalid resource/PKCE result matrix;
11. authorization-code persisted binding proof;
12. token exchange proof;
13. sequential code replay result;
14. concurrent code replay result;
15. refresh lifecycle proof;
16. sequential refresh replay result;
17. concurrent refresh replay result;
18. revocation result;
19. unbound-client compatibility result;
20. identity/user validation results;
21. Task 03 regression results;
22. full suite results;
23. fixture cleanup;
24. deviations/limitations;
25. explicit Task 05 readiness verdict.

Do not report Task 05 ready unless every mandatory live lifecycle item passes.

---

## 21. Exact Next Task

If and only if the complete rerun passes:

**Task 05 - FastMCP OAuth Resource-Server Integration and E2E Verification**

If the rerun exposes another production defect:

- do not begin Task 05;
- identify the first failing production point;
- create the smallest correction task;
- preserve the approved architecture unless evidence proves the design itself is wrong.
