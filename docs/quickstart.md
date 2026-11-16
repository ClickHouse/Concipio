# Quickstart

Parent: [Concipio](../README.md)

Concipio traces code to its design, finds where the two disagree, and
keeps agents' work from getting lost between sessions. Agents do the
work; you read what they found and sign the design's structure. On its
first large codebase, a C storage driver of about 100,000 lines, the
audit it drove found eight serious defects, which agents then fixed.

## Install

Concipio lives at `ClickHouse/Concipio`, visible inside ClickHouse.
Install it as a tool, at its latest release:

```sh
uv tool install git+ssh://git@github.com/ClickHouse/Concipio.git@v0.0.1
uv tool update-shell     # puts ~/.local/bin, where cpo is, on PATH
```

If `cpo` is "command not found" afterwards, open a new shell, or add
`~/.local/bin` to `PATH` yourself; your agent's shell needs it too.

## Five minutes, no setup

Run these in any repository. None writes a file.

- `cpo helpers` lists functions that look like copies of one another,
  and what each copy does differently. Copies whose guards have drifted
  apart are where bugs hide.
- `cpo unreachable` lists comments claiming a state cannot happen
  ("unreachable", "cannot be exhausted") that no test backs.
- `cpo unwritten` lists checks whose comment names a past bug, in code
  no design describes: rules that were never written down.
- `cpo lint` lists broken links and docs nothing links to.
- `cpo status` sums it up.

## Hand it to an agent

Give your agent this, adjusted to your repository:

> Run `cpo help agent` and follow its section on adopting Concipio. Take
> the whole codebase through the audit, and tell me when the draft is in
> order or you need a decision from me.

To start smaller, name a directory instead of the whole codebase. With no
design to start from, the agent drafts one first: the audit hands it the
code no design describes, a file's declarations at a time, then has other
agents check each section it wrote, and keeps every lead it notices.

`cpo help agent` is the agent's whole manual: how to declare or draft a
design, audit it section by section, record what it finds, and cite it
from the code. It opens:

> Concipio (`cpo`) traces code to its design and holds the state of the
> work on both: it records your judgments and checks them, and makes none
> itself.

## Read what it found

- `cpo status` shows the work in progress first, then the score.
- `cpo audit status <name>` shows an audit: the code left to draft, each
  section verified, stale, a finding, or a question for a person, and
  the open leads. It says when the draft is ready for you.
- `cpo audit why <name> <section>` shows what changed in a section since
  it was checked, as a diff.

A *finding* says something is wrong, and where. A *question* is
something only a person can decide; answering those is your part.

## Your part

You review the design's structure, not every line: whether its sections
are the right ones, in the right places. When a section is right, sign
its outline with `{Signed="Your name 2026-11-07"}`. When it is not,
leave a directive instead, such as
`{Restructure="split this; the queue part belongs in queue.md"}`, and
an agent will carry it out.

## What lands in your repository

Versioned, and reviewed as any change is:

- the design docs, corrected as the audit finds errors;
- citations in code comments, such as `Implements DESIGN §5c`;
- `.cpo`, a few lines of settings, and `.cpo-baseline.toml`, the
  problems known when Concipio was adopted.

Kept on your machine, in Concipio's store, and never committed: which
sections an agent has claimed and checked, and review-mode records.

## Settings you may want

`cpo config` prints every setting in effect and marks the defaults. The
ones most often changed:

- `lint.section_limit` and `lint.breadth_limit`: how long a section may
  run, and how much code one design point may claim.
- `lint.postponed`: docs you will link later, counted but not failed.
- `archive`: old text kept verbatim, which no check reads.
- `[retired]`: names of removed mechanisms, so lint finds prose that
  still describes them.
- `unwritten.incident`: your bug tracker's tag pattern, such as
  `'PROJ-\d+'`, so `cpo unwritten` recognises your incidents.

## Cost

A small model covering one changed span of a review used about 1,200
tokens, and re-checking a section after the code changed means reading
only the diff `cpo audit why` shows.
