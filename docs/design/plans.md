# Audits

Parent: [Concipio](../../README.md)

**Status: proposed.** Claiming, recording, and status are built [W8, W10, W13], over
design sections and the code they name or cite; the rest is not.

Onboarding a C codebase to Concipio found real defects, and nearly all of
them came from one move: take a design section's claims and check them
against the code. Concipio supplied the units of work and the premise
that the design is something the code must answer to, but none of the
state. The agent kept its worklist, findings, and claims in files of its
own, lost some to each compaction of its context, briefed every helper by
hand, and showed no progress in any number Concipio reports
([the adoption's account](../consultations/2026-11-07-first-adoption.md)).
This doc specifies audits whose state an agent would rather keep in
Concipio, from an adoption's first day.

It builds on the kinds of design point [Y1, Y12], the store [V22], the
helper reports [T51, T53], unwritten rules [T58], and claims of
impossibility [T63].

## Why an agent would keep its state here

- **CPO§W22:** Writing a note is cheaper than any tool, so Concipio
  wins on reading instead. The brief for a unit holds the design text and
  the exact code it names or cites, in fewer tokens than the agent spends
  finding them itself, and recording the outcome is one more word on the
  same command. The bookkeeping is a by-product of the read.
- **CPO§W23:** What Concipio returns, a notes file cannot compute: which
  verified units have gone stale since, which units another agent holds,
  and how far the audit has come [W13].
- **CPO§W24:** State survives compaction without anyone remembering it:
  a harness hook prints `cpo brief` when a session starts and after its
  context is compacted, and the brief opens with the audits in flight.
- **CPO§W25:** A project keeps its own ledgers. Concipio reads a table
  `.cpo` names, such as a defect ledger with a column of section
  references, and adds staleness to its rows; it asks no agent to move
  its records into Concipio's format, and adds no required process.

## Units and verification

- **CPO§W2:** An audit's unit is a design point with the code it claims
  [Y12]: a mechanism, a library, or, before anything cites the design, a
  section and the code it names. A unit is small enough to read whole,
  which the breadth and section limits ensure [M49, M41].
  - **CPO§W4:** A look-alike cluster joins the unit of any of its copies,
    whole. Its differences are the unit's checklist [T53], and an agent
    shown one copy cannot see that another drifted.
- **CPO§W21:** A unit is verified when an agent or a person has checked
  its claims against its code: "checked against `<sha>` by `<who>`". The
  record is glue [M53], so recording work does not churn versioned text.
  It goes stale when the unit's text, or code it names or cites,
  changes. This extends `Verified` [F16] to every point, not only
  critical ones, and needs no citation to work.
- **CPO§W1:** An audit covers every unit in its scope once, then again
  only what has gone stale, so a re-run after a month of commits
  revisits only what those commits touched.

## Named audits

- **CPO§W15:** An audit has a name, which may simply be its date, a
  scope, and a checklist. The scope is paths or a subtree of the design;
  the checklist names what each unit is judged on: whether its code does
  what its text says, look-alike differences, unwritten rules, and
  unbacked claims. `.cpo` declares audits a project runs more than once.
- **CPO§W16:** Running an audit on a schedule is the project's business:
  CI or cron runs `cpo audit run <name>` and hands its units to agents.
  Concipio keeps the audit's state and never schedules itself.

## Claims and briefs

- **CPO§W8:** `cpo audit next <name>` claims a unit for the agent asking
  and hands it the brief: the unit's text, its code, each cluster's
  differences, and the rules and claims in scope. A claim names its
  holder and expires, so several agents work one audit without a
  hand-written brief each, and work an agent abandons returns to the
  queue.
- **CPO§W27:** A claim's holder is `$CPO_AGENT`, or else the session of
  the nearest harness among the process's ancestors: Claude Code's
  `CLAUDE_CODE_SESSION_ID`, Codex's `CODEX_THREAD_ID`, or pi's
  `PI_SESSION_ID`. A harness passes its own variables to any harness it
  starts, so the nearest one decides. These IDs survive compaction, and
  a claim records the holder's messaging socket where the harness has
  one. Subagents share their parent's session, and Antigravity names
  none, so each needs a `CPO_AGENT`; Concipio prints one to set rather
  than guess.
- **CPO§W26:** A large model may claim a unit and split it into child
  claims for helpers, each with a narrower slice of code and a stated
  question. Smaller models do useful work when handed a slice and told
  what to check, not when left to find their way through a large file.
- **CPO§W6:** A brief is sized to a budget the claimant states, in
  tokens. A unit larger than one budget splits along its sub-points.
- **CPO§W7:** Units are offered in order of risk: clusters whose
  differences include a guard, unwritten rules, and unbacked claims
  first; then the core logic a project names in `.cpo`; then the rest.
- **CPO§W9:** Whether a brief includes the design text is a setting, so
  a project can measure what the docs add [W14].

## Outcomes

- **CPO§W10:** A claim ends with an outcome: verified, a finding, or a
  question for a person, recorded against the unit's fingerprints. A
  finding names what is wrong and the lines; a question names whom it is
  for, the unit's owner by default [F1].
- **CPO§W11:** A finding records whether the design text changed the
  verdict, as when a difference first read as drift proved intended.
  Those records are the evidence for whether the docs earn their keep.
- **CPO§W12:** Every finding and question ends as one of: a fix; a
  to-do point with a tracker reference, when the team has no cycles yet
  [Y8]; a verdict that two look-alikes differ on purpose [Y7]; a rule
  written into the design [T58]; or corrected design text, after which
  the unit is verified and ready to cite [Y13].

## Human sign-off

- **CPO§W17:** A person reviews a design's structure, not every line:
  whether the docs, their sections, and their statements are the right
  ones, in the right places. They sign a doc or section with a field,
  `{Signed="Josh 2026-11-06"}`, and git records who committed it. This
  refines [M25], which signs only that a doc should exist.
  - **CPO§W18:** A signature covers the outline by default: titles,
    headings, and statement names. `Covers=text` signs the whole text.
    When the part a signature covers changes after the signing commit,
    lint reports the signature stale, as it does `Verified` [F16].
- **CPO§W19:** Instead of signing, a reviewer may leave a directive,
  `{Restructure="split into three; the queue part belongs in queue.md"}`.
  A directive is a to-do point [Y8], which an agent carries out or files
  with the tracker.
- **CPO§W20:** `cpo brief --unsigned` lists what awaits signing, from
  the master down, so a person signs the top of the tree first.

## Progress

- **CPO§W13:** `cpo audit status <name>` reports the verified share of
  the scope, by units and by the lines of code they claim, apart from
  coverage; what has gone stale since; and which claims, findings,
  questions, and to-do points are open. An adoption's first weeks show
  their work here, long before citations move coverage [Y13].

## First trial

- **CPO§W14:** The first trial audits a family of look-alike release
  routines in a C codebase, where the cluster's differences already led
  to real questions. It runs with and without the design text in the
  brief, on a small model and on a large one, and the four runs are
  compared by findings, false leads, and tokens.

## Open questions

- Should the verified share count toward the score [M50], or stand
  beside it as coverage does?
- `cpo audit` already scores the docs [M50]. Should the score become
  `cpo score`, leaving `cpo audit` to these named audits, or should these
  take another name?
- Which harnesses can run a hook after compaction, and what does an
  agent on one that cannot do instead?
