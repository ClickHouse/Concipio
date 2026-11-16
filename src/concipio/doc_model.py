"""A model of a doc: the blocks and inline elements Concipio reads, each
with its range in the original text. A backend builds it from one format;
the first reads Markdown with tree-sitter-markdown [CPO§D1, CPO§D4]."""

import re
from dataclasses import dataclass, field
from functools import lru_cache

BLOCKS = {"section", "heading", "list", "item", "paragraph", "quote", "code", "html"}
INLINE = {"code_span", "link", "attrs"}


# Implements [CPO§D2, CPO§D3]
@dataclass
class Node:
    """An element of a doc. `start` and `end` are byte offsets into the
    text, the end exclusive; `line` and `last` are its first and last
    lines, counted from 1."""
    kind: str
    start: int
    end: int
    line: int
    last: int
    children: list = field(default_factory=list)
    inline: list = field(default_factory=list)
    level: int = 0
    title: str = ""
    marker: str = ""
    indent: int = 0
    target: tuple | None = None
    fields: dict | None = None
    heading: "Node | None" = None

    def walk(self, kinds=None):
        """This node and every node under it, blocks and inline, in order."""
        if kinds is None or self.kind in kinds:
            yield self
        for n in self.inline:
            if kinds is None or n.kind in kinds:
                yield n
        for c in self.children:
            yield from c.walk(kinds)


# Implements [CPO§D1]
@dataclass
class Doc:
    text: bytes
    root: Node
    errors: list = field(default_factory=list)

    def walk(self, kinds=None):
        return self.root.walk(kinds)

    def slice(self, node_or_range):
        a, b = (node_or_range.start, node_or_range.end) if isinstance(node_or_range, Node) \
            else node_or_range
        return self.text[a:b].decode(errors="replace")

    def code_lines(self):
        """The lines inside code blocks, where Concipio reads nothing."""
        return {n for c in self.walk({"code"}) for n in range(c.line, c.last + 1)}


@lru_cache(maxsize=1)
# Implements [CPO§D4]
def parsers():
    import tree_sitter_markdown as tsm
    from tree_sitter import Language, Parser
    return Parser(Language(tsm.language())), Parser(Language(tsm.inline_language()))


# Implements [CPO§D2]
def lines_of(ts, data=None):
    """A tree-sitter node's first and last lines. A block's range runs on
    past its last newline to where the next block's indent or quote
    markers end, so its last line is the last that holds more than
    those."""
    first = ts.start_point[0] + 1
    if data is None:
        last = ts.end_point[0] if ts.end_point[1] == 0 else ts.end_point[0] + 1
        return first, max(first, last)
    return first, last_line(data, ts.start_byte, ts.end_byte, first)


# Implements [CPO§D2]
def last_line(data, start, end, first):
    end = len(data[start:end].rstrip()) + start
    while end > start:
        head = data.rfind(b"\n", start, end) + 1
        if head > start and not data[head:end].strip(b" \t>"):
            end = len(data[start:head - 1].rstrip()) + start
            continue
        break
    return max(first, line_at(data, end - 1) if end > start else first)


_newlines = {}


# Implements [CPO§D2]
def line_at(data, offset):
    """The line holding a byte offset, counted from 1, from the offsets of
    the text's newlines, found once."""
    import bisect
    key = id(data)
    if key not in _newlines or _newlines[key][0] is not data:
        _newlines.clear()
        _newlines[key] = (data, [m.start() for m in re.finditer(rb"\n", data)])
    return bisect.bisect_left(_newlines[key][1], offset) + 1


# Implements [CPO§D2]
def node(kind, ts, data, **kw):
    first, last = lines_of(ts, data)
    return Node(kind, ts.start_byte, ts.end_byte, first, last, **kw)


HEADING_LEVEL = re.compile(rb"atx_h(\d)_marker")


# Implements [CPO§D4, CPO§D5]
def parse(text):
    """The model of a Markdown doc. Sections are built from the headings
    at the top level, whether marked with `#` or underlined, so a section
    runs from its heading to the next heading of its level or above."""
    data = text.encode() if isinstance(text, str) else text
    block, _ = parsers()
    tree = block.parse(data)
    errors = Errors()
    flat = []
    for ts in top_level(tree.root_node, errors):
        flat.append(convert(ts, data, errors))
    inlines(errors.pending, data)
    root = Node("document", 0, len(data), 1, max(1, data.count(b"\n") + (not data.endswith(b"\n"))))
    root.children = nest(flat, data)
    return Doc(data, root, list(errors))


class Errors(list):
    """The lines the grammar could not parse, and the inline text still to
    read, gathered while the blocks are."""

    def __init__(self):
        super().__init__()
        self.pending = []


