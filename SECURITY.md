# Security policy

## Report a vulnerability privately

Email [Matej Palenik](mailto:matejpale@gmail.com), the maintainer listed in the
package metadata. Please do not disclose an unpatched vulnerability in a public
issue or pull request.

Include the affected version or commit, optional extras in use, a description of
the impact, and a minimal reproduction. Remove credentials, personal data and
customer documents from the report. If GitHub's private "Report a vulnerability"
option is enabled for this repository, it can also be used.

The maintainer will assess reports, coordinate reproduction and remediation with
the reporter, and publish relevant fix and mitigation information through release
notes and security advisories. Response and remediation times are best effort;
the project currently offers no contractual response-time guarantee.

## Current support scope

Domain Kernel is a pre-alpha, non-commercial open-source SDK. No stable release or
guaranteed security-support period has been declared yet. Evaluation should use the
latest available revision or prerelease. A stable or commercial release needs an
explicit supported-version policy and security-support period.

The configured CI audit checks the current committed dependency lockfile on pull
requests, main pushes, release tags and a weekly schedule. It does not continuously
rescan historical releases or the dependency versions resolved by consuming
applications. Consumers own the monitoring of their deployed environments.

## Dependency update policy

The project configures uv to exclude registry artifacts uploaded less than seven
days ago. This covers transitive dependencies and optional, development and build
requirements. Artifacts without upload timestamps are unavailable under this
policy. Use `uv sync --locked`; checks and releases must not regenerate the lock.
Review intentional dependency changes and run the project checks and
`uv audit --locked` before merging them.

Dependabot uses the same seven-day delay for ordinary uv and GitHub Actions
version updates. Its security-update pull requests bypass Dependabot's cooldown;
they do not automatically override the uv policy or authorize merging.
For an urgent security fix, assess the risk of waiting and verify the upstream
release before approving a narrow, temporary exception. Record the reason and
expiry, then remove the exception once the artifact is old enough. The previous
Tornado exception is recorded below.

This delay gives newly compromised releases time to be detected; it cannot prove
that a dependency is safe. The uv rule covers registry resolution, not Git or
direct-URL dependencies, local code, downloaded model assets, Python interpreters
or independently installed tools. Review those separately. SDK consumers must
configure their own dependency policy.

References:

- [uv dependency cooldowns](https://docs.astral.sh/uv/concepts/resolution/#dependency-cooldowns)
- [uv and Dependabot cooldowns](https://docs.astral.sh/uv/guides/integration/dependabot/#dependency-cooldown)
- [Dependabot cooldown options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#cooldown-)

### Approved temporary exception: Tornado 6.6.1

On 2026-11-16, maintainer Matej Palenik explicitly approved a manual upgrade from
Tornado 6.6 to 6.6.1 before its seven-day cooldown elapsed. After verifying that a
CLI-only override makes normal locked commands fail, the maintainer approved a
temporary Tornado-only configuration exception to keep those checks working.
This addresses
[GHSA-5cjw-f85j-cv6r](https://github.com/advisories/GHSA-5cjw-f85j-cv6r).
The [upstream release notes](https://www.tornadoweb.org/en/stable/releases/v6.6.1.html)
and PyPI publication timestamps were reviewed. The maintainer accepts the shorter
observation period for this security fix rather than retaining the known vulnerable
version until the cooldown elapses.

The exception covers only resolving and installing `tornado==6.6.1`, including an
isolated verification of the update. `tool.uv.exclude-newer-package` sets Tornado's
cutoff to `2026-11-09T21:10:00Z`; the upgrade selects exactly 6.6.1. This fixed
cutoff does not admit later releases. All other packages retain the seven-day
policy. A notebook dependency minimum prevents returning to the vulnerable version.

Approval expired at **2026-11-16 21:10 UTC**, when the reviewed release artifacts
aged past seven days. On 2026-11-17, DK-042 removed the package-specific setting
and regenerated the lockfile with:

```sh
uv add --group notebook 'tornado>=6.6.1' --no-sync
uv lock --check
uv sync --locked --group notebook
uv audit --locked
```

The Tornado minimum remains in the notebook dependency group. The generated lockfile
uses the ordinary seven-day registry cooldown.

## Repository and workflow protections

Changes to `main` require a pull request, up-to-date passing CI checks and resolved
review conversations. A separate rule requires maintainer approval and code-owner
review for security-sensitive files. The sole maintainer can bypass that review
rule when merging a pull request, but cannot bypass the required checks. Release
tags matching `v*` can only be created by the maintainer and cannot be moved or
deleted under the active rules.

GitHub Actions is restricted to the reviewed action repositories and requires
full SHA pins. The generated `actions.lock` records action commits, upstream
references and repository identities; a required CI job checks its provenance.
This is CI verification, not a claim that GitHub's native "Require lockfile"
execution policy is enabled. See [the settings definitions and maintenance
instructions](.github/security-settings.md).

## Supply-chain evidence and CRA scope

The release workflow produces CycloneDX dependency inventories, checksums and signed
artifact provenance. Their scope and verification instructions are documented in
the [README](README.md#dependencies-and-software-bill-of-materials-sbom). Generated
SBOMs remain release assets rather than committed source files.

These controls support supply-chain review; the project does not claim CRA
conformity or certification. The European Commission distinguishes non-commercial
open-source development, commercial manufacturers and open-source software
stewards. Reassess applicability if the project's distribution, monetisation or
organisational role changes. Enterprise integrators must assess their own products
and obligations.

For an in-scope offering, maintainers must establish the applicable risk assessment,
support period, vulnerability-handling and reporting processes, technical
documentation and conformity assessment before making a compliance claim. An SBOM
and passing CI are only part of that evidence.

References:

- [European Commission: CRA and open source](https://digital-strategy.ec.europa.eu/en/policies/cra-open-source)
- [European Commission: CRA implementation dates](https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act)
- [Regulation (EU) 2024/2847](https://eur-lex.europa.eu/eli/reg/2024/2847/oj)

## Website and JavaScript tooling

The documentation workspace uses pnpm with a seven-day minimum release age
(`minimumReleaseAge: 10080`), strict enforcement and rejection of missing publish
timestamps. `trustLockfile: false` reapplies policy to the locked dependency graph.
Provenance downgrade protection has no age-based bypass. Transitive exotic sources
are blocked and dependency build scripts require explicit review. No build scripts
are currently approved. Use frozen installs in CI and never hand-edit the lockfile.

The scoped resolver pin selects a compatible version that passes provenance checks.
The scoped PostCSS selector and minimatch upgrades address
[GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf) and
[GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249).
These pins do not bypass cooldown or provenance checks; remove them when upstream
ranges select compatible fixed versions. The documentation lint, typecheck and
build gates verify the selected tooling together.

`pnpm audit:docs` includes development dependencies. npm Dependabot follows the
same weekly schedule and seven-day cooldown. Review security-update PRs against
these install policies as well; an updater's exception does not authorize a local
or CI bypass.

GitHub Pages publication is manual from `main`, after required checks, with
write permissions confined to the deployment job. The website's dependencies do
not enter the Python wheel, source distribution or Python release SBOM scopes.
