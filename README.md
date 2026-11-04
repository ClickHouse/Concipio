# Concipio

Hardware engineers can trace every wire on a board to the line of the
instruction-set spec it implements. Software lost that rigor as languages rose
and systems grew. Concipio aims to bring it back, starting where the loss hurts
most: code review.

**CPO§M29:** A person should understand at least the high-level concepts of the
code they change. Agents make it easy never to learn them: an engineer can
work in an unfamiliar language and an unfamiliar system, and merge code nobody
on the team has understood. Concipio helps a reviewer climb from the concepts
they know, through the medium-level concepts they don't, down to the code,
without exhausting their attention.

**CPO§M52:** Concipio holds docs to three standards. **Completeness:** every
line of code traces to a design, and every doc is reachable. **Correctness:**
the docs say what the code does, and agree with one another. **Consumability:**
every design fits on a screen, and what matters most stays near the top.

Concipio is a tool for LLM agents. An agent sweeping a diff asks Concipio what
remains, and Concipio answers pass or fail: either every changed span of code
belongs to a concept or is explicitly marked unjustified, or here is what is
left. The agent then uses the resulting concept graph to walk a human through
the change, one concept at a time.

This README is Concipio's master design document. A tag such as `CPO§M3`
defines a design point; within the design docs, `[M3]` refers to it.

## Install

`uv tool install git+<this repository's URL>` puts `cpo` on your path, or
`uv tool install --editable <a checkout>` to follow a checkout's changes,
reinstalling with `--reinstall` whenever its dependencies change. If the shell
then cannot find `cpo`, `uv tool update-shell` adds uv's tool directory to the
path. `cpo --help`
lists the commands, and `cpo help agent` is the guide for agents.

## The problem

LLMs made code cheap to write and expensive to review. Reviewers fall behind,
and the code that slips through tends to fail in three ways: it does nothing,
it does the wrong thing, or it does the right thing in too many places. Design
documents drift from the code, and requirements go missing without anyone
noticing.

Models have the same attention problem that reviewers do. A small model loses
track partway through a large diff. A large model skims. Neither can tell you
what it skipped.

## Two uses, one core

**CPO§M30:** Concipio's core is a concept graph and an exhaustive check over
it. Review builds the graph; traceability keeps it.

1. **Review** [M28]. An agent maps a diff to concepts and walks a human
   through it. This comes first, because it needs nothing from the
   repository.
2. **Traceability.** A repository keeps its concepts permanently, in design
   docs and code comments, and CI checks them. This is the hardware analogy
   taken literally.

The two share their data, their checks, and their tools. What review alone
cannot do is learn. A review that rebuilds its concepts from scratch makes
the same judgment calls again, differently, and nobody checks them. Kept
concepts can be reviewed once, by a stronger model or a person, and reused by
every later review. Traceability may still cost more attention than it saves
[R13], so it is adopted gradually [M39], and only what review proves worth
keeping gets persisted.

```
master design      reads like a pitch (often the README)
  design docs      each more detailed and more narrowly focused than its parent
    concepts       the medium-level purposes that code serves
      comments     where code states its assumptions
        code
```

**CPO§M1:** The hierarchy is soft. Concipio does not distinguish requirements
from design: a product requirement, a process spec, and an algorithm spec are
all design statements. A repository decides how deep its docs go. In review
mode, the design text may be nothing more than a pull request description.

**CPO§M41:** Every design fits on a screen. A statement longer than about 20
lines becomes nested statements, and a section with more than about 60 lines
of its own becomes subsections or a child doc. Sections and files are
interchangeable for this rule; what matters is that a reader can take in one
design at a time, then go deeper only where they need to. Docs that define no
statements, such as notes and reports, are exempt.

- **CPO§M51:** `cpo coverage` reports how much code the design's citations
  claim: lines inside declarations some comment cites, by directory, with
  tests counted apart and files no parser reads counted as unmeasured.
  Strictly only `Implements` and `Tests` citations cover code [T6]; a project
  still adopting can count every mention, and watch the strict number grow.
