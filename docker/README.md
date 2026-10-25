# Container images

The root [Dockerfile](../Dockerfile) builds the Vue UI and installs the locked
Python runtime dependencies in separate stages. The final Debian/Python image
contains the API, compiled UI, AVIF support, and ffmpeg for video posters. One
Uvicorn process serves both the API and SPA, including Vue Router deep links.

## Release pipeline

The [release workflow](../.github/workflows/release.yml) handles containers and
GitHub releases in the same run. This avoids relying on a `release: published`
event from another workflow's `GITHUB_TOKEN`, which does not trigger new runs.

1. Prepare application files from the exact Git tag and verify that backend,
   frontend, and tag versions agree.
2. Build `linux/amd64`, load it locally, and start a temporary container with a
   fresh database and storage in tmpfs.
3. Check startup migrations, health, About/version, the empty library API,
   compiled assets, SPA deep links, API/asset 404s, ffmpeg, and AVIF support.
4. Push `ghcr.io/delfianto/lychee:<exact-tag>` using the built-in GitHub token.
5. Publish the GitHub release with its change notes.

An image failure stops release publication. Main-branch and PR runs build and
smoke-test without publishing or registry credentials. The push step reuses the
builder's tested layers; GitHub Actions caching also reuses layers across runs.
Dependency installs remain cached while their manifest/lock inputs are unchanged.

Only the exact release tag is published: no SHA tags, moving beta alias, or
`latest` alias. This keeps deployment versions explicit and prevents an older
backfill from moving an alias backwards. Non-version tags, and tags containing
characters Docker cannot use, still receive GitHub releases without images.

The application always comes from the requested tag. For backfills, the Dockerfile
and SPA adapter come from the workflow's revision, so releases predating these
files can still be built. Builds reject tag/app-version mismatches. The Docker
context allowlist excludes local environments, dependencies, databases, and host
configuration; the final image contains only runtime application/build artifacts.

## Pulling a version

Once its workflow has built the image, use the exact tag:

```sh
docker pull ghcr.io/delfianto/lychee:v0.1.0-beta.14
```

Persist `/data` for the SQLite database and `/library` for library files,
thumbnails, and other generated storage. The image listens on port 8000 and has
an HTTP health check. Existing deployments can keep their volume paths and
`DATABASE_URL`, `STORAGE_PATH`, and `LYCHEE_SECRET_KEY` settings. See
[backend configuration](../backend/.env.example) for the full environment list.
The deployment runs one Uvicorn worker because task ownership and SSE state are
process-local.

For the existing compose installation, retain its explicit `IMAGE_TAG`, pull that
version from GHCR, and restart the service through its normal deployment tooling.
A local source build is no longer required once that tag's image is published.

GHCR creates new packages as private by default. For anonymous pulls, change the
package visibility to public once in GitHub's package settings; otherwise log in
with a token allowed to read the package. The workflow links the package to this
repository using the OCI source label. If a pre-existing package has independent
permissions, grant this repository Actions write access to that package.
[GitHub container-registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

## Local build and verification

```sh
just image-build v0.1.0-beta.14 lychee:local
just image-smoke lychee:local 0.1.0-beta.12
```

These use the same preparation and smoke scripts as CI. The build checks out
application files into an isolated temporary context, rather than modifying the
working tree. The smoke check uses a unique container name and automatically
removes its container on success or failure; it never mounts the live library
or database.

`just release-check` checks container/release tooling with formatting, lint,
types, and offline tests. The full container build/smoke run is separate so
ordinary `just check` does not require a Docker daemon.

To backfill an already published GitHub release, run **Actions → release → Run
workflow** on `main` with its existing tag. Its curated GitHub release notes
remain intact while the missing image is built and published. Automatic support
starts after these workflow changes are committed/pushed; older releases have
no registry image until their container build has run successfully.
