# MCP ERPNext Architecture & Mental Model

![MCP ERPNext Architecture & Mental Model](./mcp-erpnext-architecture-mental-model.png)

## Purpose

This directory contains the shared architecture and mental-model visualization for the MCP integration built around:

* `mcp_identity`
* `mcp_erpnext`
* Frappe Framework
* ERPNext
* MCP clients and transports

The diagram is intended to provide a high-level visual explanation of how an MCP request moves from a client through authentication, identity resolution, MCP tool execution, Frappe runtime context, service orchestration, and finally into native ERPNext business operations.

The same diagram is intentionally maintained in both the `mcp_identity` and `mcp_erpnext` repositories so that either repository can be understood independently.

---

## Source of Truth

The diagram is **documentation**, not the authoritative implementation specification.

The current application source code is the final source of truth.

If there is ever a difference between this diagram, another architecture document, and the current implementation, the current implementation must be inspected and treated as authoritative.

The diagram should then be updated to match the implementation.

---

## Application Responsibilities

### `mcp_identity`

`mcp_identity` owns the trust and execution-identity boundary.

Its responsibilities include:

* HTTP authentication mode selection
* Trusted-header authentication
* Bearer secret validation
* OAuth resource-server integration
* OAuth token verification
* Frappe user resolution
* STDIO execution-user resolution through `MCP_FRAPPE_USER`
* Validation that the resolved Frappe user exists and is enabled

`mcp_identity` does **not** own ERPNext business tools or ERPNext business rules.

---

### `mcp_erpnext`

`mcp_erpnext` owns the MCP and ERPNext business-execution boundary.

Its responsibilities include:

* FastMCP server execution
* STDIO transport
* Streamable HTTP transport
* MCP profile selection
* Tool registration and exposure
* Direct and REST backend routing
* Frappe runtime lifecycle
* MCP tool contracts
* Business service orchestration
* Read/query capabilities
* Approval workflows
* ERPNext transaction capabilities

Final business permissions, document validation, controller behavior, accounting rules, and transaction rules remain the responsibility of native Frappe and ERPNext.

---

## High-Level Mental Model

The intended mental model is:

```text
MCP Client
    ↓
Transport
    ↓
Identity / Authentication
    ↓
MCP Profile + Tool
    ↓
Execution Runtime / Backend
    ↓
Service Layer
    ↓
Native Frappe / ERPNext
```

In simple terms:

> The client says what it wants.
> `mcp_identity` establishes who is acting.
> `mcp_erpnext` controls which MCP capability may execute.
> Frappe establishes the execution context.
> The service layer orchestrates the operation.
> Native ERPNext remains the final authority for permissions and business behavior.

---

## Runtime Paths Represented in the Diagram

The diagram currently represents the following implemented runtime models.

### Direct Backend + STDIO

```text
MCP Client
    ↓
mcp_erpnext
    ↓
mcp_identity
    ↓
MCP_FRAPPE_USER
    ↓
Frappe Runtime
    ↓
ERPNext
```

The configured STDIO execution user is resolved and validated through `mcp_identity`.

---

### Direct Backend + Streamable HTTP + Trusted Header

```text
MCP Client
    ↓
Bearer Secret + User Email
    ↓
mcp_identity
    ↓
Resolved Frappe User
    ↓
mcp_erpnext
    ↓
Scoped Frappe Runtime
    ↓
ERPNext
```

Each request establishes its own execution identity.

An HTTP request must not silently fall back to the process-level STDIO service user when request identity is missing or invalid.

---

### Direct Backend + Streamable HTTP + OAuth

```text
User / MCP Client
    ↓
Frappe OAuth
    ↓
mcp_identity OAuth Resource Server
    ↓
Verified OAuth Subject
    ↓
mcp_erpnext
    ↓
Frappe Runtime
    ↓
ERPNext
```

The verified OAuth token subject becomes the Frappe execution identity.

---

### REST Backend + STDIO

```text
MCP Client
    ↓
mcp_erpnext
    ↓
REST Backend Router
    ↓
ERPNext REST Client
    ↓
Remote mcp_erpnext API
    ↓
Registered MCP Operation
    ↓
Remote ERPNext
```

The remote Frappe API-token owner is the execution principal for this path.

The REST bridge uses controlled, registered MCP operations rather than arbitrary Python method or CRUD dispatch.

---

## MCP Profiles

`mcp_erpnext` follows a profile-based tool exposure model.

A server process exposes the tools belonging to its configured profile.

Current profile concepts include:

* Sales
* Purchase
* Accounts

Profiles control MCP capability exposure. They do not replace native Frappe or ERPNext permissions.

---

## Persistent Write Model

Persistent business writes generally follow a controlled lifecycle such as:

```text
Resolve / Validate
        ↓
Prepare
        ↓
Store Approval State
        ↓
Return Preview
        ↓
User / Agent Approval
        ↓
Confirm
        ↓
Atomic Approval Claim
        ↓
Native ERPNext Write
```

Approval state is server-side and tied to the relevant execution context.

The preview shown to an MCP client is not itself the authoritative payload for the final database write.

Native Frappe and ERPNext permissions and validation still apply during the final operation.

---

## Diagram Maintenance Rule

This diagram must be reviewed whenever an architectural change affects any of the following:

* MCP transport
* HTTP authentication
* STDIO identity
* OAuth
* execution-user resolution
* Direct backend behavior
* REST backend behavior
* remote execution identity
* MCP profiles
* tool exposure
* Frappe runtime lifecycle
* approval storage or approval semantics
* service-layer boundaries
* native ERPNext execution
* communication between `mcp_identity` and `mcp_erpnext`

If the architecture changes materially, update:

1. the implementation,
2. relevant tests and architecture documentation,
3. this README when necessary,
4. `mcp-erpnext-architecture-mental-model.png` in both repositories.

---

## Shared Documentation Rule

This architecture asset is intentionally duplicated in:

```text
mcp_identity/docs/architecture/
```

and:

```text
mcp_erpnext/docs/architecture/
```

Both copies should represent the same architecture revision.

When the shared architecture diagram is updated, both repositories should receive the corresponding update so they do not drift from each other.

---

## Last Verified

Architecture visualization last verified against the implementation:

**September 18, 2026**

Future changes should update this date only after the diagram has been checked against the actual implementation.

---

## Important Principle

> Code is the source of truth.
> The architecture diagram is a visual representation of that source of truth.
