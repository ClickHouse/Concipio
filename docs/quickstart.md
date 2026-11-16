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

> Run `cpo help agent` and follow its section on adopting Concipio.
> Propose a milestone, and once I agree, work until it is reached or you
> need a decision from me.

The agent comes back with a milestone sized by `cpo audit propose`, such as
"39 units of code (5,862 lines) to describe in a design, each section then
checked by a second agent; 2 leads to look into". Agree, or name a
directory to start smaller. With no design to start from, the agent drafts
one first: the audit hands it the code no design describes, a file's
declarations at a time, then has other agents check each section it wrote,
and keeps every lead it notices. A run with nobody to ask, from CI, takes
its milestone from a `[[milestone]]` entry in `.cpo`, with the audit's
`name` and a `scope`.

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
are the right ones, in the right places. Run `cpo sign`. For each doc
that is unsigned, or changed since you signed it, it shows what changed
since your last signature, and asks:
- **sign**, which writes `{Signed="Your name 2026-11-16T21:03:07Z"}` under
  the title, to the second;
- **skip**;
- or leave a **directive**, such as
  `{Restructure="split this; the queue part belongs in queue.md"}`,
  which an agent will carry out.

`cpo sign --sections` signs section by section, and `cpo sign --list`
shows what awaits you without asking anything.

To make signatures provable, so that no agent can sign for you, sign with
an SSH key that has a passphrase: set `git config user.signingkey
~/.ssh/id_ed25519`, the private key, and list each signer's public key in
`.cpo-signers`, one line per person, as `Your_Name ssh-ed25519 AAAA...`,
with underscores for the spaces in your name.
`cpo sign` then adds a `Sig`, and `ssh-keygen` asks for the passphrase
each time. A key held in ssh-agent signs without asking, so keep this one
out of it, or name its `.pub` and add it with `ssh-add -c`, which asks
each time instead. `[signing] require = "ssh"` in `.cpo` makes lint
reject any signature without a `Sig`.

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
