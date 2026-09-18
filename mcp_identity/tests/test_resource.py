from __future__ import annotations

import unittest

from mcp_identity.resource import MCPResourceError, canonicalize_mcp_resource


class CanonicalMCPResourceTests(unittest.TestCase):
	def test_canonical_https_resources(self):
		cases = {
			"HTTPS://MCP.Example.COM:443/mcp/": "https://mcp.example.com/mcp",
			"https://mcp.example.com": "https://mcp.example.com",
			"https://mcp.example.com/": "https://mcp.example.com",
			"https://mcp.example.com:8443/Mcp": "https://mcp.example.com:8443/Mcp",
			"https://bücher.example/mcp": "https://xn--bcher-kva.example/mcp",
			"https://[2001:0db8::1]:443/mcp": "https://[2001:db8::1]/mcp",
			"https://mcp.example.com/a%2fb": "https://mcp.example.com/a%2Fb",
		}
		for value, expected in cases.items():
			with self.subTest(value=value):
				self.assertEqual(canonicalize_mcp_resource(value), expected)

	def test_loopback_http_requires_explicit_allowance(self):
		for value in ("http://localhost:80/mcp", "http://dev.localhost/mcp", "http://127.0.0.1/mcp"):
			with self.subTest(value=value):
				with self.assertRaises(MCPResourceError):
					canonicalize_mcp_resource(value)
				self.assertTrue(
					canonicalize_mcp_resource(value, allow_loopback_http=True).startswith("http://")
				)

	def test_invalid_or_ambiguous_resources_are_rejected(self):
		values = (
			"/mcp",
			"ftp://mcp.example.com/mcp",
			"https://user@mcp.example.com/mcp",
			"https://mcp.example.com/mcp?x=1",
			"https://mcp.example.com/mcp#fragment",
			"https://mcp.example.com/mcp\n",
			"https://mcp.example.com/a/../mcp",
			"https://mcp.example.com/a/%2e%2e/mcp",
			"https://mcp.example.com//mcp",
			"https://mcp.example.com/a\\mcp",
			"https://mcp.example.com/%xx",
			"https://mcp.example.com:/mcp",
			"https://mcp.example.com./mcp",
			"https://bad_host.example/mcp",
			"http://example.com/mcp",
		)
		for value in values:
			with self.subTest(value=value), self.assertRaises(MCPResourceError):
				canonicalize_mcp_resource(value, allow_loopback_http=True)

	def test_path_case_and_domain_aliases_remain_distinct(self):
		self.assertNotEqual(
			canonicalize_mcp_resource("https://mcp.example.com/MCP"),
			canonicalize_mcp_resource("https://mcp.example.com/mcp"),
		)
		self.assertNotEqual(
			canonicalize_mcp_resource("https://mcp.example.com/mcp"),
			canonicalize_mcp_resource("https://alias.example.com/mcp"),
		)
