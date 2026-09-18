# MCP Identity Task 04V Frappe OAuth Resource-Binding Live Verification Report

Verification date: 2026-09-18

## Verdict

**BLOCKED. Task 05 must not begin.**

Migration, schema metadata, hook registration, canonicalization tests, and both
mandatory two-connection row-lock tests passed on the local test site. The
first real native OAuth RPC request exposed a Task 04 production defect before
authorization could run:

```text
install_mcp_oauth_validator_for_request()
  -> _clear_binding()
  -> hasattr(frappe.flags, "mcp_oauth_resource_binding") is true
  -> delattr(frappe.flags, "mcp_oauth_resource_binding")
  -> KeyError: 'mcp_oauth_resource_binding'
  -> HTTP 500
```

`frappe.flags` is backed by Frappe's `_dict` behavior, for which a missing
attribute reads as `None` rather than raising `AttributeError`. The
`hasattr()` guard in `mcp_identity/oauth_compat.py` therefore does not prove
that the key exists. This blocks every wrapped OAuth endpoint at fresh-request
startup and prevents the required authorization, exchange, refresh, and
revocation lifecycle proof.

Per Task 04V's engineering rule, production code was not fixed in this
verification task.

## Confirmed context

### Site selection and safety boundary

- Bench: `/home/frappe/frappe-bench`.
- Selected site: `yob.localhost`.
- Selection basis: it is the existing local MCP runtime site referenced by the
  current project documentation, already had `mcp_erpnext` and `mcp_identity`
  installed, uses a `.localhost` name, and the operator explicitly authorized
  this environment for local test writes.
- Database: MariaDB `10.11.14-MariaDB-0ubuntu0.24.04.1`.
- `allow_tests` was absent/false before testing. It was temporarily enabled for
  the gated Frappe test runner and restored to `false` afterward.

No secret value, OAuth code, access token, refresh token, password, database
password, or encryption key is included in this report.

### Repository and runtime versions

| Component | Branch / commit | Runtime/source version |
| --- | --- | --- |
| `mcp_identity` | `main` / `5cc9fcbb49d0704bf0b7fb48a82a315e0d426246` | `0.0.1` |
| `mcp_erpnext` | `master` / `12ef04ea69280b79b2849dda574d1290a613ade2` | `0.0.1` |
| Frappe | `version-16` / `c1f1e8ec3708750d7254f7f99d869ffb9886f19f` | `16.34.0` |
| ERPNext | `version-16` / `12cd563fb9a79731f75ae2a45b1446a0a2dd9e74` | `16.35.0` |
| oauthlib | installed package | `3.3.1` |
| Python MCP SDK | installed package | `1.29.0` |
| Python | Bench environment | `3.14.3` |

The Python distribution metadata reported older Frappe/ERPNext package
versions (`16.25.0` / `16.15.0`), while the site-aware `bench list-apps` result
and inspected source reported `16.34.0` / `16.35.0`. This report uses the
site-aware installed-app/source versions as authoritative for the tested site.

### Initial installed-app and OAuth state

`mcp_identity` was already installed; no `install-app` command was needed. The
site reported these installed applications:

```text
frappe 16.34.0
yob_core 0.0.1
yob_auth 0.1.0
erpnext 16.35.0
payments 0.0.1
india_compliance 16.9.0
yob_storefront 0.0.1
mcp_erpnext 0.0.1
mcp_identity 0.0.1
```

Before migration:

- none of the three `custom_mcp_resource` Custom Fields existed;
- one pre-existing `MCP Local Chatbot Demo` OAuth Client existed and was not
  modified;
- OAuth metadata endpoints and dynamic client registration were enabled in
  OAuth Settings; global skip-authorization was disabled;
- the Task 04 patch had not yet been applied to the site.

## Migration and schema verification

Executed twice:

```bash
./env/bin/bench --site yob.localhost migrate
```

Both migrations exited successfully. The first run executed:

```text
mcp_identity.patches.v1_0.add_oauth_resource_binding_fields
Success
```

The second migration completed without rerunning or duplicating the patch. A
post-migration query found one Patch Log row and exactly these three fields:

| DocType | Type | Required | Hidden | Read only | No copy | Print hidden | Report hidden | Insert after |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| OAuth Client | Small Text | 0 | 0 | 0 | 0 | 0 | 0 | scopes |
| OAuth Authorization Code | Small Text | 0 | 1 | 1 | 1 | 1 | 1 | scopes |
| OAuth Bearer Token | Small Text | 0 | 1 | 1 | 1 | 1 | 1 | scopes |

