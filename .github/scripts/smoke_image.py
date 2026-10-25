"""Boot an isolated image and verify migrations, API, SPA routing and media tools."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def smoke(image: str, version: str, revision: str | None = None) -> None:
    name = f"lychee-smoke-{uuid.uuid4().hex[:12]}"
    try:
        docker(
            "run",
            "--detach",
            "--rm",
            "--name",
            name,
            "--publish",
            "127.0.0.1::8000",
            "--tmpfs",
            "/data",
            "--tmpfs",
            "/library",
            image,
        )
        address = docker("port", name, "8000/tcp")
        base = f"http://{address}"
        deadline = time.monotonic() + 90
        while True:
            try:
                with urlopen(f"{base}/api/health", timeout=2) as response:
                    assert json.load(response) == {"status": "ok"}
                break
            except (URLError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("Container did not become healthy") from None
                time.sleep(0.25)
        with urlopen(f"{base}/api/about", timeout=5) as response:
            assert json.load(response)["version"] == version
        with urlopen(f"{base}/api/libraries", timeout=5) as response:
            assert json.load(response) == [], (
                "Smoke tests must start with an empty isolated database"
            )
        for path in ("/", "/settings?section=libraries", "/series/smoke-test"):
            with urlopen(base + path, timeout=5) as response:
                assert "text/html" in response.headers.get("Content-Type", "")
                html = response.read().decode()
                assert '<div id="app">' in html and "/src/main.ts" not in html
        assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
        assert assets, "Built frontend assets are missing"
        for path in assets:
            with urlopen(base + path, timeout=5) as response:
                assert response.read() and "text/html" not in response.headers.get(
                    "Content-Type", ""
                )
        for path in ("/api/not-a-route", "/assets/missing.js", "/missing.ico"):
            try:
                urlopen(base + path, timeout=5).close()
            except HTTPError as error:
                with error:
                    assert error.code == 404
                    if path.startswith("/api/"):
                        assert json.load(error)["error"]["code"] == "not_found"
            else:
                raise AssertionError(f"Missing path returned HTML or success: {path}")
        docker("exec", name, "ffmpeg", "-version")
        docker(
            "exec", name, "python", "-c", "from PIL import features; assert features.check('avif')"
        )
        labels = json.loads(
            docker("image", "inspect", "--format", "{{json .Config.Labels}}", image)
        )
        assert labels["org.opencontainers.image.version"] == version
        if revision:
            assert labels["org.opencontainers.image.revision"] == revision
        print(f"Container smoke check passed: {image} ({version})")
    except BaseException:
        subprocess.run(["docker", "logs", name], check=False)
        raise
    finally:
        subprocess.run(["docker", "rm", "--force", name], check=False, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--revision")
    args = parser.parse_args()
    smoke(args.image, args.version, args.revision)


if __name__ == "__main__":
    main()
