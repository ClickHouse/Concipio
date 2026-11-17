# Astra consultation: prior art and design critique (2026-10-18)

Model requested: gpt-6-astra, reasoning effort high, read-only. Run against commit 5ea8797.

## Prompt

You are consulting on the design of Concipio, a tool in early design (no code yet).
Read README.md (the master design) and docs/design/trace-format.md in the current
directory. Tags like CPIO§M3 define design points; [M3] cites them.

Context the docs do not yet capture, from the project owner:

- North star: the tool exists to bring humans back into the loop on code review
  without draining their attention. Its founding premise is that a human should
  understand at least the high-level concepts of the code they edit, and that
  agents make it easy never to learn them. Tags and doc hierarchies are a
  hypothesis that may add toil; the owner wants evidence, not doctrine.
- First deliverable: helping the owner review a ~1,700-line Ruby pull request
  (Ubicloud, a cloud control plane) written by an agent, in a language the owner
  does not read, by building from the high-level concepts he knows to the
  medium-level ones he doesn't, down to the code.
- Links should run one way: more specific artifacts link to less specific ones
  (code to docs, detailed docs to broader docs), because specific things churn
  more in large repos.
- Anything Concipio stores in the tracked tree must be mergeable by Concipio
  itself, with no human or agent judgment.
- Target languages are C/C++ (Postgres extensions, a Linux device-mapper module)
  and Ruby.

Please do two things.

1. Prior art. List tools, research, and practices that overlap any part of
   this design: requirements traceability, concept/feature location, literate
   programming, code-to-doc linking, annotation anchoring, LLM code-review and
   codebase-explanation tools, guided code-review ordering. For each: what it
   does, which design points it overlaps (by tag), what Concipio should borrow
   or avoid, and whether it is still maintained, if you know. Say when you are
   unsure an item exists or works as described.

2. Design critique. Find contradictions between design points, places where
   the docs conflict with the owner's context above, mechanisms that will fail
   in practice, and missing pieces for the first deliverable. For each finding
   give: the tags involved, a concrete scenario where it fails, and a proposed
   change. Rank by how much it matters to the first deliverable.

Be specific. Skip generic advice.

## Answer

Concipio’s most promising contribution is the bridge from a reviewer’s existing knowledge to the unfamiliar mechanisms in a change. The current design specifies trace bookkeeping much more precisely than that bridge.

I read [README.md](/Users/josh/Projects/Concipio/README.md) and [trace-format.md](/Users/josh/Projects/Concipio/docs/design/trace-format.md). My recommendation is to make [M28]—the temporary, repository-neutral review mode—the first experiment, and defer committing the trace format until it demonstrates better review for the attention spent.

The Ubicloud scenarios below are proposed failure cases, not defects I verified in the actual PR. I could not retrieve PR B or PR A through the browser.

For the prior-art list, “maintained” means I found current project or vendor evidence; it does not mean I tested the product. The borrow/avoid judgments are my recommendations.

**1. Prior art**

