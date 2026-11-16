# Educational benchmark

Reviewed on 15 November 2026 against Apollo Odyssey's
[Intro to GraphQL with TypeScript & Apollo Server](https://www.apollographql.com/tutorials/intro-typescript/01-course-overview-and-setup).
This assesses the teaching experience, not SDK implementation completeness, extraction accuracy
or legal correctness. The preview intentionally retains simulated SDK results.

## What was reviewed

The review followed all fourteen lesson pages from setup through mutations, including explanations,
code progression, expected responses, practice prompts and transitions. Browser inspection also
covered the SDL lesson's expandable explanation and practice controls, and the Explorer lesson.
It did not complete the certification, build Apollo's server or validate every exercise answer.

Apollo introduces the application and bounded feature before setup, states prerequisites and
provides a completed branch for recovery. These are particularly effective orientation aids.
[Course overview and setup](https://www.apollographql.com/tutorials/intro-typescript/01-course-overview-and-setup)

Its lessons introduce concepts through small examples, offer optional deeper explanations and
ask the learner to apply them. Later lessons reconnect earlier pieces and show expected query
results, making progress observable.
[Schema definition language](https://www.apollographql.com/tutorials/intro-typescript/03-schema-definition-language-sdl),
[Querying real data](https://www.apollographql.com/tutorials/intro-typescript/10-querying-real-data)

The final feature grows out of an application need and includes an unsuccessful input followed by
a repair. Failure is part of learning the contract, rather than an unrelated warning.
[Mutations](https://www.apollographql.com/tutorials/intro-typescript/14-mutations)

These patterns informed the tour's structure; Apollo's prose and application were not copied.

## Changes made to the tour

| Teaching pattern | Concrete application | Stable cells |
|---|---|---|
| Show the destination first | Preview the instructions-for-use consumer contract and its separate qualified logging rule before configuration. | `tour-destination-introduction`, `tour-destination-preview` |
| Explain the mental model before its machinery | Define project, model, definition, proposal, review and publication; distinguish identity, name, revision and model kind. | `tour-mental-model` |
| Teach one transition at a time | Split the first authoring workflow into building, impact inspection, decision submission and publication, with a result after each stage. | `c2-author`, `c2-impact`, `c2-decision`, `c2-preview` |
| Make inputs traceable | Explain gateway ownership, provisioned source files, pinned ontology dependencies and selected review-case identities. | `c1-introduction`, `c3-introduction`, `c5-introduction`, `c6-introduction` |
| Show the actual consequence | Compare the two document meanings in C6 and highlight changed versus unchanged fields in C7. | `c6-preview`, `c7-preview` |
| Preserve meaning through the handoff | Add a descriptive logging rule through the existing API and retrieve it from the independent consumer bundle. | `c7-add-rule`, `c9-preview`, `c9-consumer-preview` |
| Learn from a repair | Show the invalid relationship draft, repair its endpoint and retain the advisory manual result as UNKNOWN. Policy changes are a separate optional branch. | `c8-rejected-draft`, `c8-preview`, `e1-introduction` |
| Practice, then explain | Add one question with an expandable explanation after every main chapter, plus three independent completion tasks. | `c1-checkpoint` through `c10-checkpoint`, `tour-completion` |
| Separate reading from actions | Evidence and inspection choices update immediately; only simulated changes require a reason, preview and explicit submission. | Chapter experiment controls |
| Defer optional depth | Route advanced exercises by the developer's next task and give them specific learning checks. | `tour-completion`, E1–E10 and R1 |
| Reduce the size of each step | Separate C6's distinct meanings, source mapping and reference mapping; build C7's fields, rule, key repair and check in one draft before review. | C6–C7 staged cells |
| Let the learner try and recover | Six two-part tasks provide answer-specific feedback, hints and worked answers, including free-text consumer lookups. | `c4-prompts-practice`, `c6-review-practice`, `c6-mapping-practice`, `c7-shape-practice`, `c7-identity-practice`, `c7-handoff-practice` |

The paired source, saved notebook and static HTML contain the same canonical teaching results.
Fixture checks protect publication counts, review identities, definition revisions, the process
path, recovery cases and the LinkML example. The acceptance experiment does not implicitly publish,
and action reasons describe concrete developer motivations. The qualification is carried by a published rule;
it is not confined to an HTML annotation beside an optional attribute.

## First-time developer reassessment

The reader can now answer five questions before reaching the advanced exercises:

1. What am I producing? A reusable, reviewed model bundle, illustrated before C1.
2. What do I do next? Each chapter explains the missing capability and the next operation.
3. What actually changed? Staged results and focused comparisons separate proposals from acceptance.
4. Why does a published field have this meaning? Evidence and the descriptive rule remain inspectable.
5. What can my application consume? C9 reloads the bundle and shows both supported projections
   and the interpretations the application still owns.

C6 and C7 now expose one decision or draft change at a time, with no planned block longer than
24 nonblank lines. Nine focused intermediate results make the pending/accepted boundary visible.
Six practice tasks require an explicit answer check and explain the particular misconception;
changing an answer clears stale feedback, while rerunning a cell preserves the learner's work.
The free-text task requires finding the attribute and rule names in the inspector. Static worked
answers remain available without a kernel. The C4 discovery addition teaches instruction
precedence and fixed output validation over the full AI Act; it extends the planned
discovery contract without changing the implemented SDK or canonical model.

Remaining limitations are independent practice and measured pacing. Most feedback tasks still
use bounded choices; they do not assess an open-ended modelling solution or execute learner code.
The advanced appendix remains substantial. Three completion tasks require independent inspection,
but there is no evidence yet that a new reader can finish them unaided. The 60–90 minute estimate
needs a timed user trial. The smaller steps add scrolling, so a newcomer trial should check that
the benefit in comprehension outweighs the longer chapter presentation.

## Ratings

These are subjective editorial scores using the same rubric before and after this pass. They
are not measured learning outcomes. The baseline is the preceding Apollo-benchmark pass
(8.9 overall), not the earlier SDK-wide ratings. Apollo scores reflect the inspected course pages,
not a claim of complete accessibility or certification testing.

| Category | Tour before | Tour after | Change | Apollo benchmark |
|---|---:|---:|---:|---:|
| Clear purpose and visible deliverable | 9.2 | 9.2 | 0.0 | 9.5 |
| Narrative continuity and motivation | 9.0 | 9.3 | +0.3 | 9.5 |
| Pacing and cognitive load | 8.5 | 9.2 | +0.7 | 9.5 |
| Explanation of concepts and API choices | 9.0 | 9.3 | +0.3 | 9.3 |
| Practice and useful feedback | 8.5 | 9.1 | +0.6 | 9.5 |
| Visual explanation | 9.0 | 9.0 | 0.0 | 9.2 |
| Consistent, understandable expected results | 9.0 | 9.0 | 0.0 | 9.3 |
| Finished artifact and consumer handoff | 9.2 | 9.2 | 0.0 | 9.5 |
| **Unweighted mean, rounded** | **8.9** | **9.2** | **+0.2** | **9.4** |

The mean change is calculated before rounding the displayed totals (8.925 to 9.1625).

Apollo remains the stronger benchmark for pacing and active practice. The tour's particular
strength is making provenance, semantic qualifications and review consequences visible in a
single evolving artifact. To justify a higher score, observe first-time developers doing the
completion tasks, shorten the steps where they hesitate, and test whether they can explain the
field/rule distinction without opening the answer. Adding more model content or decoration
alone would not establish that improvement.

See [VALIDATION.md](VALIDATION.md) for executed checks and the scope of manual VS Code testing.
