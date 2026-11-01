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
- **CPO§T36:** A tracked list records retired IDs and the final number of
  each merged provisional ID. Concipio checks citations against it without
  needing history, so a shallow clone can tell a retired ID from a new one
  [T5].
- **CPO§T20:** Tags inside Markdown code, whether blocks or inline spans,
  are examples. Concipio parses Markdown, and source comments, before it looks
  for tags.
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
- **CPO§T22:** Each role's syntax is a regular expression in `.cpo`, in which
  `${TAG}` stands for any tag. A project may replace the defaults, for
  instance to use an ASCII sign in place of `§`, and may add roles of its own.
  Patterns use Python's syntax, which `grep -P` and `rg -P` also accept for
  ordinary patterns, so a person can run the same search Concipio does.
- **CPO§T34:** Projects that already use Doxygen's `\satisfies` and
  `\verifies`, or StrictDoc's `@relation`, can map those markers to
  Concipio's roles [T22] instead of adding a second set.
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
  statement, not for helpers, which cite what they support [M7]. Unjustified
  code [M7] never becomes exempt automatically; a person writes the reason,
  and the linter flags an exemption added in the same change as the code it
  exempts.
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
