# Trace format

Parent: [Concipio](../../README.md)

**Status: draft hypothesis.** This doc sketches persistent traceability
[M30]. Nothing in it is built before review mode has been tried on a real
change, and what that review teaches will revise it [R13].

This doc defines how a repository records its traces: the tags that name
design statements, the roles in which code and docs cite them, and the anchors
that stand in for citations where code cannot carry one. It refines [M13],
[M14], [M15], [M20], [M24], and [M36], and answers [R3], [R4], and [R7].

**CPO§T1:** The format is conventions for text people already write:
concepts are statements in design docs, and citations are comments in code.
By default Concipio adds nothing else to the tracked tree. Anchor files appear
only where code cannot carry a citation, and `.cpo` only where a project
overrides a default.

## Tags

- **CPO§T2:** A tag is a prefix, the section sign, and an ID: `GROW§3` or
  `CPO§M3`. The prefix may be any string without whitespace or brackets,
  including emoji. An ID is a number, optionally preceded by capital letters
  naming a namespace, and followed, while the ID is provisional, by a suffix
  [T31].
- **CPO§T3:** A doc's definitions choose its prefix; no config declares it.
  Concipio finds every definition by scanning the repository's Markdown, so a
  citation needs no path, and two docs that define the same tag fail the
  check. A family of docs may share a prefix and split it by namespace: the
  master owns `CPO§M` and `CPO§R`, and this doc owns `CPO§T`. Every
  definition in a namespace must come from the doc that owns it, so two docs
  cannot collide by numbering into the same namespace.
- **CPO§T37:** A tag is an identity, not a name. Every tool output and every
  agent reply that mentions a tag gives its name with it, as in "R2
  (Competing concepts)." A definition may carry a short bold title for this;
  otherwise its first sentence serves [T4]. IDs stay serial and stable while
  names can be reworded freely.
- **CPO§T5:** IDs are never reused. A tag that was defined in history and is
  defined nowhere now is *retired*; citing it fails the check. Retiring a
  statement leaves its old citations visibly broken instead of silently
  pointing at something new.
- **CPO§T31:** An ID minted on a branch is provisional and carries a short
  random suffix, as in `CPO§M50.k3`, so that no two branches mint the same
  one. At merge, Concipio assigns the next free number and records the
  mapping in the retired list [T36]. A branch stacked on the merged one still
  cites `M50.k3`; when it rebases, Concipio rewrites those citations from the
  recorded mapping. Neither step needs judgment [M36].
- **CPO§T65:** `cpo elaborate <tag> "<text>"` adds a point under a
  statement or section, minting its tag so nobody has to: the next free
  ID in the parent's namespace, never a retired one [T5], or for a
  numbered section the next sub-number, as `5c.4` under `5c`, with a
  heading one level deeper. Agents and people refine a design without
  counting IDs by hand, and promoting a to-do [Y19] is the same step.
- **CPO§T36:** A tracked list records retired IDs and the final number of
  each merged provisional ID. Concipio checks citations against it without
  needing history, so a shallow clone can tell a retired ID from a new one
  [T5].
- **CPO§T20:** Tags inside Markdown code, whether blocks or inline spans,
  are examples, except in a block tagged `cpo`, which holds data [F14].
  Concipio parses Markdown, and source comments, before it looks for tags.
- **CPO§T29:** Concipio warns about a statement that no code implements,
  unless the statement is marked planned or descriptive [M5]. Mentions in
  other docs do not silence the warning.

## Roles

- **CPO§T21:** Every occurrence of a tag has a role. The default roles are
  *definition*, *implementation*, *test*, and *reference*. Concipio can say,
  for any tag, where it is defined, implemented, tested, and mentioned.
- **CPO§T4:** A tag in bold, followed by a colon inside or outside the bold,
  at the start of a paragraph or list item in a design doc defines it:
  `**GROW§3:**`. The statement is that paragraph or item, up to any nested
  item that is a definition of its own [T38]. The colon keeps a bold mention
  from becoming a definition by accident. Each tag
  has exactly one definition. The definition's first sentence, or its bold
  title if it has one, is its human-readable name.
- **CPO§T38:** A definition nested in another definition's list item
  refines it: the outer statement is its parent, and Concipio derives the
  outline from the nesting. Each nested statement elaborates its parent
  rather than starting a new topic, so a reader can skip a whole branch.
  Concipio cannot check that rule; agents and reviewers can.
