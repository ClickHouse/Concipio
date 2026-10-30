"""Find tag definitions and citations in a repository."""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PREFIX = r"[^\s\[\]§*`]+"
ID = r"[A-Z]*\d+(?:\.[a-z0-9]+)?"
TAG = re.compile(rf"({PREFIX})§({ID})")

# Implements [CPO§T4]
DEFINITION = re.compile(
    rf"^(?P<indent>\s*)(?P<marker>(?:[-*]|\d+\.)\s+)?"
    rf"\*\*(?P<prefix>{PREFIX})§(?P<id>{ID})(?::\*\*|\*\*:)\s*(?P<rest>.*)$"
)
TITLE = re.compile(r"^\*\*(.+?)\*\*")
SHORT_LIST = re.compile(rf"\[({ID}(?:,\s*{ID})*)\]")
ROLE_WORD = re.compile(r"\b(Implements|Tests)\s*\[$")


@dataclass
class Definition:
    tag: str
    path: str
    line: int
    text: str
    name: str
    lines: int = 1
    parent: str | None = None
    children: list = field(default_factory=list)
    citations: list = field(default_factory=list)


@dataclass
class Citation:
    path: str
    line: int
    role: str
    text: str


def repo_root(start="."):
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start, capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip())


def tracked_files(root):
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, text=True, check=True,
    )
    return [p for p in out.stdout.split("\0") if p]


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


def find_definitions(root, files):
    defs = {}
    errors = []
    for path in files:
        if not path.endswith(".md"):
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
            text = " ".join(l.strip() for l in body if l.strip())
            text = re.sub(r"^(?:[-*]|\d+\.)\s+", "", text)
            after_tag = DEFINITION.match(raw[i])
            rest = after_tag["rest"] if after_tag else m["rest"]
            text = re.sub(r"^\*\*[^*]+\*\*:?\s*", "", text)
            d = Definition(tag, path, i + 1, text, statement_name(rest, text),
                           lines=len(body))
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
        is_doc = path.endswith(".md")
        lines = prose_lines(text) if is_doc else enumerate(text.splitlines(), 1)
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
                        Citation(path, n, role, line.strip()))
            if is_doc and short_prefix:
                for m in SHORT_LIST.finditer(line):
                    for ident in re.split(r",\s*", m.group(1)):
                        tag = f"{short_prefix}§{ident}"
                        if tag in defs:
                            defs[tag].citations.append(
                                Citation(path, n, "reference", line.strip()))


def load(start="."):
    root = repo_root(start)
    files = tracked_files(root)
    defs, errors = find_definitions(root, files)
    find_citations(root, files, defs)
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
