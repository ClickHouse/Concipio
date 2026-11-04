<!-- Implements [CPO§V25] -->
<!-- Draft. This is the text `cpo help agent` will print. -->

# Reviewing a change with Concipio

You are reviewing a change so that a human can understand it. Concipio
(`cpo`) holds the review's state and checks your work; it makes no judgments.
You make them, and `cpo` records them. Every command prints JSON.

You are expected to be a large model. Delegate span-by-span work to
sub-agents on a small, inexpensive model; do the judgment-heavy steps
yourself.

When you mention a tag such as `R2` to the human, give its name with it:
"R2 (Competing concepts)." `cpo show R2` prints a tag's name and text.

## 1. Start the review

Run `cpo review init <base>..<head>`. If the change is stacked on others,
pass them with `--stacked-on`; they are context, not scope. The output tells
you whether the repository has adopted Concipio and lists the spans to cover.

## 2. Harvest before you draft

Collect the design text that already exists: the pull request description,
linked issues, commit messages, and any docs the change touches. Add all of
it with `cpo statement add --quote "<exact text>"`, not only the claims,
and keep its shape: a summary first, then its points with `--parent`, then
the claims under each point. Give each a `--kind`: `claim` for what code
must do, `context` for the problem and background, `planned` for future
work, and `descriptive` for facts such as measurements. These are *given*
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
behavior, which is what the human needs to see. Draft a statement
(`cpo statement add --drafted`) only to describe such behavior, never to
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

Concipio holds docs to three standards: completeness (every line of code
traces to a design, every doc is reachable), correctness (the docs say what
the code does and agree with one another), and consumability (every design
fits on a screen, and what matters most stays near the top). The commands:

- `cpo audit` scores all three. `cpo audit --against main` fails only if a
  change made the score worse; aim to lower it a little in every commit.
- `cpo lint` reports each problem, and passes when nothing is new or worse
  than `.cpo-baseline.toml`. After fixing problems, tighten the baseline with
  `cpo lint --write-baseline`. Never rewrite it to hide a new problem.
- `cpo coverage` shows how much code the design's citations claim, by
  directory. `--strict` counts only `Implements` and `Tests` citations.
- `cpo path <doc or tag>` shows how a doc is reached from the master;
  `cpo show <tag>` shows a statement and everything citing it; `cpo brief`
  prints what nobody may lose.

The conventions:

- `.cpo` declares the docs whose numbered headings define citable sections,
  with their prefix and citation pattern. Within a doc, a bare `§5c` means
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

## Asking why

Concipio also answers questions outside a review. Before reading files to
learn why some code exists, run `cpo why <path>:<line>`. It returns the
code's concepts, the design statements above them, and the other regions
that implement the same thing, usually in a few hundred tokens.
