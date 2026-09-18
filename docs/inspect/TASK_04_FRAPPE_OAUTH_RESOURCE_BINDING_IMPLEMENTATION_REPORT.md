# MCP Identity Task 04 Frappe OAuth Resource-Binding Implementation Report

Implementation date: 2026-09-18

## 1. Result and repository context

Task 04 is implemented in `mcp_identity` as a compatibility extension of the
installed Frappe OAuth authorization server. It does not expose OAuth through
FastMCP.

The inspected checkout was:

- `mcp_identity`: branch `main`, base commit
  `5cc9fcbb49d0704bf0b7fb48a82a315e0d426246`, with the uncommitted Task 03
  implementation and task/report documents preserved;
- `mcp_erpnext`: branch `master`, base commit
  `12ef04ea69280b79b2849dda574d1290a613ade2`, with the existing Task 03
  changes preserved and no Task 04 production edit;
- Frappe: branch `version-16`, commit
  `c1f1e8ec3708750d7254f7f99d869ffb9886f19f`, source version `16.34.0`;
- oauthlib: installed version `3.3.1`;
- Python: Bench environment Python `3.14`.

## 2. Files changed by Task 04

- `README.md`
- `docs/inspect/MCP_IDENTITY_TASK_04_FRAPPE_OAUTH_RESOURCE_BINDING_IMPLEMENTATION_REPORT.md`
- `mcp_identity/hooks.py`
- `mcp_identity/identity.py` (startup failure text only; OAuth remains disabled)
- `mcp_identity/oauth_compat.py`
- `mcp_identity/resource.py`
- `mcp_identity/patches.txt`
- `mcp_identity/patches/v1_0/__init__.py`
- `mcp_identity/patches/v1_0/add_oauth_resource_binding_fields.py`
- `mcp_identity/tests/test_oauth_compat.py`
- `mcp_identity/tests/test_oauth_patch.py`
- `mcp_identity/tests/test_oauth_replay_integration.py`
- `mcp_identity/tests/test_resource.py`

No Frappe core, ERPNext business, approval, REST, or `mcp_erpnext` production
file was changed by Task 04.

## 3. Schema and migration

The post-model-sync patch calls Frappe's native
`create_custom_fields(CUSTOM_FIELDS, update=True)` helper. It defines exactly:

- `OAuth Client.custom_mcp_resource`: optional `Small Text`, after `scopes`;
- `OAuth Authorization Code.custom_mcp_resource`: optional hidden, read-only,
  no-copy, print-hidden and report-hidden `Small Text`, after `scopes`;
- `OAuth Bearer Token.custom_mcp_resource`: the same protected metadata as the
  authorization-code field.

No field is required, unique, or indexed. There is no new DocType, sidecar
table, token hash, or duplicate authorization/access/refresh secret. The patch
does not query or backfill existing records and is idempotent through the
native helper's update behavior.

The patch was not executed against a site and `bench migrate` was not run. A
site becomes an OAuth Authorization Server for this compatibility layer only
after `mcp_identity` is installed there and migrated.

## 4. Canonical resource behavior

`canonicalize_mcp_resource()` is the single implementation used for OAuth
Client validation, request resources, and persisted bindings. It requires an
absolute HTTP(S) URL, rejects credentials/query/fragment/controls, applies IDNA
and lowercase host normalization, canonicalizes IP literals, removes default
ports, preserves non-default ports and path case, uppercases percent escapes,
rejects invalid escapes/dot segments/repeated slashes/backslash aliases, and
applies one trailing-slash policy. HTTPS is mandatory except when the caller
explicitly enables loopback-only HTTP for tests/development. Domain aliases
remain distinct. Request processing never derives a resource from Host or
forwarding headers and rejects duplicate `resource` parameters.

The OAuth Client validation event permits blank bindings, canonicalizes a
nonblank binding, and rejects invalid values. Existing records are not
auto-populated.

## 5. Native extension points and dispatch-bypass analysis

The implementation subclasses the installed
`frappe.oauth.OAuthWebRequestValidator` and overrides only:

