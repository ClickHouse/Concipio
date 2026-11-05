# Audit waves

Parent: [Concipio](../../README.md)

**Status: proposed.** Nothing here is built.

Review mode sweeps one change. Applied to a large C codebase, Concipio's whole-codebase
reports found real bugs: copies of one routine whose guards had drifted
apart, and rules kept only in the comment beside the check that enforces
them. Those were found by reading every function, not by reading a diff.
This doc specifies how an agent audits a whole codebase that way, in
waves it can finish, without losing its place between them.

It builds on review mode's spans and store [V1, V22], the helper taxonomy
[T51], look-alike clusters [T52, T53], and unwritten rules [T58].

## Waves

- **CPO§W1:** An audit covers every function in a codebase, once, and
  then again only where the code has changed. It is review mode run
  against an empty base: every declaration is a span, keyed by its
  fingerprint in the store [K2], so a re-audit after a month of
  commits revisits only what those commits touched.
- **CPO§W2:** A wave is the part of an audit one agent takes in one
  sitting. Waves follow mechanisms, not files, so an agent reads one
  mechanism whole and judges its parts against each other.
  - **CPO§W3:** A design point's wave holds the code citing it and the
    helpers its callers serve [T51].
  - **CPO§W4:** A look-alike cluster is never split between waves. Its
    differences are the wave's checklist [T53], and an agent shown one
    copy cannot see that another drifted.
  - **CPO§W5:** Code serving four or more design points, or none, has no
    mechanism yet. Until the design names one, it is grouped by
    communities in the call graph: functions that call one another more
    than they call the rest. Such a wave says so, since naming the
    mechanism it found is one of its outputs [W12].
- **CPO§W6:** A wave is sized to a budget the agent states, in tokens,
  from the measured cost of a sweep [R13]. A mechanism larger than one
  budget splits along its sub-points, and a cluster that alone exceeds
  it is its own wave.
- **CPO§W7:** Waves run in order of risk: first the clusters whose
  differences include a guard, and the unwritten rules [T58]; then the
  core state logic a project names in `.cpo`; then the rest.

## The brief

- **CPO§W8:** `cpo waves next --budget N` hands an agent its next wave:
  the spans, the design text they cite, each cluster's differences, and
  the unwritten rules in scope. Like `cpo next`, it is the whole context
  the agent needs, so a small model can take a wave [M10, V26].
- **CPO§W9:** Whether a brief includes the design text is a setting, so
  a project can measure what the docs add: the same wave, with and
  without them, compared by findings and by cost [W14].

## Outcomes

- **CPO§W10:** Each span ends a wave as fine, a finding, or a question
  for a person, recorded against its fingerprint. A finding names what
  is wrong and the lines; a question names what the agent could not
  decide. A span left unrecorded keeps the wave open.
- **CPO§W11:** A finding records whether the design text changed the
  verdict: whether a difference first read as drift turned out to be
  intended, or the reverse. Those records are the evidence for whether
  the docs earn their keep, apart from the rigor of reviewing every
  line.
- **CPO§W12:** Every finding and question leads somewhere: a bug to
  file, a rule to write into the design [T58], a citation to add, or a
  mechanism to name [W5]. An audit therefore grows the design as it
  goes, and its coverage with it [M51].

## Status

- **CPO§W13:** `cpo waves status` reports how much of the codebase has
  been audited, by mechanism, how much has gone stale since, and what
  findings and questions are open. Like coverage, the audited share is
  a number a project can hold from falling [T40].

## First trial

- **CPO§W14:** The first wave is a family of look-alike release
  routines in a C codebase, where the cluster's differences already
  led to real questions. It runs twice, with and without the
  design text in the brief, on a small model and on a large one, and
  the four runs are compared by findings, false leads, and tokens.

## Open questions

- Should the call-graph communities of [W5] come from a standard
  algorithm, such as Leiden, or from something simpler Concipio can
  explain to a reader?
- Who answers a wave's questions: the person who owns the mechanism,
  read from a field [F1], or whoever runs the audit?
