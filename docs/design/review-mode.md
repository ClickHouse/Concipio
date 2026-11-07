# Review mode

Parent: [Concipio](../../README.md)

Review mode is what milestone 1 runs on. An agent sweeps one change in a
repository that has not adopted Concipio, builds a concept graph in a
per-user store, and walks a reviewer through it. This doc specifies
what Concipio, the command-line tool, does in that mode. The walkthrough skill
gets its own doc.

It refines [M3, M4, M5], [M21], [M22], [M28], [M31], [M32], [M34], [M35], and
[M37, M38, M39], and answers [R2], [R3], [R4], [R11], and [R13].

**CPO§V1:** Review mode asks nothing of the repository: no `.cpo`, no tags,
no docs, no hooks. Everything it writes lives in the store [V22], and it
runs the same on a repository that will never adopt Concipio.

## The store

- **CPO§V22:** The store is a directory per project under
  `$XDG_DATA_HOME/concipio/`, which defaults to `~/.local/share/concipio/`.
  It is data, not cache: kept concepts and reviewer marks cost judgment to
  make and cannot be regenerated for free. A project is identified by its
  repository's root commit, so every clone and worktree of one project, at
  any path, shares one store. A human-readable name from the remote URL sits
  beside it.
- **CPO§V23:** `cpo review init` says whether the repository has adopted
  Concipio, meaning it has a `.cpo` or any definitions [T4]. If it has,
  concepts are checked against its docs and those missing from them draw
  warnings [M40]. If not, the review runs from the store alone and draws no
  warnings about docs.

## Division of labor

- **CPO§V2:** Concipio never judges [M37]. The agent decides what the
  statements are, what the concepts are, which spans belong to which, and
  why; the reviewer decides what they understood. Concipio records those
  decisions, checks that they are complete and consistent, and refuses ones
  that lack the evidence they require.
- **CPO§V3:** The graph changes only through Concipio's commands, and every
  command is appended to a log in the store. Stall detection [M22], the
  agent's ledger [M34], and the cost record [R13] are all read from that log.

## The manifest

- **CPO§V4:** `cpo review init` writes a manifest [M32] that fixes what the
  review covers. It records:
  - the repository, and the base and head commits of the change;
  - each change it is stacked on, by base and head;
  - a snapshot of each source of design text, such as a pull request
    description, a linked issue, or a doc in the repository; a pull request
    is named with its repository, since a number alone is ambiguous across
    forks;
  - the span rules in force [V8] and the parser versions used.

  A review never silently follows a moving branch. A new head means a new
  manifest, and the old graph is carried over to it [V11].
- **CPO§V5:** Changes the review is stacked on are context, not scope. Their
  spans are outside [M3]. Their design text and any concepts kept from their
  own review [V12] are available, so a concept in this change may have a
  parent from an earlier one. For milestone 1, the change the test pull
  request is stacked on is context, and the pull request is scope.

## Design statements

- **CPO§V6:** The agent splits the design text into statements with
  `cpo statement add`, quoting the text each statement comes from. Concipio
  rejects a quote that does not appear in a snapshot. Such statements are
  *stated* [M38]. A statement the agent writes from the code instead is
  *inferred*, and carries no quote.
  - **CPO§V31:** Harvesting keeps all of the design text and its structure.
    Each statement may name a parent statement, so a summary, its numbered
    points, and the claims under each point keep their shape. Each has a
    kind: a *claim*, which code must implement; *context*, such as the
    problem being solved; *planned* work; or a *descriptive* fact, such as a
    measurement. Only claims need code, and a parent counts as implemented
    when a statement refining it is.
- **CPO§V7:** Each statement gets a short local ID, `D1`, `D2`, and so on,
  unique within the project's store.

## Spans

- **CPO§V8:** A span is a diff hunk widened to the smallest named declaration
  around it, unless that declaration is a class, module, or file body, or is
  longer than a limit set in the manifest, in which case the span is the hunk
  itself. A hunk that spans several declarations splits at them. Lines that
  carry nothing alone, such as comments, blank lines, block ends, and the
  opening lines of classes and `describe` blocks, join a neighboring span.
  Files with no parser, such as YAML, use the hunk. Deleted code forms spans
  on the base side, scoped by the declarations it was deleted from [M32].