- **CPO§M49:** Every design point claims no more code than a reader can
  hold in mind: by default, 200 lines of implementation, tests counted
  apart. A point that claims more needs refining into sub-points; a
  routine longer than that needs extracting into smaller ones, which in
  hot paths means inline functions, so the rule never costs performance.

**CPO§M2:** Over time, kept concepts should lead a project toward a practice
nobody has to impose. A master design that reads like a pitch; below it, docs
at the level of a PRD; below those, docs detailed enough to nearly be code;
then code whose helpers are well abstracted. Concipio fills the remaining gap
between the lowest design doc and the code.

## Design points

### Concepts and coverage

- **CPO§M31:** A concept is a node between design statements and code. It has
  a name; a claim specific enough to check; a parent, which is a design
  statement or a broader concept; the spans it covers; its assumptions; and
  any open questions. Concepts nest, so the medium-level concepts a reviewer
  lacks sit under the high-level ones they know.
  - **CPO§M6:** Agents flag sites that independently maintain the same rule,
    conversion, or invariant. A model, a scheduler, and a guest script that
    collaborate on one feature are normal architecture, not duplication. In
    review, the search covers the change and the code it references;
    searching the whole repository waits for the concepts that traceability
    keeps.
- **CPO§M3:** Every changed span belongs to at least one concept, or is marked
  unjustified.
  - **CPO§M32:** A review covers exactly the change under review. A review
    manifest pins the base and head revisions, the changes this one is
    stacked on, which serve as context, and a frozen copy of the design text.
    Added, modified, and deleted code all count. A deleted span needs a
    concept that explains why its removal is intended. Changed lines are
    grouped by the declaration or top-level block that encloses them,
    including Ruby DSL blocks.
  - **CPO§M7:** Marking a span unjustified is a valid outcome, never a
    failure. Agents must prefer it over generic concepts like "utility
    helpers." Helpers join the concepts whose implementation they support.
    - **CPO§M8:** At the end of a sweep, unjustified code goes into an
      odds-and-ends report. Some of it is benign; dates have to be formatted
      somewhere. Some of it is a smell: why didn't the existing formatter
      handle this, and which design statement asked for it?
      - **CPO§M45:** Unjustified code may still be explained. When design
        text that makes no claim, such as the problem being solved or work
        planned for later, accounts for a span, the span says so, and
        reports list it apart from code nobody explains. A reviewer then
        need not ask about what the author already said.
- **CPO§M4:** Every concept should trace to at least one design statement. A
  concept without one is reported as *undeclared behavior*: the change does
  something its design text does not mention. That may be a bug, a feature
  nobody documented, or a concept the agent made up; the reviewer decides
  which.
  - **CPO§M42:** A strict check fails on undeclared behavior too, so every
    changed span must reach a design statement, given or drafted. Drafting
    a statement to cover it is allowed, and its provenance shows [M38].
  - **CPO§M38:** Every design statement records its provenance: *given*, from
    design text that existed before the review, or *drafted*, written by the
    agent from the code. Coverage is reported against each separately. A
    drafted statement never hides undeclared behavior [R8].
- **CPO§M5:** The reverse is also true: Every design statement should trace to
  at least one concept, unless it is context, planned work, or a description
  rather than a claim. A claim with no concept is reported as an
  *unimplemented claim*: a missed requirement, or a description that
  overpromises.

### The tool

- **CPO§M9:** The agent uses the tool, not the other way around. Concipio is
  a command-line tool that any agent harness can call, so it works with any
  model. The agent decides what to do next; Concipio decides whether the work
  is done.
  - **CPO§M37:** Concipio is mechanical and never calls a model. Every
    judgment, such as what a concept is, whether a name is too generic, or
    whether a claim is true, is made by the agent or the reviewer, and
    Concipio records it. Concipio checks structure: completeness, resolution,
    and that recorded judgments have the evidence they require.
    - **CPO§M11:** Concipio supports semantic analysis, which agents perform,
      not static analysis. Parsers supply structure, and existing static
      tools may serve as optional inputs to the agent, but neither is the
      product.
  - **CPO§M22:** Concipio reports progress between checks and says when a
    sweep has stalled: the remaining work stops shrinking, or the same spans
    are attached and detached repeatedly. The agent or its harness decides
    what to do about a stall.
  - **CPO§M46:** Concipio answers "why" for agents too. Asked about a line or
    a symbol, it returns the chain of concepts and statements above it and
    the other regions of its mechanism [K17, K18], in a few hundred tokens,
    where an agent would otherwise read file after file to reconstruct the
    same rationale. Large models gain as much from this as small ones.
  - **CPO§M10:** Kept concepts are what make small models useful. Without a
    map, a sweep must invent concepts, which takes a large model. With one, a
    sweep classifies each change against existing concepts, which small
    models do well. Large models and people review the concepts, the most
    expensive attention going to the fewest artifacts. Large models need the
    exhaustive check too: it shows them what they skipped, and it lets an
    authoring agent check how its code is organized.
