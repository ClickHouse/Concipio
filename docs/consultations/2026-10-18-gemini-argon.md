# Gemini Argon consultation: prior art and design critique (2026-10-18)

Solicited by Josh with a prompt similar to the Astra consultation, against the same draft. Copied verbatim.

Concipio is aiming at a brutal, real problem: LLM-generated diffs invert the ergonomics of software engineering, turning authoring into a commodity and review into a cognitive bottleneck. The core insight—using an exhaustive coverage invariant (every span \-\> concept \-\> statement or unjustified) to force small models not to skim, and then using that graph to drive a topological walkthrough for a human—is sharp.

However, there is a tension right down the middle of Concipio.md and trace-format.md: **you are designing two tools at once.** Tool A is a lightweight, ephemeral diff-comprehension engine for reviewing a 1,700-line PR (Ubicloud\#949) without polluting the repo (\[M28\], \[T18\]). Tool B is a heavy, DO-178C-style permanent requirements traceability and cryptographic doc-ratification system (\[M23\], \[M25\], \[T2\]–\[T17\]). Right now, the specification for Tool B is starving the specification for Tool A.

## **1\. Prior Art**

### **Requirements Traceability (Docs-as-Code)**

* **StrictDoc & Doorstop**

  * **What they do:** Open-source, text-based requirements management tools storing requirements in Markdown/YAML/RST (Doorstop) or a custom domain-specific grammar (StrictDoc) alongside code in Git, linking requirements to source files and tests.

  * **Overlaps:** \[M1\], \[M3\]–\[M5\], \[M20\], \[M23\], \[M24\], \[T1\]–\[T9\], \[T21\]–\[T25\].

  * **Borrow:** StrictDoc’s realization that bidirectional links stored in both files cause constant merge conflicts (\[R7\]); StrictDoc computes reverse links dynamically at build/query time, just like \[T25\].

  * **Avoid:** Doorstop stores one YAML file per requirement and hashes content to detect staleness; in active repos, rebasing branches turns those hashes into merge-conflict hell. Also avoid StrictDoc's rigid grammar—your regex role matching in \[T22\] is much friendlier to existing Markdown.

  * **Status:** Both are actively maintained (StrictDoc very heavily in automotive/embedded spaces; Doorstop more lightly).

* **Mantid / Cargo-vet / Chromium OWNERS & Security Reviews**

  * **What they do:** cargo-vet and Chromium's IPC/security review checklists track human ratification of code/dependencies in version control, invalidating or flagging changes when underlying assumptions shift.

  * **Overlaps:** \[M25\], \[M26\].

  * **Borrow:** Store audit/ratification ledger entries in a single append-only/structured file or git-notes equivalent that has a custom deterministic merge driver, rather than inline signatures that break on file moves.

  * **Status:** Actively maintained.

### **Concept / Feature Location & Code-to-Doc Linking**

* **Robillard & Murphy, *Concern Graphs* (2002–2007) & Featureous**

  * **What they do:** Academic research and IDE tooling for mapping "concerns" (concepts that crosscut files/functions) onto structural AST elements (\[R4\]) so developers can understand scattered implementations without reading the whole codebase.

  * **Overlaps:** \[M3\], \[M6\], \[M13\], \[M14\], \[R3\], \[R4\], \[T8\].

  * **Borrow:** Their formalization of granularity (\[R4\]): concerns attach cleanly to declarations (methods/classes/structs), while sub-method spans ("reads/writes/calls inside a monster function") are treated as exceptions requiring structural projection.

  * **Avoid:** Relying purely on static call graphs to infer concepts—they fail across dynamic dispatch, IPC, or shell boundaries (like Ruby models calling guest scripts in Ubicloud\#949).

  * **Status:** Historical academic work (inactive tools, foundational concepts).

* **CodeTour (VS Code) & Swimm**

  * **What they do:** CodeTour records ordered walkthroughs of codebases anchored to files/lines for onboarding and PR explanation. Swimm links Markdown docs to code snippets and uses a CI check \+ AST/git-diff heuristics to auto-update or flag broken anchors when code moves.

  * **Overlaps:** \[M14\], \[M18\], \[M19\], \[R3\], \[T10\]–\[T14\].

  * **Borrow:** CodeTour’s dead-simple JSON schema for ordered walkthrough steps (file, line/selection, description), which lets an editor adapter (\[M18\]) jump from concept to concept immediately. From Swimm, borrow the distinction between "cosmetic shift" (line numbers moved, AST node identical) and "semantic drift" (signature or body mutated) (\[R3\]).

  * **Avoid:** Swimm’s heavy committed metadata inside Markdown files, which alienates developers reading raw text in a terminal.

  * **Status:** Both actively maintained.

### **Annotation Anchoring**

* **git blame \-L / git log \-L & W3C Web Annotation Data Model (TextQuoteSelector)**

  * **What they do:** W3C TextQuoteSelector (used by Hypothesis) anchors annotations to changing documents using exact quote \+ prefix \+ suffix context, falling back to fuzzy matching. git log \-S / \-L tracks line ranges across history.

  * **Overlaps:** \[M14\], \[R3\], \[T10\]–\[T13\].

  * **Borrow:** Prefix/suffix context around quotes when anchoring to lines that aren't unique on their own (\[T12\]), or better yet, AST-path \+ quote.

  * **Avoid:** Requiring exact global uniqueness of a single-line quote within a file (\[T12\]) without structural scope (see Critique \#3 below).

  * **Status:** Active standards/built-ins.

### **Guided Code-Review Ordering & Change Decomposition**

* Barnett et al., *Helping Developers Help Themselves: Automatic Decomposition of Code Review Changesets* (ICSE 2015, Microsoft Research — "ClusterChanges") & Credible / Reviewable

  * **What they do:** Partition large diffs into coherent, independent clusters and order them topologically (e.g., data model / schema \-\> core logic \-\> callers \-\> tests) so a human reviews by concept rather than alphabetical filepath.

  * **Overlaps:** \[M10\], \[M18\], \[M19\], \[M28\].

  * **Borrow:** The explicit distinction between *def-use ordering* (bottom-up: show the helper before the caller) and *intent ordering* (top-down: show the high-level entrypoint/design statement, then the medium-level orchestrator, then the low-level implementation). Your owner context explicitly asks for top-down intent ordering.

  * **Status:** Research paper (2015); commercial/open-source descendants exist in tools like Reviewable and Graphite (though Graphite requires the author to split stacks upfront, whereas you need post-hoc decomposition for an already-written PR).

### **Design Assumptions & Lightweight Contracts**

* **Linux Kernel Lockdep annotations / Sparse (\_\_user, \_\_iomem, \_\_must\_hold) & Doxygen @pre/@post**

  * **What they do:** Encode non-local assumptions (context, locking, address space, units) either as compiler attributes (Sparse) or structured comments (Lockdep comments / Doxygen).

  * **Overlaps:** \[M16\], \[M17\], \[R5\], \[T27\], \[T28\], Milestone 3 (a kernel module).

  * **Borrow:** For Milestone 3 (a kernel module), categorize assumptions specifically around kernel failure modes: execution context (atomic/softirq vs process/sleeping), locking hierarchy, sector vs byte vs page units, and endianness/on-disk alignment.

  * **Avoid:** Trying to build a general theorem prover. Treating hoisted cross-site assumptions as shared tags (\[T28\]: producer marks IMPL\[TAG\], consumer marks bare \[TAG\]) is genuinely clever and lightweight—keep that.

## **2\. Design Critique (Ranked by Impact on Milestone 2: Ubicloud\#949)**

### **1\. The Missing Middle: No Data Model or Lifecycle for Concept in Review Mode**

* **Tags involved:** \[M1\], \[M3\], \[M4\], \[M21\], \[M28\], \[T6\], \[T18\], \[T19\].

* **The conflict / failure mode:** In "The layers" (\[M1\]), the hierarchy has five tiers: master design \-\> design docs \-\> concepts \-\> comments \-\> code. In \[M3\] and \[M4\], spans belong to *concepts*, and *concepts* trace to *design statements*. However, trace-format.md completely erases the concept layer\! In trace-format.md, design statements get tags (CPIO§M3), and code comments (IMPL\[CPIO§M3\]) or anchors cite those design statement tags directly. There is no syntax, ID scheme, or schema for a *concept* anywhere in trace-format.md. **Concrete failure on Ubicloud\#949:** The PR description has 4 high-level numbered points ("design statements") and \~1,700 lines of Ruby/bash/specs. If 450 lines of Ruby implement Point \#1 across 8 files, mapping all 450 lines directly to Statement \#1 skips the exact thing the project owner needs: *the medium-level concepts* that bridge the 4 high-level points to the Ruby methods. Furthermore, in Review Mode (\[M28\], \[T18\]), nothing is written to the tracked repo—everything lives in .git/cpio/. Yet .git/cpio/'s schema is completely undefined, while trace-format.md spends 100% of its budget defining committed repo artifacts (IMPL\[...\] comments and .cpio TOML) that Review Mode isn't even allowed to use\!

* **Proposed change:** Explicitly formalize **Concepts** as first-class nodes in .git/cpio/graph.json (or .toml/SQLite) between Design Statements and Code Spans. A Concept has: id, parent\_statement\_id (or parent\_concept\_id, allowing a 2-level tree of high-level \-\> medium-level concepts), title, claim (a falsifiable 1-2 sentence explanation of how the Ruby/C code achieves the parent statement), assumptions, and spans (with roles: entrypoint, core, helper, plumbing, test). When graduating from Review Mode to permanent repo tracking (\[T19\]), you can decide whether concepts become sub-bullets in a design doc or stay ephemeral.

### **2\. What is an "Effective Span" in a Diff with Deletions, DSLs, and Stacked PRs?**

* **Tags involved:** \[M3\], \[M11\], \[M12\], \[M21\], \[R4\], \[R10\], \[T8\], Milestone 2 (Ubicloud\#949 stacked on \#924).

* **The conflict / failure mode:** \[M21\] says Concipio gives a deterministic pass/fail verdict on whether "every effective span belongs to a concept or is marked unjustified". \[R4\] and \[T8\] say coverage attaches to AST syntax nodes (functions, methods, classes, blocks). **Concrete failure on Ubicloud\#949:**

  * **Ruby DSLs & Metaprogramming (\[R10\]):** In Sequel/Roda/RSpec (Ubicloud's stack), huge amounts of logic live outside standard def methods: migration blocks (Sequel.migration do ... end), state machine transitions, dataset scopes, or RSpec it / before / let blocks. If your Tree-sitter parser only counts method and class nodes as "effective spans," half the PR is invisible. If it counts every Ruby block (do ... end), every .map { |x| ... } becomes a separate span requiring coverage.

  * **Modifications & Deletions in a Diff:** If a PR edits 3 lines inside a 120-line method, or *deletes* a 15-line guard clause (which might be a critical security regression\!), what is the "effective span" that Concipio demands the agent cover? A deleted block no longer exists in the post-image AST\!

  * **Stacked Context (\#924 \-\> \#949):** Milestone 2 notes \#949 is stacked on \#924. If an agent sweeps \#949's diff, \#949 calls helpers or mutates tables introduced in \#924. If Concipio only parses \#949's diff hunks, the agent lacks \#924's concepts.

* **Proposed change:**  
  In Diff/Review Mode (\[M28\]), define the universe of **Effective Spans** at the **diff-hunk / sub-hunk level grouped by enclosing AST container**, *including deleted hunks*. Specifically:

  * Every contiguous added/modified hunk inside a declaration (or top-level DSL call/block) is an effective span that must be claimed by a concept.

  * Every non-trivial deleted hunk (e.g., deleted control flow, deleted method, deleted assertion) is *also* an effective span that must be attached to a concept explaining *why its removal is safe/intended*.

  * To handle \#924 \-\> \#949, allow cpio init-sweep \--base-concepts \<path-to-924-graph\> so the \#949 sweep loads \#924's concept tree as pre-existing parent/sibling concepts (\[M12\], \[R2\]).

### **3\. Anchor Mergeability & Uniqueness Contradict Owner Constraints and C/Ruby Reality**

* **Tags involved:** \[M14\], \[M23\], \[R3\], \[R7\], \[T10\]–\[T14\], plus Owner Constraint (*"Anything Concipio stores in the tracked tree must be mergeable by Concipio itself, with no human or agent judgment"*).

* **The conflict / failure mode:** First, \[T10\] claims: *"Conflicts over anchors follow conflicts over code, which git already handles"*. That directly contradicts the owner's constraint that Concipio must deterministically merge its own tracked files without human/agent judgment. If two branches add \[\[anchor\]\] blocks to the end of cpio/anchors/src/backend/foo.c.toml, standard git merge will raise a text conflict\! Even worse, \[T14\] says presubmit rewrites the commit \= "..." field of anchors on feature branches to match the merge result—which is mathematically impossible in standard Git (a file inside a commit cannot contain the SHA-1 of the commit that is about to be created\!). Second, \[T12\] states: *"A quote must match exactly one place in its file. Concipio rejects an ambiguous or missing quote when the anchor is written"*. **Concrete failure on C (a kernel module) and Ruby (Ubicloud):** In C kernel modules, you routinely have multiple static functions or switch branches with identical opening lines or boilerplate, or in Ruby RSpec files, multiple before do or it "handles errors" do blocks in the same file. Under \[T12\], an agent trying to anchor it "validates volume size" do or a common C signature/macro invocation will fail if the line appears twice in a 1,500-line file.

* **Proposed change:**

  1. **Drop commit rewriting on merge (\[T14\]):** Record base\_commit (an ancestor on main when the branch diverged, or the tree/blob hash before the edit) only as a fallback hint. Never try to write the merge commit's own SHA into the tree being committed.

  2. **Scope quotes by AST symbol path:** Change \[\[anchor\]\] from a flat file-wide quote to (symbol\_path, quote)—e.g., scope \= "VolumeGrower\#execute" \+ quote \= "resize\_fs(vol)". Within a single function/method, quotes are almost always unique.

  3. **Deterministic Custom Merge Driver:** Register a cpio merge-driver in .gitattributes for .cpio and \*.toml anchor files. Because \[\[anchor\]\] entries are an unordered set keyed by (tag, role, scope, quote), Concipio can union-merge concurrent additions, drop anchors whose target symbols were deleted in the merged code file, and sort the output canonically—achieving 100% zero-judgment merges.

### **4\. Bidirectional Link Contradiction (\[M20\] vs. Owner Constraint & \[T25\])**

* **Tags involved:** \[M20\], \[M24\], \[T9\], \[T25\], plus Owner Constraint (*"Links should run one way: more specific artifacts link to less specific ones... because specific things churn more"*).

* **The conflict / failure mode:** The owner states: *"Links should run one way: more specific artifacts link to less specific ones (code to docs, detailed docs to broader docs), because specific things churn more in large repos."* Yet \[M24\] and \[T9\] mandate the exact opposite for docs: *"Every design doc is cited by its parent, up to the master... A design doc is part of the hierarchy when its parent links to it \[M24\]"*. And \[R12\] relies on this: *"a new doc must be cited by its parent \[M24\], so creating one means editing a design someone already approved"*. **Concrete failure:** If you have a high-level storage.md doc, and two engineers on separate branches add specific sub-design docs (online-volume-growth.md and snapshot-gc.md), requiring storage.md (the less-specific parent) to link downward to every child forces every specific feature branch to edit the shared parent doc, causing \[R7\] merge conflicts and violating the owner's one-way rule. Meanwhile, \[M20\] says *"Links run both ways"*, whereas \[T25\] clarifies that stored links only run code \-\> doc and reverse links are computed dynamically.

* **Proposed change:** Align \[M20\], \[M24\], and \[T9\] with \[T25\] and the owner's rule: **Stored links always point UP (child \-\> parent).** Code cites concepts/leaf docs; specific design docs declare parent: CPIO§M4 (or link upward to their parent doc in their header). Concipio's query engine and linter dynamically construct the downward tree (master \-\> children \-\> concepts \-\> code). To preserve \[R12\] (preventing rogue unapproved docs from polluting the tree), \[M26\] already solves this: a new child doc requires a human ratification signature (\[M25\]) before merge, without needing to touch the parent doc.

### **5\. Walkthrough Mechanics (\[M18\], \[M19\]) Are Under-Specified for Non-Ruby Readers**

* **Tags involved:** \[M18\], \[M19\], \[R9\], Milestone 2 (Ubicloud\#949).

* **The conflict / failure mode:** The first deliverable's success criterion is: *"helping the owner review a \~1,700-line Ruby pull request... in a language the owner does not read, by building from the high-level concepts he knows to the medium-level ones he doesn't, down to the code"*. Currently, \[M18\] and \[M19\] only say: *"A large model chooses a few snippets per concept, across files, and presents them in order. Adapters open those snippets in the reviewer's editor or terminal. The walkthrough always shows code"*. **Concrete failure on Ubicloud\#949:** Showing a C/C++ systems programmer 5 snippets of idiomatic Ruby/Sequel/Roda ("a few snippets per concept") without explaining Ruby's implicit receivers, Sequel dataset methods, or control-flow idioms leaves the reviewer guessing whether the code actually matches the concept claim (\[R9\]). Furthermore, "a few snippets per concept" breaks the exhaustive coverage promise (\[M3\]) during review: if a concept covers 12 spans across 4 files, and the large model only picks 3 snippets to show, where can the reviewer see the other 9 spans if they get suspicious?

* **Proposed change:**  
  Define the walkthrough structure in the upcoming walkthrough design doc around three explicit guarantees:

  1. **Topological Concept Spine:** Present the tree from the 4 PR statements \-\> \~10–15 medium-level concepts \-\> the Unjustified / Odds-and-Ends bucket (\[M8\]) \-\> the Unimplemented / Missing Claims bucket (\[M5\]).

  2. **Primary vs. Exhaustive Spans per Concept:** Every concept presentation must list *all* covered spans (so nothing is hidden), split into **Primary Snippets** (shown inline with the code \+ a translation of language-specific idioms/magic for non-native readers \+ explicit local assumptions \[M16\]) and **Supporting/Boilerplate Spans** (collapsed to 1-line summaries, expandable on demand).

  3. **Interactive Verification Actions:** In the walkthrough skill, allow the human to flag a span or concept as verified, suspect (triggers an immediate deep-dive sub-query on invariants/edge cases), or unjustified.

## **3\. Recommended Minimum Viable Path to Milestone 2 (Ubicloud\#949)**

Because the project owner wants **evidence, not doctrine** on whether tags and doc hierarchies add toil, do not build trace-format.md's permanent repo annotations, TOML sidecars, regex role parsers, or doc ratification (\[M23\], \[M25\], \[T1\]–\[T17\]) before testing Milestone 2\.

To crush Milestone 2 (Ubicloud\#949), you only need **Review Mode (\[M28\], \[T18\])**:

1. **Diff Span Extractor (cpio init \<base\>..\<head\>):** Parses the git diff of \#949 (and optionally \#924), groups changed/added/deleted lines into addressable AST/hunk spans (S1..Sn), and writes .git/cpio/state.json alongside the 4 numbered design statements from the PR description (D1..D4).

2. **Agent CLI (cpio status, cpio concept add/update, cpio attach, cpio check):** Lets a sweeping agent create medium-level concepts under D1..D4, attach spans S1..Sn (or mark them unjustified with a reason), record assumptions (\[M16\]), and run cpio check to get the exact list of uncovered spans, orphan concepts, or unimplemented design statements (\[M21\], \[M22\]).

3. **Walkthrough Skill (cpio walkthrough):** Reads the completed .git/cpio/state.json and guides the human top-down from D1..D4 \-\> Concepts \-\> Ruby/bash/spec diffs, ending with the unjustified odds-and-ends report (\[M8\]).

If that workflow makes reviewing \#949 effortless and catches a real bug or smell in the agent-written Ruby, you have hard evidence that the concept-graph invariant works—and *then* you will know exactly which parts of that graph are worth persisting into permanent repo tags (trace-format.md) for Milestone 3 (a kernel module).