- **CPO§V9:** Concipio uses tree-sitter for every language, so the rules read
  the same across them. These count as named declarations at first:
  - **Ruby:** `def`, including `label def` in Ubicloud progs; a block passed
    to a class-level call, such as a Sequel association with a block; and
    `Sequel.migration` bodies. A run of adjacent class-level calls without
    blocks, such as `semaphore` and `one_to_many` lines, forms one span.
  - **RSpec:** each `it`, and each `before`, `after`, `let`, or `subject`
    block. `describe` and `context` give scope but are never spans.
  - **Shell:** each function; otherwise the hunk.
  - **C:** each function, each struct, union, or enum definition, each
    `typedef`, and each `#define`. C++ waits for its grammar.

  The list grows as reviews find constructs it handles badly, and each review
  records the version it used.
- **CPO§V10:** A span's identity is its path, its scope, and a quote, as for
  anchors [T10, T12]. Concipio reports any span whose quote is ambiguous
  within its scope, and widens the quote until it is unique.
- **CPO§V11:** When a change gets a new head, as when it is rebased,
  `cpo reviewable` pins a new review and carries the latest earlier review
  of the same design text into it. A span carries when its path, scope, and
  quote match, or failing that when its path and scope match exactly one
  span; it keeps its ID, so claims that cite it stay true. A carried span
  whose code changed returns to the remaining work, with its old attachment
  shown, until an agent confirms or replaces it. Stated statements carry only
  if their quotes still appear in the new design text.

## The graph

- **CPO§V12:** The graph holds statements, concepts [M31], spans,
  attachments, unjustified marks [M7], and reviewer marks. It is JSON in the
  store. Concepts are kept per project, not per review, so a later review
  starts from them [M28]. Each concept's text is a
  draft design-doc statement in Markdown, `**GROW§3:** ...`, so moving it into
  a doc [M39] means pasting it and adding `Implements` comments. `cpo export` and
  `cpo import` move concepts between users, so a team can share them
  without committing anything.
- **CPO§V13:** An attachment joins a span to a concept in a role:
  *implementation* or *test* [T21]. A test span attaches with the test role,
  so the walkthrough can show, for each claim, the tests that assert it.
- **CPO§V14:** `cpo unjustified` marks a span with a reason. Concipio
  requires the reason to be non-empty and never turns an unjustified mark into
  anything else [T15]. With `--see`, the mark also names a context or
  planned statement that accounts for the span [M45].

## Commands

- **CPO§V15:** Every command prints text on a terminal and JSON otherwise, for
  agents; `--human` and `--json` override the default.

| Command | Effect |
|---|---|
| `cpo review init <base>..<head>` | Write the manifest [V4] and list the spans |
| `cpo statement add` | Add a stated or inferred statement [V6] |
| `cpo concept add`, `cpo concept edit` | Add or change a concept [M31] |
| `cpo concept merge` | Combine two concepts, recorded as such; `concept edit` renames [R2] |
| `cpo attach`, `cpo detach` | Join a span to a concept, or undo it [V13] |
| `cpo unjustified` | Mark a span unjustified [V14] |
| `cpo check [--strict]` | Give the verdicts; with `--strict`, fail on undeclared behavior too [V17, M42] |
| `cpo render` | Write the review as a design doc in the store [V29] |
| `cpo lint` | Check that every design fits on a screen [M41] |
| `cpo next [--path P]` | Give the next piece of work, with its context, optionally only from paths starting with P [V24] |
| `cpo status` | Report progress, stalls, and cost [V18] |
| `cpo record` | Record tokens an agent spent [V19] |
| `cpo reviewable <PR or range>` | Exit 0 if the change is ready for human review, or show the first unmet obligation [V28] |
| `cpo show <tag>...` | Show a statement, concept, or span: its name, text, location, and everything that cites or attaches to it [T37] |
| `cpo mark` | Record what the reviewer saw or concluded [V16] |
| `cpo why <path:line>` | Explain why a line exists: its record, the design above it, and its mechanism [M46] |
| `cpo lsp` | Serve editors over the Language Server Protocol [M43] |
| `cpo help agent` | Print the agent protocol [V25] |

- **CPO§V24:** Concipio holds the review's state so the agent does not have
  to. `cpo next` returns the next piece of work: an unattached span with its
  code, its changed lines marked, and the concepts that might fit it, or a
  concept that lacks a claim. A small agent can run a whole sweep by calling `cpo next` and
  answering, with no memory of its own between calls.

- **CPO§V28:** `cpo reviewable` is the gate between the agents' work and the
  human's. Given a pull request or a range, it pins the change, reusing a
  review already pinned to the same commits, and exits 0 when both verdicts
  pass. Otherwise it shows the first unmet obligation and exits 1. Anything
  that can run a command and read an exit code can drive a change to
  reviewable: a skill, CI, or an editor.

