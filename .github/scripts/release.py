"""Generate tag-based release notes; publish only when explicitly requested."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
VERSION = re.compile(r"^v?\d+\.\d+\.\d+(?P<pre>-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
CONVENTIONAL = re.compile(r"^(\w+)(?:\(([^)]+)\))?(!)?:\s*(.+)$")
CATEGORIES = {
    "feat": "Features",
    "fix": "Fixes",
    "perf": "Performance",
    "docs": "Documentation",
    "refactor": "Maintenance",
    "test": "Maintenance",
    "build": "Maintenance",
    "ci": "Maintenance",
    "chore": "Maintenance",
    "bench": "Maintenance",
    "release": "Maintenance",
}
ORDER = (
    "Breaking changes",
    "Features",
    "Fixes",
    "Performance",
    "Changes",
    "Documentation",
    "Maintenance",
)


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check)


def markdown(text: str) -> str:
    return re.sub(r"([\\`*_{}\[\]<>])", r"\\\1", text).replace("@", "&#64;")


@dataclass(frozen=True)
class Release:
    tag: str
    body: str
    prerelease: bool

    def payload(self) -> dict[str, str | bool]:
        return {
            "tag_name": self.tag,
            "name": f"Lychee {self.tag}",
            "body": self.body,
            "draft": False,
            "prerelease": self.prerelease,
            # Let GitHub select latest by version for stable releases; beta and
            # arbitrary non-version tags must never displace a stable release.
            "make_latest": "false" if self.prerelease else "legacy",
        }


def generate(tag: str, repository: str, server: str = "https://github.com") -> Release:
    if git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        raise ValueError("Release notes require full history and tags (checkout fetch-depth: 0)")
    ref = f"refs/tags/{tag}"
    if git("check-ref-format", ref, check=False).returncode:
        raise ValueError(f"Invalid tag: {tag!r}")
    target = git("rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    if target.returncode:
        raise ValueError(f"Tag does not exist: {tag!r}")
    commit = target.stdout.strip()
    # Describe the parent, rather than HEAD, so an older/manual release gets its
    # own predecessor and never includes commits from a newer branch tip.
    described = git("describe", "--tags", "--abbrev=0", f"{commit}^", check=False)
    previous = described.stdout.strip() if described.returncode == 0 else ""
    revision = f"refs/tags/{previous}..{commit}" if previous else commit
    url = f"{server.rstrip('/')}/{repository}"
    curated = git("show", f"{ref}:notes/releases/{tag}.md", check=False)
    intro = curated.stdout.strip() if curated.returncode == 0 else ""
    if not intro and git("cat-file", "-t", ref).stdout.strip() == "tag":
        intro = markdown(git("for-each-ref", "--format=%(contents:subject)", ref).stdout.strip())

    history = git(
        "log", "--no-merges", "--reverse", "--format=%H%x00%s%x00%b%x00", revision
    ).stdout.split("\0")
    entries = []
    for offset in range(0, len(history) - 2, 3):
        sha, subject, body = (part.strip() for part in history[offset : offset + 3])
        match = CONVENTIONAL.match(subject)
        kind, scope, breaking, title = match.groups() if match else ("", "", "", subject)
        category = CATEGORIES.get(kind, "Changes")
        footer = re.search(r"(?m)^BREAKING(?: CHANGE|-CHANGE):\s*(.+)$", body)
        if breaking or footer:
            category = "Breaking changes"
        elif scope == "deps" or kind == "deps":
            category = "Maintenance"
        label = subject if kind not in CATEGORIES else (f"{scope}: {title}" if scope else title)
        if footer:
            label += f" — {footer.group(1)}"
        entries.append((kind, category, f"- {markdown(label)} ([{sha[:7]}]({url}/commit/{sha}))"))
    # Version-bump commits add noise when there are actual change commits. Keep
    # them as a fallback for the project's existing single-commit releases.
    if any(kind != "release" for kind, _, _ in entries):
        entries = [entry for entry in entries if entry[0] != "release"]
    groups: dict[str, list[str]] = defaultdict(list)
    for _, category, line in entries:
        groups[category].append(line)
    sections = [intro] if intro else []
    sections.append("## Changes")
    for category in ORDER:
        if groups[category]:
            sections.append(f"### {category}\n\n" + "\n".join(groups[category]))
    if not entries:
        sections.append("No source changes since the previous tag.")
    if previous:
        comparison = f"{quote(previous, safe='')}...{quote(tag, safe='')}"
        sections.append(
            f"**Full changelog:** [{markdown(previous)} → {markdown(tag)}]({url}/compare/{comparison})"
        )
    else:
        sections.append(f"**Full history:** [{markdown(tag)}]({url}/commits/{quote(tag, safe='')})")
    version = VERSION.fullmatch(tag)
    return Release(tag, "\n\n".join(sections) + "\n", version is None or bool(version.group("pre")))


def publish(release: Release, repository: str, token: str, api_url: str) -> str:
    if not token:
        raise ValueError("GITHUB_TOKEN is required to publish a release")
    endpoint = f"{api_url.rstrip('/')}/repos/{repository}/releases"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "lychee-release",
    }
    request = Request(f"{endpoint}/tags/{quote(release.tag, safe='')}", headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            existing = json.load(response)
        print("Release already exists; preserving its notes and publication state.")
        return existing["html_url"]
    except HTTPError as exc:
        if exc.code != 404:
            raise
    request = Request(
        endpoint,
        data=json.dumps(release.payload()).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)["html_url"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY"),
        required="GITHUB_REPOSITORY" not in os.environ,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    release = generate(
        args.tag, args.repository, os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    )
    if args.output:
        args.output.write_text(release.body)
    else:
        print(release.body)
    if args.publish:
        print(
            publish(
                release,
                args.repository,
                os.environ.get("GITHUB_TOKEN", ""),
                os.environ.get("GITHUB_API_URL", "https://api.github.com"),
            )
        )


if __name__ == "__main__":
    main()
