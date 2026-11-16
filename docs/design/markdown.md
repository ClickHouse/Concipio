# Reading and editing docs

Parent: [Concipio](../../README.md)

**Status: proposed.** Concipio still reads docs with line patterns in
`src/concipio/docs.py`; nothing here is built.

Concipio finds sections, statements, fields, and citations in Markdown
with regular expressions over lines. That misses what the patterns do
not foresee, such as a heading underlined rather than marked with `#`,
or a fence of four backticks around one of three, and it gives no exact
place to change. Signing a section [W17] needs both: the exact text a
signature covers, and the exact place its fields go, so that writing a
signature changes nothing else. This doc puts a model of a doc between
Concipio and the parser, and makes every change to a doc a splice into
its original text.

## The model

- **CPO§D1:** Concipio reads a doc through its own model, never a
  parser's tree. The model holds what Concipio needs, each element with
  its byte and line range in the original text:
  - **CPO§D2:** Blocks: sections, each with its heading's level and
    title and its child sections; lists and list items, each item with
    its marker, its indent, and the lists nested in it; paragraphs;
    block quotes; and code blocks, which Concipio skips.
  - **CPO§D3:** Inline: code spans, which hide tags and fields [T20],
    links with their targets, and attribute lists.
- **CPO§D4:** A backend builds the model from one format. The first
  reads Markdown with tree-sitter-markdown's block and inline grammars,
  as Concipio reads code with tree-sitter [T66]. Another format, such as
  reStructuredText or Org, would be another backend building the same
  model; nothing above the model names Markdown. None is planned.
- **CPO§D5:** Where a grammar's tree differs from what a writer means,
  the backend makes the model say what the writer meant. An underlined
  heading opens a section, as a `#` heading does, though the grammar
  does not nest one. A region the grammar cannot parse is reported by
  lint with its lines, not guessed at.

## What Concipio finds in it

- **CPO§D6:** Sections are headings, numbered ones defining tags as a
  source's pattern says [T39]. A statement is a list item whose first
  line opens with its bold tag, and it extends over the item, nested
  lists included. Citations and references are found in prose only,
  never in code.
- **CPO§D7:** Fields are attribute lists in a heading, a paragraph, or
  an item's first paragraph, still parsed by Python-Markdown's
  `attr_list` [F1], since the grammar has no node for them. The model
  supplies the boundaries; the parser reads what is inside.

## Editing

- **CPO§D8:** Concipio changes a doc only by splices: a byte range of
  the text it parsed and the text to put there. Nothing is rendered
  again, so every byte outside a splice is unchanged. Splices apply in
  one pass from the end of the file; overlapping ones are refused, and
  so is a file whose bytes changed since it was parsed.
- **CPO§D9:** The model offers edits as splices: set a field in an
  element's attribute list, adding the list where it belongs; add an
  item under another, with its marker and indent; add a section; change
  a link's target. Each is tested by round trip: parse, edit, and find
  exactly the lines expected changed. `cpo sign`, `cpo elaborate`, and
  `cpo mv` [W36] edit through these.
- **CPO§D10:** The text a signature covers is defined over the model,
  so that another implementation can verify it: the bytes of the
  section's range, with line endings as `\n`, trailing whitespace
  removed, and the value of every signature field in the range removed,
  nested sections' included. A sub-section signed later then leaves its
  parent's signature valid while its text is unchanged.

## Switching readers

- **CPO§D11:** The model replaces the line patterns for headings,
  sections, fences, and statement extents. Before the switch, the two
  readers must give the same tags, citations, and lint problems on
  Concipio's docs and an adopter's, except where the patterns were wrong,
  such as underlined headings, four-backtick fences, and statements in
  block quotes; each difference is listed and judged. The grammar is a
  new dependency, so the tool must be installed again.
