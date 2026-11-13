"""Find tag definitions and citations in a repository."""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PREFIX = r"[^\s\[\]§*`()'\",;:]+"
ID = r"[A-Z]*\d+(?:\.[a-z0-9]+)?"
TAG = re.compile(rf"({PREFIX})§({ID})")

# Implements [CPO§T4]
DEFINITION = re.compile(
    rf"^(?P<indent>\s*)(?P<marker>(?:[-*]|\d+\.)\s+)?"
    rf"\*\*(?P<prefix>{PREFIX})§(?P<id>{ID})(?::\*\*|\*\*:)\s*(?P<rest>.*)$"
)
TITLE = re.compile(r"^\*\*(.+?)\*\*")
SHORT_LIST = re.compile(rf"\[({ID}(?:,\s*{ID})*)\]")
# Implements [CPO§T6], and a numbered design's own form, "Implements §5a".
ROLE_WORD = re.compile(r"\b(Implements|Tests)\s*\[?$")


@dataclass
class Definition:
    tag: str
    path: str
    line: int
    text: str
    name: str
    lines: int = 1
    heading: bool = False
    fields: dict = field(default_factory=dict)
    parent: str | None = None
    children: list = field(default_factory=list)
    citations: list = field(default_factory=list)


@dataclass
class Citation:
    path: str
    line: int
    role: str
    text: str
    col: int = 0
    end: int = 0


def repo_root(start="."):
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start, capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip())


# Concipio's own files mention tags by the hundred, as the subjects of
# their records, and never cite them.
OWN_FILES = (".cpo", ".cpo-baseline.toml")


# Markdown in its common spellings, MDX included, as documentation sites
# such as Mintlify and Docusaurus write it [T67].
DOC_EXTENSIONS = (".md", ".mdx", ".markdown")


# Implements [CPO§T67]
def is_doc(path):
    """Whether a file is Markdown, which Concipio reads as a doc."""
    return str(path).endswith(DOC_EXTENSIONS)


# Instructions for agents, which are neither design nor code [CPO§T71].
AGENT_FILES = ["CLAUDE.md", "*/CLAUDE.md", "AGENTS.md", "*/AGENTS.md", "GEMINI.md",
               ".claude/*", ".cursor/*", ".github/*"]


def tracked_files(root):
    """The files git tracks or would, as they stand on disk: a tracked file
    deleted but not yet committed is gone, and a submodule is not a file.
    Instructions for agents are left out, unless `.cpo` names its own."""
    import fnmatch
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, text=True, check=True,
    )
    skip = config(root).get("agent_files", AGENT_FILES)
    return [p for p in out.stdout.split("\0") if p and p.rsplit("/", 1)[-1] not in OWN_FILES
            and (Path(root) / p).is_file() and not any(fnmatch.fnmatch(p, g) for g in skip)]


# Implements [CPO§T72]
def site_pages(root, files):
    """The pages a documentation site's navigation lists, which readers
    reach through the site rather than through links: Mintlify's
    `docs.json` and `mint.json`, whose pages are named without their
    extensions, relative to the file."""
    import json
    out = set()
    docs_in = {f for f in files if is_doc(f)}
    for f in files:
        if Path(f).name not in ("docs.json", "mint.json"):
            continue
        try:
            nav = json.loads((Path(root) / f).read_text()).get("navigation")
        except (ValueError, OSError, AttributeError):
            continue
        base = str(Path(f).parent)

        def walk(x):
            if isinstance(x, str):
                for ext in DOC_EXTENSIONS:
                    page = str(Path(base) / (x.lstrip("/") + ext)) if base != "." else \
                        x.lstrip("/") + ext
                    if page in docs_in:
                        out.add(page)
            elif isinstance(x, list):
                for y in x:
                    walk(y)
            elif isinstance(x, dict):
                for y in x.values():
                    walk(y)
        walk(nav)
    return out


# Implements [CPO§T20]
def prose_lines(text):
    """Yield (line number, line) for Markdown outside code, with inline
    code spans blanked so tags inside them are ignored."""
    fence = None
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = None
            yield n, ""
            continue
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            yield n, ""
            continue
        yield n, re.sub(r"`[^`]*`", lambda m: " " * len(m.group(0)), line)


