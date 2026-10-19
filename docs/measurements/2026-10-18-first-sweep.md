# First sweep of review mode

The first run of review mode on a real change, following the
make-reviewable skill. Recorded so later runs have a baseline.

## Setup

- **Change:** an agent-written pull request of about 1,700 lines across
  20 files: Ruby models, a background job, guest scripts, and specs,
  stacked on an earlier change, in a repository that has not adopted
  Concipio.
- **Spans:** 234 (156 RSpec examples, 52 methods, 6 shell functions, 20
  hunks).
- **Orchestrator:** Claude Opus 5.5. It added 16 given statements from the
  pull request description, skipping its headings, and drafted 18
  concepts from span scope names without reading the code.
- **Sweep:** six Claude Haiku sub-agents, one per group of related files,
  at most four at a time, each looping `cpo next --path`.

## Cost

| Group | Spans | Haiku tokens | Tool uses | Seconds |
|---|---:|---:|---:|---:|
| 1. A background job and its spec | 42 | 50,258 | 89 | 154 |
| 2. Guest scripts and their specs | 49 | 54,914 | 101 | 156 |
| 3. A resource model and its sizing | 45 | 51,639 | 65 | 165 |
| 4. A server state machine and its spec | 46 | 57,713 | 63 | 200 |
| 5. A volume model and its spec | 34 | 43,596 | 74 | 181 |
| 6. Two server models | 18 | 31,465 | 26 | 84 |
| **Total** | **234** | **289,585** | **418** | |

That is **1,237 Haiku tokens per span**. The smallest group cost the most
per span (1,748), which suggests each sub-agent's fixed overhead is
roughly 10,000 to 15,000 tokens; larger batches amortize it.

The orchestrator's own tokens were not measured. Its work was the
statements, the 18 concepts, reviewing two proposals, and repairing five
claims.

Before the sweep, one `cpo next` reply was 8,589 bytes, 60% of it a
statement list repeated on every call. Dropping the statements and adding
`--brief` cut it to 1,560 bytes for the first call and 847 after.

## What the sweep found

- **A small model overruled the large model's claim.** The orchestrator
  claimed that an operation already started keeps its original target. The
  Haiku sub-agent read the code, found that it rereads the latest target
  so that later requests can enlarge an operation in progress, refused to
  attach the claim, and said why. One half of the change behaves as the
  claim says and the other does not, while the pull request states the
  rule as if it applied to both. That is a question for the reviewer.
- **Sub-agents could not see what changed.** Spans widen to the enclosing
  method, and `cpo next` showed the whole method. Haiku classified a
  metrics method as generic export, when the change only keeps
  observations running through an outage; and it called a one-line eager
  load generic enumeration. `cpo next` now marks the changed lines.
- **Claims drafted before the sweep cite guessed spans.** Three concepts
  failed *Explained* because their claims cited spans that Haiku reasonably
  attached elsewhere. `cpo check` found all three; fixing them took one
  edit each.
- **Five of six groups proposed no new concepts.** Either 18 concepts
  covered the change, or Haiku hesitates to propose. The only proposal came
  from the diff-blind case above.

## Result

`cpo reviewable` exits 0: 234 of 234 spans covered, every concept
explained, all 16 given statements implemented, and one span unjustified
(a `require` in a spec).

## Not yet measured

- Whether the attachments are right. A human reviewer's comments on the
  pull request are the first independent check.
- The reviewer's time and understanding, which the walkthrough measures.

## After the rebase

The pull request was later rebased. `cpo reviewable` carried the first
review to the new head: of 236 spans, 194 matched unchanged, 32 matched
with changed code, and 10 were new. Matched spans kept their IDs, so every
concept's claim stayed valid.

One Haiku sub-agent handled the 42 spans that needed a look, for **63,188
tokens, 1,504 per span**: higher per span than the first sweep, since
confirming a carried classification still means reading the code, but
about a fifth of re-sweeping all 236 spans at the first sweep's rate. It
confirmed 27 carried classifications, changed 5, and left two new test
setup spans unjustified.

`cpo reviewable --strict` now exits 0: every span reaches a given
statement, and the rendered design passes `cpo lint`.