- **CPO§M21:** Concipio gives two pass/fail verdicts on the agent's work.
  *Traced:* [M3] holds; undeclared behavior [M4] and unimplemented claims
  [M5] are reported alongside, not failed. *Explained:* every concept has a
  claim that cites at least one attached span as evidence, and every reference
  resolves or is reported as unverified. A failing verdict comes with the list
  of what remains. Neither verdict says the reviewer understood anything; only
  the reviewer can say that [M35].
### Adoption

- **CPO§M28:** Rigor is opt-in and incremental. In review mode, the concept
  graph lives in a per-user store outside the repository; nothing is written
  to the repository, ratified, or linted. Concepts persist there from one
  review to the next. Concipio writes such files only where a repository's
  docs do not yet bridge the gap to its code, and for a review that gap is
  only the diff.
  - **CPO§M12:** Sweeps are incremental. A diff updates the existing graph; it
    does not rebuild it.
  - **CPO§M39:** Adoption is a ladder, and a repository can stop on any rung:
    1. review mode, which asks nothing of the repository;
    2. concepts kept in the store across reviews;
    3. an ordinary design doc contributed for one feature, which the host
       project need only tolerate, cited by `Implements [GROW§3]` comments
       where the project accepts them and by anchors kept in the store where
       it does not;
    4. full traceability.

    The lower rungs must stay useful on their own, because many teams will
    not climb further.
    - **CPO§M40:** Human review of design text is invited, never required.
      Concepts in the store need none. In a repository with no design at
      all, a review still runs, and the agent proposes the top-level concepts
      itself [R15]. The agent may suggest that the human review its docs and
      check them in, unless it knows the project does not want them. A
      repository that has adopted Concipio is held to its own framework:
      Concipio warns about concepts missing from its docs.

### Review

- **CPO§M18:** A walkthrough runs top-down: the design statements, then the
  concepts under each, then the code, then the unjustified code [M8] and the
  unimplemented claims [M5]. It opens by stating the top-level concepts and
  asking the reviewer to confirm or correct them [R15]. Any harness can drive
  one; the first is a Claude skill. Adapters open code in the reviewer's
  editor or terminal.
  - **CPO§M33:** Each step goes from a concept the reviewer knows, to the
    unfamiliar mechanism, to the exact code, to a question the reviewer can
    now answer, such as "if execution stops between these two calls, what
    happens on retry?" The agent explains only the language features that
    answer depends on.
  - **CPO§M19:** The walkthrough always shows code. A reviewer approves code,
    not Concipio's description of it.
  - **CPO§M34:** Concipio keeps two ledgers: what the agent accounted for, and
    what the reviewer saw. Each concept lists all its spans. Those not shown
    are marked sampled, delegated, or deferred, and stay one step away.
    - **CPO§M35:** The reviewer can mark a span or concept *verified*,
      *suspect*, or *unclear*. Suspect starts a closer look. Unclear stays on
      the ledger until it is resolved.

- **CPO§M43:** Readers navigate with tools they already use. `cpo lsp`
  gives any editor that speaks the Language Server Protocol go to
  definition, find references, hover, and an outline for tags in docs and
  code, and, in a rendered review, jumps from a span to its code.
  - **CPO§M44:** Concipio never writes HTML into docs, because the raw text
    is what people read and maintain. Plain Markdown can only link to
    headings, so links in rendered docs go to headings and files, written as
    reference links that stay out of the way, and the language server
    handles everything finer.

