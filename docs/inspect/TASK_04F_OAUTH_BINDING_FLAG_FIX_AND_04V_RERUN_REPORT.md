# MCP Identity Task 04F OAuth Binding Flag Fix and Task 04V Rerun Report

Verification date: 2026-09-18

## Verdict

**PASS. Task 05 may begin.**

The request-local binding cleanup defect is fixed, the complete native OAuth
resource-binding lifecycle passes on `yob.localhost`, both two-connection replay
tests pass, and disposable live fixtures were removed. The existing unrelated
`mcp_erpnext` approval-policy baseline remains unchanged.

## Context and scope

- Bench: `/home/frappe/frappe-bench`.
- Site: `yob.localhost`, local/testing-only.
- Runtime: Frappe `16.34.0`, ERPNext `16.35.0`, oauthlib `3.3.1`, Python MCP
  SDK `1.29.0`.
- Only `mcp_identity` changed for this task; no `mcp_erpnext` production change,
  Frappe core change, schema redesign, or Task 05 feature was added.

## Root cause and production fix

The old cleanup used `hasattr(frappe.flags, key)` followed by `delattr`. The
installed Frappe `_dict` is a `dict` subclass with `__getattr__ = dict.get` and
`__delattr__ = dict.__delitem__`. A missing key therefore reads as `None`, but
`hasattr` returns true and `delattr` raises `KeyError`.

The exact production change in `mcp_identity/oauth_compat.py` is:

```diff
 def _clear_binding() -> None:
-    if hasattr(frappe.flags, _BINDING_FLAG):
-        delattr(frappe.flags, _BINDING_FLAG)
+    frappe.flags.pop(_BINDING_FLAG, None)
```

`pop(key, None)` uses the mapping API supported by the installed Frappe
`_dict`, is a no-op for an absent key, removes an existing key, and preserves
unrelated request-local flags. No process-global state or new abstraction was
introduced.

## Tests and test-fake correction

`mcp_identity/tests/test_oauth_compat.py` now uses real Frappe `_dict` for the
flags fake instead of `SimpleNamespace`. It covers missing-key cleanup,
idempotence, existing-state removal, unrelated-flag preservation, stale-state
removal at wrapper initialization, and all four wrappers: `authorize`,
`approve`, `get_token`, and `revoke_token`.

`mcp_identity/tests/test_oauth_live_integration.py` commits the parent test
connection after threaded RPC calls so MariaDB's transaction snapshot does not
hide records committed by the request connection. This is test-harness-only;
OAuth production behavior is unchanged.

## Migration and schema

Commands:

```bash
./env/bin/bench --site yob.localhost migrate
./env/bin/bench --site yob.localhost migrate
```

Both completed successfully. The patch log contains exactly one
`mcp_identity.patches.v1_0.add_oauth_resource_binding_fields` row. The three
approved `custom_mcp_resource` fields exist exactly once with the expected
`Small Text` type and flags; no sidecar DocType exists. Existing unbound OAuth
Clients remain unbound.

## Complete live 04V results

Command:

```bash
MCP_IDENTITY_RUN_OAUTH_DB_TESTS=1 \
  ./env/bin/bench --site yob.localhost run-tests \
  --app mcp_identity \
  --module mcp_identity.tests.test_oauth_live_integration
```

Result: **5/5 passed**.

The live suite proved:

- all legacy, v1, and v2 supported RPC dispatch forms reach the override;
- bound authorization succeeds with the canonical resource and S256 PKCE;
- missing, wrong, malformed, duplicate, and non-S256 resource/PKCE inputs fail
  with safe OAuth errors;
- authorization-code user, client, scopes, PKCE, and resource persist correctly;
- token exchange preserves identity/client/scopes/resource and invalidates the
  code atomically;
- sequential code replay fails;
- refresh rotation preserves identity/client/scopes/resource and revokes the
  old access/refresh pair;
- sequential refresh replay fails;
- wrapped native revocation works;
- blank-resource clients retain native Frappe OAuth behavior;
- Guest and missing/deleted token users fail closed.

Mandatory concurrency command:

```bash
MCP_IDENTITY_RUN_OAUTH_DB_TESTS=1 \
  ./env/bin/bench --site yob.localhost run-tests \
  --app mcp_identity \
  --module mcp_identity.tests.test_oauth_replay_integration
```

Result: **2/2 passed**: authorization-code replay serialization and
refresh-token replay serialization. Each proves exactly one claim succeeds
across two database connections.

## Regression and static verification

```bash
cd /home/frappe/frappe-bench/apps/mcp_identity
/home/frappe/frappe-bench/env/bin/python -m unittest discover \
  -s mcp_identity/tests -p 'test_*.py'
```

Result: **60 passed**, 7 expected operator-gated skips.

```bash
cd /home/frappe/frappe-bench/apps/mcp_erpnext
/home/frappe/frappe-bench/env/bin/python -m unittest \
  mcp_erpnext.tests.test_identity \
  mcp_erpnext.tests.test_http_transport \
  mcp_erpnext.tests.test_runtime \
  mcp_erpnext.tests.test_rest_backend
```

Result: **51 passed**. The existing Pydantic warning did not fail the suite.

The full consumer suite ran 385 tests: 380 passed, with the same four
approval-policy `KeyError` errors and one `PROFILE_MISMATCH` failure documented
by Task 03. No approval, identity, REST, or OAuth behavior was changed here.

Compile and whitespace checks passed:

```bash
/home/frappe/frappe-bench/env/bin/python -m compileall -q \
  apps/mcp_identity/mcp_identity apps/mcp_erpnext/mcp_erpnext
git -C apps/mcp_identity diff --check
git -C apps/mcp_erpnext diff --check
```

The site setting `allow_tests` was restored to `false` after verification.
Disposable OAuth Clients, codes, and bearer tokens were cleaned; unrelated
OAuth Clients, users, Custom Fields, and the Patch Log were preserved.

## Boundaries and readiness

`MCP_HTTP_AUTH_MODE=oauth` remains disabled at FastMCP startup. No FastMCP
`TokenVerifier`, protected-resource metadata, OAuth challenge handling, DCR,
CIMD, ChatGPT integration, or external IdP work was added. Those remain Task 05
scope. Since every mandatory Task 04V lifecycle and replay item passed, Task 05
is unblocked.
