# Kinds of design point

Parent: [Concipio](../../README.md)

**Status: proposed.** Nothing here is built.

Not every design point asks the same of the code under it. A point that
describes one mechanism should claim a bounded stretch of code and be
tested. A library routine serves many mechanisms and owes its callers a
contract. Deferred work needs an owner and goes stale. Treating them all
alike either leaves the library and the debt unsupported or holds them to
rules that do not fit. This doc gives each kind its own rules.

## Kinds

- **CPO§Y1:** A statement may carry a `Kind` field: `mechanism`,
  `library`, or `todo`. Each kind has its own obligations, checked as
  schemas are [F4, F5], applied by kind rather than by doc. A leaf point
  that code cites is a mechanism unless it says otherwise; a project may
  add kinds of its own.

## Mechanisms

- **CPO§Y2:** A mechanism is a leaf design point, or one close to a leaf,
  with the code that implements it: the code citing it, and the uncited
  helpers only that code calls [T51]. It is small enough to read whole in
  one sitting, which is what makes it the unit of an audit [W2].
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
  already does the same job [Y6].

## Duplicates

- **CPO§Y6:** Finding routines that do the same job in different words
  needs embeddings, and comparing every pair is too costly in a large
  codebase. An agent, or an optional extra, writes embeddings to the
  store, and Concipio does the nearest-neighbour search; it computes
  none itself [M9]. Embeddings and candidate pairs are derived, belong
  to the model that made them, and stay in the store.
- **CPO§Y7:** A verdict on a pair is a decision, and is checked in so
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
  that cites a to-do point, `TODO [PROJ§TD12]: ...`, is tracked; one that
  cites nothing is loose, counted, and held from growing by the baseline
  [T40], so a project pays its debt down over time.
- **CPO§Y11:** `cpo todo` lists open to-do points by owner, priority, or
  age, with links built from a URL template `.cpo` gives for the tracker
  field, `Tracker=JIRA-1234`. Concipio exports what a tracker can import
  and can compare its points with a tracker's export, but calls no
  tracker itself.

## Open questions

- Should a library's contract be checked against its callers'
  assumptions mechanically, as with typed preconditions, or only by an
  audit's judgment?
- Does a to-do point belong in the design doc it concerns, or in one
  backlog doc per project, as a roadmap?
