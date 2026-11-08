<!-- Implements [CPO§V25] -->
<!-- This is the text `cpo help agent` prints. -->

# Working with Concipio

Concipio (`cpo`) traces code to its design and holds the state of the work
on both: it records your judgments and checks them, and makes none itself.
Every command prints JSON unless given `--human`. Read the part you need:

- **Reviewing a change**, so a person can understand it: the numbered
  sections below.
- **Adopting Concipio in a repository**, with or without a design doc to
  start from: its section, after the review.
- **Working an audit**, checking a design against its code: its section.
- **Asking why** some code exists: the last section.

Run `cpo status` first: it lists any audit or review already in progress.

# Reviewing a change

You are reviewing a change so that a human can understand it. Concipio
holds the review's state and checks your work; you make the judgments, and
`cpo` records them.

You are expected to be a large model. Delegate span-by-span work to
sub-agents on a small, inexpensive model; do the judgment-heavy steps
yourself.

When you mention a tag such as `R2` to the human, give its name with it:
"R2 (Competing concepts)." `cpo show R2` prints a tag's name and text.

## 1. Start the review

Run `cpo review init <base>..<head>`. If the change is stacked on others,
pass them with `--stacked-on`; they are context, not scope. The output tells
you whether the repository has adopted Concipio and lists the spans to cover.

## 2. Harvest before you infer

Collect the design text that already exists: the pull request description,
linked issues, commit messages, and any docs the change touches. Add all of
it with `cpo statement add --quote "<exact text>"`, not only the claims,
and keep its shape: a summary first, then its points with `--parent`, then
the claims under each point. Give each a `--kind`: `claim` for what code
must do, `context` for the problem and background, `planned` for future
work, and `descriptive` for facts such as measurements. These are *stated*
statements. Do not write statements of your own yet.

The top statement is the cornerstone of the review. If the change belongs
to a design the repository already has, make that design's statement its
parent instead of starting a new tree.

## 3. Settle the top-level concepts

If the repository has design docs, use them. Otherwise ask the human what
the change is for, at the highest level. If they cannot or will not say,
propose the top-level concepts yourself, in a few sentences each. The
walkthrough will ask the human to confirm them.

## 4. Sweep

Dispatch small-model sub-agents. Each one loops:

1. Run `cpo next`. It returns one span with its code and the concepts that
   might fit it, or reports that nothing remains. Lines marked `+` or `-`
   are what the change touched; classify that change.
2. Do one of three things:
   - `cpo attach <span> <concept>`, adding `--role test` for test code;
   - propose a new concept, with a name, a claim specific enough to check,
     and a parent;
   - `cpo unjustified <span> --reason "<why>"`.
3. Repeat.

Prefer marking a span unjustified over attaching it to a vague concept such
as "helpers" or "utilities." A helper belongs to the concept it serves, and
a shared test fixture to the concepts its tests cover. If context or
planned work in the design text accounts for an unjustified span, say so:
`cpo unjustified <span> --reason "<why>" --see D<n>`.

Review every proposed concept before adding it with `cpo concept add`. Merge
duplicates with `cpo concept merge`. If the code does something no statement
mentions, add a concept for it anyway; `cpo` will report it as undeclared
behavior, which is what the human needs to see. Infer a statement
(`cpo statement add --inferred`) only to describe such behavior, never to
justify it.

## 5. Finish

Run `cpo check` and `cpo status` until both verdicts pass. If `cpo status`
reports a stall, stop and tell the human what is stuck, rather than
continuing to try.

## 6. Hand off

Start the walkthrough. Afterward, if the project would welcome design docs,
suggest that the human review the concepts and check them in. If you know it
would not, say nothing; the concepts stay in the store either way.

When the change merges, its concepts should join the design of the branch it
merged into: merge duplicates with the concepts already there, and make the
review's cornerstone a child of that branch's design.

## Adopting Concipio in a repository

Adopt in small steps; every step leaves the repository better, and none
needs a person's time until the design is ready to sign.

1. See where the repository stands. These need no setup: `cpo status`,
   `cpo coverage`, `cpo helpers --counts`, `cpo unreachable`, and
   `cpo unwritten`. Fix any broken links `cpo lint` reports first; they
   are cheap and certain.
2. Find the design. If the repository has a design doc, one that says how
   the code works rather than how to use it, declare it in `.cpo`; the
   doc's path is enough, as `[[source]]` then `doc = "DESIGN.md"`, and
   `cpo config` shows what was inferred. Then record today's problems
   with `cpo lint --write-baseline`, in a commit of its own.