1. **StrictDoc — the closest requirements-to-code precedent.** It manages structured requirements and traces them to source through comment markers or external relations, including language-aware scopes. Overlaps [M3–M5, M13, M15, M20, M23; T6, T8, T23, T25]. Borrow its source-side links and generated reverse views; examine its scope handling before inventing yours. Avoid making structured requirements authoring a prerequisite for reviewing an existing PR. **Maintained:** releases continued in 2026. [Traceability documentation](https://strictdoc.readthedocs.io/en/stable/stable/docs/strictdoc_01_user_guide-TRACE.html), [releases](https://github.com/strictdoc-project/strictdoc/releases).

2. **Doorstop — requirements stored with version control.** It links lower-level items to parent requirements, validates the graph, and marks links suspect when a referenced item’s fingerprint changes. Overlaps [M4, M5, M12–M14, M23–M25; T5, T9]. Borrow the distinction between an existing link and a link whose meaning needs reconsideration. Avoid clearing suspect status merely because the link still resolves. **Maintained:** its changelog records July 2026 updates. [Validation model](https://doorstop.readthedocs.io/en/v2.1.2/cli/validation/), [current changelog](https://github.com/doorstop-dev/doorstop/blob/develop/CHANGELOG.md).

3. **Sphinx-Needs — traceability embedded in ordinary documentation.** It represents requirements, specifications, tests, and other items inside Sphinx documents, with configurable links and generated reports. Overlaps [M1, M4, M5, M13, M15, M20; T21–T25, T30]. Borrow typed relationships, derived backlinks, and queryable reports. Avoid exposing a large configuration language before the core review questions are settled. **Maintained:** current documentation and an active changelog. [Project documentation](https://sphinx-needs.readthedocs.io/en/latest/), [changelog](https://sphinx-needs.readthedocs.io/en/latest/changelog.html).

4. **IBM DOORS / DOORS Next — established requirements traceability practice.** DOORS Next offers explicit relationship types; classic DOORS tracks suspect links when linked objects change. Overlaps [M4, M5, M12, M15, M20, M25]. Borrow the separation of “refines,” “implements,” and “verifies,” plus revision-sensitive validity. Avoid importing an approval-heavy lifecycle into a one-person review experiment. **Maintained commercial family;** these are distinct products, and I am not assuming feature parity. [DOORS Next link types](https://www.ibm.com/docs/en/engineering-lifecycle-management-suite/doors-next/7.2.0?topic=projects-link-types-in-requirements), [classic DOORS suspect links](https://www.ibm.com/docs/en/elms/ermd/9.7.0?topic=data-suspect-links-changed-objects).

5. **Doxygen — now directly overlaps the proposed trace syntax.** Its `\requirement`, `\satisfies`, and `\verifies` commands define requirements and associate implementation and tests with them; it generates cross-references. Overlaps [M13, M15, M20; T4, T6, T21, T23, T25]. Borrow or support these markers for C/C++ instead of requiring duplicate annotations. Their presence still does not establish semantic correctness. **Maintained:** August 2026 release documented. [Requirements support](https://www.doxygen.nl/manual/requirements.html), [changelog](https://www.doxygen.nl/manual/changelog.html).

6. **CWEB / noweb — literate programming.** They organize prose and code for human explanation, with source assembled from named chunks. CWEB targets C/C++; noweb is language-independent. Overlaps [M2, M13, M18, M19; R4]. Borrow presentation order independent of file order and named explanations spanning multiple code locations. Avoid requiring Ubicloud to adopt a new source-authoring/build pipeline. **Mature, available projects; current maintenance cadence not established here.** [CWEB](https://www-cs-faculty.stanford.edu/~knuth/cweb.html), [noweb](https://www.cs.tufts.edu/~nr/noweb/).

7. **Biggerstaff, Mitbander, and Webster’s concept-assignment research / DESIRE.** This directly addresses relating implementation structures to human domain concepts, using plausible reasoning and design recovery. Overlaps [M3, M4, M10, M11; R1, R2, R9]. Borrow its framing: concept assignment is a fallible inference requiring domain knowledge. Avoid treating a completed assignment as a proof. **Historical research; I found no evidence of a currently maintained DESIRE product.** [Original research description](https://www.microsoft.com/en-us/research/publication/the-concept-assignment-problem-in-program-understanding/).

8. **Feature-location research, especially Dit et al.’s survey.** This literature studies finding source relevant to a feature using textual, structural, dynamic, and combined techniques. Overlaps [M3, M11, M27; R6, R10]. Borrow several evidence channels: vocabulary search, dependency exploration, and execution observations. Avoid interpreting a retrieved relevant function as the complete implementation of a feature. **Research literature, not one installable maintained tool.** [Survey](https://onlinelibrary.wiley.com/doi/10.1002/smr.567).

9. **FEAT / Concern Graphs and ConcernMapper.** FEAT represents concerns through structural relationships; ConcernMapper lets developers group scattered code under higher-level concerns. Overlaps [M3, M6, M13, M18; R2, R4]. Borrow many-to-many concern membership and cross-file views. Their central premise is a useful correction to [M6]: scattered implementation can be normal. **Historical Java/Eclipse research tools; present compatibility and maintenance are unverified.** [FEAT](https://www.cs.ubc.ca/labs/spl/projects/concerngraph.html), [ConcernMapper](https://www.cs.mcgill.ca/~martin/cm/).

10. **W3C Web Annotation and Hypothesis — robust annotation anchoring.** W3C selectors combine exact text, surrounding context, positions, and resource state; Hypothesis describes fuzzy reattachment and orphaned annotations. Overlaps [M14; T10–T14; R3]. Borrow multiple independent locating signals and explicit orphan states. Avoid silently accepting a fuzzy match as the same code with the same meaning. **W3C is a published standard; Hypothesis remains maintained.** [Selectors](https://www.w3.org/TR/selectors-states/), [Hypothesis anchoring](https://web.hypothes.is/blog/fuzzy-anchoring/), [client releases](https://github.com/hypothesis/client/releases).

11. **Swimm — documentation tied to code.** Its documented IDE workflow embeds live snippets/tokens, exposes relevant docs beside code, and detects or updates affected documentation. Overlaps [M12–M14, M18, M20; R3, R12]. Borrow nearby explanations and visible freshness status. Avoid equating synchronized snippets with accurate explanatory prose. **The product is active in 2026; availability of every older Auto-sync feature was not verified.** [Documented workflow](https://swimm.io/blog/announcing-swimm-s-ide-plugin-the-most-intuitive-way-to-document-code), [2026 product direction](https://swimm.io/blog/swimm-2-0-the-understanding-platform-for-ai-modernization).

12. **CodeTour — guided code-reading order.** Its VS Code extension records ordered steps with prose and source locations, including introductory content steps and cross-file tours. Overlaps [M18, M19; R3, R4]. Borrow its presentation model or use it as a prototype adapter. Avoid making an editor-specific tour file the authoritative concept graph. **Exists and remains available; ongoing maintenance is uncertain.** [Repository and format](https://github.com/microsoft/codetour).

13. **ClusterChanges and empirical change-decomposition studies.** ClusterChanges automatically decomposes changesets for review. A separate controlled experiment with 28 developers found fewer false reports from decomposition, but no improvement in defects found or understanding of the change rationale. Overlaps [M18, M19; R4, R9]. Borrow coherent review units; test whether they help this reviewer. Avoid claiming concept grouping inherently improves comprehension. **Historical research; current ClusterChanges availability is unverified.** [ClusterChanges](https://www.microsoft.com/en-us/research/publication/helping-developers-help-themselves-automatic-decomposition-of-code-review-changesets/), [controlled experiment](https://arxiv.org/abs/1805.10978).

14. **Google’s review-navigation practice.** Reviewers first assess the overall change, then its most important part, then the remainder in an appropriate sequence. Overlaps [M18, M19]. Borrow early examination of the central design decision and permission to stop when it is wrong. Avoid spending the reviewer’s attention completing a polished tour of a design already rejected. **Published practice; not a software maintenance question.** [Review navigation](https://google.github.io/eng-practices/review/reviewer/navigate.html).

15. **CodeRabbit — LLM review plus change explanations.** It offers PR review, summaries, walkthroughs, diagrams, and conversational follow-up. Overlaps [M10, M18, M19, M28; R9]. Borrow succinct orientation and follow-up tied to the change. Use it as a baseline for whether Concipio’s extra tracing buys anything. Avoid treating a vendor’s “walkthrough” label as evidence of learning or exhaustive inspection. **Active commercial product; effectiveness claims not independently verified here.** [Product description](https://coderabbit.app/).

16. **GitHub Copilot code review.** It reviews changes, gathers repository context, and proposes fixes. GitHub explicitly documents missed problems and false positives. Overlaps [M10, M11, M12, M28; R9]. Borrow actionable findings with source context and revision-specific re-review. Avoid conflating an automated reviewer’s output with what the human understands. **Active product.** [Capabilities](https://docs.github.com/en/copilot/concepts/agent-capabilities/agent-powered-workflows-and-operations/code-review), [limitations](https://docs.github.com/en/copilot/responsible-use/agents).

17. **DeepWiki / Devin Wiki — generated codebase explanation.** It generates architecture diagrams, documentation, source links, and repository Q&A. Overlaps [M2, M4, M10, M18, M27; R8, R9, R12]. Borrow source-grounded exploration and progressively narrower explanations. Avoid promoting descriptions inferred from implementation into authoritative requirements. **Active product; generated explanations are not independently validated by their citations.** [Official documentation](https://docs.devin.ai/work-with-devin/deepwiki).

18. **Automerge / CRDT practice — relevant to the owner’s merge invariant.** Automerge deterministically combines concurrent operations, while exposing competing values for conflicting property assignments. Overlaps [M13; T10, T18; R2, R7]. Borrow explicit merge algebra and preservation of competing assertions. Avoid assuming deterministic convergence chooses the correct meaning of prose. **Maintained project.** [Conflict semantics](https://automerge.org/docs/reference/documents/conflicts/).

**2. Design critique, ranked by importance to the first deliverable**

**1. “Explained” does not mean the reviewer learned enough to review.**  
Tags: [M18, M19, M21; R9].

Scenario: a walkthrough says a resize operation is safe to retry and displays Ruby supporting that claim. You cannot independently identify which side effect happens before an exception, so the code display provides little protection against a mistaken explanation. Both verdicts can pass.

Change: define a walkthrough step as a bridge from known concept → unfamiliar mechanism → exact code → a question the reviewer can now answer. For example: “If execution stops between these two operations, what happens on retry?” Supply the Ruby semantics needed for that particular answer. Track “still unclear” separately from “shown.” Rename the mechanical verdict to something like “explanations present”; reserve understanding for evidence from the reviewer.

**2. The reviewed change and its stacked context have no precise identity.**  
Tags: [M12, M28; T18], Ubicloud milestone.

Scenario: diffing PR B against main includes PR A, while diffing against the wrong revision of PR A omits a relevant change. A subsequent rebase makes the saved explanation refer to a different program. Deleted code has no current node to attach to.

Change: start every review with a manifest containing exact base/head revisions, the intended comparison, prerequisite revisions, and a snapshot of the PR description. Represent additions, modifications, and deletions, with old-side and new-side evidence. Classify PR A material as prerequisite context and expose its review status. This is necessary before any coverage number is meaningful.

**3. The coverage mechanism permits the failure [R1] warns about.**  
Tags: [M3, M7, M21; T6, T8, T15, T16; R1, R4].

Scenario: one file-opening citation to “online volume growth” covers hundreds of lines containing validation, persistence, execution, and recovery. [T8] explicitly permits file coverage, although [R4] says whole-file anchoring says nothing. Alternatively, one exemption disposes of the difficult file.

Change: freeze an independently enumerated inventory of review obligations. Broad citations may provide context, but must not automatically discharge all descendant obligations. Permit bounded sub-symbol spans where needed, as [R4] already anticipates. Report separate counts for attributed, unexplained, unjustified, unsupported, and excluded work. Marking code unjustified should complete classification without implying review readiness.

**4. The middle layer—the product’s central value—has no defined representation.**  
Tags: [M1, M4, M13, M21; T4, T19, T21].

Scenario: the four PR-description points map directly to code. A useful intermediate concept such as “desired capacity versus observed capacity” exists only in agent prose. The tool cannot distinguish that concept from a requirement, locate its explanation, or ensure the walkthrough uses it. [T19] also allows a concept to become a code comment, while [T4] defines identities only in design documents.

Change: define a minimal local review record: concept identity, explanation, broader intent references, prerequisite concepts, evidence bindings, and unresolved questions. Explicitly decide whether a persistent concept is a tagged design statement or a separate entity. For PR B, these records can remain entirely in working state; no document promotion is necessary.

**5. The design collapses intention, observation, and obligation.**  
Tags: [M1, M4, M5, M21, M25; T29; R8].

Scenario: an agent observes a behavior in code, writes a statement describing it, and uses that statement to justify the behavior. Conversely, an architectural explanation or future plan is called a missed requirement because it has no implementation. A reference from another paragraph suppresses [T29]’s warning even though no code implements the statement.

Change: keep the soft hierarchy, but record provenance and obligation separately: owner-stated intent, externally specified behavior, code-derived observation, proposed interpretation; required now, planned, descriptive, or out of scope. Test missing implementation independently of incoming references. [M21] currently omits [M5] from both verdicts, despite the milestone requiring claims without code to be found.

**6. Exhaustive agent accounting can hide selective human exposure.**  
Tags: [M3, M18, M19, M21; R9].

Scenario: the agent covers the entire diff but chooses three reassuring snippets. The recovery branch is never shown. The reviewer sees a completed walkthrough and mistakes that for having reviewed the change.

Change: maintain separate ledgers for agent accounting and human exposure. Every changed obligation should be identifiable as inspected, represented by a sample, explicitly delegated, or deferred. Each concept view should expose its omitted changed spans. Do not force every line onto the screen; make the sampling decision and remaining work visible.

**7. Cross-site assumptions need conditions and evidence, not just shared tags.**  
Tags: [M16, M17; T27, T28; R5, R10].

Scenario: a worker relies on a size being expressed in bytes and on a previous state being durably recorded. A producer and consumer cite the same statement, but use different units or establish it on different execution paths. A tag search looks convincing without establishing the contract.

Change: make `establishes` and `relies-on` first-class roles for assumptions, with the relevant condition, producer/consumer sites, and evidence status. Prioritize units, persistence boundaries, ordering, retries, and failure propagation for the resize review. Runtime or test evidence can remain optional to obtain, but its absence must remain visible when a claim depends on it.

**8. Test linkage can overstate what is verified.**  
Tags: [M15; T6, T23, T24; R9].

Scenario: a spec mocks the guest resize operation and executes the control-plane method. It cites the growth concept and contributes coverage. That establishes neither successful guest growth nor safe recovery after partial completion.

Change: distinguish “test cites concept,” “test executes implementation,” and “test asserts this behavior.” For important claims, show the relevant assertion and mocked boundary. Generate test questions around failure between steps and re-entry, rather than counting all tests attached to the concept equally.

**9. [M6] treats a normal property of this deliverable as suspicious.**  
Tags: [M6, M7, M18; R12].

Scenario: online growth appears in a Ruby model, orchestration code, a guest script, and specs—the exact cross-file structure identified in the milestone. Flagging all disconnected sites as possible duplication produces a report dominated by expected architecture.

Change: distinguish collaboration across layers from repeated implementation of the same responsibility. The useful question is “Are two sites independently maintaining the same rule, conversion, or invariant?” A model validating a request and a guest applying it are different responsibilities. Defer duplication detection unless it can make that distinction.

**10. Location freshness and explanation freshness are conflated.**  
Tags: [M12, M14; T10–T13; R3, R6].

Scenario: `def resize` remains unchanged while its body changes substantially. The quote still resolves, so the anchor survives even though its explanation is obsolete. Separately, an unchanged function becomes unsafe because a called helper or referenced assumption changes.

Change: track location resolution, code revision, and claim validity separately. Use symbol identity and surrounding text to locate; use bounded source fingerprints to detect edits; use recorded evidence dependencies to invalidate affected explanations. A content hash of the local function alone is insufficient for a claim about its environment.

There is also a literal bug in [T13]: a quote that matched an immutable recorded commit will continue matching that commit. That condition does not detect current-code changes.

**11. New code cannot satisfy the main-branch anchor rule as written.**  
Tags: [M23; T10, T14, T26].

Scenario: PR B introduces a method absent from main. Its anchor cannot point to a main-branch commit containing the method. Presubmit then tries to replace the anchor’s commit with the final squash commit. Embedding that commit’s own hash into its tracked tree would change the hash.

Change: allow review anchors to target the pinned review snapshot. Separate portable source identity from repository-history retention. For persisted annotations, consider source blob identity plus symbol/span selectors, or a previously existing source commit with an explicit retention policy. Drop the requirement that every source revision already be on main. A later metadata commit is possible, but must be specified as such.

**12. The milestones front-load the hypothesis that needs testing.**  
Tags: [M2, M10, M25, M26, M28; R8, R12], milestone order.

Scenario: self-hosting from the first commit requires deciding IDs, document ownership, signatures, linter behavior, and tracked merges before you discover whether the walkthrough helps you review Ruby. The project can succeed at maintaining its own traces while failing its founding purpose.

Change: put the Ubicloud review experiment first. Compare a plain agent walkthrough with one using Concipio’s concept mapping and obligation ledger. Measure reviewer attention, independently answerable questions, explanation corrections, and annotation effort. Do not repeatedly show the same material and interpret familiarity as improvement. Defer the small-model/large-model division until there is evidence that it preserves quality at lower cost.

**13. The stored hierarchy directly contradicts the owner’s link direction.**  
Tags: [M20, M24, M27; T9, T25; R12].

Scenario: adding a detailed resize document requires editing the stable master document. Many independent feature branches contend on that master simply to register their children.

Change: detailed documents cite their broader parents. Discover documents by scanning the configured root, then derive the downward navigation view. Validate that each adopted document can reach an approved root by following upward links.

[M20] is compatible with the owner’s rule if it means bidirectional *navigation*: [T25] already generates reverse code views. Rewrite that distinction explicitly. Remove parent editing as [R12]’s approval mechanism; it imposes precisely the upward churn the owner wants to avoid.

**14. The tracked format does not meet the judgment-free merge requirement.**  
Tags: [M13; T1, T10, T17; R2, R7].

Scenario: two branches add anchors to the same TOML array, edit the same concept paragraph, or change the same role configuration. Their code edits merge cleanly while the annotations conflict. [T10]’s claim that anchor conflicts follow code conflicts is therefore false. [R2] also requires a human choice without separating that choice from repository merging.

Change: specify the merge algebra before permitting tracked writes. One candidate is immutable, uniquely identified assertion records, deterministic set union, explicit supersession, and deletion records. Concurrent assertions remain separate data; merging does not select a semantic winner. Derived views can be regenerated.

This requires relaxing [M13]’s opposition to metadata, or restricting what Concipio writes. Arbitrary mutable prose cannot simultaneously remain the sole authoritative storage and guarantee meaningful automatic merges. For the first deliverable, [M28] avoids this problem entirely.

**15. IDs and namespace ownership create avoidable branch conflicts.**  
Tags: [T2–T5; R2, R7].

Scenario: two branches both allocate `T31`. Or a statement moves into a narrower document, but its namespace is owned by the old document. A shallow clone cannot determine whether an apparently new ID was retired in inaccessible history.

Change: use collision-resistant immutable identities, with short readable labels as aliases if needed. Keep identity independent of document location. Record retirement explicitly in current authoritative state; history can support investigation without being required for every validation. If the existing letters-plus-number syntax stays, long random numeric identifiers can fit it, though their ergonomics need testing.

**16. Ratifying a document’s existence does not perform the review promised elsewhere.**  
Tags: [M25, M26; R8, R12].

Scenario: an already-ratified document receives hundreds of code-derived statements. Its signature remains valid. [R12]’s write-amplification mitigation has not constrained the new text, and [R8]’s requirement that a human adopt each derived statement has no recorded mechanism.

Change: distinguish permission to have a document from acceptance of a particular inferred requirement. Keep inferred intent provisional until explicitly accepted, recording the accepted revision where persistence matters. Avoid requiring signatures for the review experiment. Ordinary review may be enough for enduring docs, but the design should not credit path ratification with validating their content.

**17. The format has smaller ambiguities that will produce inconsistent implementations.**  
Tags: [T2, T7, T8, T10, T18, T20–T22, T26].

| Concrete failure | Proposed change |
|---|---|
| The anchor example uses `role = "impl"`; the configured role is `implementation`. | Define canonical stored role names and any aliases. |
| The README uses grouped/ranged references such as `[M13–M15, M20, …]`; [T7] specifies only `[M3]`. | Specify and test the actual reference grammar used by the design. |
| A regex finds a definition inside a fenced example, despite [T20]. | Parse Markdown context first, then recognize roles. Likewise, recognize source comments before scanning tags. |
| A comment before a Ruby DSL block or C preprocessor construct has ambiguous coverage. | Specify language-specific attachment rules and explicit “unsupported/ambiguous” outcomes. |
| “Convert anchors to tags for any file” includes files whose premise is that they cannot carry tags. | Limit conversion to supported, editable source with representable scopes; report other cases as unsupported. |
| In a linked Git worktree, `.git` can be a file rather than a directory. | Locate working state through Git’s path-resolution facilities and define worktree/session isolation. |

**18. Foreign references contradict the unconditional resolution verdict.**  
Tags: [M21, M23; T30].

Scenario: a Postgres extension cites upstream design unavailable in the current checkout. [T30] calls this unverified rather than failing, while [M21] requires every reference to resolve. If the foreign docs later change, the same local code can acquire a different apparent justification.

Change: pin foreign design identity and revision. Separate unavailable evidence from invalid references, and expose both in the verdict. “Locally complete, with two unverified external dependencies” is meaningful; an unconditional “Explained” is not. This can wait until after PR B, but should be decided before the Postgres use case.

For the first deliverable, I would make the acceptance test concrete with the following review packet:

| Artifact | What it must establish |
|---|---|
| **Review manifest** | Exact PR B comparison, PR A prerequisite snapshot, and frozen intent text. |
| **Concept route** | A short path from concepts you already know into mechanisms you need to learn. Candidate mechanisms include desired versus observed capacity, orchestration state, resize ordering, and retry behavior; the actual code must determine the route. |
| **Evidence cards** | Each important claim has exact source, necessary Ruby explanation, relevant test assertions, and remaining uncertainty. |
| **Change ledger** | Every changed obligation—including deletions—is accounted for; sampled or unseen material remains visible. |
| **Reviewer checks** | You can explain the operation’s sequence, identify persistence and failure boundaries, predict a retry outcome, and locate the code supporting those answers. |
| **Cost record** | Your active review time, agent preparation cost, corrections required, and repository annotation work—initially zero. |

A successful run should leave you able to challenge an explanation and navigate to the deciding code. That is the evidence needed before making tags and document hierarchies permanent project obligations.
