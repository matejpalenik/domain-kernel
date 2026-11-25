# Issue tracker: GitHub

Issues, specs, and tickets live in `matejpalenik/domain-kernel`. Use `gh` with
`GH_REPO=matejpalenik/domain-kernel` set so commands target this repo. Confirm
the target with `gh repo view --json nameWithOwner` before the first write.
Only publish or modify issues with user authorization.

- Read: `gh issue view <number> --json number,title,body,labels,comments`.
- List: `gh issue list --state open`, with `--label` as needed.
- Publish: `gh issue create --title "..." --body-file <draft>`.
- Update: use `gh issue comment`, `gh issue edit --add-label` or
  `--remove-label`, and `gh issue close`. Give the reason before closing.

## Parent links and blockers

Prefer native GitHub sub-issues and dependencies. In the paths below,
`REPO` is `matejpalenik/domain-kernel`; get an issue's numeric database ID
with `gh api repos/REPO/issues/NUMBER --jq .id`.

- Attach a child: `gh api -X POST repos/REPO/issues/PARENT/sub_issues -F sub_issue_id=CHILD_ID`.
- Add a blocker: `gh api -X POST repos/REPO/issues/CHILD/dependencies/blocked_by -F issue_id=BLOCKER_ID`.
- List open blockers: `gh api --paginate repos/REPO/issues/CHILD/dependencies/blocked_by --jq '.[] | select(.state == "open") | .number'`.
- If native links are unavailable, use `Part of #N` or `Blocked by: #N`
  at the top of the ticket. A ticket is ready when every blocker is closed.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## Wayfinding

Use a `wayfinder:map` issue and child issues labelled `wayfinder:research`,
`wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`. The frontier
is the unassigned open children with no open blockers. Claim with
`gh issue edit <number> --add-assignee @me`; on resolution, record the outcome
and link the closed child from the map's Decisions-so-far.