3. If it has none, write one. Start a design doc beside the README and
   link it from there. Give it numbered sections, one per mechanism, each
   a few paragraphs, taking the facts from the code, the user docs, and
   the tests; say what the code does now, in claims a reader could check.
   Then declare it and record the baseline, as in step 2. Do not cite it
   from code yet.
4. Audit it: `cpo audit next <date>`, as below. For a design you wrote,
   the audit is a second, independent read, so give each section to a
   fresh helper rather than checking your own draft.
5. Cite as sections are verified, upgrading references to `Implements`
   where the code truly implements the section.
6. Ask a person to sign the outline of what is verified: whether the
   sections are the right ones, in the right places, not every line.

Concipio holds docs to three standards: completeness (every line of code
traces to a design, every doc is reachable), correctness (the docs say what
the code does and agree with one another), and consumability (every design
fits on a screen, and what matters most stays near the top). The commands:

- `cpo status` lists the work in progress, then scores all three.
  `cpo status --against main` fails only if a change made the score worse;
  aim to lower it a little in every commit.
- `cpo lint` reports each problem, and passes when nothing is new or worse
  than `.cpo-baseline.toml`. After fixing problems, tighten the baseline with
  `cpo lint --write-baseline`. Never rewrite it to hide a new problem.
- `cpo coverage` shows how much code the design's citations claim, by
  directory. `--strict` counts only `Implements` and `Tests` citations.
- `cpo helpers` sorts the uncited functions by the design points their
  callers serve, and lists look-alikes that may duplicate one another. Cite
  a helper's point, merge real duplicates, and give shared infrastructure
  a point of its own.
- `cpo unwritten` lists guards whose comments name an incident, in code
  citing no design. Each is a rule to write into the design and cite.
- `cpo unreachable` lists comments claiming a state cannot happen that no
  test, static assertion, or tested design point backs. Write the test
  that drives the state and name it in the comment, or correct the claim.
- `cpo path <doc or tag>` shows how a doc is reached from the master;
  `cpo show <tag>` shows a statement and everything citing it; `cpo brief`
  prints what nobody may lose.

The conventions:

- `.cpo` declares the docs whose numbered headings define citable sections;
  the doc's path is enough, and its prefix and patterns default. Within a doc, a bare `§5c` means
  that doc's section; in code, it means the source marked `bare_in_code`, or
  the one a file names with a `cpo-default: PREFIX` comment.
- A citation of the form `Implements §5c` or `Tests §5c` covers the
  function or block it documents. A bare `§5c` is only a reference. Upgrade a
  reference to `Implements` only when the code truly is that section's
  implementation; a reference that explains is not one.
- Code that serves no design, such as plumbing, takes a comment
  `CPO§exempt: <why>` above it. Coverage counts it as accounted for, apart
  from cited code. Never exempt a helper; cite what it supports.
- Every doc must be reachable from the master by links; give each one a line
  of description where it belongs. Fields are Markdown attribute lists:
  `{Importance=critical}` keeps a statement near the top and in the brief, and
  `{Stale="why"}` marks what you cannot fix yet. A critical statement also
  carries `{Verified=<date>}`, set only after you check it against the code;
  lint asks again when the date ages or the code citing it changes.
- Headings say what is true now. Dates and status words such as "built" or
  "settled" in a design's headings are history, which belongs in reports.
- When a mechanism is removed, list its names under `[retired]` in `.cpo`,
  each with why; lint then finds the passages that still describe it. Old
  text kept verbatim goes under a path `.cpo` lists in `archive`, where
  nothing in it counts. Never hide a section in a blockquote.
- A design point should claim no more than 200 lines of code; refine it into
  sub-points, or extract smaller routines.

## Working an audit

An audit is a named worklist of design sections, each checked against the
code it names or cites. Several agents can work one at a time.

1. `cpo audit next <name>` claims a section for you and prints its text and
   code. It resumes your claim if you already hold one.
2. Check each claim the section makes against the code.
3. Record the outcome: `cpo audit done <name> <unit> --verified`, or
   `--finding "<what is wrong, and where>"`, or
   `--question "<what a person must decide>" --for <whom>`. Recording
   changes no file in the repository, so you can record a finding before
   the fix and the corrected prose land.
4. Repeat. `cpo audit mine <name>` shows what you hold, and
   `cpo audit status <name>` shows the whole audit.

If Concipio cannot tell who you are, it prints a `CPO_AGENT` line to export.
Keep that line in any summary of your work, and give each helper you start
its own.

## Asking why

Concipio also answers questions outside a review. Before reading files to
learn why some code exists, run `cpo why <path>:<line>`. It returns the
code's concepts, the design statements above them, and the other regions
that implement the same thing, usually in a few hundred tokens.