# Implements [CPO§D5]
def top_level(ts, errors):
    """The blocks at the top level of the doc, with the grammar's own
    sections opened, since the model builds sections itself."""
    for c in ts.children:
        if c.type in ("section", "document"):
            yield from top_level(c, errors)
        elif c.type == "ERROR":
            errors.append(lines_of(c))
            yield from top_level(c, errors)
        else:
            yield c


# Implements [CPO§D4, CPO§D5]
def convert(ts, data, errors):
    t = ts.type
    if t == "atx_heading":
        m = next((HEADING_LEVEL.match(c.type.encode()) for c in ts.children
                  if HEADING_LEVEL.match(c.type.encode())), None)
        inner = next((c for c in ts.children if c.type == "inline"), None)
        n = node("heading", ts, data, level=int(m.group(1)) if m else 1,
                 title=data[inner.start_byte:inner.end_byte].decode(errors="replace").strip()
                 if inner else "")
        if inner:
            errors.pending.append((n, inner))
        return n
    if t == "setext_heading":
        under = next((c for c in ts.children if c.type.startswith("setext_h")), None)
        para = next((c for c in ts.children if c.type == "paragraph"), None)
        inner = next((c for c in para.children if c.type == "inline"), None) if para else None
        n = node("heading", ts, data, level=1 if under and under.type == "setext_h1_underline" else 2,
                 title=data[inner.start_byte:inner.end_byte].decode(errors="replace").strip()
                 if inner else "")
        if inner:
            errors.pending.append((n, inner))
        return n
    if t in ("fenced_code_block", "indented_code_block"):
        return node("code", ts, data)
    if t == "html_block":
        return node("html", ts, data)
    if t == "paragraph":
        n = node("paragraph", ts, data)
        for c in ts.children:
            if c.type == "inline":
                errors.pending.append((n, c))
        return n
    if t == "list":
        n = node("list", ts, data)
        n.children = [convert(c, data, errors) for c in ts.children if c.type == "list_item"]
        return n
    if t == "list_item":
        marker = next((c for c in ts.children if c.type.startswith("list_marker")), None)
        n = node("item", ts, data,
                 marker=data[marker.start_byte:marker.end_byte].decode().strip() if marker else "",
                 indent=marker.start_point[1] if marker else ts.start_point[1])
        n.children = [convert(c, data, errors) for c in ts.children
                      if c.type not in ("block_continuation",) and not c.type.startswith(
                          ("list_marker", "task_list_marker"))]
        n.children = [c for c in n.children if c is not None]
        return n
    if t == "block_quote":
        n = node("quote", ts, data)
        n.children = [x for x in (convert(c, data, errors) for c in ts.children
                                  if c.type not in ("block_quote_marker", "block_continuation"))
                      if x is not None]
        return n
    if t == "ERROR":
        errors.append(lines_of(ts))
    # Anything else, such as a thematic break or link definitions, holds
    # nothing Concipio reads.
    return node("other", ts, data)


# Implements [CPO§D5]
def nest(flat, data):
    """Sections from the top-level headings: each runs to the next heading
    of its level or above, and holds the blocks and sections between."""
    top = Node("document", 0, len(data), 1, 1)
    top.level = 0
    stack = [top]
    for b in flat:
        if b.kind == "heading":
            while stack[-1].level >= b.level:
                close(stack.pop(), b.start, data)
            s = Node("section", b.start, len(data), b.line, b.last, level=b.level,
                     title=b.title, heading=b)
            s.children.append(b)
            stack[-1].children.append(s)
            stack.append(s)
        else:
            stack[-1].children.append(b)
    while len(stack) > 1:
        close(stack.pop(), len(data), data)
    return top.children


# Implements [CPO§D5]
def close(section, end, data):
    section.end = end
    section.last = last_line(data, section.start, end, section.line)


ATTR_LIST = re.compile(rb"\{(:?[^{}\n]*)\}")


