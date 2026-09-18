# MCP Identity Frappe OAuth RFC 8707 Resource-Binding Design

Design date: 2026-09-17

## 1. Executive Summary

### Decision

OAuth mode can be implemented without patching Frappe core, but not without a
small Frappe-native schema extension and an `mcp_identity` compatibility
validator.

The selected design is:

```text
one pre-registered Frappe OAuth Client
  custom_mcp_resource = canonical MCP resource
          |
authorization request --resource--> native Frappe login/consent
          |
OAuth Authorization Code.custom_mcp_resource
          |
token request --same resource--> OAuth Bearer Token.custom_mcp_resource
          |
refresh request --same resource--> replacement bound token
          |
FastMCP TokenVerifier --exact resource/client/scope/user checks--> Frappe user
```

`mcp_identity` will add an optional `custom_mcp_resource` field to `OAuth
Client`, `OAuth Authorization Code`, and `OAuth Bearer Token`. A request hook
will install a subclass of Frappe's native `OAuthWebRequestValidator` for the
native OAuth endpoints. The subclass will require one canonical `resource` for
clients whose `custom_mcp_resource` is populated, preserve it on the native
authorization code and bearer-token records, and enforce the same value during
code exchange and refresh.

Frappe document events will populate the two issued-record fields. The bearer
token `before_insert` event will also invalidate the consumed authorization
code, or revoke the consumed refresh-token record, in the same database
transaction as insertion of the replacement token. The validator will acquire
the source row with `SELECT ... FOR UPDATE`. This closes the installed Frappe
16.34.0 code/refresh replay races without replacing Frappe's login, consent,
client authentication, redirect checks, PKCE implementation, token generation,
expiry, user ownership, scopes, or revocation endpoint.

The standalone MCP server will validate opaque tokens directly against the
authoritative Frappe site database. It will accept only an active, unexpired
token whose resource, expected client, recorded scopes, and enabled non-Guest
native Frappe user all match. It will never consult `X-MCP-User-Email` or fall
back to `MCP_FRAPPE_USER` in OAuth mode.

This design deliberately uses a pre-registered public OAuth client for the
first release. Native Frappe DCR creates an OAuth Client without a trusted MCP
resource association, so dynamically registered clients remain unsupported for
this OAuth mode until a separate DCR-binding design is approved.

```text
Chosen design:
Frappe-native record extensions plus an mcp_identity OAuthWebRequestValidator
compatibility subclass installed by before_request, with transactional document
events and a FastMCP opaque TokenVerifier.

Resource source:
MCP_OAUTH_RESOURCE_SERVER_URL in the MCP resource-server process, cross-checked
against OAuth Client.custom_mcp_resource in the Frappe site.

Authorization binding:
OAuth Client.custom_mcp_resource -> OAuth Authorization
Code.custom_mcp_resource.

Token exchange:
The request resource must equal the locked authorization-code binding; the new
OAuth Bearer Token receives the binding while the code is invalidated in the
same transaction.

Refresh:
The request resource must equal the locked source-token binding; the replacement
token receives the same binding while the source token pair is revoked in the
same transaction.

Bearer verification:
Native OAuth Bearer Token lookup plus status, expiry, resource, expected-client,
recorded-scope, OAuth Client binding, and enabled non-Guest User checks.

Execution identity:
Validated OAuth Bearer Token.user.

Schema:
Three optional Frappe Custom Fields on native OAuth records; no new DocType and
no second storage of authorization codes, access tokens, or refresh tokens.

OAuth mode can be implemented:
YES, after the schema/validator task is implemented and verified. OAuth must
remain unavailable until then.
```

## 2. Repository / Version Context

The following local source was inspected read-only:

| Component | Branch | Commit/version | Relevant working-tree state |
|---|---|---|---|
| `mcp_identity` | `main` | `5cc9fcbb49d0704bf0b7fb48a82a315e0d426246` | Pre-existing untracked `docs/tasks/` and `docs/inspect/` |
| `mcp_erpnext` | `master` | `12ef04ea69280b79b2849dda574d1290a613ade2` | Clean |
| Frappe | `version-16` | `c1f1e8ec3708750d7254f7f99d869ffb9886f19f`; source version `16.34.0` | Pre-existing unrelated untracked files under `frappe/locale/` and `frappe/twilio_whatsapp_notification/` |
| ERPNext | `version-16` | `12cd563fb9a79731f75ae2a45b1446a0a2dd9e74`; source version `16.35.0` | Clean |
| Python MCP SDK | installed package | `mcp==1.29.0` | Inspected from the Bench virtual environment |
| oauthlib | installed package | `oauthlib==3.3.1` | Inspected from the Bench virtual environment |

The official `frappe/frappe` `version-16` branch was also inspected on
2026-09-17. Its OAuth grant source and OAuth Bearer Token schema still contain
no RFC 8707 grant/token resource field or `request.resource` enforcement. The
installed commit remains the implementation authority for this design.

Primary external protocol references:

