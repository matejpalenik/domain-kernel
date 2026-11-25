# Full AI Act walkthrough acceptance

The [coverage ledger](coverage.json) records the pinned edition, expected outputs,
and supporting verification for all 43 v1 capability IDs.

## Publisher PDF and Luna

The live check reused the cached publisher PDF and verified its hash against the
pinned English Official Journal edition of 12 July 2024. Docling parsed all 144 pages. A fresh
SQLite client reopened the complete text of PDF page 59 using its evidence locator.

One LiteLLM request sent the retained text of the full revision to GPT-6 Luna
using the SDK's default instructions and the recruitment model description.
The workspace ledger recorded **136,054 input tokens and 856 output tokens**.
The SDK rejected the response during proposal validation and created no draft
or discovery review cases. The stored diagnostic groups several possible
validation failures. It does not identify an offending field.

The saved notebook reopens that failed run and shows the diagnostic. The
sample reviewer then authors the documentation handoff directly from the
publisher's pages. Its five definitions include the relationship from provider
to instructions for use and the cited Article 13 rule preserving *where relevant*.
The sample record passed validation against the exported JSON Schema.

## Restart and independent handoff

A second fresh kernel ran every cell in the same workspace with external
connections blocked. The discovery run, decisions, publication, and artifact
bytes matched. The workspace ledger still recorded one provider attempt.
A file-only process verified the bundle digest and opened all five definitions,
including the relationship endpoints and PDF evidence. The notebook renders that
complete model from the reopened bundle.

The notebook tests supply a 144-page test PDF in an isolated workspace. They
check that all pages reach the gateway with the SDK default instructions.
One response contains concepts and a directed relationship, whose endpoints the
notebook displays. Another has an unknown endpoint and exercises the no-draft
path. Both cases complete the sample handoff and reopen after a kernel restart.

## Newcomer session

Give a Python developer the root README and a ready locked environment. Time
their first independent bundle read, with ten minutes as the target. Note where
they hesitate. Ask them to explain which text goes into discovery, which decisions
the reviewer recorded, and how the receiving application reads the model.
Record their frontend, elapsed time, and feedback before closing human acceptance.

This session is pending.