No DocType owned by the `MCP Identity` module exists. No sidecar/duplicate
token table was added. Existing OAuth Clients retained a blank resource; the
patch did not backfill them.

## Hook and dispatch verification

The live site hook registry resolved all four Task 04 overrides:

```text
frappe.integrations.oauth2.authorize    -> mcp_identity.oauth_compat.authorize
frappe.integrations.oauth2.approve      -> mcp_identity.oauth_compat.approve
frappe.integrations.oauth2.get_token    -> mcp_identity.oauth_compat.get_token
frappe.integrations.oauth2.revoke_token -> mcp_identity.oauth_compat.revoke_token
```

The test-only integration harness executed the bound authorization request by
all supported installed dispatch forms:

```text
legacy root cmd dispatch
/api/method/frappe.integrations.oauth2.authorize
/api/v2/method/frappe.integrations.oauth2.authorize
```

All three reached `mcp_identity.oauth_compat.authorize` and failed at the same
`_clear_binding()` line. This proves the override is active and no tested
dispatcher bypassed it, but also proves the wrapper is currently unusable.

## Canonical resource verification

The current `mcp_identity` suite passed its canonical resource cases. The
coverage confirms:

- HTTPS acceptance and scheme/host normalization;
- default-port removal and non-default-port preservation;
- path-case preservation and one trailing-slash policy;
- rejection of query, fragment, userinfo, dot segments, repeated slashes,
  malformed percent escapes, invalid hosts, and non-loopback HTTP;
- distinct domain aliases;
- duplicate request-resource rejection in the compatibility tests;
- no Host or Forwarded-header resource inference in production code.

The ordinary suite command and result were:

```bash
cd /home/frappe/frappe-bench/apps/mcp_identity
/home/frappe/frappe-bench/env/bin/python -m unittest discover \
  -s mcp_identity/tests -p 'test_*.py'
```

```text
Ran 58 tests
OK (skipped=7)
```

The seven skips are the operator-gated DB modules when the explicit gate is
not set.

## Mandatory database replay verification

After temporarily setting `allow_tests=true`, the corrected operator-gated
suite was executed with:

```bash
MCP_IDENTITY_RUN_OAUTH_DB_TESTS=1 \
  ./env/bin/bench --site yob.localhost run-tests \
  --app mcp_identity \
  --module mcp_identity.tests.test_oauth_replay_integration
```

Result:

```text
test_authorization_code_lock_serializes_replay PASS
test_refresh_token_lock_serializes_replay      PASS
Ran 2 tests in 0.817s
OK
```

Each test uses two independent `frappe.init()` / `frappe.connect()` database
contexts. The first transaction selects the still-active source with
`for_update=True`, the assertion confirms the second transaction has not
finished after 0.2 seconds, the first transaction consumes and commits, and
the second then reads no eligible row. The final assertion is exactly:

```text
{"first": source_name, "second": None}
```

This proves MariaDB row blocking/serialization at the source-claim boundary.
It does not rescue the blocked HTTP lifecycle because token issuance never
gets past `_clear_binding()`.

## OAuth lifecycle and identity results

### Proven

- A real bound OAuth Client can be inserted and its canonical resource is
  persisted by the Task 04 validation hook.
- The active hook registry and all three RPC dispatch paths invoke the Task 04
  wrapper.
- The two-connection code and refresh source-claim boundaries serialize and
  permit only one successful claim.
- A separate DB-backed test passed for Guest and missing/deleted token owners:
  `validate_refresh_token()` returned false for both against real native bearer
  rows and a real bound client.
- The unit suite continues to prove disabled-user rejection and the absence of
  `X-MCP-User-Email` / `MCP_FRAPPE_USER` in OAuth issuance code.

### Blocked / not proven

Because the first fresh OAuth request returns HTTP 500, Task 04V could not
prove any of the following end-to-end requirements:

- bound authorization-code creation through native authorize/consent;
- missing/wrong/duplicate resource and S256 errors as standards-safe OAuth
  responses rather than server errors;
- persisted code user/scope/resource continuity;
- native PKCE verifier execution;
- code-to-bearer resource preservation and atomic insertion;
- sequential code replay failure through the real token endpoint;
- refresh-to-replacement user/client/scope/resource continuity;
- atomic source revocation plus replacement insertion;
- sequential old-refresh rejection through the real token endpoint;
- native revocation through the wrapped endpoint;
- unbound-client native endpoint compatibility.

