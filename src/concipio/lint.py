"""Check that every design fits on a screen, reaches the master, and
claims no more code than a reader can hold."""

import fnmatch
import posixpath
import re
from dataclasses import dataclass

from . import docs, spans as spans_mod

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
LINK_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s")
STATEMENT_LIMIT = 20
SECTION_LIMIT = 60
BREADTH_LIMIT = 200
LINK = re.compile(r"\]\(\s*<?([^)>\s]+)>?[^)]*\)|^\s{0,3}\[[^\]]+\]:\s*<?([^>\s]+)>?", re.M)


@dataclass
class Problem:
    path: str
    line: int
    rule: str
    message: str
    key: str = ""
    value: int = 0


def sections(text):
    """Yield (line, level, title, own_lines) for each section, where
    own_lines counts the section's text up to the next heading of any
    level, so subsections are measured on their own. Text before the first
    heading is a section of level 0."""
    lines = [line for _, line in docs.prose_lines(text)]
    raw = text.splitlines()
    marks = [(i, len(m[1]), m[2]) for i, line in enumerate(lines)
             if (m := HEADING.match(line))]
    starts = [(-1, 0, "(top)")] + marks
    for k, (i, level, title) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(raw)
        # Link reference definitions never render, so they take no room.
        body = [l for l in raw[i + 1:end] if not LINK_DEF.match(l)]
        while body and not body[-1].strip():
            body.pop()
        while body and not body[0].strip():
            body.pop(0)
        if i >= 0 or body:
            yield i + 1, level, title, len(body)


# Implements [CPO§M41]
def lint(root, files, defs, statement_limit=STATEMENT_LIMIT, section_limit=SECTION_LIMIT):
    problems = []
    for d in defs.values():
        # A numbered heading defines its whole section; the section rule
        # measures it instead.
        if d.lines > statement_limit and not d.heading:
            problems.append(Problem(
                d.path, d.line, "statement-length",
                f"{d.tag} ({d.name}) is {d.lines} lines; split it into nested "
                f"statements of at most {statement_limit}", d.tag, d.lines))
    designs = {d.path for d in defs.values()}
    for path in files:
        # A doc that defines no statements is not a design: notes, reports,
        # and records of consultations are free to run long.
        if not path.endswith(".md") or path not in designs:
            continue
        text = (root / path).read_text(errors="replace")
        for line, level, title, n in sections(text):
            if n > section_limit:
                problems.append(Problem(
                    path, line, "section-length",
                    f'section "{title}" has {n} lines of its own; split it into '
                    f"subsections or a child doc of at most {section_limit}", title, n))
    return sorted(problems, key=lambda p: (p.path, p.line))


def links_of(path, text):
    """The Markdown files a doc links to, resolved against its directory.
    A link to a directory reaches the docs directly inside it."""
    out = set()
    for m in LINK.finditer(text):
        target = (m.group(1) or m.group(2) or "").split("#", 1)[0]
        if not target or re.match(r"^[a-z]+:", target):
            continue
        out.add(posixpath.normpath(posixpath.join(posixpath.dirname(path), target)))
    return out


# Implements [CPO§M24]
def orphans(root, files, defs, master="README.md", postponed=()):
    """Docs no chain of links reaches from the master, following Markdown
    links between docs and citations of tags, in either direction. Return
    (orphans, postponed orphans)."""
    md = [f for f in files if f.endswith(".md")]
    known = set(md)
    edges = {f: set() for f in md}

    def join(a, b):
        if a in known and b in known and a != b:
            edges[a].add(b)
            edges[b].add(a)

    dirs = {}
    for f in md:
        dirs.setdefault(posixpath.dirname(f), []).append(f)
    for f in md:
        text = (root / f).read_text(errors="replace")
        for target in links_of(f, text):
            if target in known:
                join(f, target)
            for g in dirs.get(target.rstrip("/"), []):
                join(f, g)
    for d in defs.values():
        for c in d.citations:
            join(c.path, d.path)
    seen, todo = {master}, [master]
    while todo:
        for g in edges.get(todo.pop(), ()):
            if g not in seen:
                seen.add(g)
                todo.append(g)
    lost = sorted(f for f in md if f not in seen)
    later = [f for f in lost if any(fnmatch.fnmatch(f, p) for p in postponed)]
    return [f for f in lost if f not in later], later


def covered_node(decls, line):
    """The declaration a citation on this line documents: the innermost one
    around it, or the one that starts just below it, as a comment above a
    function documents that function [T8]."""
    inside = [d for d in decls if d[0] <= line <= d[1] and not d[2].endswith("scope")]
    if inside:
        return min(inside, key=lambda d: d[1] - d[0])
    below = [d for d in decls if line < d[0] <= line + 3 and not d[2].endswith("scope")]
    return min(below, key=lambda d: d[0]) if below else None


def breadth(root, defs):
    """For each statement, the code its citations claim: the declarations
    they document, deduplicated, with tests counted apart."""
    cache = {}
    out = {}
    for d in defs.values():
        impl, tests, nodes = 0, 0, set()
        for c in d.citations:
            if c.path.endswith(".md"):
                continue
            if c.path not in cache:
                try:
                    text = (root / c.path).read_text(errors="replace")
                except (FileNotFoundError, IsADirectoryError):
                    cache[c.path] = []
                    continue
                lang = spans_mod.language_of(c.path, text)
                cache[c.path] = spans_mod.declarations(lang, text) if lang else []
            node = covered_node(cache[c.path], c.line)
            key = (c.path, node[0], node[1]) if node else (c.path, c.line, c.line)
            if key in nodes:
                continue
            nodes.add(key)
            size = key[2] - key[1] + 1
            if spans_mod.is_test(c.path):
                tests += size
            else:
                impl += size
        out[d.tag] = {"implementation": impl, "tests": tests, "regions": len(nodes)}
    return out


def check(root, files, defs, limits):
    """Every rule, with limits from `.cpo` [T33]."""
    problems = lint(root, files, defs, limits["statement_limit"], limits["section_limit"])
    lost, later = orphans(root, files, defs, limits["master"], limits["postponed"])
    for f in lost:
        problems.append(Problem(f, 1, "orphan",
                                f"{f} is reachable from {limits['master']} by no chain of links "
                                "or citations; describe and link it from where it belongs, "
                                "or postpone it in .cpo", f, 1))
    if limits["breadth_limit"]:
        for tag, b in breadth(root, defs).items():
            if b["implementation"] > limits["breadth_limit"]:
                d = defs[tag]
                problems.append(Problem(
                    d.path, d.line, "breadth",
                    f"{tag} ({d.name}) claims {b['implementation']} lines of code in "
                    f"{b['regions']} regions; refine it so no point claims more than "
                    f"{limits['breadth_limit']}", tag, b["implementation"]))
    return sorted(problems, key=lambda p: (p.rule, p.path, p.line)), later


def known(problem, baseline):
    """A problem the baseline already records, no worse than it was."""
    for b in baseline:
        if (b["rule"], b["path"], b["key"]) == (problem.rule, problem.path, problem.key):
            return problem.value <= b["value"]
    return False
