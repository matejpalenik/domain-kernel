---
name: domain-kernel-maintainer-docs
description: Write, edit, or review Domain Kernel's maintainer-facing Markdown on GitHub, including ARCHITECTURE.md and contributor guides. Official SDK documentation in apps/docs uses its own authoring workflow.
---

# Write maintainer documentation

## Write for a new teammate

Assume basic Python and GitHub navigation. Explain project terms and
architectural ideas where the reader first needs them. Keep a term when it
names a distinction that matters, and use it consistently. A snapshot is a
saved copy of the model at a particular point in time. A reader should be
able to follow the paragraph before opening the [glossary](../../../GLOSSARY.md).

Start with who does what and what happens next. Use “you” for actions the
reader takes. Name the SDK, the application, or the reviewer when they act.
Use headings that help someone find an answer, such as “Where to find the
code.” Cut slogans, sentences that announce what the heading already says,
and summaries that repeat a point in more abstract words. Keep transitions
that explain why the next step happens.

Use ASD-STE100 Simplified Technical English as a style reference. Aim for
one main point per sentence. Break up long strings of nouns. Put a condition
first when the reader needs it before acting. Let clarity determine sentence
length. [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf)

## Show how the SDK fits together

Open the overview in [ARCHITECTURE.md](../../../ARCHITECTURE.md) with a
problem from the supplier catalog. Show someone proposing a definition
by hand and how a supplier document can lead to another proposal. The
paths meet at review. Follow one change from review to publication.

Show what runs inside the application, what the SDK and application each
own, and where data is saved. Map the main parts and their dependencies.
Link from the overview to deeper design sections in the same file. Give the
reader an exact entry point or symbol to search for, with branch-relative
links to relevant source and tests.

Keep the rules maintainers must preserve and the reasons behind them. State
the condition and what the reader can observe. For example, if a reviewer
accepts a change after you prepare a release, the SDK rejects an attempt to
publish that older snapshot as a new version. Link to the code for the exact
checks. Use a short Python snippet when its arguments or call order explain
a rule. For full runnable examples, link to the [official docs source](../../../apps/docs/) or the
[notebook tour](../../../examples/notebooks/README.md), following the
repository's [content ownership guidance](../../../docs/documentation.md#content-ownership).

## Give each diagram one question

Use Mermaid when relationships or a sequence are easier to follow in a
diagram. The question “What runs inside the application?” needs its own
view. “What happens when you publish?” needs a view of the steps. Use short,
plain labels such as “Is the saved copy still current?” Label arrows with
a verb or phrase that explains the relationship or action. Explain the
outcome in nearby prose and put exact code identifiers there for lookup.

For an example that shows the same rule in prose and Mermaid, see the
[publication rewrite](../../../docs/evidence/maintainer-documentation-research.md#why-publication-rejects-an-older-snapshot).

## Check the edit

Edit the requested material and repair affected links and definitions.
Use the architecture for design intent and inspect source and tests for
what the SDK does at this revision. Label proposed behavior beside the
claim. When the design and code disagree, cite both and show the maintainer
what differs.

Follow changed links and anchors. Preview changed Mermaid diagrams on
GitHub when available. When a newcomer is available to try a substantial
rewrite, ask them to explain what the SDK does, trace one change, and find
a test for an important rule. Use the places they get stuck to revise the
document. Report what you checked and what remains open.
