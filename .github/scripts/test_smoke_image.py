"""The container check rejects broken routing/versioning and always removes its container."""

from __future__ import annotations

import io
import json
import subprocess
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

import smoke_image


class Response(io.BytesIO):
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        super().__init__(body)
        self.headers = {"Content-Type": content_type}


class SmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls = []
        self.about_version = "1.2.3"
        self.bad_api_fallback = False
        runner = patch.object(smoke_image.subprocess, "run", side_effect=self.docker)
        runner.start()
        self.addCleanup(runner.stop)
        requester = patch.object(smoke_image, "urlopen", side_effect=self.request)
        requester.start()
        self.addCleanup(requester.stop)

    def docker(self, args, **_kwargs):
        self.calls.append(args)
        result = ""
        if args[1] == "port":
            result = "127.0.0.1:18999"
        if args[1:3] == ["image", "inspect"]:
            result = json.dumps(
                {
                    "org.opencontainers.image.version": "1.2.3",
                    "org.opencontainers.image.revision": "revision",
                }
            )
        return subprocess.CompletedProcess(args, 0, stdout=result)

    def request(self, url, **_kwargs):
        path = urlsplit(url).path
        if path == "/api/health":
            return Response(b'{"status":"ok"}')
        if path == "/api/about":
            return Response(json.dumps({"version": self.about_version}).encode())
        if path == "/api/libraries":
            return Response(b"[]")
        if path in ("/assets/missing.js", "/missing.ico", "/api/not-a-route"):
            if path == "/api/not-a-route" and self.bad_api_fallback:
                return Response(b"<html>Wrong SPA fallback</html>", "text/html")
            raise HTTPError(
                url, 404, "Not found", Message(), io.BytesIO(b'{"error":{"code":"not_found"}}')
            )
        if path.startswith("/assets/"):
            return Response(b"compiled asset", "text/javascript")
        return Response(
            b'<html><div id="app"></div><script src="/assets/app.js"></script></html>', "text/html"
        )

    def assert_removed(self) -> None:
        cleanup = [args for args in self.calls if args[1:3] == ["rm", "--force"]]
        self.assertEqual(len(cleanup), 1)
        self.assertTrue(cleanup[0][-1].startswith("lychee-smoke-"))

    def test_healthy_image_checks_all_routes_and_is_removed(self) -> None:
        smoke_image.smoke("lychee:test", "1.2.3", "revision")
        self.assert_removed()

    def test_wrong_version_fails_and_is_removed(self) -> None:
        self.about_version = "0.0.1"
        with self.assertRaises(AssertionError):
            smoke_image.smoke("lychee:test", "1.2.3")
        self.assert_removed()

    def test_api_must_not_return_the_spa_for_an_unknown_route(self) -> None:
        self.bad_api_fallback = True
        with self.assertRaisesRegex(AssertionError, "Missing path"):
            smoke_image.smoke("lychee:test", "1.2.3")
        self.assert_removed()

    def test_unhealthy_container_times_out_and_is_removed(self) -> None:
        with (
            patch.object(smoke_image, "urlopen", side_effect=URLError("Not ready")),
            patch.object(smoke_image.time, "monotonic", side_effect=[0, 91]),
            self.assertRaises(TimeoutError),
        ):
            smoke_image.smoke("lychee:test", "1.2.3")
        self.assert_removed()