# Implements [CPO§D3]
def inlines(pending, data):
    """The code spans, links, and attribute lists of every inline text in
    a doc, from one run of the inline grammar over all their ranges, as an
    editor runs it. Text with no backtick, bracket, or brace holds none."""
    from tree_sitter import Range
    import bisect
    todo = [(n, ts) for n, ts in pending
            if any(c in data[ts.start_byte:ts.end_byte] for c in (b"`", b"[", b"{"))]
    if not todo:
        return
    todo.sort(key=lambda x: x[1].start_byte)
    starts = [ts.start_byte for _, ts in todo]

    def owner(offset):
        i = bisect.bisect_right(starts, offset) - 1
        return todo[i][0] if i >= 0 and offset < todo[i][1].end_byte else None

    _, parser = parsers()
    parser.included_ranges = [Range(ts.start_point, ts.end_point, ts.start_byte, ts.end_byte)
                              for _, ts in todo]
    try:
        tree = parser.parse(data)
    finally:
        parser.included_ranges = []
    spans = []

    def walk(t):
        if t.type == "code_span":
            spans.append((t.start_byte, t.end_byte))
            n = owner(t.start_byte)
            if n is not None:
                n.inline.append(Node("code_span", t.start_byte, t.end_byte,
                                     t.start_point[0] + 1, t.end_point[0] + 1))
            return
        if t.type in ("inline_link", "full_reference_link", "image"):
            dest = next((c for c in t.children if c.type == "link_destination"), None)
            n = owner(t.start_byte)
            if n is not None:
                n.inline.append(Node("link", t.start_byte, t.end_byte, t.start_point[0] + 1,
                                     t.end_point[0] + 1, target=(dest.start_byte, dest.end_byte)
                                     if dest else None))
        for c in t.children:
            walk(c)

    walk(tree.root_node)
    spans.sort()
    span_starts = [a for a, _ in spans]
    for n, ts in todo:
        chunk = data[ts.start_byte:ts.end_byte]
        for m in ATTR_LIST.finditer(chunk):
            a, b = ts.start_byte + m.start(), ts.start_byte + m.end()
            i = bisect.bisect_right(span_starts, a) - 1
            if i >= 0 and a < spans[i][1]:
                continue  # an attribute list in code is code [T20]
            fields = attr_fields(m.group(1).decode(errors="replace"))
            if fields is not None:
                line = ts.start_point[0] + chunk.count(b"\n", 0, m.start()) + 1
                n.inline.append(Node("attrs", a, b, line, line, fields=fields))
    for n, _ in todo:
        n.inline.sort(key=lambda x: x.start)


def attr_fields(body):
    """The fields of an attribute list's body, or None if the braces are
    prose: Python-Markdown's own parser reads it [CPO§D7, CPO§F1]."""
    from markdown.extensions.attr_list import get_attrs_and_remainder
    body = body.lstrip(":").strip()
    if "," in re.sub(r'"[^"]*"|\'[^\']*\'', "", body):
        return None
    pairs, rest = get_attrs_and_remainder(body)
    if rest.strip() or not pairs:
        return None
    fields = {}
    for k, v in pairs:
        if re.search(rf"(?<![\w.#-]){re.escape(k)}\s*=", body):
            fields[k] = v
        elif k == "." or f"#{k}" in body:
            continue
        else:
            return None
    return fields or None


# Implements [CPO§D8]
@dataclass(frozen=True)
class Splice:
    """Text to put in place of a byte range of the text a doc was parsed
    from; an empty range inserts."""
    start: int
    end: int
    text: str


class SpliceError(Exception):
    pass


# Implements [CPO§D8]
def apply(original, splices, current=None):
    """The text with the splices applied, from the end, so each range
    still means what it meant when the doc was parsed. Overlapping splices
    are refused, as two inserts at one place are, since their order would
    be a guess; so is a file whose text changed since it was parsed."""
    if current is not None and current != original:
        raise SpliceError("the doc changed since it was read; read it again")
    ordered = sorted(splices, key=lambda s: (s.start, s.end))
    for a, b in zip(ordered, ordered[1:]):
        if b.start < a.end or b.start == a.start:
            raise SpliceError(f"splices overlap at bytes {a.start}-{a.end} and {b.start}-{b.end}")
    out = original
    for s in reversed(ordered):
        if not 0 <= s.start <= s.end <= len(original):
            raise SpliceError(f"splice {s.start}-{s.end} lies outside the doc")
        out = out[:s.start] + s.text.encode() + out[s.end:]
    return out


# Implements [CPO§D8]
def write(path, doc, splices):
    """Apply splices to a doc's file, refusing if it changed since it was
    read."""
    from pathlib import Path
    path = Path(path)
    path.write_bytes(apply(doc.text, splices, path.read_bytes()))


# Implements [CPO§D9]
def quote(value):
    if '"' in value or "\n" in value:
        raise SpliceError(f"a field's value cannot hold a quote or a line break: {value!r}")
    return f'"{value}"'


# Implements [CPO§D7, CPO§D9]
def own_attrs(doc, n):
    """The attribute list that holds an element's fields: a heading's own,
    or one alone on the line under it; an item's, in its first paragraph;
    a paragraph's own."""
    if n.kind == "section":
        n = n.heading
    if n.kind == "heading":
        found = [a for a in n.inline if a.kind == "attrs"]
        if found:
            return found[0]
        after = next_block(doc, n)
        if after is not None and after.kind == "paragraph" and after.line == n.last + 1:
            body = doc.slice(after).strip()
            only = [a for a in after.inline if a.kind == "attrs"]
            if len(only) == 1 and doc.slice(only[0]).strip() == body:
                return only[0]
        return None
    if n.kind == "item":
        para = next((c for c in n.children if c.kind == "paragraph"), None)
        n = para if para is not None else n
    found = [a for a in n.inline if a.kind == "attrs"]
    return found[0] if found else None