- **CPO§T6:** A comment marks implementation with `Implements [GROW§3]` and a
  test with `Tests [GROW§3]`. The bracketed tag is complete, so every site
  that implements or tests a statement is one grep away. Only these roles
  cover code [M3]. A citation states where the reason for the code lives; it
  never states a condition the code must meet.
- **CPO§T32:** `See [GROW§3]`, or a tag in any other wording, is a reference.
  It covers nothing and counts toward nothing. It should say in a few words
  how the statement bears on the code here, not restate the statement, which
  an editor can show on hover.
- **CPO§T8:** A covering citation applies to the declaration or top-level
  block that the comment documents: a function, method, class, struct, or a
  block passed to a top-level or class-level call, such as a Ruby DSL block.
  A comment that opens a file gives context but covers nothing [R4]. Where
  the attachment is ambiguous, as before a preprocessor construct, Concipio
  reports it as ambiguous rather than guessing.
- **CPO§T7:** Design docs may cite statements in their own doc set by short
  form: `[M3]`, or a list such as `[M3, R4]`. The prefix is the one the citing
  doc's family uses. Short forms are references. There are no ranges: a
  search for `M14` must find every citation of it, and a range from `M13` to
  `M15` would hide it. Code comments always use full tags, one per citation
  [T6].

## Configurable syntax
- **CPO§T22:** Each role's syntax is a regular expression in `.cpo`, in which
  `${TAG}` stands for any tag. A project may replace the defaults, for
  instance to use an ASCII sign in place of `§`, and may add roles of its own.
  Patterns use Python's syntax, which `grep -P` and `rg -P` also accept for
  ordinary patterns, so a person can run the same search Concipio does.
- **CPO§T34:** Projects that already use Doxygen's `\satisfies` and
  `\verifies`, or StrictDoc's `@relation`, can map those markers to
  Concipio's roles [T22] instead of adding a second set.

### Numbered sections

- **CPO§T39:** A project whose design already numbers its sections need not
  retag them. `.cpo` can declare a doc whose numbered headings are
  definitions, with a prefix, a pattern for its headings, and a pattern for
  its citations elsewhere, such as `DESIGN.md §6c`. Each heading defines
  its section, its nesting gives the tree, and the size rule measures it as
  a section [M41]. A repository that has not adopted Concipio keeps that
  `.cpo` in the store [T17].
  - **CPO§T60:** A heading in a declared doc that looks numbered but
    that its heading pattern does not read is reported. It defines no
    section, so citations of it dangle in silence, which is worse than an
    error.
- **CPO§T41:** A bare section number, `§5c`, means section 5c of the doc it
  is written in, or of the doc linked just before it, as in
  "[the answers](answers.md), §5". Concipio finds any doc's numbered
  headings without configuration, so editors can follow such references
  in every doc. In a doc that defines tags by its numbered headings
  [T39], a resolved bare number is also a citation of the tag; elsewhere
  it is navigation only, since it names no tag.
- **CPO§T43:** In a doc that defines tags by its numbered headings [T39], a
  bare section number that names none of its sections is dangling, and
  `cpo lint` reports it. Other docs may number their own sections yet cite
  another doc's bare, so their bare numbers are not checked.
- **CPO§T44:** A code file is not a doc and has no sections of its own, so a
  bare `§5c` in a comment means whatever the project says. A source in
  `.cpo` with `bare_in_code = true` is what bare numbers mean in code, and a
  file can override that with a comment, `cpo-default: SPEC`, in its first
  lines, naming another source by prefix or path.
  - **CPO§T62:** A section number in a comment that follows another doc's
    name, `notes.md §10` or `ERRATA §3`, is that doc's,
    and does not count toward the default's section. A doc is named by a
    path, a Markdown file name, a declared prefix, or the name of one of
    the project's docs. Comments are often written in capitals, so a
    capitalized word alone does not name one.

### Stale and retired text

- **CPO§T42:** A statement, a section, or a whole doc may be marked stale
  with a field that says why, `{Stale="the roster is now five reviewers"}`.
  A whole doc carries it between its title and its first section, or in its
  front matter. Marking staleness is cheaper than fixing it, and better than
  leaving it unmarked, so a stale mark is reported as debt, not as a problem
  [M50].
