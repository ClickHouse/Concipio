# Store design: review notes (2026-11-01)

Josh's inline comments on the first draft of [the store design](../design/store.md), as written, kept because they shaped its second draft.

# The store

Parent: [Review mode](review-mode.md)

**Status: design, not built.** This replaces the store layout that review
mode uses today [V12, V22], and the carry-over between heads [V11].

The store keeps what agents and reviewers decided about a repository's code,
outside the repository [M28]. Today it files that work by review, so every
new head of a change gets its own copy: when the first test change was rebased, 194
of its 236 spans were copied unchanged. This doc keys the work to the code
instead, so one record serves every commit where its code is unchanged.

## Identity

- **K1:** A project is identified by the root commit reached by following
  first parents from the default branch's tip. Every clone, fork, and
  worktree of the project shares one store. A repository that imported
  another project's history keeps its own identity, because the imported
  root is never on its first-parent line.
  
  > I agree the project is technically defined this way. However, in practice,
  > I believe it should be exceedingly rare for that commit to appear in any of
  > our blame layer caches. Even if some of the SHAs are hundreds of commits
  > old, most files will not have existed at the very first commit of the
  > repository, which is often just README.md or the like (which I'll grant,
  > the Concipio discipline increases in likelihood of being applicable to a
  > repository after thousands of commits).

- **K2:** A region is a stretch of code that the span rules ([V8]) cut out.
  Its identity is its path and its scope, and its fingerprint is a hash of
  its text with each line's surrounding whitespace removed and blank lines
  dropped. Reindenting a region does not change its fingerprint; changing
  a token does.

  > Treating all whitespace between a newline as 0 or 1 space is probably a
  > solid play, here. Particularly if we want to include the comments mentioned
  > in [V8]: indentation often means reflow, and sometimes means breaking words,
  > which may have been connected by a hyphen previously. It may not be worth
  > handling that reflow case perfectly; it's okay if it causes us to just have
  > a slightly duplicated index, in my opinion. What we're really guarding
  > against, dup-wise, is trees of commits giving each leaf its own copy of
  > everything over time. The changes themselves will accumulate linearly, and
  > deduping that in more places is "cool"--particularly because it allows
  > tracking provenance back through time like an extension of the blame layer.
  > But it will share similar faults, and we have to accept that on some level
  > unless we decide that the driving agent should handle apprising the text as
  > identical (cpo could offer simple calls to override the char-wise matching
  > algorithm for a particular section, if that turned out to matter).

## Records

- **K3:** A record holds what was decided about one region: the concepts
  it serves, in which role, or an unjustified mark. It also holds the
  region's fingerprint, its first and last three lines as evidence a person
  can read, its line range at the commit where it was reviewed, that commit,
  and the review that made the decision.

  > As I'm seeing this come together in my head, I'm leaning more and more on
  > the idea that overlapping concept should be rarer than hierarchical concepts
  > (not because Concipio doesn't support them, but because organization leds
  > itself  naturally to hierarchical reasoning). I wouldn't consider that the
  > fundamental theorem of Concipio, but it's a hypothesis I'm partial to and
  > very interested in putting to the test as this project grows. I mention this
  > because what was decided in a region likely includes or was influenced by
  > what was decided in its file (the hierarchy of translation unit / module ->
  > function -> line of code). Without engaging in the holy war of whether every
  > meaningful subdivision of a function should have been extracted iteself as a
  > function (I have colleagues on both sides of that fence), Concipio more or
  > less should be: it should be easy to trace a "why" not just through a
  > particular mechanism (which I'm increasingly using as a vocab term to refer
  > to spatially isolated regions of code working together to implement a single
  > design bullet), but through the full hierarchy of the files/functions that
  > contain it. This may come across as sardonic, but I feel a bit as though
  > we're implementing a dynamically scoped language for documenting stuff.

- **K4:** A record applies at any commit whose tree has a region with the
  same path, scope, and fingerprint, whatever the commit's hash. A rebase,
  squash, or cherry-pick that leaves a region's text alone leaves its record
  in force, so a record is written once, not once per head.
- **K5:** A record goes stale when its region's scope still exists but
  its fingerprint differs. A stale record never applies. `cpo check` counts
  its region as uncovered, and `cpo next` offers it to an agent with the old
  decision shown, to confirm or replace [V11]. Concipio never stretches a
  record over code nobody reviewed.
- **K6:** A record whose scope no longer exists is orphaned. Concipio
  keeps it as history but never applies it. When git reports that the file
  was renamed, the record moves to the new path mechanically, since the
  region did not change.

  > I want to point out a second kind of orphaning that Concipio needs to be
  > aware of: SHA orphaning due to rebase. We can detect this any time we
  > actually need to query Git for the blame layer, provided our cache agrees
  > somewhere with blame: if our own blame layer chooses to differ (such as in
  > our reindent/reflow case from before), it should nonetheless cache the
  > current git SHA for the line according to Git. This tells us not only that
  > Git's opinion didn't change, but that we can certify that the commit we cite
  > is a parent of that commit in the tree.

- **K7:** An unjustified mark says what a reviewer should do about it:
  *request* a change, such as removing the code, or record that the code is
  *unplaced*, meaning it serves a purpose no single concept captures. Only
  requests count as unjustified in reports. Unplaced regions go back to the
  sweep, to attach to the concepts they serve or their nearest common
  parent.

  > This point spans two divides, a bit ungracefully.
  > - Divide 1: Pull request vs full codebase. A pull request will want
  >   actionable feedback in an immediate sense. A late-adopting code base will
  >   likely prefer a longer-term plan.
  > - Divide 2: Big agent vs small agent. I think making PR recommendations
  >   falls outside of Haiku territory and probably into Opus and human
  >   territory, and any long-term planning is there with great certainty.
  >
  > Still, by and large, I agree with this point. As a review tool, this is an
  > important takeaway.