### Assumptions and decisions

- **CPO§M16:** An assumption is something code at one site relies on that is
  established elsewhere, with no syntax connecting the two. Code should state
  its assumptions, usually in comments, and agents check those comments
  against the code.
  - **CPO§M17:** Assumptions are classified by a fixed vocabulary that a
    repository can extend later. Contract programming is one acceptable
    format, not a goal.
- **CPO§M47:** A decision is recorded with its reason, not as a ruling. It
  names who decided, a person or an agent, why, and the statements,
  assumptions, or measurements the reason rests on. Neither a person's word
  nor "the way it works" is a reason by itself.
  - **CPO§M48:** A decision whose premises change is flagged for review,
    not silently kept. "We chose X because Y" should be questioned as soon
    as Y stops being true.

## Traceability, a later hypothesis

These points describe persistent traceability [M30]. They are drafted in
[the trace format](docs/design/trace-format.md) and will be revised by what
review teaches before any of them is built.

- **CPO§M13:** The graph lives in the design docs and code comments that people
  already read, so a pull request shows its concept changes beside its code
  changes. By default Concipio adds no files of its own. A repository that
  needs much Concipio metadata has knowledge that belongs in its docs.
  - **CPO§M20:** Links name stable identities, never positions, and a link
    never forces its target to change when its source does. Code cites
    design statements, and detailed docs cite broader ones; a design may also
    cite a stable tag defined in a code comment. What a link must not do is
    make a broad doc a choke point that every narrower change has to edit,
    so a doc's children, and the code and tests behind a statement, are
    views Concipio derives rather than lists anyone maintains.
    - **CPO§M24:** Every doc is reachable from the master by some chain of
      links or citations, in either direction, just as unreachable code is
      dead code. Concipio checks that a doc is reachable, not how: a section
      may list the discussions behind it with a line each, or a doc may cite
      its parent, as the people and agents maintaining it prefer. Historic
      docs count too, so each needs a succinct description somewhere.
    - **CPO§M50:** `cpo audit` scores a repository rather than passing or
    failing it: every problem, counted by rule, and a total. With
    `--against` it compares another commit, and fails only if the total
    grew, so every commit can leave the docs a little better without having
    to fix all of them. Both commits are scored under today's `.cpo`, so a
    commit that adopts a new check is not a regression for the old problems
    it finds; a commit that loosens the checks fails instead. Debt a project has marked, such as stale docs and
    postponed orphans, is reported beside the score, not in it, so that
    marking a problem never costs more than hiding it.
  - **CPO§M27:** Before creating a concept or design statement, an agent
      searches for an existing one by walking the doc hierarchy down from the
      master. The hierarchy is the index. A vector index may speed the
      search, but it is generated and never committed.
  - **CPO§M14:** Anchors survive ordinary edits, and a human can follow them.
    Anchors whose code has changed are marked stale.
  - **CPO§M15:** Tests link to the concepts they verify.
  - **CPO§M36:** Concipio merges any file it writes without human or agent
    judgment.
- **CPO§M23:** Once a repository is onboarded, the checks that need no judgment
  run as a CI linter with no agent: every reference resolves, every ID has
  one definition, every span and doc reaches the master [M24], and every
  anchor resolves. A linter can confirm that links exist, not that they are
  true; that remains a job for agents and reviewers.
- **CPO§M25:** A human ratifies every design doc by signing it. The signature
  attests that the doc should exist, not that its text is final, so edits
  need ordinary review but no new signature. It covers the doc's path relative
  to the design root: a set of docs can move together, but a doc copied or
  moved alone loses its ratification.
  - **CPO§M26:** Agents may draft unratified docs on a branch. The linter
    fails on unratified docs at merge.

## Non-goals

- Static analysis. Linters, type checkers, and analyzers already exist.
- Contract programming as a requirement.
- A mandated document hierarchy.
- Replacing human review. Concipio directs attention; it does not grant
  approval.

## Where this will blow up

