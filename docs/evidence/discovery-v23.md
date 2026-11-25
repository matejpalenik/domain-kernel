# Document discovery v23 benchmark

`Model.discover()` now uses whole-question discovery, including the
review-example fix. These archived results describe two different live runs.
The fix rerun did not include PDFs and does not replace the full-run figures.

| Run | Drafts saved | Automated reviews finished | Required meanings | PDF checks passed | Provider calls | Metered tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original v23 | 12/12 | 3/12 | 46/60 | 5/17 | 27 | 891,632 |
| v23 with the review-example fix | 3/3 | 3/3 | 10/10 | Not run | 6 | 86,787 |

The original run covered four real procurement PDFs (10 to 173 pages) and
eight controlled Word, Excel, or mixed-format packets. First and final draft
coverage were the same. None of the four PDF reviews finished. Review
completion means the SDK accepted the automated review responses, not that
the draft answered every question or was approved by a human.

The scores measure coverage against a provisional, single-assessor key.
They do not measure precision, validate an automated handoff, or establish
transfer to a new industry. The PDF checks apply only to the four PDF
packets. The [scorecard](discovery-v23-scorecard.json) records the individual
cases, stage calls, and exact-evidence audit. No metered calls were missing
usage in either run.

Both runs used GPT-6 Luna with `xhigh` reasoning through Codex, frozen
captures and competency questions, and a 128-item review limit. The original
used up to eight concurrent packets. The fix reran three packets with up
to three concurrent packets; the provider supplied all three examples.

An independent offline replay passed all five archived replies that previously
failed for a missing example. The SDK used the text of already cited spans.
The raw replies and graphs stayed unchanged and no provider was called.

## Verify the retained results offline

In this workspace the private captures, SQLite receipts, provisional matches
and SHA-256 manifest are retained under
`local/benchmarks/runs/full-source-discovery-comparison`. The verifier also
uses the pinned procurement key under `local/benchmarks/procurement/grader`.
Raw files are not distributed with the SDK. From the repository root, with
the retained bundle present:

```sh
uv run --locked --no-sync python -B -m benchmarks.v23
```

The verifier checks each retained file against its manifest, reconstructs
the initial and final graphs from the saved replies, runs the PDF checks,
and verifies all 15 scorecard rows and the five missing-example cases.
It also reopens and resumes the archived 173-page run with its original
provider profile and no provider. A fresh `Model.discover()` replay on the
same captures opens 65 review cases and leaves deferred question checks
visible. The archived scorecard includes the separately checkpointed work;
the fresh replay does not replace it.