- **CPO§T45:** A heading in a design doc that records history, a date or a
  status word such as "built", "settled", or "unscheduled", is reported. A
  design says what is true now; when it changed belongs in reports, and why
  in decisions with reasons [M47]. `.cpo` may change the list of words.
- **CPO§T47:** A heading inside a blockquote, `> ### 5.1`, is reported in a
  design doc. Concipio does not read it as a section, so its text counts
  toward the section above it; it is almost always a section someone hid.
- **CPO§T48:** `.cpo` may list retired terms, each with why it retired:
  `[retired] legacy_gate = "the gate was removed"`. `cpo lint` reports each live
  doc and code comment that still uses one, since a passage naming a removed
  mechanism is likely to describe it as current. A passage that names it
  only to say it is gone is recorded in the baseline [T40].
  - **CPO§T50:** A retired term that code still defines or uses, outside
    its comments and strings, is reported too. Either the mechanism is not
    gone, or its retirement is unfinished.
- **CPO§T49:** `.cpo` may name archive paths by glob, for old text kept
  verbatim. An archived doc defines nothing, cites nothing, and is checked
  by no rule; it is only a link target, and only links into it make it
  reachable [M24].

## Questions and checks

- **CPO§T23:** Concipio answers the common questions these roles allow, so
  neither agents nor people need to write the searches: which statements lack
  an implementation, which lack a test, and, given coverage data, whether the
  tests that cite a statement exercise the code that implements it [M15].
- **CPO§T24:** Concipio indexes a project's own test design rather than
  replacing it. A test matrix can be a design doc whose cases are tagged
  statements. Tests cite the cases they cover, and a project-defined role
  records cases that cannot be tested, with the reason.
- **CPO§T9:** A design doc names its parent in its opening lines, with a link
  to the parent doc. The master names none. Concipio derives each doc's
  children [M20].
- **CPO§T33:** Every warning is a lint rule with a severity that `.cpo` can
  set, including off.
- **CPO§T40:** Every limit starts where a project is and moves toward the
  defaults. `.cpo`'s `[lint]` table sets the statement, section, and
  breadth limits; `cpo lint --write-baseline` records today's problems, and
  later runs fail only on problems that are new or worse than recorded. A
  project can also postpone orphans by listing paths or globs under
  `postponed`; they are counted in every report but do not fail it, so a
  project can adopt Concipio before every old doc has a home.
  - **CPO§T61:** The baseline records which Concipio wrote it. When lint
    finds new problems and Concipio has changed since, it says so: a new
    rule or a wider measure finds old problems, which a reviewer must not
    mistake for growth. The project records the new measure in a commit
    of its own, before the change, so each commit's growth is its own.

## Helpers and the rules they keep

Code no design claims still says what it serves, through its callers, and
what rules it keeps, through its guards and their comments.

- **CPO§T51:** `cpo helpers` sorts the functions no citation covers by the
  design they serve: the design points cited by the nearest code that calls
  them. A helper serving one point should cite it [M7].
  - **CPO§T57:** The report groups helpers by what they serve. One serving
    many points is shared infrastructure, or a mechanism that deserves its
    own point. One that only uncited code, only tests, or nothing calls is
    reported as such, and so is one named only outside any function, as a
    callback in a table is.
  - **CPO§T52:** Beside the taxonomy, `cpo helpers` clusters helpers that
    may duplicate one another: the same body, the same top-level name in
    different files, or mostly the same calls, weighing a rare call above a
    common one. These are candidates for a person or an agent to judge, not
    findings. Code that says the same thing in other words needs a model to
    find, which Concipio leaves to the agent.
  - **CPO§T53:** For each cluster, `cpo helpers` lists what the copies do
    not share: the calls and fields only some of them use, by which copies
    use them. Copies that drifted apart, one asserting a guard another
    lacks, are where duplication hides bugs, so a reviewer reads this
    list as a checklist.
    - **CPO§T55:** Each difference is labelled by the role it plays in the
      copy that has it: a guard, a condition that returns early or an
      assertion; an output, a write through a pointer parameter; a
      signature difference, a use of a parameter no other copy has; or
      body. Guards come first, since a guard one copy lacks can be a bug,
      while an output or a parameter explains a difference without drift.
      A guard over a parameter only one copy takes is still a guard, marked
      as depending on the signature, since it may be drift all the same.
    - **CPO§T56:** Clusters take in cited functions too, each shown with
      what it cites. A difference in a copy that cites the design is
      likely intended, and one in a copy that cites nothing is the one to
      ask about. A copy that cites nothing but calls a function that
      does is shown with that call, since the rule it keeps is likely
      the callee's.
  - **CPO§T54:** Function-like macros stay in the call graph, so a guard
    written as a macro shows among the differences, but are listed as
    helpers only on request.