# Implements [CPO§T4]
ATTR_LIST = re.compile(r"\{(:?[^{}\n]*)\}")
CPO_FENCE = re.compile(r"^\s*(```|~~~)cpo\s*$")


# Implements [CPO§F1]
def attribute_fields(line):
    """The key=value pairs of the Markdown attribute lists on a line, as
    Pandoc, kramdown, and Python-Markdown write them: `{Owner=Josh}` or
    `{: Owner="Josh V" Updated=2026-11-03}`. Braces that do not parse
    wholly as an attribute list are prose, and are left alone. Return the
    fields and the line with its attribute lists removed."""
    from markdown.extensions.attr_list import get_attrs_and_remainder
    found = {}
    kept = line
    # Fields are never read from inline code [T20].
    visible = re.sub(r"`[^`]*`", lambda c: " " * len(c.group(0)), line)
    for m in ATTR_LIST.finditer(visible):
        body = m.group(1).lstrip(":").strip()
        # Attribute lists separate pairs with spaces; a comma outside quotes
        # means prose, such as the set {N=32, N=1}.
        if "," in re.sub(r'"[^"]*"|\'[^\']*\'', "", body):
            continue
        pairs, rest = get_attrs_and_remainder(body)
        if rest.strip() or not pairs:
            continue
        fields, words = {}, False
        for k, v in pairs:
            if re.search(rf"(?<![\w.#-]){re.escape(k)}\s*=", body):
                fields[k] = v
            elif k == "." or f"#{k}" in body:
                continue  # a class or an id, which attribute lists also carry
            else:
                words = True
        if words or not fields:
            continue
        found.update(fields)
        kept = kept.replace(line[m.start():m.end()], "", 1)
    return found, kept


def pattern_fields(pattern, line):
    """A project's own field syntax, as a pattern with `key` and `value`
    groups [F13]."""
    found = {m["key"]: m["value"].strip() for m in pattern.finditer(line)}
    return found, pattern.sub("", line) if found else line


def statement_fields(lines, pattern=None):
    """The fields of a statement's lines: inline fields, and TOML in fenced
    blocks tagged `cpo` [F14]. Return the fields and the lines without
    them."""
    import tomllib
    fields, kept, block, other = {}, [], None, None
    for line in lines:
        if block is not None:
            if line.strip().startswith(("```", "~~~")):
                try:
                    fields.update(tomllib.loads("\n".join(block)))
                except tomllib.TOMLDecodeError as e:
                    fields.setdefault("__errors__", []).append(f"cpo block: {e}")
                block = None
            else:
                block.append(line.strip())
            continue
        if CPO_FENCE.match(line):
            block = []
            continue
        if other is not None:
            if line.strip().startswith(other):
                other = None
            kept.append(line)
            continue
        if line.strip().startswith(("```", "~~~")):
            other = line.strip()[:3]  # an ordinary code block: an example
            kept.append(line)
            continue
        found, line = pattern_fields(pattern, line) if pattern else attribute_fields(line)
        fields.update(found)
        kept.append(line)
    return fields, kept


def statement_extent(lines, start, indent, is_item):
    """Return the lines of the statement that begins at index `start`: its
    paragraph, or its list item up to the first nested definition, which
    begins a child statement."""
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if is_item and DEFINITION.match(line):
            break
        if not line.strip():
            if not is_item:
                break
            end += 1
            continue
        if line.lstrip().startswith("#"):
            break
        line_indent = len(line) - len(line.lstrip())
        if is_item and line_indent <= indent:
            break
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


# Implements [CPO§T37]
def statement_name(rest, text):
    title = TITLE.match(rest)
    if title:
        return title.group(1).rstrip(".")
    sentence = re.split(r"(?<=[^\d\s][.!?])\s", text, maxsplit=1)[0]
    return sentence if len(sentence) <= 90 else sentence[:87].rstrip() + "..."


def field_pattern(root):
    """A project's own field syntax from `.cpo`, or None for attribute
    lists [F13]."""
    pattern = config(root).get("fields", {}).get("pattern")
    return re.compile(pattern) if pattern else None