- [MCP Authorization specification, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [RFC 8707 - Resource Indicators for OAuth 2.0](https://datatracker.ietf.org/doc/html/rfc8707)
- [RFC 9728 - OAuth 2.0 Protected Resource Metadata](https://datatracker.ietf.org/doc/html/rfc9728)
- [OpenAI MCP authentication guide](https://developers.openai.com/plugins/build/auth)
- [Frappe OAuth 2 API guide](https://docs.frappe.io/framework/user/en/guides/integration/rest_api/oauth-2)
- [Frappe OAuth setup guide](https://docs.frappe.io/framework/user/en/guides/integration/how_to_set_up_oauth)
- [official Frappe `version-16` OAuth validator](https://github.com/frappe/frappe/blob/version-16/frappe/oauth.py)
- [official Frappe `version-16` OAuth endpoints](https://github.com/frappe/frappe/blob/version-16/frappe/integrations/oauth2.py)
- [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

The MCP specification requires `resource` on both authorization and token
requests and requires the resource server to prove that the access token was
issued specifically for it. OpenAI documents the same end-to-end echo and
audience check. RFC 8707 permits a resource to be required and uses
`invalid_target` for a missing, malformed, unknown, or unacceptable target.

## 3. Native Frappe OAuth Lifecycle Trace

### Persistence

| Record | Installed fields relevant to the grant | Finding |
|---|---|---|
| `OAuth Client` | client ID/secret, redirect URIs, scopes, grant/response type, token auth method, allowed roles | No resource/audience field |
| `OAuth Authorization Code` | client, user, scopes, code, expiry, redirect URI, validity, nonce, PKCE challenge/method | No resource/audience field |
| `OAuth Bearer Token` | client, user, scopes, access token, refresh token, expiry, status | No resource/audience field |
| `OAuth Settings` | metadata/DCR/consent settings and resource-metadata display fields | Metadata only; no grant binding |

The exact installed schemas are under
`frappe/integrations/doctype/oauth_client/`,
`oauth_authorization_code/`, `oauth_bearer_token/`, and `oauth_settings/`.

### Endpoint/callback trace matrix

| Stage | Installed entry point / callback | Request values handled natively | Values persisted or returned | Resource result / usable extension |
|---|---|---|---|---|
| Authorization | `frappe/integrations/oauth2.py:authorize()` -> oauthlib `validate_authorization_request()` | `client_id`, response type, exact redirect URI, scopes, state, nonce, PKCE challenge/method; oauthlib generically parses `resource` | validation credentials are kept only for the current request | `resource` is available on the oauthlib request but not validated; request-local validator substitution is possible |
| Consent/issuance | `oauth2.py:approve()` -> `create_authorization_response()` -> `OAuthWebRequestValidator.save_authorization_code()` | same authorization request, authenticated Frappe session user | native authorization-code fields listed above | first persistence loss; `doc_events.before_insert` can populate an app-owned field |
| Code exchange | `oauth2.py:get_token()` -> oauthlib authorization-code grant -> `validate_code()` | client auth/ID, grant type, code, redirect URI, code verifier, generically parsed `resource` | restores code user/scopes; generates access/refresh values | validator subclass can lock and compare the code binding before issuance |
| Token save | `OAuthWebRequestValidator.save_bearer_token()` | validated client/user/scopes and generated tokens | native bearer-token record and commit | `doc_events.before_insert` can copy binding and atomically consume source state |
| Refresh | oauthlib refresh grant -> `authenticate_client()`, `validate_refresh_token()`, `get_original_scopes()`, `save_bearer_token()` | client auth/ID, refresh token, optional scope, generically parsed `resource` | new access/refresh record; installed source leaves old record Active | validator subclass plus locked source and token insert event can enforce binding and rotate atomically |
| Revocation | `oauth2.py:revoke_token()` -> oauthlib -> validator `revoke_token()` | token and optional type hint, authenticated client behavior from oauthlib/Frappe | native status becomes Revoked | native lifecycle is sufficient because binding is on the same row |
| Introspection | `oauth2.py:introspect_token()` | token and type hint | active/status, client, expiry, scopes, optional OIDC user data | no resource and incomplete active checks; do not use for MCP verification |
| Native bearer auth | `frappe/auth.py` -> `get_oauth_server().verify_request()` -> `validate_bearer_token()` | Authorization Bearer token and route-derived required scopes | sets native Frappe user for WSGI request | no resource; standalone FastMCP does not use this WSGI path |
| AS metadata | `oauth2.py:get_authorization_server_metadata()` | no grant input | issuer/endpoints, code+refresh grants, client auth methods, S256, optional DCR | discovery is reusable; it does not advertise or implement token resource binding |
| Frappe PRM | `oauth2.py:get_protected_resource_metadata()` | request origin and OAuth Settings display fields | Frappe-origin resource metadata | describes Frappe itself, not the separately configured MCP path |

### Authorization request and consent

1. `frappe.integrations.oauth2.authorize()` passes the request URL/body/headers
   to oauthlib's `validate_authorization_request()`.
2. oauthlib 3.3.1's generic `Request` adds arbitrary query/body keys to its
   internal parameter dictionary. Therefore a single `resource` value reaches
   the oauthlib request as `request.resource`; oauthlib itself does not validate
   RFC 8707 semantics or duplicate `resource` occurrences.
3. Frappe validates the client, exact registered redirect URI, response type,
   allowed scopes, role, and optional PKCE values.
4. Guest users are redirected through native Frappe login. Logged-in users see
   Frappe's native consent page unless the native skip policy applies.
5. The consent continuation URL retains unrecognized request parameters, so
   `resource` can reach `approve()`; this must be regression-tested for GET and
   form-encoded POST requests.
6. `approve()` validates the authorization request again and calls oauthlib's
   native authorization response creation.
7. `OAuthWebRequestValidator.save_authorization_code()` stores the native code
   fields and commits. It never reads or stores `request.resource`.

### Authorization-code token exchange

1. `frappe.integrations.oauth2.get_token()` passes `r.form` to oauthlib's
   `create_token_response()`.
2. oauthlib parses `resource`, but its installed authorization-code grant does
   not treat it as a standard validated parameter.
3. Native client authentication and grant validation run.
4. `OAuthWebRequestValidator.validate_code()` loads a valid code for the
   client, restores scopes/user, and performs Frappe's PKCE check.
5. oauthlib creates opaque access and refresh values.
6. `save_bearer_token()` stores client, user, scopes, opaque secrets, and
   expiry, then commits.
7. `invalidate_authorization_code()` marks the code invalid in a second commit.

The separate commits create a concurrent code-replay window in the installed
implementation. The compatibility layer must close it for MCP-bound grants.

### Refresh

1. Native client authentication resolves the client from the request or refresh
   token.
2. `validate_refresh_token()` finds an Active bearer-token record and restores
   its user. It does not compare a resource and does not explicitly compare the
   source token's client with the authenticated client.
3. `get_original_scopes()` restores scopes from the source token.
4. oauthlib 3.3.1 generates a new access token and, by default, a new refresh
   token.
5. `save_bearer_token()` inserts and commits the replacement record. Installed
   Frappe 16.34.0 does not revoke the old record, so the old refresh token can be
   reused.

### Bearer validation

`OAuthWebRequestValidator.validate_bearer_token()` loads the opaque token and
checks expiry, status, an enabled User, and whether requested scopes exist in
the OAuth Client's current scope list. It does not check a token resource and
does not use the scopes recorded on the token as the authorization ceiling.

Frappe WSGI authentication invokes that validator for Frappe HTTP routes, but
the standalone FastMCP/uvicorn process does not pass through Frappe WSGI. It
therefore needs its own authoritative native-record verifier.

### Revocation, introspection, and cleanup

- `revoke_token()` marks the native token record Revoked by access or refresh
  token and commits. Because one record contains both values, either value then
  represents a revoked pair.
- `introspect_token()` loads the native record and reports `active` from status,
  with client/scopes/expiry. It does not report resource and does not apply all
  bearer-validation checks. It is not sufficient for MCP verification.
- `delete_oauth2_data()` and the bearer-token cleanup remove invalid/revoked or
  old native records. A field on the native record is removed with its owner and
  needs no sidecar cleanup.
- Frappe's protected-resource metadata describes the Frappe origin inferred
  from the request URL. It does not describe a separately hosted MCP URL and is
  not an issuance-time resource binding.

## 4. Where `resource` Is Lost Today

The first irreversible loss is
`OAuthWebRequestValidator.save_authorization_code()` in
`apps/frappe/frappe/oauth.py`: oauthlib has parsed the value, but the Frappe
authorization-code record has no field and the method does not copy it.

The value can also arrive at `get_token()`, but `validate_code()`,
`validate_refresh_token()`, and `save_bearer_token()` ignore it. Consequently:

- an authorization code has no target-resource proof;
- an opaque access/refresh token pair has no target-resource proof;
- refresh cannot preserve a value that was never recorded;
- revocation works only on the unbound native pair; and
- bearer validation cannot distinguish a normal Frappe token from an MCP token.

A dedicated client ID narrows which client received a token but does not repair
this loss. The OAuth client is the party using the token; the MCP URL is the
resource accepting it. These are different OAuth roles and identifiers.

## 5. Frappe-Native Extension Points

| Extension | Capture authorization resource | Code/token/refresh enforcement | Decision |
|---|---:|---:|---|
| `before_request` hook | Yes; runs before the whitelisted OAuth endpoint and can install `frappe.local.oauth_server` | Yes, by supplying a validator subclass to the unchanged native endpoint | **Use** for the compatibility validator |
| `doc_events` | Yes, from validated request-local flags | Yes; can populate custom fields and make source-record state changes in the token insert transaction | **Use** for atomic persistence/consumption |
| Frappe Custom Fields | Persistence only | Holds binding on native records across workers | **Use**; supported, minimal schema extension |
| `extend_doctype_class` | No request/grant callback | Can validate fields but cannot intercept oauthlib grant decisions | Do not use as the primary seam |
| `override_doctype_class` | Same limitation and replaces a controller | No benefit for the pass-through native controllers | Reject |
| `override_whitelisted_methods` | Yes | Would require wrapping/copying `authorize`, `approve`, `get_token`, and possibly revocation | Reject; substantially more native endpoint duplication |
| `auth_hooks` | Runs in Frappe request authentication | Wrong boundary for AS grant issuance and not used by standalone FastMCP | Reject |
| permission/query hooks | No | OAuth service records are accessed internally with elevated permissions | Not relevant |
| OAuth Settings | Metadata and DCR switches only | No RFC 8707 grant/token field or hook | Insufficient |
| Frappe protected-resource metadata | Advertises the Frappe request origin | Does not bind an issued token to the external MCP resource | Insufficient |

`frappe.integrations.oauth2.get_oauth_server()` reuses an already-populated
`frappe.local.oauth_server`. A narrowly scoped `before_request` hook can set it
to the same oauthlib `WebApplicationServer`, using an
`MCPResourceBindingOAuthValidator(OAuthWebRequestValidator)`. Native endpoint
functions remain unchanged.

The hook must run only for the exact Frappe authorization, approval, token, and
revocation method paths. It must not alter unrelated requests or use a process
global. The server object belongs to `frappe.local`, which is request-local.

## 6. Candidate Design Comparison

### Candidate A - extend native OAuth records: selected

Advantages:

- the resource lives beside the native client, code, access/refresh pair, user,
  scopes, expiry, and status;
- no OAuth secret is copied to another table;
- native revocation and cleanup automatically cover the binding;
- Custom Fields and request/document hooks are supported Frappe mechanisms;
- shared database truth works across web workers and MCP processes;
- unrelated clients coexist because blank fields retain native behavior.

Costs:

- three schema columns and an idempotent migration are required;
- the validator is coupled to installed Frappe/oauthlib callbacks and needs an
  upgrade compatibility test;
- installed native commit boundaries must be tightened for MCP-bound flows.

### Candidate B - `mcp_identity` sidecar binding DocType: rejected

A sidecar needs a stable reference to an authorization code or bearer-token
pair. On the installed version, that reference is the raw authorization/access/
refresh secret or a derivative maintained in parallel. It adds uniqueness,
cleanup, revocation synchronization, orphan, and transaction-consistency
problems while native records already own the lifecycle. Hashing identifiers in
the sidecar reduces disclosure but still duplicates secret-derived lookup state
and does not eliminate dual-write races.

### Candidate C - compatibility authorization/token endpoints: rejected

New endpoints could preserve `resource`, but safely delegating only part of the
flow still requires copying Frappe's login continuation, consent rendering,
OAuth errors, client authentication, PKCE, redirect validation, issuance,
refresh, and revocation orchestration. That is a second OAuth server surface and
has more upgrade/security risk than substituting the native validator behind
unchanged endpoints.

### Candidate D - dedicated OAuth Client only: rejected as the binding

The dedicated client remains required as defense in depth and an operational
allowlist. It is not a resource audience. Without a persisted code/token
resource, its tokens remain acceptable anywhere that accepts general Frappe
bearer tokens. It cannot prevent cross-resource replay between two servers that
trust the same Frappe authorization server/client.

### Candidate E - native/upstream capability: unavailable

Installed Frappe 16.34.0 and the official `version-16` source inspected on
2026-09-17 parse no RFC 8707 value into grant persistence or bearer validation.
Frappe's RFC 9728 metadata and oauthlib's generic request parsing do not fill
that gap. An upgrade alone is therefore not a demonstrated solution.

## 7. Chosen Resource-Binding Architecture

### Authorization-server compatibility seam

Proposed components in `mcp_identity`:

```python
class InvalidTargetError(OAuth2Error):
    error = "invalid_target"

class MCPResourceBindingOAuthValidator(OAuthWebRequestValidator):
    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs): ...
    def validate_code(self, client_id, code, client, request, *args, **kwargs): ...
    def validate_refresh_token(self, refresh_token, client, request, *args, **kwargs): ...

def install_mcp_oauth_validator_for_request() -> None: ...
def validate_oauth_client_resource(doc, method=None) -> None: ...
def bind_authorization_code_before_insert(doc, method=None) -> None: ...
def bind_bearer_token_before_insert(doc, method=None) -> None: ...
```

The exact implementation must call native validation first where doing so does
not create a race, and must preserve native behavior completely when the OAuth
Client has no `custom_mcp_resource`.

For an MCP-bound client:

1. authorization validation runs only after native client and redirect checks;
2. exactly one `resource` is required;
3. its canonical form must equal the client binding;
4. S256 PKCE and a non-empty challenge are required;
5. code exchange locks the valid code and matches client/resource/S256;
6. refresh locks the Active source token and matches client/resource;
7. request-local flags carry only code/token record names, client, grant kind,
   and canonical resource to document events; never raw token values;
8. the token insert event consumes the locked source in the same transaction.

### Resource-server seam

```python
@dataclass(frozen=True)
class VerifiedPrincipal:
    frappe_user: str
    client_id: str
    scopes: tuple[str, ...]
    resource: str
    issuer: str
    expires_at: int

def canonicalize_mcp_resource(value: str, *, allow_loopback_http: bool = False) -> str: ...
def resolve_configured_frappe_user(user_name: str) -> str: ...
def get_http_auth_mode(environ: Mapping[str, str]) -> HTTPAuthMode: ...
def load_http_identity_settings(environ: Mapping[str, str]) -> HTTPIdentitySettings: ...
def verify_frappe_oauth_access_token(token: str, policy: FrappeOAuthPolicy) -> VerifiedPrincipal | None: ...
def build_http_auth_integration(settings, *, frappe_site: str, sites_path: str): ...
```

The `TokenVerifier` adapter returns SDK `AccessToken` with the raw token only
because the SDK contract requires it, and retains it only in request-local auth
context. It sets `client_id`, recorded scopes, expiry, canonical resource,
native Frappe user as `subject`, and `claims={"iss": configured_issuer}`.

## 8. Canonical Resource Definition

The resource is the public MCP endpoint URL including the path that identifies
this server, for example:

```text
https://mcp.example.com/mcp
```

Rules:

1. Source only from trusted deployment configuration and the site-owned OAuth
   Client field. Never derive it from `Host`, `Forwarded`, or
   `X-Forwarded-*` headers.
2. Require an absolute URL with scheme and authority. Reject userinfo, query,
   fragment, control characters, and an empty host.
3. Require HTTPS. Permit HTTP only for an explicit test/development policy and
   only for `localhost`, `*.localhost`, or loopback IP literals.
4. Lowercase scheme and DNS host. Convert an internationalized DNS name to its
   ASCII IDNA form. Preserve IPv6 brackets in serialization.
5. Remove the default port (`443` for HTTPS, `80` for permitted HTTP); preserve
   an explicit non-default port.
6. Include the MCP path. Preserve path case. Reject dot segments and repeated
   slash aliases. Normalize percent-escape hex digits to uppercase but do not
   decode escaped path octets.
7. Normalize an empty/root path to no trailing slash and remove one terminal
   slash from a non-root path. Thus `https://mcp.example.com/mcp/` is stored as
   `https://mcp.example.com/mcp`.
8. Normalize the configured value once at startup and when saving the OAuth
   Client field. Normalize each incoming `resource` with the same pure
   function, then compare the resulting strings exactly.
9. Accept exactly one resource. Multiple `resource` parameters are rejected
   even though RFC 8707 permits them, because this service intentionally issues
   a single-audience token.
10. Domain aliases are not equivalent. Each alias needs its own configured
    OAuth client/resource/server deployment or is rejected.
11. One MCP process serves one canonical resource. Multiple processes may use
    the same Frappe authorization server only with distinct client/resource
    policies.

The value in FastMCP protected-resource metadata, the 401 challenge metadata,
the OAuth Client field, authorization/token/refresh requests, stored token
binding, and verifier policy must all resolve to this exact string.

## 9. Persistence / Schema Decision

Outcome B: Frappe-native record extension required.

Create these optional Custom Fields in an idempotent `mcp_identity` patch:

| DocType | Field | Type | Properties |
|---|---|---|---|
| `OAuth Client` | `custom_mcp_resource` | Small Text | optional, editable by existing System Manager permissions, no index/unique; insert after `scopes` |
| `OAuth Authorization Code` | `custom_mcp_resource` | Small Text | optional, hidden, read-only, no-copy, print/report hidden, no index/unique; insert after `scopes` |
| `OAuth Bearer Token` | `custom_mcp_resource` | Small Text | optional, hidden, read-only, no-copy, print/report hidden, no index/unique; insert after `scopes` |

`Small Text` avoids the normal `Data` length ceiling for an absolute URI. No
lookup begins with the resource, so an index is unnecessary. Code/access token
identity remains the native primary/unique lookup. Fields cannot be required
because existing and unrelated Frappe OAuth records must remain valid.

The patch should use Frappe's `create_custom_fields(..., update=True)` pattern
and be listed in `mcp_identity/patches.txt`. It must not export all site Custom
Fields as broad fixtures. An OAuth Client validation event canonicalizes or
rejects a nonblank binding.

No new `mcp_identity` DocType is required. No authorization code, access token,
refresh token, client secret, or duplicate token hash is added outside the
native OAuth records.

## 10. OAuth Authorization-Code Binding

For clients with blank `custom_mcp_resource`, invoke the native validator and
do nothing else.

For a bound client:

1. Native client, role, exact redirect, response type, and scope checks run.
2. The compatibility validator checks duplicate parameters, requires exactly
   one resource, canonicalizes it, compares it with the client field, and
   requires PKCE S256.
3. Missing/malformed/mismatched/multiple values raise `invalid_target` only
   after native redirect validation, preventing an error redirect to an
   unvalidated URI.
4. The validated client/resource is stored in request-local `frappe.flags`.
5. The authorization-code `before_insert` event checks that the document client
   matches the flag and writes the canonical resource before native save/commit.
6. Login and consent continuation must carry the same parameter; validation is
   repeated by `approve()` rather than trusting a prior request.

The resource is never read from a cookie, email header, browser Host header, or
process-global variable.

## 11. Token Exchange Enforcement

For an MCP-bound client, `validate_code()` must:

1. select the code by name, client, and `validity="Valid"` with
   `for_update=True`;
2. require its stored resource and S256 challenge;
3. require exactly one token-request resource and exact canonical equality;
4. call/preserve native code, user, scope, redirect, and PKCE validation;
5. put code name/client/resource in request-local state.

The bearer-token `before_insert` event writes the same resource and marks that
locked code Invalid before inserting the new token. Native
`save_bearer_token()` then commits both changes together. Native's later
`invalidate_authorization_code()` is idempotent.

This ordering means a crash before commit creates neither a usable token nor a
consumed code. A concurrent exchange blocks on the row lock and then observes
the invalid code. Changed, missing, multiple, or unbound resources fail before
token generation/persistence.

## 12. Refresh-Token Enforcement

For an MCP-bound source token, `validate_refresh_token()` must:

1. locate the Active source record by native refresh-token lookup with
   `for_update=True`;
2. require the authenticated client to equal the source record's client;
3. require the source binding to equal the current OAuth Client binding;
4. require exactly one refresh-request resource equal to that binding;
5. revalidate the enabled non-Guest source user;
6. restore the native user and scopes and store only the source record name and
   canonical resource in request-local state.

oauthlib generates a replacement access/refresh pair. The bearer-token
`before_insert` event copies the resource and marks the locked source record
Revoked in the same transaction as the replacement insertion. Concurrent reuse
then fails after the first transaction commits.

Resource switching on refresh is not supported. Although RFC 8707 can support
resource subsets, this project intentionally has one resource per grant.

## 13. Revocation / Cleanup

Native revocation remains authoritative. Revoking either opaque value marks the
single record that owns the access/refresh pair Revoked; the verifier rejects it
on the next request. Rotation also marks the old pair Revoked.

No binding cleanup callback is needed because the binding is a column on the
native record. Native deletion of invalid codes, revoked tokens, or expired old
tokens removes it. Revocation must not delete or recreate binding data, and a
stale binding can never reactivate a Revoked native record.

The native introspection endpoint is not used by the MCP verifier. If a later
task exposes resource in introspection, it must also correct native active-state
checks and secure the endpoint; that is not required for the local verifier.

## 14. Opaque Bearer Verification

For every protected MCP HTTP request:

1. accept a Bearer token only from the Authorization header;
2. in a short-lived initialized Frappe site context, locate the native `OAuth
   Bearer Token` by the installed version's authoritative access-token lookup;
3. require `status == "Active"`;
4. require current time strictly before `expiration_time`;
5. require `token.client == MCP_OAUTH_FRAPPE_CLIENT_ID`;
6. require token resource, OAuth Client resource, and configured MCP resource to
   be the same canonical string;
7. parse scopes from the token record and require every configured scope;
8. require the OAuth Client still exists; client scopes may be checked as an
   additional policy but must not expand the token's recorded scopes;
9. require the native token user exists, is enabled, and is not Guest;
10. return a pure verified principal/SDK `AccessToken`, then destroy the auth
    lookup's Frappe context in `finally`.

No JWT validation is invented for an opaque token. No remote introspection call
is necessary because the MCP process shares the authoritative Frappe site. The
raw token is used only for the native indexed/primary lookup and SDK
request-local context; it must never be logged, fingerprinted with a reversible
scheme, returned in an MCP result, or copied into approval state.

Frappe's official branch may change opaque-token storage (for example, hashing
at rest). The verifier must use the installed Frappe helper/lookup convention
rather than assuming forever that the document name is the raw token. An
upgrade compatibility test is mandatory.

## 15. Identity Mapping

The only execution identity in OAuth mode is:

```text
validated OAuth Bearer Token.user
  -> existing enabled User
  -> explicit Guest rejection
  -> frappe.set_user(validated_user)
```

`X-MCP-User-Email` is ignored even if present. `MCP_FRAPPE_USER` is ignored in
OAuth HTTP mode and remains only the configured stdio identity. No email,
userinfo, `sub`, or caller header overrides the native token owner.

The native User is rechecked on every request, so disabling or deleting it takes
effect without waiting for token expiry.

## 16. MCP SDK / FastMCP Integration Boundary

Installed MCP SDK 1.29.0 provides:

- `AuthSettings(issuer_url, resource_server_url, required_scopes)`;
- the async `TokenVerifier` protocol and `AccessToken` result;
- `BearerAuthBackend` for every-request verification;
- `RequireAuthMiddleware` with 401/403 challenges;
- `AuthContextMiddleware` with a reset-in-`finally` `ContextVar`;
- path-aware RFC 9728 protected-resource metadata routes.

OAuth mode should construct FastMCP with `AuthSettings` and the
`FrappeOAuthTokenVerifier`; it must not mount the SDK authorization-server
provider routes because Frappe remains the authorization server at a separate
issuer URL.

The SDK does not compare `AccessToken.resource` with `resource_server_url`.
That comparison is therefore a mandatory responsibility of the custom verifier
before it returns `AccessToken`.

`mcp_erpnext.runtime` should obtain `get_access_token()` from the SDK auth
context, require a verified subject, and pass that subject into its fresh
Frappe business-operation scope. Absence of the auth context on configured HTTP
must fail closed; it must never select stdio behavior based on whether a request
object happened to expose headers.

## 17. `mcp_identity` / `mcp_erpnext` Ownership

### `mcp_identity`

- HTTP auth-mode and identity setting parsing/validation;
- configured stdio User validation;
- trusted-header authentication and User resolution;
- canonical resource parsing;
- Custom Field migration and OAuth Client resource validation;
- request hook and Frappe OAuth validator subclass;
- authorization-code/token document event handlers;
- opaque token verifier and SDK auth integration assembly;
- verified-principal/error contracts and focused tests.

### `mcp_erpnext`

- `MCP_TRANSPORT`, listener, path, allowed hosts, profile, backend, site, and
  approval settings;
- passing trusted site/sites-path values to the identity integration;
- constructing FastMCP with the returned `AuthSettings` and `TokenVerifier`;
- Frappe business-operation init/connect/destroy and `frappe.set_user()`;
- ERPNext tools, native permissions, profiles, REST backend, observability, and
  approval policy.

The async token verifier should offload its bounded synchronous Frappe lookup to
a worker thread. The identity-owned verifier initializes/connects/destroys a
short auth-only Frappe context inside that worker using the site and sites path
supplied by `mcp_erpnext`; it returns only immutable verified data. The later
business scope is independently initialized by `mcp_erpnext`.

No provider-specific branch belongs in ERPNext service/tool code.

## 18. Environment Variable Contract

| Variable | Decision | Owner / validation |
|---|---|---|
| `MCP_HTTP_AUTH_MODE` | **Keep**; `trusted_header|oauth`; absent means `trusted_header` | `mcp_identity`; blank/unknown explicit value fails startup; relevant only to Streamable HTTP |
| `MCP_HTTP_SHARED_SECRET` | **Keep** for trusted-header only | Sensitive; minimum 32 chars in trusted mode; never read as credentials in OAuth mode. A stale value may remain but grants no access |
| `MCP_OAUTH_PROVIDER` | **Remove from proposed contract** | Redundant while the only approved provider is Frappe; do not build a speculative provider framework |
| `MCP_OAUTH_ISSUER_URL` | **Keep** | Non-secret canonical public Frappe issuer origin; HTTPS, no credentials/query/fragment/path, no trailing slash; exact match to AS metadata |
| `MCP_OAUTH_RESOURCE_SERVER_URL` | **Keep** | Non-secret canonical public MCP endpoint, normalized by section 8 and matched to the site OAuth Client field |
| `MCP_OAUTH_REQUIRED_SCOPES` | **Keep** | Non-secret space-delimited non-empty set; trim/deduplicate/reject control characters; advertise and enforce against token-record scopes |
| `MCP_OAUTH_FRAPPE_CLIENT_ID` | **Keep** | Non-secret exact pre-registered client allowlist; required in OAuth mode and cross-checked on every request |
| `MCP_FRAPPE_USER` | **Keep unchanged** | stdio configured identity only; ignored by all HTTP/OAuth paths |

OAuth startup also requires direct local Frappe backend/site configuration. REST
backend stays stdio-only and continues to execute as the remote API-key owner.

The Frappe authorization-server process does not need MCP process environment
variables to decide the audience. Its trusted policy anchor is the
site-controlled `OAuth Client.custom_mcp_resource`. The MCP process environment
independently supplies the expected client/resource and must match the site
record; this two-sided check prevents proxy headers or one misconfigured process
from silently changing the audience.

Initial deployment uses an operator-created public OAuth Client with
Authorization Code, Code response, token auth method None, exact ChatGPT
callback URI, S256 PKCE, required MCP scopes, and the canonical resource field.
DCR/CIMD support is outside the first implementation.

## 19. Request Isolation / Multi-Worker Safety

All durable authorization truth is in the Frappe site database. No
authorization code, active token, refresh state, resource binding, or user is
stored in a module global or process-local cache.

- Frappe web requests use `frappe.local`; the compatibility oauthlib server and
  temporary flags are request-local.
- Code and refresh consumption use database row locks and one token-insert
  transaction, so separate web workers serialize replay attempts.
- MCP bearer verification opens a bounded auth-only site context and destroys it
  in `finally`.
- SDK auth context is a `ContextVar` reset in `finally`.
- `mcp_erpnext` opens a separate business-operation context, applies exactly the
  verified user, and destroys it before and after each HTTP operation.
- No Frappe Document or connection crosses an `await` boundary.

Tests must cover two processes conceptually with two independent connections;
single-process in-memory tests alone are not proof of locking behavior.

## 20. Error / Challenge Contract

| Condition | Authorization server | MCP resource server |
|---|---|---|
| Missing/malformed/multiple/unsupported resource | OAuth `invalid_target`; no token | N/A |
| Changed resource at code/refresh exchange | OAuth `invalid_target` | N/A |
| Invalid/replayed code or refresh token | OAuth `invalid_grant` | N/A |
| Missing/malformed/unknown/expired/revoked/unbound/wrong-resource bearer | N/A | 401 Bearer challenge with `resource_metadata`; public shape does not reveal which check failed |
| Disabled/deleted/Guest token user | N/A | same generic 401 |
| Valid token, missing required scope | N/A | 403 with `error="insufficient_scope"`, required scope, and `resource_metadata` |
| Provider/database unavailable | fail closed; standard server/temporary error | 503 is preferable when validity cannot be established; never accept |

The installed SDK 1.29.0 includes the resource metadata URL in challenges but
does not add the `scope` parameter to every challenge. The integration task must
test current behavior and add only a narrow standards-compliant wrapper if the
required scope is absent.

Logs may contain a correlation ID, mode, provider constant, site, client
fingerprint, and non-secret failure category. They must not contain raw tokens,
authorization codes, refresh tokens, Authorization headers, client/shared
secrets, or raw request bodies.

## 21. Migration / Backward Compatibility

### Migration

1. Deploy the Custom Field patch while OAuth mode is still unavailable.
2. Leave all existing client/code/token bindings blank; do not backfill. There
   is no evidence that existing tokens were issued for the MCP resource.
3. Create/configure one dedicated client and populate its canonical resource by
   an explicit operator action in the future approved rollout.
4. Install the validator/hooks and tests.
5. Enable OAuth mode only after schema capability and client/resource parity are
   checked at startup.

Existing non-MCP clients remain native because blank client binding is the
compatibility switch. Existing unbound tokens can continue to work for their
existing Frappe integrations but are always rejected by the MCP verifier.

### Rollback

1. Set the MCP HTTP mode back to `trusted_header` and restart only under an
   operator-approved deployment action.
2. Revoke the dedicated MCP client's active tokens before removing the
   compatibility hooks.
3. Remove hooks/code only after OAuth mode is disabled everywhere.
4. The optional fields may remain harmlessly. If schema removal is required,
   take a backup and use an explicit reverse patch after token revocation; it
   destroys only stored resource bindings and is not required for functional
   rollback.

### Preserved paths

- Stdio remains `MCP_TRANSPORT=stdio` plus `MCP_FRAPPE_USER`; no OAuth flow.
- Missing HTTP auth mode remains current trusted secret + email header.
- Trusted-header behavior and header name remain unchanged.
- REST backend remains bound to the remote API credential owner and stdio.
- Native ERPNext permissions and `frappe.set_user()` remain authoritative after
  authentication.
- OAuth never bypasses `CONFIRM_WRITE`, ApprovalStore policy, or Draft-only
  business workflow rules.

## 22. Security Risks / Controls

| Risk | Control |
|---|---|
| Token confusion / confused deputy | Three-way exact check: configured resource, client resource, token resource; expected client is additional defense only |
| Cross-resource replay | Resource A token fails at Resource B even under the same issuer/user/client database |
| Cross-client substitution | Exact expected client and source-record client checks; client ID is not treated as audience |
| Authorization-code interception/replay | Native exact redirect + S256 PKCE, locked valid code, atomic invalidation with token insert |
| Refresh resource escalation | Locked source token; replacement inherits exact resource; caller cannot change it |
| Refresh replay | Locked source record and atomic source revocation/replacement insertion |
| Revoked/expired token | Checked against native record on every HTTP request |
| Header impersonation/fallback | OAuth mode ignores email header and stdio user; no fallback |
| Scope expansion after client edit | Required scopes are checked against scopes stored on the token, not only current client scopes |
| User lifecycle | Existing/enabled/non-Guest checked on every request |
| Proxy/origin confusion | Trusted configured URL only; no Host/forwarded derivation |
| Secret duplication | No sidecar; raw opaque values remain only in native storage and request-local SDK context |
| Worker identity leakage | Frappe and SDK ContextVars plus pre/finally cleanup; no globals |
| Upgrade drift | Pin/version gate, focused callback/schema tests, and live canary before upgrading Frappe/oauthlib/MCP SDK |

## 23. Future Test Matrix

### Pure canonicalization

- valid HTTPS origin and path;
- scheme/host case normalization;
- IDNA host and IPv6/non-default port;
- default port removal;
- root/non-root trailing slash policy;
- path case preservation and percent-escape normalization;
- reject relative URL, credentials, query, fragment, dot segments, repeated
  slash, controls, non-loopback HTTP, and aliases.

### Authorization lifecycle

- correct resource survives login and consent;
- correct resource with auto-consent;
- missing, blank, malformed, unsupported, duplicate, and multiple resource;
- bound and unbound clients coexist;
- S256 required for bound client; plain/missing rejected;
- authorization code stores exact canonical resource;
- wrong resource during exchange fails without issuing a token;
- correct exchange copies resource and atomically invalidates code;
- sequential and concurrent code replay fail;
- native exact redirect and PKCE-verifier failure remain enforced.

### Refresh and revocation

- refresh preserves client, user, scopes, and resource;
- missing/changed/multiple refresh resource fails;
- authenticated client mismatch fails;
- replacement insertion and old-pair revocation are atomic;
- sequential and concurrent old-refresh replay fail;
- access-token and refresh-token revocation both reject the pair;
- expired/revoked native records never regain validity;
- native cleanup needs no orphan cleanup.

### Bearer verification and identity

- valid opaque token returns exact native User and SDK fields;
- unknown, expired, revoked, unbound, wrong-resource, wrong-client token fails;
- token-record scope is authoritative; current client scopes cannot expand it;
- missing required scope yields 403; correct scopes succeed;
- missing/deleted/disabled/Guest User fails with the same public 401;
- `X-MCP-User-Email` and `MCP_FRAPPE_USER` are ignored in OAuth mode;
- token/access header never appears in logs or errors;
- database/provider failure fails closed.

### Concurrency and isolation

- two users concurrently in async tasks and worker threads;
- two resource policies concurrently;
- sequential reused ASGI worker;
- exception before and after principal application;
- token switch within one stateful MCP session cannot retain the old principal;
- two database connections/processes race one code and one refresh token;
- no Frappe context or SDK auth ContextVar remains after failure.

### Configuration and metadata

- absent mode defaults to trusted header;
- blank/unknown mode fails startup;
- mode-specific required/ignored values;
- issuer/resource/client/site mismatch fails startup;
- OAuth mode cannot start before Custom Fields exist;
- protected-resource metadata resource exactly matches configured URL/path;
- authorization server metadata is reachable and advertises code, refresh,
  S256, and the actually selected client-registration method;
- 401/403 challenges contain resource metadata and required scopes;
- DCR-created/unbound client cannot obtain an MCP-accepted token.

### Regression

- all current trusted-header tests unchanged;
- current stdio behavior unchanged after configured-user resolver move;
- REST backend unchanged;
- unrelated blank-binding Frappe OAuth client flow unchanged;
- ERPNext permission differences for two OAuth users remain effective;
- prepare/approval/confirm policy remains effective for OAuth-authenticated
  writes;
- full established `unittest` suites pass;
- Frappe/oauthlib/MCP SDK upgrade contract test passes.

### Operator-approved live verification

After unit/static work, use a non-production site and dedicated client to prove:

1. schema migration and field metadata;
2. browser login/consent, code exchange, database bindings, refresh rotation,
   replay rejection, revocation, and two-worker behavior;
3. FastMCP discovery, 401/403, initialize, tools/list, and a permission-sensitive
   read through MCP Inspector;
4. ChatGPT predefined-client authorization, correct Frappe user, short-expiry
   refresh, revocation, and reconnect;
5. trusted-header and stdio regression separately.

Live OAuth verification creates clients/codes/tokens and requires explicit
operator approval. It was not performed in this spike.

## 24. Recommended Implementation Sequence

Keep the work split so the compatibility path remains reviewable and OAuth is
never enabled before its audience proof exists.

1. **Task 03 - MCP Identity Auth-Mode Foundation and Trusted-Header / Stdio
   Refactor**
   - add identity-owned settings and configured-user resolver;
   - preserve trusted-header behavior;
   - select runtime path from configured transport/mode and fail closed;
   - add no OAuth mode that can start successfully yet.
2. **Task 04 - Frappe OAuth Resource-Binding Compatibility Implementation**
   - add the three Custom Fields and migration;
   - add canonicalization, validator request hook, document events, locking,
     atomic code consumption/refresh rotation, and focused regression tests;
   - keep FastMCP OAuth mode unavailable.
3. **Task 05 - FastMCP OAuth Resource-Server Integration and E2E Verification**
   - add opaque verifier, SDK `AuthSettings`, protected-resource metadata,
     challenges, and verified-principal runtime consumption;
   - update config/docs/commands as applicable;
   - run static/unit verification, then separately authorized live Frappe,
     Inspector, and ChatGPT verification.

Do not combine Task 04 and Task 05: the resource server must not be exposable
until the authorization server binding has independent tests and migration
gating.

## 25. Limitations / Unverified Items

- No site/database query was run. Effective OAuth Settings, OAuth Client rows,
  installed Custom Fields, DCR state, scopes, token lifetimes, proxy URLs, and
  app-install state on `yob.localhost` remain unverified.
- No OAuth code/token/client was created, refreshed, introspected, or revoked.
- The consent continuation's preservation of `resource` is source-supported but
  needs an integration test for both supported request methods.
- MariaDB/PostgreSQL row-lock behavior and the document-event transaction
  sequence were not exercised live.
- The precise Custom Field removal procedure must be tested on a disposable site
  before documenting rollback commands.
- Frappe 16.34.0's native token storage is the installed authority. Later
  official source may hash tokens or change refresh rotation; the future code
  must adapt through native helpers and contract tests rather than pinning raw
  lookup assumptions.
- MCP SDK 1.29.0 challenge output must be integration-tested, especially scope
  parameters and stateful-session identity switching.
- Frappe does not currently advertise/implement CIMD. DCR is intentionally not
  supported for this first bound-client design. ChatGPT must be configured with
  the exact pre-registered client shown by its management UI.
- Frappe's current authorization response does not advertise RFC 9207 issuer
  identification. OpenAI's callback-ID-specific redirect remains the expected
  compatibility path; exact live UI values must be verified.
- No service, build, migration, cache clear, restart, external write, or live
  OAuth/MCP request was performed.

## 26. Exact Next Tasks

### Task 03 - MCP Identity Auth-Mode Foundation and Trusted-Header / Stdio Refactor

Implement the common auth-mode/settings/principal boundary described in this
report, with zero trusted-header/stdio/REST behavior expansion and with OAuth
startup hard-disabled as `MCP_IDENTITY_CONFIGURATION_ERROR` until the Task 04
capability check exists.

### Task 04 - Frappe OAuth Resource-Binding Compatibility Implementation

Implement exactly the three Custom Fields, canonical resource function,
request-local native-validator substitution, transactional document events,
row-lock/code-consumption/refresh-rotation behavior, and focused tests specified
in sections 7-13 and 23. Do not add FastMCP OAuth exposure or create live OAuth
records.

### Task 05 - FastMCP OAuth Resource-Server Integration and E2E Verification

Implement the Frappe opaque `TokenVerifier`, FastMCP auth/metadata/challenge
assembly, and `mcp_erpnext` verified-principal consumption. Preserve native
permissions and approval guards. Perform record-creating live verification only
as a separately approved operator step after unit/static tests pass.
