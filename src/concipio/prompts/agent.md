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

## Asking why

Concipio also answers questions outside a review. Before reading files to
learn why some code exists, run `cpo why <path>:<line>`. It returns the
code's concepts, the design statements above them, and the other regions
that implement the same thing, usually in a few hundred tokens.