def find_definitions(root, files, pattern=None):
    defs = {}
    errors = []
    for path in files:
        if not is_doc(path):
            continue
        raw = (root / path).read_text(errors="replace").splitlines()
        prose = [line for _, line in prose_lines("\n".join(raw))]
        open_items = []  # (indent, tag) of enclosing list-item definitions
        for i, line in enumerate(prose):
            m = DEFINITION.match(line)
            if not m:
                if line.strip() and not line.startswith((" ", "\t")):
                    open_items.clear()
                continue
            tag = f"{m['prefix']}§{m['id']}"
            body = statement_extent(raw, i, len(m["indent"]), bool(m["marker"]))
            fields, kept = statement_fields(body, pattern)
            text = " ".join(l.strip() for l in kept if l.strip())
            text = re.sub(r"^(?:[-*]|\d+\.)\s+", "", text)
            after_tag = DEFINITION.match(kept[0] if kept else raw[i])
            rest = after_tag["rest"] if after_tag else m["rest"]
            text = re.sub(r"^\*\*[^*]+\*\*:?\s*", "", text)
            d = Definition(tag, path, i + 1, text, statement_name(rest, text),
                           lines=len(body), fields=fields)
            # Implements [CPO§T38]
            indent = len(m["indent"])
            while open_items and open_items[-1][0] >= indent:
                open_items.pop()
            if m["marker"]:
                if open_items:
                    d.parent = open_items[-1][1]
                open_items.append((indent, tag))
            else:
                open_items.clear()
            if tag in defs:
                errors.append(f"{tag} is defined twice: {defs[tag].path}:"
                              f"{defs[tag].line} and {path}:{i + 1}")
            else:
                defs[tag] = d
    for d in defs.values():
        if d.parent in defs:
            defs[d.parent].children.append(d.tag)
    return defs, errors


def role_before(line, start):
    m = ROLE_WORD.search(line[:start + 1])
    return {"Implements": "implementation", "Tests": "test"}.get(
        m.group(1) if m else "", "reference")


def find_citations(root, files, defs):
    defined_prefixes = {}
    for d in defs.values():
        defined_prefixes.setdefault(d.path, set()).add(d.tag.split("§")[0])
    for path in files:
        try:
            text = (root / path).read_text()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        doc = is_doc(path)
        lines = prose_lines(text) if doc else enumerate(text.splitlines(), 1)
        prefixes = defined_prefixes.get(path, set())
        # Implements [CPO§T7]
        short_prefix = next(iter(prefixes)) if len(prefixes) == 1 else None
        for n, line in lines:
            if DEFINITION.match(line):
                line = DEFINITION.sub(lambda m: m["indent"] + (m["rest"] or ""), line)
            for m in TAG.finditer(line):
                tag = m.group(0)
                if tag in defs:
                    role = role_before(line, m.start() - 1)
                    defs[tag].citations.append(
                        Citation(path, n, role, line.strip(), m.start(), m.end()))
                elif not line[m.end():m.end() + 1] == "@":
                    # A tag pinned to another repository's release is that
                    # repository's to check [T30]. A numbered section's ID
                    # runs on past the digits, as `DESIGN§5c` does; the
                    # source reader counts such a citation when it resolves.
                    full = re.match(SECTION_ID, line[m.start(2):])
                    full = f"{m.group(1)}§{full.group(0)}" if full else tag
                    if full not in defs:
                        unresolved(defs, path, n, full)
            if doc and short_prefix:
                for m in SHORT_LIST.finditer(line):
                    # A list of plain numbers cites tags only if each is one;
                    # otherwise, as `[1, 64]`, it is a range, and cites nothing.
                    if re.fullmatch(r"[\d,\s]+", m.group(1)) and not all(
                            f"{short_prefix}§{x}" in defs for x in re.findall(r"\d+", m.group(1))):
                        continue
                    for im in re.finditer(ID, m.group(1)):
                        tag = f"{short_prefix}§{im.group(0)}"
                        if tag in defs:
                            col = m.start(1) + im.start()
                            defs[tag].citations.append(Citation(
                                path, n, "reference", line.strip(), col,
                                col + len(im.group(0))))
                        else:
                            unresolved(defs, path, n, tag)


HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# A section number as people write them: 5, 5.2, 5a, 5d.1, 5a‴, 5a′.1, 4a-A,
# after an optional § in the heading itself.
SECTION_ID = r"\d+(?:\.\d+)*(?:[a-z][′″‴]*(?:\.\d+)*)?[′″‴]*(?:-[A-Z])?"
# A heading that starts with something like a section number, which a
# source's own pattern may still fail to read [T60].
LOOKS_NUMBERED = re.compile(r"^(#{2,6})\s+§?(\d+[\w.′″‴-]*?)\.?\s")
NUMBERED = re.compile(rf"^#{{1,6}}\s+§?(?P<id>{SECTION_ID})\.?\s")
BARE_SECTION = re.compile(rf"§\s*(?P<id>{SECTION_ID})")


# Implements [CPO§T41]
def numbered_headings(text):
    """A doc's numbered sections, {number: line}, found in any Markdown doc
    without configuration."""
    out = {}
    for n, line in prose_lines(text):
        m = NUMBERED.match(line)
        if m and m["id"] not in out:
            out[m["id"]] = n
    return out


def config_path(root):
    """Where the project's `.cpo` is: in the repository, or for a repository
    that has not adopted Concipio, in its store [T17]. Finding it never
    creates the store."""
    from .store import data_home, project_id
    paths = [Path(root) / ".cpo"]
    try:
        paths.append(data_home() / "concipio" / project_id(root) / "cpo.toml")
    except subprocess.CalledProcessError:
        pass
    return next((p for p in paths if p.exists()), None)


def config(root):
    import tomllib
    p = config_path(root)
    return tomllib.loads(p.read_text()) if p else {}


# Implements [CPO§T39]
def sources(root):
    """Docs whose numbered headings are definitions, as `.cpo` declares
    them: each with its prefix, its heading pattern, and the pattern of its
    citations elsewhere."""
    out = []
    for src in config(root).get("source", []):
        d = source_defaults(src["doc"])
        out.append({"doc": src["doc"], "prefix": src.get("prefix", d["prefix"]),
                    "heading": re.compile(src.get("heading", d["heading"])),
                    "cite": re.compile(src.get("cite", source_defaults(
                        src["doc"], src.get("prefix", d["prefix"]))["cite"])),
                    # Whether a bare §5c in a code comment means this doc's.
                    "code_default": bool(src.get("bare_in_code"))})
    return out


# Implements [CPO§T69]
def source_defaults(doc, prefix=None):
    """What a source in `.cpo` need not say: its prefix, the doc's name in
    capitals; its headings, any numbered heading Concipio recognises, as
    `## 5.`, `### 5d.1`, or `#### §5a′`; and its citations, the prefix or
    the doc's name, then a section sign and a number."""
    stem = Path(doc).stem
    prefix = prefix or re.sub(r"\W", "_", stem).upper()
    names = "|".join(sorted({re.escape(prefix), re.escape(stem)}))
    return {"prefix": prefix,
            "heading": rf"^#{{2,6}}\s+§?(?P<id>{SECTION_ID})\.?\s",
            "cite": rf"(?:{names})(?:\.(?:md|mdx|markdown))?\s*§\s*(?P<id>{SECTION_ID})"}


def heading_definitions(root, src, defs, errors, pattern=None):
    path = src["doc"]
    try:
        text = (Path(root) / path).read_text(errors="replace")
    except FileNotFoundError:
        errors.append(f"{path}, declared in .cpo, does not exist")
        return
    raw = text.splitlines()
    prose = [line for _, line in prose_lines(text)]
    heads = [(i, len(m[1]), m[2]) for i, line in enumerate(prose) if (m := HEADING.match(line))]
    stack = []
    for k, (i, level, title) in enumerate(heads):
        while stack and stack[-1][0] >= level:
            stack.pop()
        m = src["heading"].match(raw[i])
        if not m:
            continue
        tag = f"{src['prefix']}§{m['id']}"
        end = heads[k + 1][0] if k + 1 < len(heads) else len(raw)
        fields, kept = statement_fields(raw[i:end], pattern)
        heading_line = kept[0] if kept else raw[i]
        body = [l for l in kept[1:] if l.strip()]
        name = re.sub(r"^#+\s*§?" + re.escape(m["id"]) + r"\.?\s*", "", heading_line).strip()
        # Drop the italic notes on dates and status that headings carry,
        # including ones that wrap onto the next line.
        name = re.split(r"\s+(?:—\s*)?\*\(|\s+—\s+\*|\s+\(\*", name)[0].strip() or name
        d = Definition(tag, path, i + 1, " ".join(l.strip() for l in body), name,
                       lines=len(body), heading=True, fields=fields)
        # A section's number names its parent, as 5c.1's is 5c and 1a's
        # is 1, whatever its heading's level; heading nesting decides only
        # where the number does not [T39].
        above = numbered_parent(m["id"])
        if above and f"{src['prefix']}§{above}" in defs:
            d.parent = f"{src['prefix']}§{above}"
        elif stack:
            d.parent = stack[-1][1]
        if tag in defs:
            errors.append(f"{tag} is defined twice: {defs[tag].path}:{defs[tag].line} "
                          f"and {path}:{i + 1}")
        else:
            defs[tag] = d
        stack.append((level, tag))


