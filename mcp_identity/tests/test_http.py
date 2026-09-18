from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from mcp_identity.http import TrustedHeaderAuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import Response


SECRET = "this-is-a-development-only-secret-with-32-chars"


class TrustedHeaderAuthenticationTests(unittest.TestCase):
	def setUp(self):
		async def app(_scope, _receive, _send):
			return None

		self.middleware = TrustedHeaderAuthenticationMiddleware(
			app, shared_secret=SECRET, path="/mcp"
		)

	def _dispatch(self, authorization: str | None) -> Response:
		headers = [] if authorization is None else [(b"authorization", authorization.encode())]
		request = Request(
			{
				"type": "http", "method": "POST", "path": "/mcp", "headers": headers,
				"query_string": b"", "scheme": "http", "server": ("testserver", 80),
				"client": ("testclient", 50000),
			}
		)

		async def call_next(_request):
			return Response(status_code=204)

		return asyncio.run(self.middleware.dispatch(request, call_next))

	def test_missing_malformed_and_wrong_bearer_values_are_rejected(self):
		for authorization in (None, "Basic value", "Bearer wrong-secret"):
			with self.subTest(authorization=authorization):
				self.assertEqual(self._dispatch(authorization).status_code, 401)

	def test_correct_bearer_value_reaches_the_mcp_app(self):
		self.assertEqual(self._dispatch(f"Bearer {SECRET}").status_code, 204)

	@patch("mcp_identity.http.logger")
	def test_authentication_log_never_contains_credentials(self, logger):
		self._dispatch("Bearer incorrect")
		self.assertEqual(logger.warning.call_args.args, ("MCP HTTP authentication failed",))
		self.assertNotIn(SECRET, str(logger.warning.call_args))
		self.assertNotIn("incorrect", str(logger.warning.call_args))