## Layout and format

- **K8:** The store holds, per project:
  - `name`, the remote URL, for people;
  - `statements.toml` and `concepts.toml`, the project's design;
  - `regions/`, one file per code file, mirroring the repository's paths,
    holding that file's records in line order;
  - `reviews/<base>..<head>/`, each review's manifest, its design text
    snapshots as Markdown, and its command log.

    > The "name" field could be difficult to reconcile against forks, but if
    > it's agent-chosen for human reference, that seems very workable.

- **K9:** Files people may read are TOML, read with Python's `tomllib`
  and written by a small emitter in Concipio, since the standard library
  cannot write TOML. Each record is its own table, and tables are sorted,
  so a change to one record is a small diff. The command log, which only
  machines read, stays JSON Lines.

  > Thinking more about this, I believe it's worth the tomli-w to avoid writing
  > our own emitter, and to unlock writing more complicated structured data with
  > an official lib. If TOML isn't well-suited to our glue files in the way YAML
  > is, then I suppose JSON is fine--I won't advocate for tacking two separate
  > serializers onto our dep list. But otherwise, I think the dep is well worth
  > it--we already depend on some language services, which bring in plenty of
  > side deps on their own. Hell, wouldn't surprise me if YAML or tomli-w were
  > among them already. I feel as though most people depend on one of those or
  > the other, nowadays.

## Lookups

- **K10:** To find the records at a commit, Concipio cuts the regions of
  the files in question at that commit and matches them to records. Cut
  regions are cached by git blob ID, so a file whose content is unchanged
  between commits is never parsed twice.
- **K11:** A render is a view at a commit [V29]: the statements and
  concepts, with the records that apply there. Rendering a pull request's
  head and rendering `main` are the same operation over the same records.
- **K12:** Git history is for navigation, not lookup. Concipio diffs a
  record's reviewed commit against the commit in question to find what
  changed, and uses blame only where history was rewritten: to trace a
  squash or rebase commit back to the pull request whose records describe
  it.

  > Yeah, I think a general `cpo` operation keeps git off the hot path, but I
  > also believe it's important for Concipio to assist in maintaining Git
  > history, particularly across rebases/squashes. FF is the obvious case.
  > I'm not certain if the really lightweight cases (e.g. final rebase onto
  > master or, better yet, squash of one commit that was already on master)
  > change the sha while changing nothing about the analysis, so symlinking
  > the whole dir makes sense unless the original is now orphaned (which could
  > then simply be a rename, never looking back).

## Migration

- **K13:** Existing reviews convert mechanically: each span with an
  attachment or mark becomes a record at its review's head, and the graph
  splits into `statements.toml` and `concepts.toml`. No decision is
  remade. The conversion is checked by rendering every converted review
  before and after and comparing the results.

## Open questions

- Two regions in one scope can have identical text, such as two identical
  test fixtures. Should their records key on the region's position within
  the scope as well [K2]?
  
  > Yeah, this doesn't seem to have landed in this document, but for our own
  > glue files, I was expecting to virtually duplicate the original file (or the
  > abbreviations of it that *are* mentioned in this file) into our own file
  > structure. What I think I failed to mention earlier that explains why I want
  > to do this is that, if we maintain a similar order in our own glue files as
  > in the original source, we can detect where in the file the duplicated
  > reference points live by the sheer number of pre-established reference
  > points--you know, like in a standard diff. Lines duplicated everywhere
  > wouldn't matter as long as they had defining text between them.
  
  > That being said, I think another side goal of Concipio should be to cut down
  > on duplicated code in all cases--if your test fixture setup is the same, why
  > aren't you extracting it to a helper, or subclass, or decorator, or whatever
  > your language of choice offers specifically to help you to avoid repeating
  > yourself? Duplicate concept implementations would be flagged right away, if
  > this system is working properly; I wouldn't cut much slack to someting like
  > test fixture setup that happens to use the same config. If entropy is small,
  > actual repetition across usage sites should be small.

- Should `cpo export` share the store between people as these same files,
  or as one bundle [V12]?

  > The best way for a team to share these files is to render them obsolete by
  > checking Concipio references directly into their code base. This makes git
  > the manager, as Git should be, instead of Concipio trying its hardest to
  > bolt a revision control system over top of Git for the sake of answering
  > "what would a Concipio analysis have looked like at this commit?"--it would
  > just be there. Checked in to permanent git history. That's what we should be
  > pushing for. In a way, this entire design is one huge side-quest that almost
  > detracts from the problem we're really trying to solve, but I'm still
  > interested in it as a means of further reducing the barrier to entry for
  > new users. What we should really invest in is a way to easily automate the
  > switch from Concipio's tree of side cars to direct citation within the
  > source files, up the hierarchy by a stable section ID. Mind, we haven't
  > discussed it, but there's really no reason a user couldn't also put section
  > numbers in their code doc comments and cite into those from higher-level
  > design documents. I do expect the design documents to do the same. What I
  > want to avoid is anything pointing to a line number, particularly without
  > the reference infrastructure we're discussing here to deduplicate and
  > disambiguate, outside of our glue files. The glue files (and tucking our
  > documentation away outside the git repo) are hacks to make adoption simpler
  > and possible by a single person on a team that doesn't want to embrace
  > Concipio directly.