- `validate_scopes()` for authorization-request resource and S256 checks;
- `validate_code()` for locked authorization-code binding checks;
- `validate_refresh_token()` for locked refresh source/client/resource/user
  checks.

Native scope, client, role, redirect, PKCE verifier, user/scopes restoration,
token generation, expiry, revocation, cleanup, login, consent, and endpoint
response handling remain in Frappe/oauthlib.

Frappe 16.34.0 runs `before_request` before v1 assigns `form_dict.cmd`, while
v2 resolves its method in a separate dispatcher. A raw-path hook would
therefore be a bypass risk. Task 04 uses the authoritative
`override_whitelisted_methods` resolution point instead. Thin wrappers cover
`authorize`, `approve`, `get_token`, and `revoke_token`, install a fresh
`frappe.local.oauth_server`, then immediately delegate to the original native
function. This covers:

- deprecated root RPC requests carrying `cmd` through
  `frappe.handler.execute_cmd()`;
- `/api/method/<method>` through v1 and the same handler;
- `/api/v2/method/<method>` through v2's own override resolution.

The validator and binding flags exist only on `frappe.local`/`frappe.flags`.
There is no process-global active validator or grant state. Focused source
compatibility tests assert that all three installed dispatchers still traverse
the override seam.

## 6. Authorization and code persistence

For an unbound client, `validate_scopes()` returns the native result and adds
no state. For a bound client, native scope validation succeeds first, then the
compatibility validator requires exactly one canonical resource equal to the
client binding plus a non-empty S256 challenge. Every authorization/approval
continuation re-enters the same native endpoint wrapper and revalidates the
request.

The `OAuth Authorization Code.before_insert` event accepts only matching
request-local authorization state and copies its canonical resource. If a
bound client reaches code insertion without that state, insertion fails. It
never reconstructs a binding from request headers.

## 7. Code exchange and atomic consumption

For a bound code, `validate_code()` selects the still-Valid code for the
authenticated client with `for_update=True`, checks an optional populated
expiry, enabled non-Guest user, persisted resource, current client binding,
one matching request resource, stored S256 challenge, and non-empty verifier.
It then delegates the native code/PKCE/user/scope validation and records only
the source record name, client, grant kind, and canonical resource in
request-local state.

`OAuth Bearer Token.before_insert` rechecks the locked Valid source, copies the
resource, and changes the code to Invalid. Frappe's native `save_bearer_token()`
then inserts the token and commits both changes together. The later native
invalidation remains idempotent. A competing transaction blocks on the source
row and, after the winner commits, cannot select it as Valid.

## 8. Refresh and atomic rotation

The bound refresh path selects the Active bearer-token source with
`for_update=True`. It requires the authenticated client to equal the source
client, source/client resource parity, exactly one matching request resource,
and an existing enabled non-Guest native token user. Native refresh validation
and scope restoration remain in Frappe/oauthlib.

Before replacement insertion, the bearer-token event rechecks the Active
locked source, copies the exact resource, and marks the old access/refresh pair
Revoked. Native insertion commits replacement and revocation together.
Sequential reuse therefore fails and concurrent reuse serializes on the row.
Resource switching is not supported.

Native revocation and cleanup remain authoritative because the binding is on
the native bearer-token row. There is no sidecar cleanup path.

## 9. Backward compatibility and identity boundaries

- Blank OAuth Clients/codes/tokens retain native behavior and receive no
  inferred binding.
- Existing records remain blank; they are not MCP tokens.
- The OAuth token owner remains the native Frappe `User`; bound grant/refresh
  checks reject missing, disabled, or Guest users.
- No email header, `MCP_FRAPPE_USER`, or caller-supplied identity participates
  in OAuth issuance.
- Task 03 stdio and trusted-header code paths are unchanged.
- `MCP_HTTP_AUTH_MODE=oauth` still fails at MCP server startup. The error now
  explicitly says that authorization-server resource binding alone is
  insufficient until Task 05 implements FastMCP verification.

## 10. Verification

Identity unit/source-compatibility suite:

```bash
cd /home/frappe/frappe-bench/apps/mcp_identity
/home/frappe/frappe-bench/env/bin/python -m unittest discover \
  -s mcp_identity/tests -p 'test_*.py'
```

Result at implementation time: 53 tests ran, 51 passed and two explicitly
operator-gated database concurrency tests were skipped.

Focused Task 03 consumer regression suite:

```bash
cd /home/frappe/frappe-bench/apps/mcp_erpnext
/home/frappe/frappe-bench/env/bin/python -m unittest \
  mcp_erpnext.tests.test_identity \
  mcp_erpnext.tests.test_http_transport \
  mcp_erpnext.tests.test_runtime \
  mcp_erpnext.tests.test_rest_backend
```

Result: 51 tests passed. The installed MCP/Pydantic stack emitted its existing
`IncompleteFieldDefinitionWarning`; it did not fail the suite.

Full consumer suite:

```bash
cd /home/frappe/frappe-bench/apps/mcp_erpnext
/home/frappe/frappe-bench/env/bin/python -m unittest discover \
  -s mcp_erpnext/tests -p 'test_*.py'
```

Result: 385 tests ran; 380 passed and the same five unrelated approval-policy
expectation tests identified in Task 03 failed. Customer, Item, Purchase Order,
and Quotation tests expected `TRUSTED_APPROVAL_UNAVAILABLE` under the current
`agent_delegated` default and raised `KeyError` while reading a missing `code`;
the Email test expected that code and received the pre-existing
`PROFILE_MISMATCH`. Task 04 changed none of those services or tests.

Static verification:

```bash
cd /home/frappe/frappe-bench
/home/frappe/frappe-bench/env/bin/python -m compileall -q \
  apps/mcp_identity/mcp_identity apps/mcp_erpnext/mcp_erpnext
git -C apps/mcp_identity diff --check
git -C apps/mcp_erpnext diff --check
```

Result: passed. Ruff was not run because the Bench environment reports
`No module named ruff`; no dependency was installed for this task.

## 11. Operator-gated replay proof

`test_oauth_replay_integration.py` contains two-connection row-lock tests for
authorization-code consumption and refresh-token rotation. They require an
isolated, installed, migrated test site and the explicit
`MCP_IDENTITY_RUN_OAUTH_DB_TESTS=1` gate. They were implemented but not run,
because this task did not authorize migration or database writes on a shared
site. Unit tests prove the exact `for_update=True` lookups, request-local state,
conditional source rechecks, and pre-insert state changes, but do not by
themselves prove live database blocking.

No live OAuth request, OAuth record creation, HTTP server, ChatGPT connection,
MCP Inspector flow, site migration, or service restart was performed.

## 12. Deviations and remaining limitations

The approved design expected a `before_request` hook. Installed dispatch
ordering makes that hook unable to identify every resolved method safely, so
the implementation uses Frappe's authoritative whitelisted-method override
seam with no copied endpoint logic. This is the smallest native-compatible
adjustment and closes the v1/v2/legacy route bypass identified during source
inspection.

Frappe's native code validator does not visibly enforce a populated
authorization-code expiry in this installed source. For bound codes only, the
compatibility check rejects an expired value when the native field is
populated, while leaving native blank-field behavior compatible.

Live schema, transaction, multi-worker, login/consent, token issuance,
revocation, and upgrade behavior remain unverified until the operator-gated
tests and an approved isolated-site flow are run. DCR/CIMD clients remain
unbound and unsupported for MCP. Task 04 adds no protected-resource metadata,
FastMCP `TokenVerifier`, challenge handling, bearer verification, or scope
enforcement at the MCP resource server.

## 13. Task 05 readiness

The authorization-server source and focused tests are ready for Task 05 after
an operator applies the patch and runs the gated database/OAuth integration
proof on an isolated site. Task 05 must independently verify opaque native
bearer records against exact client/resource/scopes/status/expiry/user state,
wire FastMCP auth metadata and challenges, and prove end-to-end OAuth without
changing the preserved stdio, trusted-header, permissions, or approval paths.
