# The store

Parent: [Review mode](review-mode.md)

**Status: design, not built.** This replaces the store layout that review
mode uses today [V12, V22], and the carry-over between heads [V11].

The store keeps what agents and reviewers decided about a repository's code,
outside the repository [M28]. Today it files that work by review, so every
new head of a change gets its own copy: when the first test change was rebased, 194
of its 236 spans were copied unchanged. This doc keys the work to the code
instead, so one record serves every commit where its code is unchanged.

**CPO§K22:** The store is an on-ramp, not a destination. It lets one person
use Concipio on a team that has not adopted it. A team that wants to share
the work adopts it instead: Concipio converts records into design docs and
`Implements` citations in the code [T26], and git, not Concipio, keeps the
history. Concipio does not try to be a version control system for its own
files.

## Identity

- **CPO§K1:** A project is identified by the root commit reached by following
  first parents from the default branch's tip. Every clone, fork, and
  worktree of the project shares one store. A repository that imported
  another project's history keeps its own identity, because the imported
  root is never on its first-parent line. The root commit only names the
  store; no lookup consults it.
- **CPO§K2:** A region is a stretch of code that the span rules [V8] cut out.
  Its identity is its path and its scope. Its fingerprint is a hash of its
  text with every run of whitespace, line breaks included, collapsed to one
  space, so reindenting or reflowing a region leaves it unchanged and
  changing a token does not. A reflow that splits or joins words still
  changes it; the cost is a duplicate record, never a wrong one.
  - **CPO§K15:** When an agent judges that a changed region still means what
    its record says, `cpo confirm` takes the new fingerprint without
    remaking the decision. The confirmation is logged like any decision.

## Records

- **CPO§K3:** A record holds what was decided about one region: the concepts
  it serves, in which role, or an unjustified mark. It also holds the
  region's fingerprint, its first and last three lines as evidence a person
  can read, its line range at the commit where it was reviewed, that commit,
  and the review that made the decision.
  - **CPO§K16:** When a changed region is reviewed again, its new record
    names the record it supersedes. A region's records then form a history
    like blame's, one entry per change to the code rather than one per head.
- **CPO§K4:** A record applies at any commit whose tree has a region with the
  same path, scope, and fingerprint, whatever the commit's hash. A rebase,
  squash, or cherry-pick that leaves a region's text alone leaves its record
  in force, so a record is written once, not once per head.
- **CPO§K5:** A record goes stale when its region's scope still exists but
  its fingerprint differs. A stale record never applies. `cpo check` counts
  its region as uncovered, and `cpo next` offers it to an agent with the old
  decision shown, to confirm or replace [V11, K15]. Concipio never stretches
  a record over code nobody reviewed.
- **CPO§K6:** A record whose scope no longer exists is orphaned. Concipio
  keeps it as history but never applies it. When git reports that the file
  was renamed, the record moves to the new path mechanically, since the
  region did not change.
  - **CPO§K19:** A rebase can orphan the commit a record was reviewed at
    while leaving the region itself alone. The record still applies, since
    its fingerprint decides [K4], but it would cite a commit no branch
    contains. So whenever Concipio asks git about a region, it records the
    commit git now attributes the region to, which is an ancestor of the
    code in question, and cites that.
- **CPO§K7:** A small agent that finds no purpose for a region says so and
  nothing more: either the region serves nothing it can find, or it serves
  a purpose no single concept captures. Only the driving agent or a
  reviewer turns the first into advice: in a pull request, a change to
  request; in a codebase being adopted, an item for a longer-term plan.
  Regions of the second kind go back to the sweep, to attach to the
  concepts they serve or to their nearest common parent.

## Scope

- **CPO§K17:** Records exist at every level of a file's structure: the file,
  each class or module, each function, each region within one. The answer
  to "why is this line here?" is the record of its region followed by the
  records of the scopes that enclose it, nearest first, so a line inherits
  the purpose of the function and file around it. The chain follows the
  source's nesting, so it resolves without running anything.
- **CPO§K18:** The regions that serve one concept, wherever they sit, form
  that concept's *mechanism*. A mechanism is what a reviewer reads to
  understand one design statement, and what an agent reads instead of
  opening files.

## Layout and format

- **CPO§K8:** The store holds, per project:
  - `name`, a label an agent chooses for people, such as the remote URL;
  - `statements.toml` and `concepts.toml`, the project's design;
  - `regions/`, one file per code file, mirroring the repository's paths;
  - `reviews/<base>..<head>/`, each review's manifest, its design text
    snapshots as Markdown, and its command log.
- **CPO§K21:** A region file lists its records in the source file's order,
  each with its first and last lines. Two regions with identical text are
  told apart by the records around them, as a diff places a hunk by its
  context. Identical regions are also reported as duplication [M6], since
  code repeated closely enough to collide is usually code that should be
  shared.
- **CPO§K9:** Files people may read are TOML, read with `tomllib` and written
  with `tomli-w`. The dependency is small and saves writing an emitter that
  every richer structure would strain. Each record is its own table, and
  tables keep source order, so a change to one record is a small diff. The
  command log, which only machines read, stays JSON Lines.

## Lookups

- **CPO§K10:** To find the records at a commit, Concipio cuts the regions of
  the files in question at that commit and matches them to records. Cut
  regions are cached by git blob ID, so a file whose content is unchanged
  between commits is never parsed twice.
- **CPO§K11:** A render is a view at a commit [V29]: the statements and
  concepts, with the records that apply there. Rendering a pull request's
  head and rendering `main` are the same operation over the same records.
- **CPO§K12:** Git history is for navigation, not lookup. Concipio diffs a
  record's reviewed commit against the commit in question to find what
  changed, and uses blame only where history was rewritten: to trace a
  squash or rebase commit back to the pull request whose records describe
  it, and to re-anchor provenance [K19].
  - **CPO§K20:** A new head whose regions all match existing records needs
    no new records, which covers fast-forwards and rebases that change no
    code. Its review is a new manifest that cites the old one; when the old
    head is no longer on any branch, the old review is renamed to the new
    head and never consulted again.

## Migration

- **CPO§K13:** Existing reviews convert mechanically: each span with an
  attachment or mark becomes a record at its review's head, and the graph
  splits into `statements.toml` and `concepts.toml`. No decision is
  remade. The conversion is checked by rendering every converted review
  before and after and comparing the results.

## Open questions

- Hierarchy may prove far more common than overlap: most regions may serve
  one concept, inherited through their enclosing scopes [K17], rather than
  several at once. Sweeps of a large adopting project should measure how often a region
  needs more than one concept.
