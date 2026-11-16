# Plans and audits

Parent: [Concipio](../../README.md)

**Status: proposed.** Claiming, recording, and status are built for
audits, as `cpo audit next`, `done`, `note`, `mine`, and `status` [W8,
W10, W13, W44], over design sections and the code they name or cite, and
over code no design claims yet [W40]; the rest is not.

Onboarding a C codebase to Concipio found real defects, nearly all from
one move: take a design section's claims and check them against the
code. Concipio supplied the units of work, but none of the state. The
agent kept its worklist, findings, and claims in files of its own, lost
some to each compaction, briefed every helper by hand, and showed no
progress in any number Concipio reports
([the adoption's account](../consultations/2026-11-07-first-adoption.md)).
This doc specifies plans, claimable lists of work that agents share, and
audits, the plans that check a design against its code.

A plan does not replace the to-do list a harness keeps for an agent's
current task, which already serves that task well. It multiplies that
list by every design point a project has: one row for each concept,
shared among agents, kept between sessions, and checked against the
code. It builds on the kinds of design point [Y1, Y12, Y14], the store
[V22], and the helper reports [T51, T53, T58, T63].

## Why agents keep their state here

- **CPO§W22:** Writing a note is cheaper than any tool, so Concipio wins
  on reading instead. An item's brief holds its design text and the code
  it names or cites, in fewer tokens than the agent spends finding them,
  and recording the outcome is one more word on the same command. The
  bookkeeping is a by-product of the read.
- **CPO§W23:** What Concipio returns, a notes file cannot compute: which
  verified items have gone stale, which another agent holds, and how far
  the plan has come [W13].
- **CPO§W24:** State survives compaction without anyone remembering it.
  After a compaction the agent runs `cpo plan join` again [W31]. A large
  model's summary keeps its use of Concipio fresh enough to do that
  unprompted; a harness hook that runs it is a convenience, not a
  requirement.
- **CPO§W25:** A project keeps its own ledgers. Concipio reads a table
  `.cpo` names, such as a defect ledger with a column of section
  references, and adds staleness to its rows, and adds no required
  process.

## Plans

- **CPO§W28:** A plan is a named list of work that agents claim: its
  items are design points, and its record is a log doc in the
  repository. Audits, roadmaps, and the work an audit's findings call
  for are all plans, worked by one set of commands.
- **CPO§W29:** `cpo plan start <target>` starts a plan on a part of the
  design and writes its log doc: the date, the purpose, the scope, the
  checklist, the commit it started at, and who started it. The purpose
  is inferred from the target, such as "Check DESIGN §5c against the
  code", and `--purpose` overrides it. `--log` names the doc; by default
  it is `plans/<date>-<slug>.md`, or `audits/` for an audit, with a
  slug built naively from the target or the purpose.
- **CPO§W30:** A new plan's log is filed as a bullet under the nearest
  workstream above its target [Y16], or the one `--under` names, or a new
  one `--new-workstream` creates beside the target. `.cpo` may name a
  default. With no workstream to file under, Concipio files nothing and
  says how to name one.
- **CPO§W36:** `cpo mv` renames a doc and rewrites every Markdown link
  to it, so a log or a design doc can move freely. Tags hold no paths,
  so citations need no rewriting, and a doc `cpo mv` moved keeps its
  signature [M25, W17].

## Agents

- **CPO§W31:** `cpo plan join <name>` is the handshake an agent runs
  first and again after every compaction. It settles who the agent is
  [W27], adds it to the plan's roster with its model and messaging
  socket, so a coordinator can see who is working and reach them, and
  prints what it holds, what it found, and what remains.
- **CPO§W27:** A claim's holder is `$CPO_AGENT`, or else the session of
  the nearest harness among the process's ancestors: Claude Code's
  `CLAUDE_CODE_SESSION_ID`, Codex's `CODEX_THREAD_ID`, or pi's
  `PI_SESSION_ID`. A harness passes its own variables to any harness it
  starts, so the nearest one decides. These IDs survive compaction.
  Subagents share their parent's session, and Antigravity names none,
  so each needs a `CPO_AGENT`; Concipio prints one to set rather than
  guess.
- **CPO§W26:** A large model may split its work among helpers. `cpo plan
  join <name> --helper` gives a helper an identity tied to its parent,
  each claims a narrower item with a slice of code and a stated
  question, and their claims and findings roll up to the parent. Small
  models do useful work when handed a slice, not when left to find
  their way through a large file.

## Working an item

- **CPO§W8:** `cpo plan next <name>` claims an item for the agent asking
  and hands it the brief: the item's text, its code, and for an audit
  each cluster's differences and the rules and claims in scope. A claim
  names its holder and expires, so work an agent abandons returns to
  the queue, and an agent asking again resumes its own claim.
- **CPO§W6:** A brief is sized to a budget the claimant states, in
  tokens. An item larger than one budget splits along its sub-points.
- **CPO§W10:** `cpo plan done` ends a claim with an outcome: done or
  verified, a finding, or a question for a person, recorded against the
  item's fingerprints. A question names whom it is for, the item's owner
  by default [F1]. A finding's text stays in the plan's status after the
  edits that fix it make the item stale, since that is when it is read.
- **CPO§W32:** `cpo plan note <item> "<text>"` appends a dated line to
  the item's log, which is simply its children: bullets under it, or a
  child doc it links to. When the bullets would push a section past its
  length limit [M41], the log moves to a child doc linked from the item.
- **CPO§W33:** `cpo plan close <name>` writes the plan's outcome into its
  log doc, what was done, found, and left open, and moves its bullet
  from the workstream's active list to its completed one.
- **CPO§W34:** Claims and the roster are short-lived, and exist to keep
  agents apart, so they live in the store under its lock. What a plan
  produced, its notes, outcomes, and corrected design, is versioned in
  the repository, so a scheduled run on another machine starts from
  what is checked in.

## Audits

- **CPO§W15:** An audit is a plan seeded with an item per unit of its
  scope, each asking whether the unit's text holds of its code, with a
  checklist: look-alike differences, unwritten rules, unbacked claims.
  `cpo audit start <target>` starts one; `.cpo` declares audits a
  project runs again.
- **CPO§W2:** An audit's unit is a design point with the code it claims
  [Y12]: a mechanism, a library, or, before anything cites the design, a
  section and the code it names. The breadth and section limits keep a
  unit small enough to read whole [M49, M41]. A file a section names is
  a pointer the brief shows, not a claim on the whole file, which would
  make a section that mentions a large file stale at every commit.
  - **CPO§W4:** A look-alike cluster joins the unit of any of its copies,
    whole, and its differences are the unit's checklist [T53].
- **CPO§W21:** A unit is verified when an agent or a person has checked
  its claims against its code: "checked against `<sha>` by `<who>`". The
  record goes stale when the unit's text, or code it names or cites,
  changes. This extends `Verified` [F16] to every point, and needs no
  citation to work. A check made at an earlier commit is recorded at
  that commit, `--at <sha>`, and shows stale at once if the unit has
  changed since, so earlier work is neither lost nor overstated.
- **CPO§W38:** A stale unit says why: whether its text or its code
  changed, which declarations, the commits that changed those lines,
  and a diff of each against the commit it was checked at. A comment
  that newly cites the unit without documenting any declaration is
  listed as a citation, with no diff. Code the unit stopped claiming,
  because its text no longer names it, is reported as no longer
  claimed, not as removed.
- **CPO§W39:** Of a large declaration, a unit claims only what it
  points at: the stretch after a comment inside it that cites the unit,
  the stretches starting at lines that use names the unit's text gives,
  or else the declaration's head. A unit that mentions a thousand-line
  function then goes stale when the part it describes changes, not at
  every edit to the function. The brief for a
  stale unit opens with that, and `cpo audit why` shows it alone, so a
  re-check reads the change rather than the whole unit again.
- **CPO§W12:** An audit's findings become items of the same plan: a fix,
  then the corrected prose, after which the unit is verified and ready
  to cite [Y13]. A finding the team has no cycles for becomes a to-do
  point with a tracker reference [Y8], and one that proves intended
  becomes a verdict that two look-alikes differ on purpose [Y7].
- **CPO§W11:** A finding records whether the design text changed the
  verdict, the evidence for whether the docs earn their keep.
- **CPO§W1:** A re-run of an audit offers only what has gone stale
  since. Running one on a schedule is the project's business: CI or cron
  starts it and hands its items to agents [W16].
  - **CPO§W16:** Concipio keeps a plan's state and never schedules
    itself.
- **CPO§W7:** An audit offers items in order of risk: stale ones first,
  then clusters whose differences include a guard, unwritten rules, and
  unbacked claims, then the rest. Whether a brief includes the design
  text is a setting, so a project can measure what the docs add [W9].
  - **CPO§W9:** The same unit, briefed with and without its design text,
    compared by findings and cost [W14].

## Drafting a design

An audit of a repository with no design has nothing to check. An agent
onboarding one wrote a design of six sections about the code it already
suspected, audited a twentieth of the code against it, confirmed what it
suspected, and stopped. The leads `cpo unreachable` and `cpo unwritten`
had printed went into its summary and no further. A trial on the same
codebase that first drafted a design of the whole thing, then checked
it, found a defect nobody had suspected.

- **CPO§W40:** A repository with no design starts by drafting one, and
  an audit drafts it. Code that no unit claims and nobody exempts is
  itself a unit to draft: a run of one file's top-level declarations
  that fits the brief's budget, or one declaration that does not. An
  audit begun where no design claims any code offers these before any
  section to check, so the design covers the code before anyone checks
  it; one begun on a design checks the design first, and drafts last.
- **CPO§W41:** A drafting brief holds the code and the outline of the
  design so far, and asks for sections that say what the code does now,
  in claims a reader could check, naming its declarations in backticks.
  `cpo audit done <name> <unit> --drafted` refuses while any of the
  unit's declarations is still unclaimed, and names them: each must be
  described, exempted as plumbing, or left with a question.
- **CPO§W42:** The audit records which agent drafted each section, and
  does not offer that agent the section to check, since checking one's
  own reading of the code is no second read. The section waits for a
  helper with its own `CPO_AGENT`.
- **CPO§W43:** People screen a draft once it is in order: drafted whole,
  every section checked by a second agent, and the findings recorded.
  `cpo audit status` says when that is, and asks a person to sign the
  outline [W17]. Until then a drafted doc says, in a status line under
  its title, that an agent drafted it and nobody has signed it, so no
  reader takes it for the project's own design. A finding against a
  drafted section may be a defect in the code or in the draft, and its
  brief says to check both.
- **CPO§W44:** Discoveries are recorded when they are made.
  `cpo audit note <name> "<text>"` adds a lead, something worth checking
  that is not the unit in hand, as an item of the audit that any agent
  can claim and close as it closes a unit. An audit starts with a lead
  for each unbacked claim `cpo unreachable` finds and each rule
  `cpo unwritten` finds. A lead outlives the session that noticed it,
  and `cpo audit status` lists the open ones.
- **CPO§W45:** `cpo status` on a repository whose design claims none of
  its code says so first, with the command that starts drafting one.
  The score of its docs comes after, since a broken link matters less
  than undocumented code.

## Milestones

Concipio's guide reaches an agent as instructions no person wrote for
that task, which is what a careful harness guards against. So the guide
never sets an audit's scope: a person does, and the agent then holds to
it.

- **CPO§W46:** The user's instructions and the harness's rules come
  before anything `cpo help agent` says. The guide describes the tool;
  it does not assign the work.
- **CPO§W47:** An agent given room to drive, as by "set it up and spin"
  or "go find the bugs", proposes a milestone before starting:
  `cpo audit propose <name> [--scope ...]` prints the audit's size, the
  code to draft, the sections and leads to work, as a sentence to put
  to the person. A person can judge that; "may I audit?" gives them
  nothing to judge. When it is unclear whether the agent may drive, it
  asks.
- **CPO§W48:** `cpo audit start <name> --scope ... --approved-by <who>`
  records the milestone a person approved, with its scope and when. The
  audit then draws its items from that scope, `cpo audit status` reports
  against it, and a helper or a compacted agent reads who approved the
  work rather than taking the guide's word for it. Between approval and
  the milestone the agent keeps working, and reports when the draft is
  in order [W43] or a question only a person can answer blocks it.
- **CPO§W49:** An audit that runs with nobody to ask, from CI or cron,
  takes its milestone from `.cpo` [W15]: a `[[milestone]]` entry with
  the audit's name and scope, approved by the review of the commit that
  added it.

## Planned work

- **CPO§W35:** A roadmap is a plan whose items are the planned and
  in-progress points of its scope [Y14]. An agent claims one, works it,
  and notes progress against it [W32]; when the work lands, the point
  becomes a claim about the code, and the next audit verifies it [Y15].

## Human sign-off

Agents run ahead of people; signing is how a person catches up. A
signature says that a person read a doc or section as it now stands and
agrees, so it must name exactly what was read, and must be impossible
for an agent to write on the person's behalf where the project needs
that.

- **CPO§W17:** A person reviews a design's structure, not every line:
  whether the docs, sections, and statements are the right ones, in the
  right places. They sign a doc or a section, and the signature is a
  pair of fields in the attribute list under its title or heading:
  `{Signed="Josh 2026-11-16T21:03:07Z" Sig="ssh:U1NIU0lH..."}`. This
  refines [M25], which signs only that a doc should exist.
  - **CPO§W18:** A signature covers its doc's or section's whole text,
    as the doc model defines it [D10]: everything under the heading,
    nested sections included, less every `Sig` and the nested sections'
    own signatures. When that text changes, lint reports the signature
    stale. Signing the outline alone, the headings and statement names,
    is a later option.
- **CPO§W19:** Instead of signing, a reviewer may leave a directive,
  `{Restructure="split into three; the queue part belongs in queue.md"}`.
  A directive is a to-do point [Y8], and an item of the next plan that
  covers it.
- **CPO§W20:** `cpo brief --unsigned` lists what awaits signing, from
  the master down, so a person signs the top of the tree first.

### Signing

- **CPO§W50:** `cpo sign [doc or tag ...]` is a review a person starts.
  For each doc, or with `--sections` each section, that is unsigned or
  whose signature is stale, it shows what changed since the signature,
  as a diff, or the whole text if it was never signed, and asks: sign,
  skip, or leave a directive [W19]. It refuses to run without a
  terminal to ask on, so an agent cannot answer for the person.
- **CPO§W51:** The text before is the doc as it stood at the commit
  that wrote the signature now in it, which git finds by the
  signature's own value; a signature not yet committed is compared with
  the last commit.
- **CPO§W52:** On yes, `cpo sign` writes `Signed` with the signer's name
  and the time to the second, in UTC, then signs the covered text with
  it [D10] and writes `Sig`, each as a splice [D8]. The name is
  `[signing] name` in `.cpo`, else git's `user.name`.

### Proof

- **CPO§W53:** `Sig` holds an SSH signature, made by `ssh-keygen -Y
  sign` in the namespace `concipio` with the key git signs commits
  with, `user.signingkey`. Its value is `ssh:` and the signature's
  base64, on one line. Making it needs the key's passphrase, or a touch
  of a hardware key, so only a person can sign; a key held unlocked in
  an agent should be added with `ssh-add -c`, which asks each time.
  GPG would be `pgp:` the same way, later.
- **CPO§W54:** Lint checks every signature against a signers file that
  maps names to public keys, as `ssh-keygen` reads it, with underscores
  for the spaces in a name: `[signing] signers` in `.cpo`, by default
  `.cpo-signers`. It is versioned, so adding a signer is a reviewed
  change. A signature whose text changed is stale; one whose `Sig` does
  not verify on unchanged text is invalid.
- **CPO§W55:** `[signing] require = "ssh"` in `.cpo` makes a `Signed`
  with no valid `Sig` count as unsigned, and lint reports it. An agent
  that writes a signature for a person then fails lint, and nobody has
  to tell it so. Without the setting, a signature is trusted as
  written, as `Verified` is.

## Progress

- **CPO§W13:** `cpo plan status <name>` reports what is done or verified,
  by items and by the lines of code they claim, apart from coverage;
  what has gone stale since; and which claims, findings, and questions
  are open. An adoption's first weeks show their work here, long before
  citations move coverage [Y13].
- **CPO§W37:** `cpo status` says where a person or agent stands, as
  `git status` does in the middle of a rebase: first the work in
  flight, each plan joined and how far it has come, and any review in
  progress [V18]; then the score and its problems [M50]. The share
  verified stays apart from the score, so nobody reads "2,648 to-dos
  remain" without first learning that an audit is halfway through them.
  The score moves from `cpo audit` to `cpo status`, and `cpo audit`
  means only audits [W15].

## First trial

- **CPO§W14:** The first trial audits a family of look-alike release
  routines in a C codebase, where the cluster's differences already led
  to real questions. It runs with and without the design text in the
  brief, on a small model and on a large one, and the four runs are
  compared by findings, false leads, and tokens.
