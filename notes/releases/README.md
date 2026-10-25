# Automated GitHub releases

[The release workflow](../../.github/workflows/release.yml) publishes a GitHub
Release when an existing tag is pushed. Version tags first build and smoke-test
an image, then publish it as `ghcr.io/delfianto/lychee:<exact-tag>` before the
GitHub release is published. It uses the repository's automatic `GITHUB_TOKEN`
with `contents: write` and `packages: write`; no LLM, paid API, or extra secret
is needed. See the [container guide](../../docker/README.md).

The workflow must be included in the tagged commit, so automatic publishing starts
with tags made after this change reaches the repository.

## Release notes

Notes describe commits between the tagged commit and its nearest earlier ancestor
tag, rather than the current branch tip or whichever release ran most recently.
The first tag includes its full history. Both annotated and lightweight tags work.

- The tag annotation's subject supplies a short introduction.
- Conventional commit subjects become linked entries grouped into features, fixes,
  performance, breaking changes, documentation, and maintenance. Untyped subjects
  remain in a general Changes section. `BREAKING CHANGE:` footers are included.
- Version-bump commits are omitted when there are other change commits. They remain
  a fallback for single-commit releases, as used by several existing beta tags.
- Every release includes a full comparison/history link.

Meaningful commit subjects produce useful notes automatically. An LLM is optional
for writing a more polished summary; this workflow does not infer behavior from
code diffs or invent performance claims.

For a richer introduction, commit `notes/releases/<exact-tag>.md` **before tagging**.
That Markdown replaces the tag-summary introduction; categorized changes and the
comparison link still follow it. For example, `notes/releases/v0.1.0-beta.11.md`
could contain:

```markdown
## Highlights

- Download workers now fetch files within a chapter in parallel.
- Scan and metadata requests share one I/O budget; image workers remain independent.
- One Save workers button persists all four limits together.

## Upgrade notes

Existing worker preferences carry over. No configuration migration is required.
```

The generator reads this file from the tag's Git tree. Uncommitted edits or a file
added on a later commit cannot change an older release's notes.

Preview notes without any GitHub writes:

```sh
python3 .github/scripts/release.py \
  --tag v0.1.0-beta.10 --repository delfianto/lychee \
  --output /tmp/lychee-release-notes.md
```

## Publishing and retries

Push an annotated tag after the normal application checks and version bump:

```sh
git tag -a v0.1.0-beta.11 -m "Faster file downloads and unified worker settings"
git push origin v0.1.0-beta.11
```

Version tags with a prerelease suffix, including `-alpha`, `-beta`, and `-rc`,
are marked as GitHub prereleases. Arbitrary non-version tags are also prereleases.
Stable version tags use GitHub's version-based latest-release selection; prereleases
never replace the latest stable release.

Rerunning the workflow builds/publishes the image and preserves an existing
GitHub release, including edited notes and draft state. This also lets an older
release receive a container image without changing its description. Tag deletion does not publish a release. The workflow validates its
release tooling on relevant main-branch pushes, pull requests, and before publishing.

For an older tag or a missed event, use **Actions → release → Run workflow** on
`main`, then enter the exact existing tag. This supports backfilling tags whose
commits predate the workflow, one tag per invocation.

GitHub does not emit tag-push events when more than three tags are pushed at once.
Push release tags individually, or use the manual workflow for any missing releases.
Tags pushed by another workflow's `GITHUB_TOKEN` also do not trigger new workflows;
use a GitHub App/PAT for such tag pushes or explicitly dispatch this workflow.

## Validation

`just release-check` runs formatting, lint, Python 3.12-compatible type checking,
and offline tests against temporary Git repositories and intercepted API calls.
It is included in `just check`. The GitHub workflow runs the same offline tests
before building containers. Main/PR builds smoke-test the image without registry
credentials or publishing; tag pushes/manual runs smoke-test and publish the exact
tagged application, followed by the GitHub release. Generic tags and tags that
cannot be used as Docker tags still receive GitHub releases without an image.

Reference: [GitHub automated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes),
[workflow triggers](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow),
and [tag-push events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#push).
