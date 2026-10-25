"""Prepare exact tagged application sources with the workflow's container recipe."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

import release


def metadata(tag: str | None, repository: str) -> dict[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected repository in owner/name format")
    ref = f"refs/tags/{tag}" if tag else "HEAD"
    target = release.git("rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    if target.returncode:
        raise ValueError(f"Source ref does not exist: {ref}")
    # Generic tags still get GitHub releases, but only version tags name images.
    if tag and (
        release.VERSION.fullmatch(tag) is None
        or not re.fullmatch(r"[\w][\w.-]{0,127}", tag, flags=re.ASCII)
    ):
        return {"build": "false"}
    revision = target.stdout.strip()
    version = json.loads(release.git("show", f"{revision}:frontend/package.json").stdout)["version"]
    image_tag = tag or f"v{version}"
    if not release.VERSION.fullmatch(f"v{version}") or not re.fullmatch(
        r"[\w][\w.-]{0,127}", image_tag, flags=re.ASCII
    ):
        raise ValueError(f"App version cannot be used as an image tag: {version!r}")
    if tag and tag.removeprefix("v") != version:
        raise ValueError(f"Release tag {tag!r} does not match app version {version!r}")
    runtime = ast.parse(release.git("show", f"{revision}:backend/src/core/version.py").stdout)
    runtime_version = next(
        ast.literal_eval(node.value)
        for node in runtime.body
        if isinstance(node, ast.Assign)
        and any(isinstance(name, ast.Name) and name.id == "VERSION" for name in node.targets)
    )
    if runtime_version != version:
        raise ValueError("Backend and frontend versions disagree")
    return {
        "build": "true",
        "version": version,
        "revision": revision,
        "source": f"https://github.com/{repository}",
        "image": f"ghcr.io/{repository.lower()}:{image_tag}",
    }


def prepare(context: Path, revision: str) -> None:
    if context.exists() and any(context.iterdir()):
        raise ValueError("Build context must be empty")
    context.mkdir(parents=True, exist_ok=True)
    # git archive excludes uncommitted files, local .env files, node_modules and
    # virtualenvs. The Docker allowlist provides a second boundary for build input.
    with tempfile.TemporaryFile() as archive:
        subprocess.run(
            ["git", "archive", "--format=tar", revision, "backend", "frontend", "LICENSE"],
            cwd=release.ROOT,
            stdout=archive,
            check=True,
        )
        archive.seek(0)
        with tarfile.open(fileobj=archive) as source:
            source.extractall(context, filter="data")
    # Keeping the recipe from the running workflow enables backfills for tags
    # that predate the in-repository Dockerfile. App code always comes from the tag.
    for name in ("Dockerfile", ".dockerignore", "docker/deployment.py"):
        target = context / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(release.ROOT / name, target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    parser.add_argument(
        "--repository", default=os.environ.get("GITHUB_REPOSITORY", "delfianto/lychee")
    )
    parser.add_argument("--context", type=Path)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--build", metavar="LOCAL_IMAGE")
    args = parser.parse_args()
    info = metadata(args.tag, args.repository)
    if info["build"] == "true":
        if args.context:
            prepare(args.context, info["revision"])
        if args.build:
            with tempfile.TemporaryDirectory(prefix="lychee-image-") as temporary:
                context = Path(temporary)
                prepare(context, info["revision"])
                subprocess.run(
                    [
                        "docker",
                        "buildx",
                        "build",
                        "--load",
                        "--platform",
                        "linux/amd64",
                        "--tag",
                        args.build,
                        "--build-arg",
                        f"LYCHEE_VERSION={info['version']}",
                        "--build-arg",
                        f"LYCHEE_REVISION={info['revision']}",
                        "--build-arg",
                        f"LYCHEE_REPOSITORY={info['source']}",
                        str(context),
                    ],
                    check=True,
                )
    elif args.build:
        raise ValueError("Only version tags can be built as release images")
    if args.github_output:
        with args.github_output.open("a") as output:
            for key, value in info.items():
                output.write(f"{key}={value}\n")
    print(json.dumps(info))


if __name__ == "__main__":
    main()
