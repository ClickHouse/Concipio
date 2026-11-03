# Fields, importance, and briefs

Parent: [Concipio](../../README.md)

**Status: built,** as a first cut: fields, schemas, the depth and freshness
rules, `cpo list --where`, `cpo brief`, and `cpo path`.

Diátaxis sorts docs by what a user needs: to learn, to do a task, to look
something up, or to understand. A project needs more than that: what is in
flight, who has it, how urgent it is, and which tracker items it is attached
to. That knowledge is what goes missing when an agent's context is compacted
or a memory file goes stale. This doc puts it in the same docs, as fields on
statements, which projects define and Concipio checks and answers from.

## Fields

- **CPO§F1:** A field is a key and value in a Markdown attribute list, as
  Pandoc, kramdown, and Python-Markdown already write them:
  `{Owner=Josh Updated=2026-11-03}`, or `{: Owner="Josh V"}`. It belongs to
  the statement whose text contains it, and is left out of that statement's
  text and name. Concipio parses attribute lists with Python-Markdown's own
  parser, and braces that do not parse wholly as one are prose.
  - **CPO§F13:** A project that prefers its own syntax gives `.cpo` a
    pattern with `key` and `value` groups, such as
    `\[\[(?P<key>\w+):\s*(?P<value>[^\]]+)\]\]` for `[[Owner: Josh]]`.
    Prior art is preferred, so the attribute list is the default.
  - **CPO§F14:** A value too rich for one line goes in a fenced block tagged
    `cpo`, holding TOML, inside the statement. Such a block is data, not an
    example, which is the one exception to [T20]. Larger data belongs in a
    file the statement links to.
  - **CPO§F2:** A field that describes a whole doc, such as the doc's owner,
    may go in front matter, the YAML block some docs open with. Front
    matter is the common convention for this, and GitHub renders it.
- **CPO§F3:** Concipio defines no fields and requires none. A project names
  its own, as its tracker and its habits need. Once it declares any, in
  `.cpo` or in a schema, a key it did not declare is an error, which
  catches a person's typo and an agent's malformed output alike.
- **CPO§F15:** A statement's `Updated` field is checked against git: if the
  statement's lines changed after that date, the field is stale, and so may
  be the claim. `cpo brief` also flags active work whose `Updated` date is
  older than a project-set number of days.

## Schemas

- **CPO§F4:** `.cpo` may give the statements of a part of the design a
  schema: which fields they must carry, and what each may hold.
  - **CPO§F5:** A schema applies to the statements nested under a tag, or to
    the statements of the docs matching a glob. Its constraints are JSON
    Schema, checked with the `jsonschema` package, so a project writes them
    in a standard language rather than one Concipio invents.
  - **CPO§F6:** `cpo lint` reports statements that break their schema, as
    another rule a project can start lax and tighten [T40].
- **CPO§F7:** Fields are queryable. `cpo list --where Owner=Josh` lists the
  statements whose field matches, and an agent asks Concipio what is in
  flight rather than reading every roadmap to find out.

```toml
[[schema]]
under = "PROJ§Roadmap"
require = ["Owner", "Priority"]
fields.Priority = { enum = ["critical", "high", "normal", "someday"] }
fields.Bugzilla = { pattern = '^\d+$' }
```

## Importance

- **CPO§F8:** A statement may carry `**Importance:** critical`, meaning
  nobody may miss it: a correctness gap, a reason not to use the project, a
  limit that loses data. A project may rename the field or its values in
  its schema.
  - **CPO§F16:** A critical statement says when someone last checked it
    against the code, `{Verified=2026-11-03}`. `cpo lint` reports a critical
    statement with no such date, one older than 90 days by default, or one
    whose citing code has changed since. Importance makes a claim more
    prominent, so a wrong critical claim does more harm than a wrong ordinary
    one, and it is the one most worth re-checking. A critical statement known
    to be wrong carries a stale mark as well [T42]; lint and the brief then
    report it as critical and stale, not merely unverified.
  - **CPO§F10:** A critical statement must be reachable within two links of
    the master, by default. It need not be in the master, which would make
    the master long again, but it may never be buried. `cpo lint` reports
    the ones that are, with their path [F9].
  - **CPO§F11:** `cpo brief` prints every critical statement and every
    workstream a project marks active, in a few hundred tokens. An agent
    reads it at the start of a session and after its context is compacted.
    It is computed from the docs each time, so unlike a memory file it
    cannot go stale or drop an item.
- **CPO§F9:** `cpo path` prints the shortest chain of links from the master
  to a doc, and then the statements within that doc down to a tag. It is
  how a person checks where something sits, and how the depth rule counts.

## Decisions

- **CPO§F12:** Concipio does not adopt Sphinx-Needs for fields.
  {Decided="Josh and Claude" Updated=2026-11-03}
  Sphinx-Needs writes items as Sphinx directives, which render as code
  blocks on GitHub and in plain editors, and checks them only in a Sphinx
  build. Concipio's docs must read well as plain Markdown, and its checks
  must run as a lint [M44, M23]. Its schema language is the part worth
  keeping, so schemas are JSON Schema [F5]; Concipio's fields themselves
  are attribute lists, read with Python-Markdown's parser [F1].

## Open questions

- Can a field hold several values, such as two owners, and how is that
  written?
