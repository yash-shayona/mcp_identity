"""Canonical MCP OAuth resource identifiers."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import unquote, urlsplit, urlunsplit

_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class MCPResourceError(ValueError):
    """Raised when a configured or requested MCP resource is not canonicalizable."""


def canonicalize_mcp_resource(value: str, *, allow_loopback_http: bool = False) -> str:
    """Return the one canonical URL used as an MCP OAuth resource identifier."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise MCPResourceError(
            "MCP resource must be a non-empty URL without surrounding whitespace."
        )
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise MCPResourceError("MCP resource must not contain control characters.")
    if "?" in value:
        raise MCPResourceError("MCP resource must not contain a query.")
    if "#" in value:
        raise MCPResourceError("MCP resource must not contain a fragment.")

    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise MCPResourceError("MCP resource is not a valid absolute URL.") from error

    scheme = parsed.scheme.lower()
    if not scheme or not parsed.netloc or scheme not in {"http", "https"}:
        raise MCPResourceError("MCP resource must be an absolute HTTP(S) URL.")
    if (
        parsed.username is not None
        or parsed.password is not None
        or "@" in parsed.netloc
    ):
        raise MCPResourceError("MCP resource must not contain user information.")

    try:
        host = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise MCPResourceError(
            "MCP resource contains an invalid host or port."
        ) from error
    if not host:
        raise MCPResourceError("MCP resource must contain a host.")
    if parsed.netloc.endswith(":"):
        raise MCPResourceError("MCP resource contains an empty port.")

    serialized_host, is_loopback = _canonical_host(host)
    if scheme == "http" and not (allow_loopback_http and is_loopback):
        raise MCPResourceError(
            "HTTP MCP resources are allowed only for explicit loopback development."
        )

    default_port = 443 if scheme == "https" else 80
    authority = (
        serialized_host if port in {None, default_port} else f"{serialized_host}:{port}"
    )
    path = _canonical_path(parsed.path)
    return urlunsplit((scheme, authority, path, "", ""))


def _canonical_host(host: str) -> tuple[str, bool]:
    if "%" in host:
        raise MCPResourceError("Scoped IP literals are not valid MCP resource hosts.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if host.endswith("."):
            raise MCPResourceError(
                "MCP resource DNS host must not use a trailing-dot alias."
            )
        try:
            dns_host = host.encode("idna").decode("ascii").lower()
        except UnicodeError as error:
            raise MCPResourceError(
                "MCP resource contains an invalid DNS host."
            ) from error
        labels = dns_host.split(".")
        if (
            not dns_host
            or len(dns_host) > 253
            or any(not _DNS_LABEL.fullmatch(label) for label in labels)
        ):
            raise MCPResourceError("MCP resource contains an invalid DNS host.")
        return dns_host, dns_host == "localhost" or dns_host.endswith(".localhost")

    serialized = address.compressed.lower()
    if address.version == 6:
        serialized = f"[{serialized}]"
    return serialized, address.is_loopback


def _canonical_path(path: str) -> str:
    if not path or path == "/":
        return ""
    if not path.startswith("/") or "//" in path or "\\" in path:
        raise MCPResourceError("MCP resource path contains an unsupported alias.")

    position = 0
    pieces: list[str] = []
    while position < len(path):
        if path[position] != "%":
            pieces.append(path[position])
            position += 1
            continue
        match = _PERCENT_ESCAPE.match(path, position)
        if not match:
            raise MCPResourceError(
                "MCP resource path contains an invalid percent escape."
            )
        pieces.append(match.group(0).upper())
        position = match.end()

    canonical = "".join(pieces)
    for segment in canonical.split("/"):
        if unquote(segment).casefold() in {".", ".."}:
            raise MCPResourceError("MCP resource path must not contain dot segments.")
    if canonical.endswith("/"):
        canonical = canonical[:-1]
    return canonical