def numbered_parent(ident):
    """The section a number belongs under: 5c for 5c.1, 4a for 4a-A, and 1
    for 1a or 5 for 5a′, or None for a top-level number. A primed number
    such as 5a′ stands beside 5a, not under it."""
    for pattern in (r"^(.+)\.\d+$", r"^(.+)-[A-Z]$", r"^(\d+(?:\.\d+)*)[a-z][′″‴]*$"):
        m = re.match(pattern, ident)
        if m:
            return m.group(1)
    return None


FILE_DEFAULT = re.compile(r"cpo-default:\s*([^\s*/>]+)")


def file_default(text, srcs):
    """The source a code file names as what its bare section numbers mean,
    with a `cpo-default: DESIGN` comment in its first lines [T44]."""
    for line in text.splitlines()[:30]:
        m = FILE_DEFAULT.search(line)
        if m:
            return next((s for s in srcs if m.group(1) in (s["prefix"], s["doc"])), None)
    return None


# Implements [CPO§T62]
def names_a_doc_in_code(before, names):
    """Whether a comment names a doc just before a bare section number, as
    in `notes.md §10` or `ERRATA §3`: a path, a Markdown
    file, a declared prefix, or the name of one of the project's docs. In
    code a capitalized word proves nothing, since comments shout."""
    words = before.replace("*/", " ").replace("/*", " ").replace("*", " ") \
        .replace("//", " ").replace("#", " ").split()
    if not words:
        return False
    word = words[-1].strip("([,;:`'\"")
    # A version number names another document, as `TPC-C 5.11 §3.3.2` does a
    # specification's section.
    return bool(word) and (bool(re.search(r"\w/\w", word)) or is_doc(word)
                           or word in names or bool(re.fullmatch(r"v?\d+(\.\d+)+", word)))