- **CPO§V30:** A rendered review opens with a cornerstone: the outline of
  its statements, one line each, linked to their sections. It is the root
  of the review's design, and in a pull request it mirrors the description.
  The driving agent chooses the root. Where the change belongs to a larger
  design, the root's parent is a statement in that design, and the
  cornerstone becomes a link to it.
- **CPO§V29:** `cpo render` writes the review's statements and concepts to
  the store as a Markdown design doc, one section per statement, with each
  concept's spans beneath it, and checks that it fits on a screen [M41].
  Each statement is a heading, so any viewer can link to it, and each span
  links to its file and line through reference links at the end of the
  doc, which the size rule ignores [M44].
  It is the design a review produces, in the form a repository could adopt.

## The reviewer's ledger

- **CPO§V16:** The walkthrough skill records, for each span, whether the
  reviewer was shown it, or whether it was sampled, delegated, or deferred
  [M34]. It records the reviewer's verdicts on spans and concepts, *verified*,
  *suspect*, or *unclear* [M35], with the reviewer's words. These are
  `cpo mark` commands, so they are logged like everything else.

## Verdicts and progress

- **CPO§V17:** `cpo check` gives the verdicts of [M21]:
  - *Traced* fails while any span in scope is neither attached nor marked
    unjustified. It reports undeclared behavior [M4] and unimplemented claims
    [M5] without failing on them, and reports coverage against stated and
    inferred statements separately [M38].
  - *Explained* fails while any concept lacks a claim, or has a claim that
    cites none of its attached spans.
- **CPO§V18:** `cpo status` reports what remains of the current review,
  among the work in flight it lists first [W37], and how it changed since
  the last check. It reports a stall when what remains has not shrunk for a
  number of commands set in the manifest, or when the log shows the same span
  attached and detached repeatedly [R11].

## The agent protocol

- **CPO§V25:** `cpo help agent` prints the protocol an agent follows, as a
  prompt. It ships with the tool and is versioned with it, and each step
  ends in a command, so the checks enforce what the prompt asks.
- **CPO§V26:** The protocol assumes a large model reads it and delegates.
  The large model harvests design text, settles the top-level concepts, and
  reviews the concepts others propose. It dispatches sub-agents on a small
  model, such as Haiku, to classify spans one at a time through `cpo next`
  [V24, M10]. Running a whole sweep on a large model spends a user's tokens
  on work a small one does well.
- **CPO§V27:** The protocol's steps, in order:
  1. Set the scope and run `cpo review init` [V4].
  2. Harvest the design text that already exists, such as the pull request
     description, linked issues, commit messages, and docs, and add it as
     stated statements [V6]. Harvest before inferring [R8].
  3. Settle the top-level concepts: from the repository's docs if it has
     adopted Concipio [V23], from the human if they will say, and otherwise
     by proposing them [M40, R15].
  4. Sweep: sub-agents attach each span to a concept, propose a new one, or
     mark the span unjustified. The large model reviews proposed concepts
     before they are added. Infer statements only for undeclared behavior
     [M4].
  5. Repeat `cpo check` and `cpo status` until both verdicts pass. On a
     stall, stop and report it [V18].
  6. Hand the graph to the walkthrough [M18].
  7. Suggest checking the concepts in as docs if the project would welcome
     them; otherwise leave them in the store [M40].

  [The draft prompt](../../src/concipio/prompts/agent.md) puts these steps in an agent's
  terms.

## Measurement

- **CPO§V19:** The cost record [R13] holds the reviewer's active time, which
  the skill measures; the agents' tokens, which they report with
  `cpo record` per model and per span covered, since the point of the
  backbone is to make small models cheap and the number shows whether it
  does;
  the number of concepts the reviewer corrected; and the number of unclear
  marks left at the end.
- **CPO§V20:** Before a measured walkthrough, a model that did not write the
  change reads the code and writes questions with reference answers. They are
  kept from the walkthrough agent until the reviewer has answered them in
  writing. Concipio stores them, but grading them is
  judgment and belongs to the skill.

## Open questions

- Should the agents that classify spans see the design text, or classify
  blind and leave it to `cpo check` to find what the author already
  explained [M45]? Today they see only concepts, which were drawn from the
  design text.
- A shared test fixture serves the tests of several concepts. Should it
  attach to all of them, or to their nearest common parent?

- What should the default span limit be [V8]? Too small, and one method
  splits into many spans; too large, and one concept covers a screenful of
  code [R4].
- Should design text that lives outside the repository, such as a ticket,
  need anything beyond a snapshot to count as stated [V6]?
- How do two teammates' kept concepts merge when both import into one store
  [V12, R2]?
