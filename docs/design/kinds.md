# Kinds of design point

Parent: [Concipio](../../README.md)

**Status: proposed.** Nothing here is built.

Not every design point asks the same of the code under it. A point that
describes one mechanism should claim a bounded stretch of code and be
tested. A library routine serves many mechanisms and owes its callers a
contract. Deferred work needs an owner and goes stale. Treating them all
alike either leaves the library and the debt unsupported or holds them to
rules that do not fit. This doc gives each kind its own rules, and defines
the unit of work an audit takes [W2].

## Kinds

- **CPO§Y1:** A statement or section may carry a `Kind` field:
  `mechanism`, `library`, or `todo`. Each kind has its own obligations,
  checked as schemas are [F4, F5], applied by kind rather than by doc. A
  leaf point is a mechanism unless it says otherwise; a project may add
  kinds of its own.

## The code a point claims

- **CPO§Y12:** A design point claims code in one of two ways. It *names*
  code when its text mentions a declaration or a path, as in `` `ring_take` ``
  or `src/ring.c`, which Concipio resolves to declarations as it does for
  look-alikes [T52]. It *cites* code when the code carries its tag [T6]. A
  drifted design names code long before anything cites it, so everything
  that judges a point works from the code it names or cites.
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
  already does the same job [Y6].

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
  that cites a to-do point, `TODO [PROJ§TD12]: ...`, is tracked; one that
  cites nothing is loose, counted, and held from growing by the baseline
  [T40], so a project pays its debt down over time.
- **CPO§Y11:** `cpo todo` lists open to-do points by owner, priority, or
  age, with links built from a URL template `.cpo` gives for the tracker
  field, `Tracker=JIRA-1234`. Concipio exports what a tracker can import
  and can compare its points with a tracker's export, but calls no
  tracker itself. Every roadmap item tracked this way is also what an
  agent reads after its context is compacted: `cpo brief` lists the work
  in flight and who has it [F11].

## Open questions

- Should a library's contract be checked against its callers'
  assumptions mechanically, as with typed preconditions, or only by an
  audit's judgment?
- Does a to-do point belong in the design doc it concerns, or in one
  backlog doc per project, as a roadmap?
- Which names in a section's text count as naming code: only backticked
  identifiers and paths, or any word that matches a declaration?
