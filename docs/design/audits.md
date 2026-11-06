# Audits

Parent: [Concipio](../../README.md)

**Status: proposed.** Nothing here is built.

Onboarding a C codebase to Concipio meant reading every function, and that
audit found real defects: copies of one routine whose guards had drifted,
rules kept only beside the check that enforces them, and claims of
impossibility nothing tested. A project should be able to run such an
audit again, on a schedule, with an agent working through it unattended,
while the people responsible review the design's structure as they find
time. This doc specifies both.

It builds on review mode's spans and store [V1, V22], the kinds of design
point [Y1], the helper reports [T51, T52, T53], unwritten rules [T58], and
claims of impossibility [T63].

## Named audits

- **CPO§W15:** An audit has a name, which may simply be its date, a
  scope, and a checklist. The scope is paths or a subtree of the design;
  the checklist names what each mechanism is judged on: whether its code
  does what its statement says, look-alike differences, unwritten rules,
  and unbacked claims. `.cpo` declares audits a project runs more than
  once.
- **CPO§W1:** An audit covers every mechanism in its scope once, then
  again only where something changed. Each outcome is keyed by the
  fingerprints of the code and the statement it judged [K2], so a re-run
  after a month of commits revisits only what those commits touched.
- **CPO§W16:** Running an audit on a schedule is the project's business:
  CI or cron runs `cpo audit run <name>` and hands its waves to agents.
  Concipio keeps the audit's state and never schedules itself.

## Waves

- **CPO§W2:** A wave is the part of an audit one agent takes in one
  sitting. Waves follow mechanisms, not files, so an agent reads one
  mechanism whole and judges its parts against each other [Y2].
  - **CPO§W4:** A look-alike cluster is never split between waves. Its
    differences are the wave's checklist [T53], and an agent shown one
    copy cannot see that another drifted.
  - **CPO§W5:** Code no mechanism or library claims is grouped by
    communities in the call graph, functions that call one another more
    than they call the rest, and the wave says so, since naming what it
    found is one of its outputs [W12].
- **CPO§W6:** A wave is sized to a budget the agent states, in tokens,
  from the measured cost of a sweep [R13]. A mechanism larger than one
  budget splits along its sub-points.
- **CPO§W7:** Waves run in order of risk: clusters whose differences
  include a guard, unwritten rules, and unbacked claims first; then the
  core logic a project names in `.cpo`; then the rest.

## The brief

- **CPO§W8:** `cpo audit next <name> --budget N` hands an agent its next
  wave: the code, the statements it cites, each cluster's differences,
  and the rules and claims in scope. It is the whole context the agent
  needs, so a small model can take a wave [M10, V26].
- **CPO§W9:** Whether a brief includes the design text is a setting, so
  a project can measure what the docs add: the same wave, with and
  without them, compared by findings and cost [W14].

## Outcomes

- **CPO§W10:** Each mechanism ends a wave as fine, a finding, or a
  question for a person, recorded against its fingerprints. A mechanism
  left unrecorded keeps the wave open.
- **CPO§W11:** A finding records whether the design text changed the
  verdict, as when a difference first read as drift proved intended.
  Those records are the evidence for whether the docs earn their keep,
  apart from the rigor of reviewing every line.
- **CPO§W12:** Every finding and question ends as one of: a fix; a
  to-do point, when the team has no cycles for a fix yet [Y8]; a
  verdict that two look-alikes differ on purpose [Y7]; a rule written
  into the design [T58]; or a name for code no mechanism claimed [W5].
  An audit therefore grows the design as it goes.

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
  A directive is a to-do point [Y8], which an agent carries out or
  files with the tracker.
- **CPO§W20:** `cpo brief --unsigned` lists what awaits signing, from
  the master down, so a person signs the top of the tree first and
  works down as time allows.

## Status

- **CPO§W13:** `cpo audit status <name>` reports how much of the scope
  has been audited, by mechanism, how much has gone stale since, and
  which findings, questions, and to-do points are open. Like coverage,
  the audited share is a number a project can hold from falling [T40].

## First trial

- **CPO§W14:** The first wave is a family of look-alike release routines
  in a C codebase, where the cluster's differences already led to real
  questions. It runs with and without the design text in the brief, on a
  small model and on a large one, and the four runs are compared by
  findings, false leads, and tokens.

## Open questions

- Should the communities of [W5] come from a standard algorithm, such as
  Leiden, or from something simpler Concipio can explain to a reader?
- Who answers a wave's questions: the mechanism's owner, read from a
  field [F1], or whoever runs the audit?
- `cpo audit` already scores the docs [M50]. Should the score become
  `cpo score`, leaving `cpo audit` to these named audits, or should these
  take another name?