No raw OAuth secrets were emitted while attempting these tests.

## Root cause and smallest fix task

The first incorrect point is:

```python
def _clear_binding() -> None:
    if hasattr(frappe.flags, _BINDING_FLAG):
        delattr(frappe.flags, _BINDING_FLAG)
```

The unit test uses a `SimpleNamespace` fake, whose missing-attribute semantics
differ from live `frappe.flags`; that is why source/unit verification did not
catch the defect.

The next task should make a narrowly scoped Task 04 production fix using
Frappe `_dict`-compatible deletion semantics (for example, a key-based
`pop(..., None)` after confirming the installed API), update the unit fake or
add a real `frappe._dict` regression, and rerun this entire 04V verification.
The fix must not change OAuth design, token storage, route ownership, or begin
Task 05.

## Regression results

### Task 03 focused `mcp_erpnext` consumer suite

```bash
cd /home/frappe/frappe-bench/apps/mcp_erpnext
/home/frappe/frappe-bench/env/bin/python -m unittest \
  mcp_erpnext.tests.test_identity \
  mcp_erpnext.tests.test_http_transport \
  mcp_erpnext.tests.test_runtime \
  mcp_erpnext.tests.test_rest_backend
```

Result: 51 tests passed. The existing Pydantic
`IncompleteFieldDefinitionWarning` was emitted and did not fail the suite.

### Full `mcp_erpnext` suite

```bash
cd /home/frappe/frappe-bench/apps/mcp_erpnext
/home/frappe/frappe-bench/env/bin/python -m unittest discover \
  -s mcp_erpnext/tests -p 'test_*.py'
```

Result: 385 tests ran; 380 passed, with the same five previously documented
unrelated approval-policy expectation failures:

- Customer, Item, Purchase Order, and Quotation tests raised `KeyError` while
  expecting `TRUSTED_APPROVAL_UNAVAILABLE` under the current
  `agent_delegated` default;
- the Email test received the existing `PROFILE_MISMATCH` instead of that
  expected code.

The count and failure types did not change from the Task 04 baseline.

## Static and repository verification

These checks passed:

```bash
/home/frappe/frappe-bench/env/bin/python -m compileall -q \
  apps/mcp_identity/mcp_identity apps/mcp_erpnext/mcp_erpnext
git -C apps/mcp_identity diff --check
git -C apps/mcp_erpnext diff --check
```

No tracked Frappe or ERPNext core file changed. Frappe had two pre-existing
untracked paths with timestamps from July/August 2026
(`frappe/locale/test.po` and `frappe/twilio_whatsapp_notification/`); this task
did not edit or remove them. No FastMCP `TokenVerifier`, protected-resource
challenge, `MCP_HTTP_AUTH_MODE=oauth` enablement, or ChatGPT integration was
added. OAuth mode remains fail-closed at MCP server startup.

## Test-only repository changes

- Added `mcp_identity/tests/test_oauth_live_integration.py` as a gated
  reproducer/lifecycle harness.
- Corrected `mcp_identity/tests/test_oauth_replay_integration.py` to retain the
  actual Frappe-autonamed OAuth Client name so future teardown deletes the
  fixture it inserted.

No production source file was changed by Task 04V.

## Cleanup and remaining records

An early version of both test harnesses assumed Frappe would preserve a
requested OAuth Client name. Frappe autonamed the records, so teardown removed
their codes/tokens but initially left 12 clearly labelled test clients. The
harnesses were corrected, and the cleanup helper removed exactly:

- 10 `MCP Task 04V live verification` OAuth Clients;
- 2 `MCP replay lock integration test` OAuth Clients.

Post-cleanup queries found no test-labelled OAuth Client or child-role rows.
The corrected replay suite also cleaned its final fixtures. No disposable
authorization codes, bearer tokens, test users, or active tokens remain.

The three Task 04 Custom Fields and Patch Log row intentionally remain. The
pre-existing `MCP Local Chatbot Demo` and `LibreChat Local Docker` OAuth
Clients remain unmodified with blank MCP resource bindings. Site
`allow_tests` is `false`.

## Final Task 05 readiness

**Not ready.** Task 05 is blocked until the `_clear_binding()` production
defect is fixed in a separate authorized Task 04 correction and this live
verification is rerun to completion. Passing migration and row-lock tests are
necessary evidence, but they are not sufficient while all wrapped OAuth RPC
requests fail before native OAuth processing begins.