# Implements [CPO§D9]
def next_block(doc, n):
    """The block after a heading in its section."""
    for s in doc.walk({"section"}):
        if s.heading is n:
            rest = s.children[1:]
            return rest[0] if rest else None
    return None


FIELD_AT = r"(?<![\w.#-]){key}\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s}}]+)"


# Implements [CPO§D9]
def set_field(doc, n, key, value):
    """A splice that sets one field of an element: its value alone if the
    field is there, else the field added to the element's attribute list,
    else a new attribute list where it belongs: on the line under a
    heading, or at the end of a paragraph or an item's first paragraph."""
    value = quote(value)
    attrs = own_attrs(doc, n)
    if attrs is not None:
        text = doc.text[attrs.start:attrs.end].decode()
        m = re.search(FIELD_AT.format(key=re.escape(key)), text)
        if m:
            return Splice(attrs.start + m.start(1), attrs.start + m.end(1), value)
        return Splice(attrs.end - 1, attrs.end - 1, f" {key}={value}")
    if n.kind == "section":
        n = n.heading
    if n.kind == "heading":
        # After the heading's last line, which for an underlined heading is
        # its underline.
        at = line_end(doc.text, line_start(doc.text, n.last))
        return Splice(at, at, f"\n{{{key}={value}}}")
    if n.kind == "item":
        para = next((c for c in n.children if c.kind == "paragraph"), None)
        if para is None:
            raise SpliceError("an item with no paragraph has no place for a field")
        n = para
    end = len(doc.text[:n.end].rstrip()) if n.end else n.end
    end = max(end, n.start)
    return Splice(end, end, f" {{{key}={value}}}")


# Implements [CPO§D9]
def line_end(data, at):
    """The offset of the newline ending the line that holds `at`, or the
    end of the text."""
    i = data.find(b"\n", at)
    return len(data) if i < 0 else i


# Implements [CPO§D9]
def block_end(doc, n):
    """Where text placed after a block goes: the end of its last line that
    holds more than blank space or continuation markers."""
    return line_end(doc.text, line_start(doc.text, n.last))


# Implements [CPO§D9]
def line_start(data, line):
    at = 0
    for _ in range(line - 1):
        at = data.index(b"\n", at) + 1
    return at


# Implements [CPO§D9]
def add_item(doc, parent, text, marker=None):
    """A splice adding a list item: at the end of a list, as its last item,
    or under an item, as the last of its nested items, with the marker and
    indent of its siblings. Lines after the first are indented to the
    item's text."""
    if parent.kind == "list":
        sibling = parent.children[-1]
        indent, mark, after = sibling.indent, marker or sibling.marker, parent
    elif parent.kind == "item":
        nested = next((c for c in reversed(parent.children) if c.kind == "list"), None)
        if nested is not None:
            return add_item(doc, nested, text, marker)
        indent = parent.indent + len(parent.marker) + 1
        mark, after = marker or parent.marker, parent
    else:
        raise SpliceError(f"an item goes under a list or an item, not a {parent.kind}")
    lines = text.splitlines() or [""]
    pad = " " * (indent + len(mark) + 1)
    body = f"{' ' * indent}{mark} {lines[0]}" + "".join(
        f"\n{pad}{l}" if l.strip() else "\n" for l in lines[1:])
    at = block_end(doc, after)
    return Splice(at, at, "\n" + body)


# Implements [CPO§D9]
def add_section(doc, parent, title, body=""):
    """A splice adding a section at the end of another, one level below
    it, or at the end of the doc when the parent is the doc itself."""
    level = parent.level + 1 if parent.kind == "section" else 1
    end = parent.end if parent.kind == "section" else len(doc.text)
    before = doc.text[:end]
    lead = "" if before.endswith(b"\n\n") or not before else (
        "\n" if before.endswith(b"\n") else "\n\n")
    text = f"{lead}{'#' * level} {title}\n" + (f"\n{body.rstrip()}\n" if body else "")
    if end < len(doc.text):
        text += "\n"
    return Splice(end, end, text)


# Implements [CPO§D9]
def set_link(doc, link, target):
    """A splice changing a link's target."""
    if link.kind != "link" or link.target is None:
        raise SpliceError("only a link with a target can be retargeted")
    return Splice(link.target[0], link.target[1], target)