def source_citations(root, files, defs, srcs):
    # The words that name a doc: each source's prefix, and each doc's name.
    names = {src["prefix"] for src in srcs} | {
        Path(f).stem for f in files if is_doc(f)} | {
        Path(f).name for f in files if is_doc(f)}
    for path in files:
        try:
            text = (Path(root) / path).read_text()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        named = file_default(text, srcs) if not is_doc(path) else None
        lines = list(prose_lines(text)) if is_doc(path) else \
            list(enumerate(text.splitlines(), 1))
        prev = ""
        for n, line in lines:
            # A bare number belongs to the nearest doc named before it on the
            # line: another doc's, as in `notes.md §6, §11c`, until a source's
            # own citation, as `DESIGN §15`, hands what follows back to it.
            foreign_at = []
            cited = [(m.start(), m.end()) for x in srcs for m in x["cite"].finditer(line)]
            cited_by = sorted((m.start(), x) for x in srcs for m in x["cite"].finditer(line))
            cited_at = [a for a, _ in cited]
            # A bare number that opens a line may have wrapped away from the
            # doc name ending the line before.
            def foreign(m, line=line, prev=prev):
                before = line[:m.start()]
                if not before.replace("*", "").replace("/", "").replace("#", "").strip():
                    before = prev
                return names_a_doc_in_code(before, names)
            for src in srcs:
                patterns = [src["cite"]]
                # In code, a bare §5c means the doc the file names, or else
                # the one the project names [T44].
                if not is_doc(path) and (
                        src is named or (named is None and src["code_default"])):
                    patterns.append(BARE_SECTION)
                # Inside its own doc, a bare §5c means that doc's §5c.
                if path == src["doc"]:
                    if src["heading"].match(line):
                        continue  # a heading defines its section, not cites it
                    patterns.append(BARE_SECTION)
                seen = set()
                for pattern in patterns:
                    for m in pattern.finditer(line):
                        owner = src
                        # In code, a number after another doc's name is that
                        # doc's, and not the default's [T62].
                        if pattern is BARE_SECTION and not is_doc(path):
                            if any(a <= m.start() < b for a, b in cited):
                                continue  # part of a source's own citation, `DESIGN §5`
                            if foreign(m):
                                foreign_at.append(m.start())
                                continue
                            f = max((x for x in foreign_at if x < m.start()), default=None)
                            c = max((x for x in cited_by if x[0] < m.start()),
                                    default=None, key=lambda x: x[0])
                            if f is not None and (c is None or f > c[0]):
                                continue
                            # After a source's own citation, a bare number
                            # is that source's, as `§16` in `DESIGN §15, §16`
                            # [T75].
                            if c is not None:
                                owner = c[1]
                        tag = f"{owner['prefix']}§{m['id']}"
                        # The § inside a full tag, `X§7`, is the tag's, not a
                        # bare section number.
                        if pattern is BARE_SECTION and m.start() > 0 and \
                                (line[m.start() - 1].isalnum() or line[m.start() - 1] == "_"):
                            continue
                        if tag in defs and m.end() not in seen:
                            seen.add(m.end())
                            defs[tag].citations.append(Citation(
                                path, n, role_before(line, m.start() - 1), line.strip(),
                                m.start(), m.end()))
                        elif tag not in defs and not (pattern is BARE_SECTION and
                                                      path == src["doc"]):
                            # A source's own bare numbers are dangling-section's.
                            unresolved(defs, path, n, tag, bare=pattern is BARE_SECTION)
            prev = line


def doc_fields(text, pattern=None):
    """Fields that describe a whole doc: attribute lists between its title
    and its first section, or in its front matter [F2]."""
    lines = text.splitlines()
    fields = {}
    if lines and lines[0].strip() == "---":
        import tomllib
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
        if end:
            for l in lines[1:end]:
                k, _, v = l.partition(":")
                if k.strip() and v.strip():
                    fields[k.strip()] = v.strip().strip('"')
            lines = lines[end + 1:]
    opening = []
    for l in lines:
        if l.startswith("## "):
            break
        if not l.startswith("# "):
            opening.append(l)
    found, _ = statement_fields(opening, pattern)
    fields.update(found)
    return fields


# Implements [CPO§T49]
def archived(root, files):
    """The files `.cpo` archives: kept verbatim, and read for nothing."""
    import fnmatch
    globs = config(root).get("archive", [])
    return {f for f in files if any(fnmatch.fnmatch(f, g) for g in globs)}


class Defs(dict):
    """The definitions, by tag, and the citations of tags no doc defines."""
    def __init__(self, *args):
        super().__init__(*args)
        self.unresolved = []


def unresolved(defs, path, line, tag, bare=False):
    """Note a citation of a tag no doc defines; `bare` when it was a bare
    section number that might belong to another doc."""
    if isinstance(defs, Defs):
        defs.unresolved.append((path, line, tag, bare))


def load(start=".", root=None, files=None):
    root = root or repo_root(start)
    files = files if files is not None else tracked_files(root)
    old = archived(root, files)
    files = [f for f in files if f not in old]
    pattern = field_pattern(root)
    found, errors = find_definitions(root, files, pattern)
    defs = Defs(found)
    srcs = sources(root)
    for src in srcs:
        heading_definitions(root, src, defs, errors, pattern)
    for d in defs.values():
        if d.parent in defs and d.tag not in defs[d.parent].children:
            defs[d.parent].children.append(d.tag)
    find_citations(root, files, defs)
    if srcs:
        source_citations(root, files, defs, srcs)
    return root, defs, errors


def sort_key(tag):
    prefix, ident = tag.split("§", 1)
    m = re.match(r"([A-Z]*)(\d+)", ident)
    return (prefix, m.group(1), int(m.group(2)), ident)


def resolve(query, defs):
    """Accept a full tag, or an ID that one prefix in the repository
    defines."""
    if query in defs:
        return [query]
    if "§" in query:
        return []
    return [t for t in defs if t.split("§", 1)[1] == query]
