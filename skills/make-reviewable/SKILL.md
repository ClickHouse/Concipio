---
name: make-reviewable
description: Make a pull request or commit range reviewable with Concipio: map every changed span to a concept, delegating span-by-span classification to Haiku sub-agents, until `cpo reviewable` passes. Use when the user asks to make a change reviewable, to prepare a change for a concept walkthrough, or to run Concipio on a pull request.
---

<!-- Implements [CPO§V26] -->

# Make a change reviewable

You orchestrate; Haiku sub-agents classify; `cpo` judges. Spend large-model
tokens on judgment and small-model tokens on volume, and record both.

## 1. Gate

Run `cpo reviewable <target> --json` in the repository, where the target is
`OWNER/REPO#N`, a PR URL, or `<base>..<head>`. Pass `--stacked-on` for
changes this one builds on. Exit 0 means it is already reviewable; stop.

## 2. Settle the top of the map yourself

- Read the design text in the manifest and add all of it with
  `cpo statement add --quote`, keeping its structure with `--parent` and
  typing each passage with `--kind` (claim, context, planned, descriptive).
  The top statement is the review's cornerstone; if the change belongs to
  a larger design the repository has, make that the parent.
- List the spans by scope (the `spans_by_file` output and `cpo next`), not
  by reading every line, and draft the concepts a reviewer would need:
  one per statement, plus the medium-level mechanisms beneath them. Each
  concept needs a claim specific enough to check. Add them with
  `cpo concept add`.
- If the user knows the high-level concepts, ask them; if not, propose
  yours and say so in your report.

## 3. Delegate the sweep

Group uncovered spans by file. Dispatch one Haiku sub-agent per file (at
most four at a time), each with this prompt, filled in:

> You are classifying changed code for a review, one span at a time, in
> `<repo>`. Loop: run `cpo next --path <file> --json`; after the first
> call, which lists the concepts, add `--brief` to leave the list out, and
> use `cpo show C<n>` if you need a concept's claim. If `work` is null,
> stop. Otherwise read the span's code. Lines marked `+` (or `-` for
> deleted code) are what the change touched; classify that change, not the
> whole declaration around it. Then do exactly one of:
> - `cpo attach <span> <concept>` (add `--role test` for test code), when
>   a concept clearly fits;
> - `cpo unjustified <span> --reason "<why>"`, when the code serves no
>   listed concept and no statement mentions it;
> - write down a proposal (span, name, claim, parent) and skip the span by
>   marking it unjustified with reason `proposal: <name>`.
>
> Prefer unjustified over a vague fit. A helper belongs to the concept it
> serves. Do not create concepts. When done, reply with your proposals and
> the number of spans you handled, and nothing else.

## 4. Record cost

After each sub-agent finishes, record what it spent:
`cpo record --model haiku --tokens <total> --spans <handled>`.
Record your own tokens at the end if you can see them.

## 5. Review proposals and repeat

Turn good proposals into concepts, merge duplicates (`cpo concept merge`),
then re-attach the spans you held: `cpo attach` clears their unjustified
mark. Make sure every concept's claim cites at least one span it covers,
such as "(S41)". Repeat `cpo reviewable` until it exits 0. If `cpo status`
reports a stall, stop and report what is stuck.

## 6. Report

Give the user: the verdicts, undeclared behavior and unimplemented claims
from `cpo check`, the unjustified spans with reasons, and `cpo status`
cost per model and per span. Do not start the walkthrough unless asked.
