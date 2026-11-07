# Plans and audits

Parent: [Concipio](../../README.md)

**Status: proposed.** Claiming, recording, and status are built for
audits, as `cpo audit next`, `done`, `mine`, and `status` [W8, W10, W13],
over design sections and the code they name or cite; the rest is not.

Onboarding a C codebase to Concipio found real defects, nearly all from
one move: take a design section's claims and check them against the
code. Concipio supplied the units of work, but none of the state. The
agent kept its worklist, findings, and claims in files of its own, lost
some to each compaction, briefed every helper by hand, and showed no
progress in any number Concipio reports
([the adoption's account](../consultations/2026-11-07-first-adoption.md)).
This doc specifies plans, claimable lists of work that agents share, and
audits, the plans that check a design against its code. It builds on the
kinds of design point [Y1, Y12, Y14], the store [V22], and the helper
reports [T51, T53, T58, T63].

## Why agents keep their state here

- **CPO§W22:** Writing a note is cheaper than any tool, so Concipio wins
  on reading instead. An item's brief holds its design text and the code
  it names or cites, in fewer tokens than the agent spends finding them,
  and recording the outcome is one more word on the same command. The
  bookkeeping is a by-product of the read.
- **CPO§W23:** What Concipio returns, a notes file cannot compute: which
  verified items have gone stale, which another agent holds, and how far
  the plan has come [W13].
- **CPO§W24:** State survives compaction without anyone remembering it.
  After a compaction the agent runs `cpo plan join` again [W31], which a
  harness hook can do for it.
- **CPO§W25:** A project keeps its own ledgers. Concipio reads a table
  `.cpo` names, such as a defect ledger with a column of section
  references, and adds staleness to its rows, and adds no required
  process.

## Plans

- **CPO§W28:** A plan is a named list of work that agents claim: its
  items are design points, and its record is a log doc in the
  repository. Audits, roadmaps, and the work an audit's findings call
  for are all plans, worked by one set of commands.
- **CPO§W29:** `cpo plan start <target>` starts a plan on a part of the
  design and writes its log doc: the date, the purpose, the scope, the
  checklist, the commit it started at, and who started it. The purpose
  is inferred from the target, such as "Check DESIGN §5c against the
  code", and `--purpose` overrides it. `--log` names the doc; by default
  it is `plans/<date>-<slug>.md`, or `audits/` for an audit, with a
  slug built naively from the target or the purpose.
- **CPO§W30:** A new plan's log is filed as a bullet under the nearest
  workstream above its target [Y16], or the one `--under` names, or a new
  one `--new-workstream` creates beside the target. `.cpo` may name a
  default. With no workstream to file under, Concipio files nothing and
  says how to name one.
- **CPO§W36:** `cpo mv` renames a doc and rewrites every Markdown link
  to it, so a log or a design doc can move freely. Tags hold no paths,
  so citations need no rewriting, and a doc `cpo mv` moved keeps its
  signature [M25, W17].

## Agents

- **CPO§W31:** `cpo plan join <name>` is the handshake an agent runs
  first and again after every compaction. It settles who the agent is
  [W27], adds it to the plan's roster with its model and messaging
  socket, so a coordinator can see who is working and reach them, and
  prints what it holds, what it found, and what remains.
- **CPO§W27:** A claim's holder is `$CPO_AGENT`, or else the session of
  the nearest harness among the process's ancestors: Claude Code's
  `CLAUDE_CODE_SESSION_ID`, Codex's `CODEX_THREAD_ID`, or pi's
  `PI_SESSION_ID`. A harness passes its own variables to any harness it
  starts, so the nearest one decides. These IDs survive compaction.
  Subagents share their parent's session, and Antigravity names none,
  so each needs a `CPO_AGENT`; Concipio prints one to set rather than
  guess.
- **CPO§W26:** A large model may split its work among helpers. `cpo plan
  join <name> --helper` gives a helper an identity tied to its parent,
  each claims a narrower item with a slice of code and a stated
  question, and their claims and findings roll up to the parent. Small
  models do useful work when handed a slice, not when left to find
  their way through a large file.

## Working an item

- **CPO§W8:** `cpo plan next <name>` claims an item for the agent asking
  and hands it the brief: the item's text, its code, and for an audit
  each cluster's differences and the rules and claims in scope. A claim
  names its holder and expires, so work an agent abandons returns to
  the queue, and an agent asking again resumes its own claim.
- **CPO§W6:** A brief is sized to a budget the claimant states, in
  tokens. An item larger than one budget splits along its sub-points.
- **CPO§W10:** `cpo plan done` ends a claim with an outcome: done or
  verified, a finding, or a question for a person, recorded against the
  item's fingerprints. A question names whom it is for, the item's owner
  by default [F1].
- **CPO§W32:** `cpo plan note <item> "<text>"` appends a dated line to
  the item's log, which is simply its children: bullets under it, or a
  child doc it links to. When the bullets would push a section past its
  length limit [M41], the log moves to a child doc linked from the item.
- **CPO§W33:** `cpo plan close <name>` writes the plan's outcome into its
  log doc, what was done, found, and left open, and moves its bullet
  from the workstream's active list to its completed one.
- **CPO§W34:** Claims and the roster are short-lived, and exist to keep
  agents apart, so they live in the store under its lock. What a plan
  produced, its notes, outcomes, and corrected design, is versioned in
  the repository, so a scheduled run on another machine starts from
  what is checked in.

## Audits

- **CPO§W15:** An audit is a plan seeded with an item per unit of its
  scope, each asking whether the unit's text holds of its code, with a
  checklist: look-alike differences, unwritten rules, unbacked claims.
  `cpo audit start <target>` starts one; `.cpo` declares audits a
  project runs again.
- **CPO§W2:** An audit's unit is a design point with the code it claims
  [Y12]: a mechanism, a library, or, before anything cites the design, a
  section and the code it names. The breadth and section limits keep a
  unit small enough to read whole [M49, M41].
  - **CPO§W4:** A look-alike cluster joins the unit of any of its copies,
    whole, and its differences are the unit's checklist [T53].
- **CPO§W21:** A unit is verified when an agent or a person has checked
  its claims against its code: "checked against `<sha>` by `<who>`". The
  record goes stale when the unit's text, or code it names or cites,
  changes. This extends `Verified` [F16] to every point, and needs no
  citation to work.
- **CPO§W12:** An audit's findings become items of the same plan: a fix,
  then the corrected prose, after which the unit is verified and ready
  to cite [Y13]. A finding the team has no cycles for becomes a to-do
  point with a tracker reference [Y8], and one that proves intended
  becomes a verdict that two look-alikes differ on purpose [Y7].
- **CPO§W11:** A finding records whether the design text changed the
  verdict, the evidence for whether the docs earn their keep.
- **CPO§W1:** A re-run of an audit offers only what has gone stale
  since. Running one on a schedule is the project's business: CI or cron
  starts it and hands its items to agents [W16].
  - **CPO§W16:** Concipio keeps a plan's state and never schedules
    itself.
- **CPO§W7:** An audit offers items in order of risk: stale ones first,
  then clusters whose differences include a guard, unwritten rules, and
  unbacked claims, then the rest. Whether a brief includes the design
  text is a setting, so a project can measure what the docs add [W9].
  - **CPO§W9:** The same unit, briefed with and without its design text,
    compared by findings and cost [W14].

## Planned work

- **CPO§W35:** A roadmap is a plan whose items are the planned and
  in-progress points of its scope [Y14]. An agent claims one, works it,
  and notes progress against it [W32]; when the work lands, the point
  becomes a claim about the code, and the next audit verifies it [Y15].

## Human sign-off

- **CPO§W17:** A person reviews a design's structure, not every line:
  whether the docs, sections, and statements are the right ones, in the
  right places. They sign a doc or section with a field,
  `{Signed="Josh 2026-11-06"}`, and git records who committed it. This
  refines [M25], which signs only that a doc should exist.
  - **CPO§W18:** A signature covers the outline by default: titles,
    headings, and statement names. `Covers=text` signs the whole text.
    When the part a signature covers changes after the signing commit,
    lint reports the signature stale, as it does `Verified` [F16].
- **CPO§W19:** Instead of signing, a reviewer may leave a directive,
  `{Restructure="split into three; the queue part belongs in queue.md"}`.
  A directive is a to-do point [Y8], and an item of the next plan that
  covers it.
- **CPO§W20:** `cpo brief --unsigned` lists what awaits signing, from
  the master down, so a person signs the top of the tree first.

## Progress

- **CPO§W13:** `cpo plan status <name>` reports what is done or verified,
  by items and by the lines of code they claim, apart from coverage;
  what has gone stale since; and which claims, findings, and questions
  are open. An adoption's first weeks show their work here, long before
  citations move coverage [Y13].

## First trial

- **CPO§W14:** The first trial audits a family of look-alike release
  routines in a C codebase, where the cluster's differences already led
  to real questions. It runs with and without the design text in the
  brief, on a small model and on a large one, and the four runs are
  compared by findings, false leads, and tokens.

## Open questions

- Should the share verified count toward the score [M50], or stand
  beside it as coverage does?
- `cpo audit` already scores the docs [M50]. Should the score become
  `cpo score`, so `cpo audit` means only audits?
- Which harnesses can run a hook after compaction, and what does an
  agent on one that cannot do instead?