These are the risks most likely to sink the project, the deciding ones
first. Each sub-design that touches one must say how it handles it.

### Cost

- **CPO§R13:** **Toil.** Concipio costs more than it saves: reviewers read
  graphs instead of code, authors maintain tags nobody uses, and agents spend
  tokens on work they could have reused. This is the risk that decides
  whether the project is worth doing. *Mitigations:* build review first and
  traceability only on its evidence [M30]; record, in every milestone, the
  reviewer's time, the corrections the reviewer had to make, and the effort
  spent annotating.
  - **CPO§R12:** **Write amplification.** Agents copy the code's duplication
    and inconsistency up into the design layer, and the docs become a second
    codebase to review. *Mitigations:* a human ratifies every doc [M25];
    agents search before writing [M27]; statements drafted from code stay
    marked until a human adopts them [R8]; sibling statements that maintain
    the same rule are flagged like duplicate code [M6].
  - **CPO§R7:** **Merge conflicts.** Concurrent pull requests edit the same
    docs, and the tool rewrites the same anchors. *Mitigations:* links run
    upward [M20], so a new doc never edits its parent; Concipio merges its
    own files [M36]; generated indexes stay out of the repository; an anchor
    is rewritten only when it stops resolving.
  - **CPO§R6:** **Cost and context at scale.** A full sweep of a large
    codebase is expensive, and the concept index outgrows the context window
    of a small model. *Mitigations:* give each step only the concepts relevant
    to its code; cache results by content hash; treat the full sweep as a
    one-time cost and make incremental mode [M12] the everyday path.
  - **CPO§R11:** **Unterminating agent loops.** A distractible agent rewrites
    the same concept, oscillates between two attachments, or works without
    ever reducing what remains. Because the agent drives [M9], Concipio
    cannot stop it. *Mitigation:* make stalls visible [M22] so that any
    harness can act on them.
### Understanding

- **CPO§R14:** **Shown is not understood.** A walkthrough completes, every
  verdict passes, and the reviewer still could not say what happens when the
  code fails halfway. *Mitigations:* end each step with a question the
  reviewer can answer [M33]; keep the reviewer's ledger apart from the
  agent's [M34]; let unclear stay unclear until resolved [M35].
  - **CPO§R9:** **Confident, wrong explanations.** A fluent but mistaken
    concept leads a reviewer astray more effectively than no concept at all.
    *Mitigations:* show code always [M19]; make claims specific enough to
    check; let reviewers mark a concept suspect as easily as a line of code
    [M35].
  - **CPO§R15:** **Mismatched foundations.** With no design to start from,
    the agent's top-level concepts may not be the ones the reviewer has in
    mind, or the reviewer may not hold any. This trust cuts both ways: that
    the agent read the code correctly, and that the human understands the
    project well enough to be changing it. *Mitigation:* the walkthrough
    states its top-level concepts first and asks the reviewer to confirm or
    correct them before going deeper [M18]; a reviewer who cannot is told
    so, which is the point [M29].
### The quality of the map

- **CPO§R1:** **Goodhart's law on coverage.** An agent told to cover every
  span will do so cheaply, with vague catch-all concepts. Coverage stays at
  100% and carries no information. This risk should shrink as a repository's
  design docs improve, since a good doc leaves little room for a vague
  concept. *Mitigations:* allow unjustified code [M7]; have the skill reject
  generic concept names; require each concept to make a claim someone can
  check [M31]; have a large model review a sample of concepts from every
  sweep.
  - **CPO§R8:** **Circular justification.** The other cheap route to full
    coverage: docs drafted from code merely describe the code, so the code
    justifies itself and every smell disappears. Most repositories have no
    design docs, and writing them is part of adopting traceability: a large
    model drafts them, ideally with a human, under the same exhaustive check
    as everything else. *Mitigations:* mark statements drafted from code
    [M38], and remove the mark only in a change a human reviews; have the
    drafting agent report the unjustified code it found rather than writing
    statements to cover it.
