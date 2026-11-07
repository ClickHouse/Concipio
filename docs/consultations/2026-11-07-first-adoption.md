# First adoption: what the agent kept for itself (2026-11-07)

Notes from the first agent-led adoption of Concipio, on a C storage driver
(about 100k lines of C, shell and Python, with a 6,000-line design doc).
The agent was Claude Opus 5.5, working on a long-lived branch from 2026-11-03,
with GPT Astra, Gemini 4 Argon and Gemini 3.8 Flash as reviewers. Written at
Josh's request, as input to the audits design [W1–W20] and the review-mode
store [V16–V18], not as a proposal.

## What happened

- The adoption reconciled the design doc with the code, section by section: state
  each claim a section makes, check it against the code, fix the prose or
  file the code as a defect, and archive retired text. It found 28 defects,
  most of them since fixed, and rewrote about fifteen sections.
- Concipio's measured state barely moved. Coverage ("any") went from 9.66%
  at the branch's merge-base to 9.76%; strict coverage from 0 to 0.02%. The
  audit score is 55, with 55 problems.
- The agent kept its own state the whole time: a worklist (the section order,
  in a memory file and in conversation context), a defect ledger in the
  repository, intent questions routed through a coordinating agent, and a
  claim registry it built (a table of claims in its tests, seeded from
  `cpo unreachable`).
  It read Concipio's output, lint and audit as a to-do list and the coverage
  map to choose code-only audit areas, and never wrote anything back.

## Where the defects came from

| Source | Defects | Concipio's part |
|---|---|---|
| Checking a section's claims against the code | 14 | framing: breadth and section-length lint cut the doc into checkable units, each with a stated intent to falsify |
| Test gates built from the early postmortems | 4 | none |
| Code-only audits of areas the design omits | 5 | weak: chosen from the coverage map, but 90% of the code was unmarked, so it barely narrowed the choice |
| Other agents reading gate logs, or following a lead | 3 | none |
| Argon on extracted code; a scenario breaking a defined-UB rule | 2 | none |

`cpo unreachable` found nothing directly. The two false "impossible" comments
that motivated the claim registry were found by section audits first.

The productive unit was a section's stated intent checked against its code:
a paragraph saying "the ring cannot be exhausted" gives a reviewer something
to falsify, and design-versus-code disagreements were where the bugs lived.
That is Concipio's premise, but the agent ran it without Concipio's state,
and a prompt to "reconcile the design doc with the code, section by section"
would probably have found most of the same defects.

## Why the state stayed outside

- **No place to record the work done.** The work was "section 5c checked
  against the code at commit X", and the only built record of that is
  `Verified` [F16]. The agent never used it. It applies only to critical
  statements, and it goes stale through citing code, which did not exist
  yet. Citing a section before its prose is corrected would lock the error
  in, so links naturally come after reconciliation. Coverage, the only
  number that moves, therefore measured none of this work.
- **Linking is the last step.** Coverage rewards citations, and on a
  codebase whose design has drifted, citations are the step after
  verification. An adoption's early weeks will always read near zero.

## What the agent's own bookkeeping lacked

These are the places Concipio's state would have earned its keep:

1. **Durability.** The worklist lived mostly in context, so each compaction
   kept only what its summary kept. A store survives that.
2. **Staleness.** The agent knew a section was checked at a commit, but had no
   cheap way to learn that a later commit changed the code that section describes.
   That is mechanical, and a tool does it better than an agent.
3. **A shared queue.** Parallel Astra and Argon runs had no shared worklist;
   each was briefed by hand. The smaller models did useful work only when
   handed a narrow slice and told what to check. Argon in agent mode spent
   $5.85 over two runs on a 20,000-line file and returned nothing. With an
   attached slice it found real defects.

## What the agent would have used

- **A per-section verification record**, for any section, not only critical
  statements: "checked against `<sha>` by `<who>`", going stale when code the
  section names *or* cites changes. Named identifiers are what an unlinked
  design has, so staleness cannot wait for citations. [W1] keys outcomes by
  fingerprints; this needs that to work before any spans are attached.
- **Questions and findings attached to the section** they arose in, with an
  owner, and a link out to wherever the project tracks defects. The ledger
  stays in the project's repository; Concipio holds the pointer. [W10, W12]
  cover the outcomes; who answers questions is open in the audits design, and here the answer
  was "the mechanism's owner, routed by a coordinator".
- **A claimable worklist**, so several agents take sections without a
  hand-written brief each. [W8]'s `cpo audit next` is close; this run
  needed it for doc sections before mechanisms or spans existed.
- **A progress number for verification, apart from coverage** [W13], so an
  adoption's first phase shows its work.

Not wanted, from this run: more required structure. The agent's own
structure (the ledger, matrix-style test gates, the claim registry) came from
the project's postmortem practice, and lives in the project. Concipio was
most useful as a source of units of work and as the premise that the design
is something the code must answer to.

## Caveat

One project, one large model. A smaller model may need the structure the
agent supplied for itself; the evidence above (small models useful only when
given a slice) suggests that structure is the queue and the brief, not a
stricter process.
