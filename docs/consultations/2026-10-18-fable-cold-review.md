# Fable 5.1 consultation: cold review (2026-10-18)

An independent Claude Fable 5.1 subagent read only README.md and
docs/design/trace-format.md at commit 0c27bf8, without this folder or the
design conversation. Its prompt asked what the project is for, its strongest
objections ranked, what to protect, and whether milestone 1 can run as
written. Its report follows, condensed by the session that commissioned it; proposals and scenarios are kept, some elaboration is cut.

## 1. What I understand the project to be

Concipio is a command-line checker that an LLM agent calls while reviewing a diff. The agent builds a graph of design statements, concepts, and code spans; Concipio enforces that every changed span is attached to a concept or explicitly marked unjustified, that concepts trace to statements, and that statements trace to concepts, and reports what remains. The agent then uses the graph to walk a human through the change concept by concept [M29, M30, M9, M21]. It serves reviewers who know a system at a high level but not its language or mechanisms, and secondarily authoring agents checking their own organization [M10]. A later, explicitly hypothetical mode persists these links in docs and comments and lints them in CI [M30, T1].

Where I was unsure: whether Concipio itself ever calls a model. The README describes a deterministic CLI [M9] yet assigns it semantic judgments [M11, M6, M16, M21's "checkable claim", R1's "reject generic concept names"]. That ambiguity drives my first objection.

## 2. Objections, ranked

**O1. The model boundary is undefined [M9, M11, M21, M6, M16, R1].** Every semantic check assigned to Concipio is a judgment call. Either Concipio calls a model, or these are instructions to the agent dressed as tool features. Scenario: a concept named "storage helpers" with claim "helps with storage" passes a deterministic Explained verdict. Proposed: partition design points into mechanical (Concipio enforces), agent judgment (Concipio records and prompts), and Concipio-called-model judgment (with model and cost stated). For milestone 1, Concipio is purely mechanical; Explained reduces to a non-empty claim naming at least one span or test as evidence, plus resolving references.

**O2. M4 plus M21 penalises the honest outcome [M1, M4, M5, M21, M7, R8].** A purposeful span no statement mentions forces an orphan concept (fails Traced), marking it unjustified (hides a real mechanism), or drafting a statement from code (circular justification). Scenario: an unmentioned retry loop in the guest script. Proposed: Traced fails only on unattached, unmarked spans; orphan concepts are reported and shown as "the change does this and did not say so." Statements in the frozen design text carry provenance, "given" or "drafted-from-code," with coverage reported against each separately.

**O3. The span unit is undefined for review mode [M3, M32, R4, T8].** Hunks inside large methods, class bodies, `label def`, `semaphore :foo`, `one_to_many`, RSpec `it` blocks, shell scripts, YAML. Scenario: one concept attached to a whole class body covers 400 lines. Proposed: the hunk expanded to the smallest enclosing named declaration, capped in size; for unparsed files, the hunk. Name the Ruby parser, list the Ubicloud constructs that count, record the unit in the manifest.

**O4. Spans have no identity across pushes in review mode [M12, M28, M32, M34, M35, T18].** After a new head or rebase, reviewer marks have nothing to attach to. Proposed: adopt T10's (scope, quote) identity and T11's resolution for working-state spans now; marks persist with a "changed since verified" flag.

**O5. The tool interface and mutation model are unspecified, making M22 unenforceable [M9, M22, R11, T18].** Proposed: the graph mutates only through commands (`statement add`, `concept add`, `attach`, `detach`, `mark unjustified`, `check`, `status`), and working state includes the command log, from which stall detection, the agent ledger, and the cost record follow.

**O6. Milestone 1 has no control and the pass criteria are self-graded [R13].** Proposed: sealed questions and reference answers written beforehand by someone or something with full access to the code; written answers graded against the code; baseline by a different reviewer or on a sibling PR.

**O7. T31's renumbering is wrong for stacked branches [T31, T5, M32].** PR B cites an ID PR A minted; PR A is renumbered on rebase; PR B now points at the wrong statement. Proposed: branch-unique provisional IDs, or redirects in working state.

**O8. T35 contradicts T11, T13, and M14 [T35, M36].** Dropping anchors whose scope disappeared is a judgment; mark them stale instead.

**O9. Unjustified code has no exit but exemption [M7, M8, T15, T19].** Proposed: unjustified never converts to exempt automatically; exemptions need a human-written reason; the linter flags exemptions added in the same change as the code they exempt.

**O10. M6 has no mechanism and no scope [M6, M12, R6].** Proposed: in review mode, scope it to the diff plus symbols it references; repo-wide detection waits for traceability's index.

**O11. Smaller points.** M18 names a Claude skill while M9 promises any harness. M32 does not say whether PR A's spans are inside M3, or whether PR A's description counts as design text. The pitch diagram shows concepts as a persistent layer while T19 dissolves them. The trace-format doc is far more detailed than the nonexistent review-mode doc, inverting M30's build order.

## 3. What should be protected

M7 and M8; M19, M34, and M35; M20 with T25; M30 and the trace format's status line; M9; M32's frozen design text; M33; T12 and T14; T20; and the rule that every sub-design addresses the risks it touches.

## 4. Can milestone 1 run as written?

No. Missing, in order: the O1 decision; a review-mode doc (manifest schema, on-disk graph, command set and event log, span unit and Ruby parser, span identity across pushes); statement provenance and how PR A enters the manifest; a test role in review mode; the skill's recording of the reviewer ledger; and the measurement protocol.

A minimal build: a manifest file, a JSON graph under `.git/cpio/`, a Ruby parser yielding declaration spans for the diff, a `check` command enforcing M3 mechanically with M4 and M5 reported rather than gated, a `status` command for M22, and a skill that does all the judgment and writes the ledgers. Everything in the trace format can wait, except T10–T11's span identity, which review mode needs on the first force-push.