- **CPO§R2:** **Competing concepts.** Two runs over the same code produce
  different concepts; one run produces "Auth," "Authentication," and "Login
  handling." Concepts compete for a place in the design docs, and a human
  picks the winner. The risk is that this happens silently, as noise in graph
  diffs, rather than as a decision put to a person. *Mitigations:* every sweep
  reuses existing concepts before creating new ones; renames and merges are
  explicit operations; a merge pass presents near-duplicates to a human as a
  choice.

- **CPO§R5:** **Unreliable assumptions.** Small models miss real assumptions
  and invent trivial ones ("assumes `x` is an integer"). Matching an
  assumption at one site to the code that guarantees it elsewhere is
  expensive at any model size. *Mitigations:* a fixed vocabulary with
  checklists for each language; report only what neither the type system nor
  a local check enforces; treat assertions already in the code as seeds; make
  the comment the record, so the agent checks a written claim rather than
  discovering an unwritten one.

### Anchors and languages

- **CPO§R3:** **Fragile anchors.** A refactor or a reformat breaks anchors
  across the codebase, and the whole graph goes stale at once.
  *Mitigations:* prefer citations in comments, which move with the code;
  anchor by quoted text within a named symbol rather than by line number;
  follow git history before declaring an anchor stale; separate "moved" from
  "changed."
  - **CPO§R4:** **The wrong granularity.** Anchoring individual lines buries
    the graph in noise; anchoring whole files says nothing. *Mitigation:*
    anchor to declarations and top-level blocks by default, and to spans
    within one only when it serves more than one concept.
- **CPO§R10:** **Language blind spots.** C macros hide control flow, and Ruby
  metaprogramming hides what code exists at all. *Mitigation:* where static
  structure is incomplete, let the agent use test runs or a language server
  as optional evidence [M11].

## Milestones

1. **Enforce the hierarchy.** Two mechanical checks hold on a real change
   and on Concipio's own docs: every changed line reaches a design statement
   [M42], and every design fits on a screen [M41]. The test change is
   an agent-written pull request of about 1,700 lines across Ruby models,
   a background job, guest scripts, and specs, in a
   repository that has not adopted Concipio. Its design text is the pull
   request description, and everything Concipio writes stays in the store
   [M39]. The checks must keep holding as the change is rebased.
   [The sweep's measurements](docs/measurements/2026-10-18-first-sweep.md)
   record what it cost and what it found.
2. **Prove it on a kernel module.** A C codebase adopts Concipio in its own
   repository, with
   its existing design as the master. Every line of its C, including the
   kernel module, traces to a design; assumptions about units,
   execution context, locking, and on-disk format are written down [M16];
   and a walkthrough is measured by what the reviewer can answer afterward
   and what it cost [R13, R14].
3. **Trace this repository.** Once traceability is built, Concipio traces its
   own code to this document.

## Prior art

Concipio borrows from requirements-traceability tools (StrictDoc, Doorstop,
Sphinx-Needs, and Doxygen's `\requirement`, `\satisfies`, and `\verifies`),
concern-mapping research (concept assignment, feature location, concern
graphs), annotation anchoring (W3C Web Annotation, Hypothesis), and guided
review (CodeTour, change decomposition), and records decisions as
architecture decision records do, adding links from each reason to the
statements it rests on. [docs/consultations](docs/consultations)
holds the surveys behind this list.

## Design docs

This list is for readers; under [M20], Concipio will generate it.

- [Review mode](docs/design/review-mode.md): manifest, spans, concept graph,
  commands, and verdicts [M9, M10, M11, M12, M21, M22, M28, M31, M32, M37, M38, M39, M40, R11]
- [Fields, importance, and briefs](docs/design/fields.md): project
  structure as fields on statements, schemas, and what agents must never
  lose [M24, M47]
- [The store](docs/design/store.md), a design for keying review decisions
  to code rather than to reviews [M28, R3, R6]
- [Trace format](docs/design/trace-format.md), a draft for traceability
  [M13, M14, M15, M20, M24, M36, R3, R4, R7]

Planned:

- Walkthrough skill and editor adapters [M18, M19, M33, M34, M35, R9, R14, R15]
- Assumption vocabulary [M16, M17, R5]
- Design-doc bootstrapping [M1, M4, M5, R8]
- Ratification [M25, M26, R12]
