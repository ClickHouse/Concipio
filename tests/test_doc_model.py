import difflib

import pytest

from concipio import doc_model as m

SAMPLE = """# Title

{Owner=Josh}

## 1. The ring

- **EX§1:** The ring refuses when full,
  in `ring_take` {Importance=critical}.
  - **EX§2:** A nested point.
    Continued.
- **EX§3:** See [the log](log.md).

Underlined
----------

````markdown
## not a heading {Owner=nobody}
```
````

> ## quoted
"""


def changed(before, after):
    """The lines an edit changed, as (removed, added)."""
    out = ([], [])
    for line in difflib.ndiff(before.decode().splitlines(), after.decode().splitlines()):
        if line[:2] == "- ":
            out[0].append(line[2:])
        elif line[:2] == "+ ":
            out[1].append(line[2:])
    return out


def find(doc, kind, line):
    return next(n for n in doc.walk({kind}) if n.line == line)


def test_sections_nest_by_level_and_an_underlined_heading_opens_one():
    doc = m.parse(SAMPLE)
    top = doc.root.children[0]
    assert (top.kind, top.level, top.title) == ("section", 1, "Title")
    subs = [c for c in top.children if c.kind == "section"]
    assert [(s.title, s.line) for s in subs] == [("1. The ring", 5), ("Underlined", 13)]
    assert subs[0].last == 11, "a section ends before the next heading of its level"


def test_items_nest_with_exact_lines_and_code_hides_headings():
    doc = m.parse(SAMPLE)
    items = [(i.line, i.last, i.indent, i.marker) for i in doc.walk({"item"})]
    assert items == [(7, 10, 0, "-"), (9, 10, 2, "-"), (11, 11, 0, "-")]
    assert doc.code_lines() == {16, 17, 18, 19}
    titles = [s.title for s in doc.walk({"section"})]
    assert "not a heading {Owner=nobody}" not in titles and "quoted" not in titles


def test_inline_finds_code_spans_links_and_fields_but_not_in_code():
    doc = m.parse(SAMPLE)
    first = find(doc, "item", 7).children[0]
    assert [n.kind for n in first.inline] == ["code_span", "attrs"]
    assert first.inline[1].fields == {"Importance": "critical"}
    link = next(doc.walk({"link"}))
    assert doc.slice(link.target) == "log.md"
    owners = [a.fields for a in doc.walk({"attrs"})]
    assert {"Owner": "nobody"} not in owners


def test_setting_a_field_changes_only_its_value():
    doc = m.parse(SAMPLE)
    item = find(doc, "item", 7)
    out = m.apply(doc.text, [m.set_field(doc, item, "Importance", "high")])
    assert changed(doc.text, out) == (
        ["  in `ring_take` {Importance=critical}."], ['  in `ring_take` {Importance="high"}.'])


def test_a_new_field_joins_the_list_or_goes_under_the_heading():
    doc = m.parse(SAMPLE)
    item = find(doc, "item", 7)
    out = m.apply(doc.text, [m.set_field(doc, item, "Verified", "2026-11-16")])
    assert changed(doc.text, out)[1] == [
        '  in `ring_take` {Importance=critical Verified="2026-11-16"}.']
    section = next(s for s in doc.walk({"section"}) if s.line == 5)
    out = m.apply(doc.text, [m.set_field(doc, section, "Signed", "Josh 2026-11-16T19:52:07Z")])
    assert changed(doc.text, out) == ([], ['{Signed="Josh 2026-11-16T19:52:07Z"}'])
    again = m.parse(out)
    section = next(s for s in again.walk({"section"}) if s.line == 5)
    out2 = m.apply(again.text, [m.set_field(again, section, "Sig", "ssh:abc")])
    assert changed(out, out2)[1] == ['{Signed="Josh 2026-11-16T19:52:07Z" Sig="ssh:abc"}'], \
        "the second field joins the list under the heading"


def test_items_and_sections_are_added_in_place():
    doc = m.parse(SAMPLE)
    nested = m.apply(doc.text, [m.add_item(doc, find(doc, "item", 7), "**EX§4:** New.")])
    assert changed(doc.text, nested) == ([], ["  - **EX§4:** New."])
    assert nested.decode().splitlines()[10] == "  - **EX§4:** New."
    section = next(s for s in doc.walk({"section"}) if s.line == 5)
    out = m.apply(doc.text, [m.add_section(doc, section, "1a. Its sizing", "Text.")])
    assert changed(doc.text, out) == ([], ["### 1a. Its sizing", "", "Text.", ""])
    again = m.parse(out)
    assert [s.title for s in again.walk({"section"})][:3] == [
        "Title", "1. The ring", "1a. Its sizing"]


def test_a_link_is_retargeted_alone():
    doc = m.parse(SAMPLE)
    link = next(doc.walk({"link"}))
    out = m.apply(doc.text, [m.set_link(doc, link, "docs/log.md")])
    assert changed(doc.text, out)[1] == ["- **EX§3:** See [the log](docs/log.md)."]


def test_splices_refuse_overlap_and_a_changed_file():
    doc = m.parse(SAMPLE)
    with pytest.raises(m.SpliceError):
        m.apply(doc.text, [m.Splice(0, 5, "a"), m.Splice(3, 8, "b")])
    with pytest.raises(m.SpliceError):
        m.apply(doc.text, [m.Splice(4, 4, "a"), m.Splice(4, 4, "b")])
    with pytest.raises(m.SpliceError):
        m.apply(doc.text, [m.Splice(0, 1, "x")], current=doc.text + b"edited")
    assert m.apply(doc.text, []) == doc.text
