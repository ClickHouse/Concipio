# Kinds of design point

Parent: [Concipio](../../README.md)

**Status: proposed.** Nothing here is built.

Not every design point asks the same of the code under it. A point that
describes one mechanism should claim a bounded stretch of code and be
tested. A library routine serves many mechanisms and owes its callers a
contract. Deferred work needs an owner and goes stale. Treating them all
alike either leaves the library and the debt unsupported or holds them to
rules that do not fit. This doc gives each kind its own rules, defines
the unit of work an audit takes [W2], and marks which points describe
work still to come.

## Kinds

- **CPO§Y1:** A statement or section may carry a `Kind` field:
  `mechanism`, `library`, `todo`, or `workstream`. Each kind has its own
  obligations, checked as schemas are [F4, F5], applied by kind rather
  than by doc. A leaf point is a mechanism unless it says otherwise; a
  project may add kinds of its own.

## What is and what will be

- **CPO§Y14:** A design describes what will be as well as what is. A
  point may carry `Status=planned` or `Status=in-progress`; one with
  neither describes the code as it stands. Planned points are a
  roadmap's items [W35], which agents claim and work through a plan.
  - **CPO§Y17:** Concipio owns the values of `Status`, because it acts
    on them: it offers planned points to agents, and drops the status
    when the work lands [Y15]. A project's own labels for planned work,
    such as a milestone or a release, are fields of their own,
    `{Status=planned Milestone=v2}`, which a schema can check and a query
    can select [F5, F7], rather than suffixes on the status.
- **CPO§Y15:** When planned work lands, its point drops the status and
  becomes a claim about the code as it stands, which puts it in the
  queue of any audit covering it [W2]: plan, build, verify, then cite
  [Y13]. A to-do point [Y8] differs in origin, not in handling: it is
  deferred work someone found, where a planned point is work someone
  designed.

## Workstreams

- **CPO§Y16:** A workstream is a section marked `Kind=workstream`, which
  lists the plans in flight under it, one bullet each, linking to each
  plan's log [W29]. A project may keep one at the top of its master, or
  one under each part of the design, and Concipio files a new plan
  under the nearest one above its target [W30]. Completed plans move to
  the workstream's list of completed ones.

## The code a point claims

- **CPO§Y12:** In an adopted design, code names its design, not the
  other way around: the code carries a point's tag [T6], and the point
  speaks of "the code implementing" it. A point claims the code that
  cites it.
  - **CPO§Y18:** A design written before adoption often names its code
    instead, mentioning functions and files in backticks, as in
    `` `ring_take` `` or `src/ring.c`, and nothing cites it yet. Until
    something does, Concipio takes the code a point names, resolved to
    declarations as for look-alikes [T52], as the code it claims. That
    is a bridge for adoption, not a way to write new design.
- **CPO§Y13:** Adoption turns names into citations. Citing a section
  before its claims are checked would lock its errors in, so citations
  come after verification [W21], and coverage, which counts only
  citations, rises late [M51].

## Mechanisms

- **CPO§Y2:** A mechanism is a leaf design point, or one close to a leaf,
  with the code it claims [Y12] and the uncited helpers only that code
  calls [T51]. It is small enough to read whole in one sitting, which
  makes it the unit of an audit [W2]. On a codebase no citation reaches
  yet, the mechanisms are the design's own sections.
- **CPO§Y3:** A mechanism claims no more code than the breadth limit
  [M49], and tests cite it. Inner points of the design are not
  mechanisms; they arrange mechanisms, and people review them by
  signing the structure [W17].

## Libraries

- **CPO§Y4:** A library is code serving many mechanisms: the routines
  `cpo helpers` finds serving four or more design points [T57]. It is
  supported, not exempted. Its design point states a contract, what it
  promises every caller, and the code relying on it cites the contract
  as a reference [T28].
- **CPO§Y5:** An audit asks two things of a library: whether its callers
  rely on more than its contract promises, and whether another library
  already does the same job [Y6]. Concipio cannot judge the first, but it
  can make sure nobody skips it: the audit's item for a library carries
  a checkbox for each caller the call graph finds [T51], and the item is
  done only when every box is ticked.

## Duplicates

- **CPO§Y6:** Finding routines that do the same job in different words
  needs embeddings, and comparing every pair is too costly in a large
  codebase. An agent, or an optional extra, writes embeddings to the
  store, and Concipio does the nearest-neighbour search; it computes
  none itself [M9]. Embeddings and candidate pairs are glue [M53].
- **CPO§Y7:** A verdict on a pair is a decision, and is versioned so
  that nobody asks again. Two routines that differ on purpose carry a
  comment at one of them, `CPO§distinct: from foo_release, because ...`,
  read as an exemption is [T15]. Two that do the same job become a
  to-do point to merge them [Y8].

## To-do points

- **CPO§Y8:** A to-do point is deferred work: a reviewer's directive
  [W19], an audit finding the team has no cycles for [W12], or a known
  debt. It carries an owner or a tracker reference, and goes stale after
  a number of days `.cpo` sets, as `Updated` does [F15]. When done, it is
  deleted, or becomes the design it called for.
  - **CPO§Y9:** A to-do point records its origin, such as the audit or
    review that raised it, so a project can see what each audit cost.
- **CPO§Y10:** Concipio lists every `TODO`, `FIXME`, and `XXX` in code. One
  that names a point, `TODO(PROJ§TD12)`, is tracked; one that names none
  is loose, counted, and held from growing by the baseline [T40], so a
  project pays its debt down over time. Text after the tag is optional:
  the point says what the work is, and Concipio lists every site that
  names it.
- **CPO§Y19:** A to-do may live in a code comment alone until a second
  site needs it. Then it becomes a point: `cpo todo promote path:line`
  adds it as a sub-point of the point covering that code [T65], and
  rewrites the comment to name it, so the second site can name it too.
- **CPO§Y11:** `cpo todo` lists open to-do points by owner, priority, or
  age, with links built from a URL template `.cpo` gives for the tracker
  field, `Tracker=JIRA-1234`. Concipio exports what a tracker can import
  and can compare its points with a tracker's export, but calls no
  tracker itself. Every roadmap item tracked this way is also what an
  agent reads after its context is compacted: `cpo brief` lists the work
  in flight and who has it [F11].

## Decisions

- **CPO§Y20:** A library's contract is checked by judgment, with Concipio
  keeping the checklist [Y5]. {Decided="Josh" Updated=2026-11-07}
  Concipio is not a model, so it can only make sure an agent checks
  every caller, not decide whether a caller is right.
- **CPO§Y21:** A to-do starts in code and moves into the design when two
  sites need it [Y19]. {Decided="Josh" Updated=2026-11-07} Most code is
  now written by agents, so the commands are built for them first, and
  promotion is one command rather than a hand edit.
