# MCP Identity Task 03 Auth-Mode Foundation Implementation Report

Implementation date: 2026-09-18

## 1. Result

Task 03 is implemented as an authentication-boundary refactor. Trusted-header
HTTP and stdio keep their external configuration contracts, transport now
selects the runtime path, and OAuth is recognized but fails closed before any
request identity is read.

No OAuth fields, DocTypes, hooks, patches, token verifier, protected-resource
metadata, Frappe core changes, or provider abstraction were added.

## 2. Files Changed

### `mcp_identity`

- `README.md`
- `docs/MCP_IDENTITY_V1_IMPLEMENTATION_TASK.md`
- `docs/inspect/MCP_IDENTITY_TASK_03_AUTH_MODE_FOUNDATION_IMPLEMENTATION_REPORT.md`
- `mcp_identity/identity.py`
- `mcp_identity/http.py`
- `mcp_identity/tests/test_identity.py`
- `mcp_identity/tests/test_http.py`

### `mcp_erpnext`

- `.env.example`
- `README.md`
- `docs/COMMANDS.md`
- `docs/LIBRECHAT_MCP_HTTP_SETUP.md`
- `mcp_erpnext/http_transport.py`
- `mcp_erpnext/runtime.py`
- `mcp_erpnext/settings.py`
- `mcp_erpnext/tests/test_http_transport.py`
- `mcp_erpnext/tests/test_identity.py`
- `mcp_erpnext/tests/test_rest_backend.py`
- `mcp_erpnext/tests/test_runtime.py`

The pre-existing untracked Task 02/03 and architecture-audit documents under
`docs/tasks/` and `docs/inspect/` were preserved.

## 3. Responsibility Boundary

Before this change, `mcp_erpnext.settings` read `MCP_FRAPPE_USER`,
`mcp_erpnext.runtime` treated missing HTTP headers as a stdio signal, and
`mcp_erpnext.http_transport` owned the trusted-header middleware class.

After this change:

- `mcp_identity` defines and validates `MCP_HTTP_AUTH_MODE`,
  `MCP_HTTP_SHARED_SECRET`, and `MCP_FRAPPE_USER` semantics;
- `mcp_identity` resolves enabled, non-Guest Frappe users and supplies the
  trusted-header middleware integration;
- `mcp_erpnext` still owns `MCP_TRANSPORT`, backend/site/profile settings,
  FastMCP/ASGI assembly, Frappe init/connect/destroy, `frappe.set_user()`, and
  all ERPNext operations and permissions.

## 4. HTTP Auth-Mode Contract

`MCP_HTTP_AUTH_MODE` accepts exact, case-sensitive values only:

- absent: defaults to `trusted_header`;
- `trusted_header`: requires `MCP_HTTP_SHARED_SECRET` with at least 32
  characters;
- `oauth`: recognized by the parser, then rejected with
  `MCPIdentityConfigurationError` because Frappe resource binding is not yet
  implemented;
- blank, whitespace variants, case variants, and unknown values: rejected.

Stdio returns from transport validation before any HTTP mode or secret is
validated.

## 5. Stdio Identity Flow

```text
MCP_TRANSPORT=stdio
  -> mcp_erpnext opens/reuses the configured Frappe site context
  -> mcp_identity validates MCP_FRAPPE_USER against User.name
  -> mcp_identity returns the canonical enabled, non-Guest User name
  -> mcp_erpnext calls frappe.set_user()
  -> the existing operation executes under native permissions
```

The resolver neither initializes Frappe nor calls `frappe.set_user()`.

## 6. Trusted-Header HTTP Flow

```text
MCP_TRANSPORT=streamable-http
  -> mcp_identity validates auth mode and secret at startup
  -> mcp_identity middleware validates Authorization with compare_digest
  -> runtime selects HTTP solely from MCP_TRANSPORT
  -> mcp_identity revalidates request secret and resolves X-MCP-User-Email
  -> mcp_erpnext applies the verified user with frappe.set_user()
  -> operation executes inside pre/finally Frappe cleanup
```

The two-stage secret validation and generic HTTP 401 response are preserved.
Logs contain neither the secret nor the submitted Authorization value.

## 7. Fail-Closed Proof

Focused tests prove that a Streamable HTTP process with no SDK request/header
context raises `MCPAuthenticationMissingError`; `_run_stdio_tool` is not called.
A separate regression proves a stdio process never calls HTTP identity
extraction. OAuth validation runs before request headers are inspected and does
not read the shared secret, `X-MCP-User-Email`, or `MCP_FRAPPE_USER`.

## 8. REST Semantics

The REST branch remains before local runtime identity selection, remains
stdio-only, and calls `ERPNextRestClient` using the existing API credentials.
A regression test supplies a local `MCP_FRAPPE_USER` and proves neither the
configured-user resolver nor the local stdio runtime is used.

## 9. Verification

Focused identity tests:

```bash
cd /home/frappe/frappe-bench/apps/mcp_identity
/home/frappe/frappe-bench/env/bin/python -m unittest \
  mcp_identity.tests.test_identity mcp_identity.tests.test_http
```

Result: 23 tests passed.

Focused consumer tests:

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

Full identity suite:

```bash
cd /home/frappe/frappe-bench/apps/mcp_identity
/home/frappe/frappe-bench/env/bin/python -m unittest discover \
  -s mcp_identity/tests -p 'test_*.py'
```

Result: 23 tests passed.

Full consumer suite:

```bash
cd /home/frappe/frappe-bench/apps/mcp_erpnext
/home/frappe/frappe-bench/env/bin/python -m unittest discover \
  -s mcp_erpnext/tests -p 'test_*.py'
```

Result: 383 tests ran; 378 passed and five unrelated approval-policy assertions
failed. The failures are in existing Customer, Item, Purchase Order, Quotation,
and Email confirmation tests expecting `TRUSTED_APPROVAL_UNAVAILABLE` under a
current default that is `agent_delegated` (the Email test instead observed an
existing `PROFILE_MISMATCH`). The Customer and Email failures reproduce when
each test is run alone. No approval production or test file is changed by this
task.

Static verification:

```bash
cd /home/frappe/frappe-bench
/home/frappe/frappe-bench/env/bin/python -m compileall -q \
  apps/mcp_identity/mcp_identity apps/mcp_erpnext/mcp_erpnext
git -C apps/mcp_identity diff --check
git -C apps/mcp_erpnext diff --check
```

Result: passed. Ruff was not run because the Bench virtual environment does not
have the `ruff` module installed.

No live HTTP, stdio protocol, database-writing, migration, or OAuth test was
run; none is required for Task 03.

## 10. Backward Compatibility and Deviations

- `MCP_FRAPPE_USER`, `MCP_HTTP_SHARED_SECRET`, and `X-MCP-User-Email` are
  unchanged.
- Stdio remains the default transport.
- Missing `MCP_HTTP_AUTH_MODE` preserves trusted-header deployments.
- HTTP still returns a generic 401 for bad/missing Bearer credentials.
- REST API-principal semantics are unchanged.
- A small `mcp_identity.http` module was used so importing stdio identity logic
  does not import Starlette. This is the smallest separation that moves the
  existing middleware without creating a generic authentication framework.
- No requested architecture deviation remains.

## 11. Next Task Readiness

The identity/auth-mode foundation is ready for Task 04, Frappe OAuth
Resource-Binding Compatibility Implementation. Task 04 must still add the
approved resource persistence and fail-closed validator compatibility before
OAuth can be enabled. The five unrelated approval-test expectation failures
should be reconciled separately; they do not block the Task 04 identity
boundary.
