# Repository security settings

These definitions describe the protections for `matejpalenik/domain-kernel`.
Changing a JSON file does not update GitHub automatically. Apply reviewed changes
with an administrator account, then read back the settings to confirm them.

## Branch and tag rules

| Definition | Protection |
| --- | --- |
| `rulesets/main-integrity.json` | Pull requests, resolved conversations and all four CI checks on an up-to-date branch; no bypass; no deletion or force pushes |
| `rulesets/main-review.json` | One approving review, stale approval dismissal and code-owner approval; only `matejpalenik` can bypass, and only through a pull request |
| `rulesets/release-tag-integrity.json` | Prevent moving or deleting `v*` tags; no bypass |
| `rulesets/release-tag-creation.json` | Only `matejpalenik` can create `v*` tags |

The review exception accommodates a sole maintainer who cannot approve their own
pull request. It does not override the separate CI ruleset. Revisit this exception
when another trusted reviewer joins. `CODEOWNERS` covers workflow, dependency and
security-policy changes.

The required checks are `Action dependency lockfile`, `Quality (Python 3.13)`,
`Quality (Python 3.14)` and `Dependency security`. Each must originate from the
GitHub Actions app. Update the ruleset and CI together when renaming jobs.
The initial PR must contain the CI workflow and lockfile so these checks can run.

List existing rulesets with:

```sh
gh api repos/matejpalenik/domain-kernel/rulesets
```

Use `gh api --method PUT repos/matejpalenik/domain-kernel/rulesets/RULESET_ID
--input .github/rulesets/FILE.json` to update an existing definition. Use `POST`
on the collection endpoint only for a new ruleset; do not create duplicates.
Repository administrators can edit these settings; the rules are not protection
against compromise of the administrator account itself.

## Actions and vulnerability reporting

`actions-permissions.json` requires SHA pins and selects an allowlist.
`allowed-actions.json` permits the five action repositories currently in CI, with
no blanket exception for verified publishers or GitHub-owned actions. Review and
update the allowlist when adding an action, including nested actions. Apply the
files to the `/actions/permissions` and `/actions/permissions/selected-actions`
repository API endpoints respectively, using `PUT --input`.

Keep the default workflow token read-only and workflow PR approval disabled.
Only the release job elevates its permissions. Dependabot alerts, automated
security-update PRs and private vulnerability reporting are enabled in GitHub.
Security updates still need review and CI; no auto-merge is configured.

## Maintaining the action lockfile

Use the official `github/gh-actions-lock` extension at v0.4.1. Run
`gh actions-lock --no-narrow` after editing action references, review the diff,
then run `gh actions-lock --verify --no-narrow`. Do not hand-edit `actions.lock`
or use `--accept-moved` in automation. The offline `--verify-local` option only
checks coverage, not upstream provenance.

The required CI check downloads the versioned verifier, checks its pinned hash
and verifies the lockfile without modifying it. Update the verifier version and
checksum together after reviewing a release that meets the seven-day minimum
age. The verifier is a standalone tool, so uv's cooldown does not manage it.

Full SHA references are retained alongside the lockfile. Verification may emit
`sha-as-ref` warnings recommending tag references; preserving the SHA pins here
is intentional. GitHub's separate native "Require lockfile" execution policy has
not been enabled. The lockfile does not cover runner images, shell downloads or
dependencies embedded inside an action's executable.
