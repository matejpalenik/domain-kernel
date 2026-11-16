# Releasing Domain Kernel

This guide explains how to prepare, validate, and publish a Domain Kernel release through GitHub Actions.

Releases are built from protected Git tags and include reproducible Python distributions, CycloneDX Software Bills of Materials (SBOMs), checksums, and signed provenance attestations.

**Prerequisites**

- Python 3.13 and 3.14
- [uv](https://docs.astral.sh/uv/) 0.13.7
- GitHub CLI (`gh`) with the required repository permissions
- A POSIX-compatible shell

Run all commands from the repository root, using the development environment described in [CONTRIBUTING.md](../CONTRIBUTING.md).

> [!NOTE]
> Releases are currently distributed through GitHub Releases. Publishing to PyPI is not yet configured.

## 1. Prepare the Release

Create a feature branch and update `project.version` in `pyproject.toml` to the intended release version.

For early development releases, use a prerelease version such as `0.1.0a1`.

Update the lockfile and synchronize your environment:

```sh
uv lock
uv sync --locked
```

Review and commit `pyproject.toml` and `uv.lock` together.

**Important:** Lockfile changes must be intentional and reviewed. CI and release jobs must never modify the lockfile. Keep unrelated dependency upgrades out of the release preparation unless explicitly included in the reviewed changes.

## 2. Run the Release Checks

Before merging, verify that the release passes all quality, security, and dependency checks.

```sh
uv lock --check
uv sync --locked
uv run --locked pre-commit run --all-files
uv run --locked pytest --cov --cov-report=term-missing
uv audit --locked
gh actions-lock --verify --no-narrow
```

These checks cover code quality, tests, dependency vulnerabilities, and GitHub Actions integrity.

The dependency audit includes all locked optional extras and development groups without requiring those packages to be installed.

Both `uv audit` and the GitHub Actions verification require network access. If necessary, install the pinned GitHub CLI extension following the [contributor instructions](../CONTRIBUTING.md#update-github-actions).

### Verify Supported Python Versions

Repeat the Python quality checks, distribution builds, and wheel verification using both supported Python versions:

- Python 3.13: `UV_PYTHON=3.13`
- Python 3.14: `UV_PYTHON=3.14`

After testing, restore your default environment:

```sh
unset UV_PYTHON
uv sync --locked
```

The release workflow generates and validates SBOMs using Python 3.13.

## 3. Build and Verify the Distributions

### Check Build Reproducibility

Build the wheel and source distribution twice in separate directories, then compare the resulting files.

Use a fresh temporary directory to prevent artifacts from previous builds from affecting verification.

```sh
export SOURCE_DATE_EPOCH=0

release_check_dir="$(mktemp -d)"

uv build --no-sources --out-dir "$release_check_dir/dist"
uv build --no-sources --out-dir "$release_check_dir/rebuild"

for artifact in "$release_check_dir"/dist/*.whl "$release_check_dir"/dist/*.tar.gz; do
  cmp "$artifact" "$release_check_dir/rebuild/$(basename "$artifact")"
done
```

The build backend is pinned in `pyproject.toml`. By default, `uv build` builds the wheel from the source distribution.

Matching artifacts confirm reproducibility for the current checkout and build environment.

Keep the same shell session for the remaining verification steps so that `$release_check_dir` remains available.

### Verify the Installed Wheel

Install the wheel and its hash-verified runtime dependencies into an isolated environment outside the source tree.

```sh
uv export --locked --no-dev --no-default-groups --no-emit-project --format requirements.txt --output-file "$release_check_dir/runtime-requirements.txt" > /dev/null

uv venv "$release_check_dir/wheel-env"

uv pip install \
  --python "$release_check_dir/wheel-env/bin/python" \
  --require-hashes \
  --requirements "$release_check_dir/runtime-requirements.txt"

uv pip install \
  --python "$release_check_dir/wheel-env/bin/python" \
  --no-deps \
  "$release_check_dir"/dist/*.whl
```

Verify that the installed package exposes its expected public API and includes the `py.typed` marker:

```sh
(
  cd "$release_check_dir"

  ./wheel-env/bin/python -I - <<'PY'
from importlib.resources import files

from domain_kernel import ModelId, ModelScope, ProjectId

scope = ModelScope(
    project_id=ProjectId(value="release-check"),
    model_id=ModelId(value="sales"),
)

assert scope.model_id.value == "sales"
assert files(anchor="domain_kernel").joinpath("py.typed").is_file()
PY
)
```

This verifies the installed distribution independently of the source checkout, using only runtime dependencies.

## 4. Generate and Validate the SBOMs

Each release includes two CycloneDX 1.5 dependency inventories:

| File | Contents |
|---|---|
| `sbom-core.cdx.json` | Core SDK runtime dependencies |
| `sbom-all-extras.cdx.json` | Core dependencies and all optional runtime extras |

Generate both inventories from the locked dependency graph:

```sh
uv export \
  --locked --no-dev --no-default-groups \
  --format cyclonedx1.5 \
  --output-file "$release_check_dir/dist/sbom-core.cdx.json" > /dev/null

uv export \
  --locked --no-dev --no-default-groups --all-extras \
  --format cyclonedx1.5 \
  --output-file "$release_check_dir/dist/sbom-all-extras.cdx.json" > /dev/null
```

Validate them against the official CycloneDX schema:

```sh
uv run --locked check-jsonschema \
  --schemafile https://cyclonedx.org/schema/bom-1.5.schema.json \
  "$release_check_dir"/dist/sbom-*.cdx.json
```

Schema validation requires network access and prevents publication if either inventory is invalid.

### SBOM Scope and Limitations

Both inventories describe the cross-platform dependency graph recorded in `uv.lock`, excluding development dependencies.

They do not inspect the built distributions or include external model weights, system libraries, or dependencies downloaded after installation.

The current exports include package identities, dependency relationships, and distribution hashes, but omit dependency licence and supplier metadata.

Because native SBOM export and dependency auditing are currently marked experimental by uv, CI uses a pinned, verified version and validates the generated inventories.

For additional details, see:

- [Dependencies and SBOM](../README.md#dependencies-and-software-bill-of-materials-sbom)
- [Security and compliance scope](../SECURITY.md)

> [!IMPORTANT]
> Do not commit generated SBOMs or local verification artifacts. The release workflow generates its own artifacts from the tagged commit.

## 5. Merge and Tag the Release

Once all checks pass, merge the release preparation pull request into `main`.

Update your local checkout:

```sh
git switch main
git pull --ff-only
```

Confirm that the lockfile is valid and the checkout contains the intended release version and commit:

```sh
uv lock --check
uv version --locked --short
git log -1 --oneline
```

### Create the Release Tag

Create an annotated tag matching the package version:

```sh
release_tag="v$(uv version --locked --short)"

git tag -a "$release_tag" -m "Release $release_tag"
git push origin "$release_tag"
```

Pushing the tag triggers the GitHub Release workflow.

**Tag protection:** Only maintainers can create `v*` tags. Repository rules prevent existing tags from being moved or deleted, and CI rejects tags that do not match `project.version`.

See [Repository Security Settings](../.github/security-settings.md) for details.

## 6. Automated Release Publication

The [GitHub Actions workflow](../.github/workflows/ci.yml) runs for pull requests targeting `main`, pushes to `main`, and `v*` tags.

For tagged releases, publication begins only after the required checks succeed:

1. GitHub Actions lock verification
2. Python 3.13 and 3.14 quality checks
3. Dependency vulnerability audit
4. Distribution and SBOM validation

The release job then retrieves the validated artifacts from the Python 3.13 job.

### Published Artifacts

Each successful release contains:

| Artifact | Purpose |
|---|---|
| Python wheel (`.whl`) | Installable SDK distribution |
| Source distribution (`.tar.gz`) | Source package |
| `sbom-core.cdx.json` | Core runtime dependency inventory |
| `sbom-all-extras.cdx.json` | Complete optional runtime dependency inventory |
| `SHA256SUMS` | Checksums for the four artifacts above |

The workflow also generates signed GitHub provenance attestations for all five files.

### Publication and Security

The workflow creates a draft GitHub Release, uploads the artifacts, and publishes it once the required operations succeed.

- Alpha, beta, release-candidate, and development versions are automatically marked as prereleases.
- Attestation failures prevent publication.
- Upload failures leave the release in draft state.
- Existing published releases are never overwritten automatically.

Only the release job receives the following permissions:

- `contents: write`
- `id-token: write`
- `attestations: write`

Provenance signing uses GitHub's OIDC identity and short-lived tokens, without storing a dedicated signing key.

Future PyPI publication should be implemented separately using Trusted Publishing.

## 7. Verify the Published Release

After the workflow completes:

1. Confirm that all required GitHub Actions jobs succeeded.
2. Open the published release in [GitHub Releases](https://github.com/matejpalenik/domain-kernel/releases).
3. Confirm that all five expected artifacts are present.
4. Verify the published provenance attestations and checksums.

Download the release files into the same directory, then run:

```sh
gh attestation verify SHA256SUMS --repo matejpalenik/domain-kernel
sha256sum --check SHA256SUMS
```

On macOS, replace the second command with:

```sh
shasum --algorithm 256 --check SHA256SUMS
```

Individual distributions and SBOMs can also be verified using `gh attestation verify`.

> [!NOTE]
> Provenance attestations establish artifact origin and integrity. They do not guarantee that an SBOM is complete or that its dependencies are free from vulnerabilities.

### Handling Release Failures

If publication fails, inspect the failing workflow job and any existing draft release before retrying.

Do not move protected tags or overwrite published artifacts as a routine recovery procedure. Investigate the failure and determine the appropriate corrective action before attempting publication again.

## Documentation publication

Documentation is published independently of Python releases. Ordinary pushes,
pull requests, schedules and release tags never deploy the website. Follow
[Documentation development and publication](documentation.md) to request a manual
publication from `main`, verify its result or recover a faulty publication.