- **CPO§T58:** `cpo unwritten` lists the guards, early returns and
  assertions, in code citing no design, whose comment says why they exist.
  Such a comment is a design rule someone found, often through a bug, and
  wrote down only where it is enforced. A comment naming an incident, a
  date, a bug, an issue, or a commit, is the surest sign, so those are
  listed by default; `.cpo` may add patterns of its own, such as its bug
  tags, under `[unwritten] incident`.
  - **CPO§T59:** A guard that calls a predicate, `if (!ours(n)) return`,
    may keep its reason in the predicate's header comment rather than its
    own. When that header names an incident and the predicate cites no
    design, the guard is reported with the header as its evidence, and a
    predicate many guards call is reported once, with all of them.
### Claims of impossibility

- **CPO§T63:** `cpo unreachable` lists the comments that claim a state
  cannot happen ("unreachable", "cannot be exhausted", "by construction")
  and the branches code asserts are dead, such as `ASSERT(0)`. Each is
  backed by a test the comment names, a static assertion beside it, or a
  cited design point that tests cite; one backed by none is reported. A
  claim of impossibility is the comment most likely to hide a defect,
  because nobody tests the state it rules out. `.cpo` may add phrases,
  markers, and evidence patterns, such as its scenario names, under
  `[unreachable]`.
  - **CPO§T64:** With `lint = true` under `[unreachable]`, each unbacked
    claim is a lint problem, so a project can baseline today's claims
    and require every new one to come with its evidence [T40].

## Languages

- **CPO§T66:** Concipio finds declarations through each language's
  text-object query, which maps its syntax onto one vocabulary of
  functions, classes, comments, and calls, as editors such as Neovim use
  them. The queries are vendored from nvim-treesitter-textobjects, so a
  language with a grammar and a query needs no code of Concipio's own.
  A function, or a method where the grammar says so, is a declaration; a
  class that holds functions, or a language's class or module, is a
  scope; a C-family record holding only data is a declaration named by
  its keyword. A record defined inside a function is part of it.
  - **CPO§T68:** What a query does not mark stays Concipio's own: C's
    macros and typedefs, Ruby's blocks such as RSpec's, and which
    declaration a comment documents [T8].

## Views of code

- **CPO§T25:** Design docs do not store links to the code that implements
  them. Concipio generates that view from citations whenever a reader or agent
  asks [M20]. Docs change when the design changes, not when the code does, so
  they do not become a point of contention [R7]. A doc may still link to code
  for its readers; such a link is prose, not a trace.

## Anchors

Some code cannot carry a tag: vendored code, generated code, or patches to an
upstream project whose diffs must stay small. An anchor attaches a tag to such
code from outside it.

- **CPO§T26:** Tags and anchors are interchangeable, and tags are preferred.
  Concipio converts between them for any file that can carry comments.
- **CPO§T10:** Anchors live in sidecar files that mirror the code's path:
  anchors for `src/backend/foo.c` live in `cpo/anchors/src/backend/foo.c.toml`.
  Each anchor records a tag, a role, a scope, a quote, and a commit:

  ```toml
  anchors = [
    { tag = "CPO§M3", role = "implementation", scope = "Anchor#resolve", quote = "def resolve(ref):", commit = "80e90fe" },
  ]
  ```

  The scope is the symbol path of the enclosing declaration. The scope and the
  quote together are the anchor's identity.
- **CPO§T35:** Each anchor file holds one anchor per line, sorted. A Concipio
  merge driver, registered in `.gitattributes`, merges anchor files as sets
  keyed by tag, role, scope, and quote [M36]. An anchor whose scope the
  merged code no longer contains is marked stale, not dropped; whether the
  code moved or vanished is for resolution [T11] to find out.
- **CPO§T12:** A quote must match exactly one place within its scope, and may
  carry a little surrounding text to make it so. Concipio rejects an ambiguous
  or missing quote when the anchor is written, so an agent that misquotes
  learns immediately.
- **CPO§T11:** Concipio resolves an anchor by finding its scope and quote in
  the current tree. Failing that, it follows the quoted lines forward from the
  anchor's commit through git history. Failing that, the anchor is stale.
- **CPO§T13:** Concipio rewrites an anchor only when it no longer resolves in
  the current tree but history locates it elsewhere. Code moving within its
  scope does not churn anchor files [R7].
- **CPO§T14:** An anchor's commit is the last commit on the main branch at
  which Concipio verified the anchor, or empty for code that is new on a
  branch. It is a starting point for following history [T11], never part of
  the anchor's identity. Concipio never writes a commit's own hash into that
  commit.

## Assumptions

- **CPO§T27:** A comment states a local assumption [M16] in prose, beside the
  citation of the statement the code implements.
- **CPO§T28:** An assumption shared between sites is hoisted into a design doc
  as a statement. The site that guarantees it cites it as an implementation;
  sites that rely on it cite it as a reference. A search for the tag then
  lists every site on both sides. A project that wants to tell the two sides
  apart can add a role for relying sites [T22].

## Exemptions

- **CPO§T15:** A comment containing `CPO§exempt:` and a reason covers its
  node without citing a statement. Exemptions satisfy the linter and appear
  in every report, counted. They are for code that truly serves no design
  statement, such as plumbing, not for helpers, which cite what they
  support [M7]. Unjustified code [M7] never becomes exempt automatically; a
  person writes the reason, and the linter flags an exemption added in the
  same change as the code it exempts.
  - **CPO§T46:** Coverage counts exempt code apart from both covered code
    and code nobody accounts for. An exemption says the code needs no
    design, which a reviewer can check; an unjustified mark says nobody
    has found one, which a reviewer should ask about. A project may aim to
    account for all its code while citing only part of it.
- **CPO§T16:** `.cpo` may exclude paths by glob. Excluded code is outside the
  check entirely, and the report says how much was excluded.

## Other repositories

- **CPO§T30:** A tag with another repository's prefix cites that repository's
  design, pinned to a release tag or a commit: `DRV§T3@v1.2`. Tags are
  preferred. `.cpo` lists the foreign prefixes it accepts and where their
  docs can be found, such as a submodule or a vendored copy. A foreign
  citation whose docs are absent is reported as unverified, apart from
  failures [M21]. Deciding which version to cite is the agent's job, not the
  tool's.

## Configuration

- **CPO§T17:** `.cpo` is optional. It sits at the repository root, or, for
  a project that has not adopted Concipio, in the store [T18], where only
  its user sees it. It is TOML, and every key has a default:

  ```toml
  master = "README.md"
  design_root = "."
  anchors = "cpo/anchors"
  exclude = []

  [roles]
  definition = '^\s*(?:[-*]\s+)?\*\*${TAG}(?::\*\*|\*\*:)'
  implementation = 'Implements \[${TAG}\]'
  test = 'Tests \[${TAG}\]'

  [lint]
  # bare-tag-without-note = "warn"

  [foreign]
  # DRV = "vendor/driver"
  ```

  `design_root` is the base for the relative paths that ratification signs
  [M25]. Moving the whole doc set means changing one line here. A tag matched
  by no role pattern is a reference.

## Working state

- **CPO§T18:** Everything Concipio keeps outside the repository, such as
  review manifests, kept concepts, logs, and a local `.cpo`, lives in the
  store [V22]. Nothing there is tracked, and review mode [M28] writes nothing
  else.
- **CPO§T19:** A concept kept in the store [M28] becomes a tracked
  concept by being written as a statement in the lowest design doc that
  covers it, with nested concepts as statements that cite their parents.
  Its attachments become `Implements` and `Tests` citations, or anchors where the
  code cannot carry them. Concepts that never leave the store are still
  useful to whoever keeps them.

## Open questions

- Should a definition carry a stable short name beside its number, as the
  C++ standard cites `[stmt.if]` alongside its section numbers? A citation
  could then read `[GROW§3 park-map]`, and Concipio could check that the
  name still matches the number. It is not yet clear whether agents or
  people would rather write the number, the name, or both.

- How does a design doc mark a statement planned or descriptive [M5, T29]?
