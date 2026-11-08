"""Check that every design fits on a screen, reaches the master, and
claims no more code than a reader can hold."""

import fnmatch
import posixpath
import re
from pathlib import Path
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
        if not docs.is_doc(path) or path not in designs:
            continue
        text = (root / path).read_text(errors="replace")
        for line, level, title, n in sections(text):
            if n > section_limit:
                problems.append(Problem(
                    path, line, "section-length",
                    f'section "{title}" has {n} lines of its own; split it into '
                    f"subsections or a child doc of at most {section_limit}", title, n))
    return sorted(problems, key=lambda p: (p.path, p.line))


# Implements [CPO§T73]
def broken_links(root, files):
    """Links from a doc to a file in the repository that does not exist,
    or to a heading its target does not have, which a reader follows into
    nothing."""
    present = set(files) | {posixpath.dirname(f) for f in files}
    every = {f for f in files}
    anchors = {}

    def has_anchor(target, frag):
        if target not in anchors:
            try:
                anchors[target] = anchors_of((root / target).read_text(errors="replace"))
            except (FileNotFoundError, IsADirectoryError):
                anchors[target] = None
        return anchors[target] is None or frag.lower() in anchors[target]
    out = []
    for f in files:
        if not docs.is_doc(f):
            continue
        text = (root / f).read_text(errors="replace")
        for n, line in docs.prose_lines(text):
            for m in LINK.finditer(line):
                whole = m.group(1) or m.group(2) or ""
                raw, _, frag = whole.partition("#")
                if re.match(r"^[a-z][\w+.-]*:", raw) or raw.startswith("/"):
                    continue
                # A citation such as `[Y12]: ...` at the start of a line reads
                # like a link definition; only a path-like target is a link.
                if m.group(2) and not re.search(r"[./#]", whole):
                    continue
                if not raw:
                    if frag and not has_anchor(f, frag):
                        out.append(Problem(f, n, "broken-link", f"links to #{frag}, a heading "
                                           "this doc does not have", whole, 1))
                    continue
                # A link to a line, `src/ring.c:15`, links to the file.
                raw = re.sub(r":\d+(-\d+)?$", "", raw)
                target = posixpath.normpath(posixpath.join(posixpath.dirname(f), raw))
                if not (target in present or (root / target).exists() or
                        any(e.startswith(target.rstrip("/") + "/") for e in every)):
                    out.append(Problem(f, n, "broken-link",
                                       f"links to {raw}, which does not exist", raw, 1))
                elif frag and docs.is_doc(target) and not has_anchor(target, frag):
                    out.append(Problem(f, n, "broken-link", f"links to {raw}#{frag}, but "
                                       f"{raw} has no heading #{frag}", whole, 1))
    return out


EXPLICIT_ANCHOR = re.compile(r"\{#([\w-]+)\}|<a\s+(?:name|id)=[\"']([^\"']+)[\"']")


def anchors_of(text):
    """The anchors a doc's headings make, as GitHub and most doc sites
    spell them, and any it names itself, as `{#id}` or `<a id="...">`."""
    out, seen = set(), {}
    for _, line in docs.prose_lines(text):
        for m in EXPLICIT_ANCHOR.finditer(line):
            out.add((m.group(1) or m.group(2)).lower())
        h = HEADING.match(line)
        if not h:
            continue
        title = re.sub(r"\{#[\w-]+\}|<[^>]+>", "", h.group(2)).strip()
        slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        out.add(slug if n == 0 else f"{slug}-{n}")
    return out


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


def doc_graph(root, files, defs):
    """Docs joined by Markdown links and tag citations, either way."""
    md = [f for f in files if docs.is_doc(f)]
    known = set(md)
    edges = {f: set() for f in md}

    def join(a, b):
        if a in known and b in known and a != b:
            edges[a].add(b)
            edges[b].add(a)

    dirs = {}
    for f in md:
        dirs.setdefault(posixpath.dirname(f), []).append(f)
    old = docs.archived(root, md)
    for f in md:
        if f in old:
            continue
        text = (root / f).read_text(errors="replace")
        for target in links_of(f, text):
            if target in known:
                join(f, target)
            for g in dirs.get(target.rstrip("/"), []):
                join(f, g)
    for d in defs.values():
        for c in d.citations:
            join(c.path, d.path)
    return md, edges


def paths_from(master, edges):
    """For every reachable doc, the doc it was first reached from, by a
    breadth-first walk, so following them back gives a shortest path."""
    came = {master: None}
    queue = [master]
    while queue:
        here = queue.pop(0)
        for g in sorted(edges.get(here, ())):
            if g not in came:
                came[g] = here
                queue.append(g)
    return came


# Implements [CPO§F9]
def path_to(root, files, defs, target, master="README.md"):
    """The shortest chain of docs from the master to a doc, then, for a
    tag, the chain of statements within that doc down to the tag."""
    _, edges = doc_graph(root, files, defs)
    came = paths_from(master, edges)
    doc = defs[target].path if target in defs else target
    if doc not in came:
        return None
    chain = []
    node = doc
    while node is not None:
        chain.append(node)
        node = came[node]
    chain.reverse()
    inner = []
    node = target if target in defs else None
    while node in defs:
        inner.append(node)
        node = defs[node].parent
    return chain, list(reversed(inner))


# Implements [CPO§M24]
def orphans(root, files, defs, master="README.md", postponed=()):
    """Docs no chain of links reaches from the master, following Markdown
    links between docs and citations of tags, in either direction. Return
    (orphans, postponed orphans)."""
    md, edges = doc_graph(root, files, defs)
    # A documentation site's pages are reached through its navigation, so
    # each is a root beside the master [T72].
    seen = set(paths_from(master, edges))
    for page in docs.site_pages(root, files):
        seen |= set(paths_from(page, edges))
    lost = sorted(f for f in md if f not in seen)
    later = [f for f in lost if any(fnmatch.fnmatch(f, p) for p in postponed)]
    return [f for f in lost if f not in later], later


def covered_node(decls, line, lines=None):
    """The declaration a citation on this line documents: the innermost one
    around it, or the one that starts just below it, as a comment above a
    function documents that function [T8]. Given the file's lines, a
    citation anywhere in a comment block documents what follows the block,
    however long the block runs."""
    inside = [d for d in decls if d[0] <= line <= d[1] and not d[2].endswith("scope")]
    if inside:
        return min(inside, key=lambda d: d[1] - d[0])
    if lines:
        while line < len(lines) and spans_mod.COMMENT_LINE.search(lines[line]):
            line += 1
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
            if docs.is_doc(c.path):
                continue
            if c.path not in cache:
                try:
                    text = (root / c.path).read_text(errors="replace")
                except (FileNotFoundError, IsADirectoryError):
                    cache[c.path] = ([], [])
                    continue
                lang = spans_mod.language_of(c.path, text)
                cache[c.path] = (spans_mod.declarations(lang, text) if lang else [],
                                 text.splitlines())
            node = covered_node(*cache[c.path][:1], c.line, cache[c.path][1])
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


def check(root, files, defs, limits, cfg=None):
    """Every rule, with limits from `.cpo` [T33]."""
    old = docs.archived(root, files)
    every, files = files, [f for f in files if f not in old]
    problems = lint(root, files, defs, limits["statement_limit"], limits["section_limit"])
    problems += field_problems(root, files, defs, cfg or {}, limits["master"])
    problems += dangling_sections(root, files)
    problems += history_in_headings(root, files, defs, (cfg or {}).get("lint", {}).get("history_words"))
    problems += quoted_headings(root, defs)
    problems += unread_headings(root, files)
    problems += broken_links(root, files)
    from . import claims
    problems += claims.lint_problems(root, files, defs, cfg or {})
    problems += retired_terms(root, files, (cfg or {}).get("retired", {}))
    lost, later = orphans(root, every, defs, limits["master"], limits["postponed"])
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


# Implements [CPO§T61]
def measure():
    """Which Concipio measured: a digest of its own source, which changes
    whenever a rule or a measure may have."""
    import hashlib
    here = Path(__file__).parent
    h = hashlib.sha256()
    for f in sorted(here.glob("*.py")):
        h.update(f.name.encode() + b"\0" + f.read_bytes())
    return h.hexdigest()[:12]


def known(problem, baseline):
    """A problem the baseline already records, no worse than it was."""
    for b in baseline:
        if (b["rule"], b["path"], b["key"]) == (problem.rule, problem.path, problem.key):
            return problem.value <= b["value"]
    return False


FIELD_DEFAULTS = {"importance": "Importance", "critical": ["critical"], "critical_depth": 2,
                  "updated": "Updated", "stale_after_days": 21, "known": [], "stale": "Stale",
                  "verified": "Verified", "verify_every_days": 90}


def field_settings(cfg):
    out = dict(FIELD_DEFAULTS, **cfg.get("fields", {}))
    out["schemas"] = cfg.get("schema", [])
    return out


def schema_applies(schema, d, defs):
    """A schema covers the statements nested under its `under` tag, or the
    statements of docs matching its `docs` glob [F5]."""
    if "docs" in schema and fnmatch.fnmatch(d.path, schema["docs"]):
        return True
    node = d.parent
    while node in defs:
        if node == schema.get("under"):
            return True
        node = defs[node].parent
    return False


# Implements [CPO§F6]
def field_problems(root, files, defs, cfg, master):
    import jsonschema
    s = field_settings(cfg)
    known = set(s["known"])
    for schema in s["schemas"]:
        known.update(schema.get("require", []))
        known.update(schema.get("fields", {}))
    if s["known"] or s["schemas"]:
        known.update([s["importance"], s["updated"], s["stale"], s["verified"]])
    problems = []
    for d in defs.values():
        for e in d.fields.pop("__errors__", []) if "__errors__" in d.fields else []:
            problems.append(Problem(d.path, d.line, "field-syntax", f"{d.tag}: {e}", d.tag, 1))
        if known:
            for key in d.fields:
                if key not in known:
                    near = [k for k in known if k.lower() == key.lower()]
                    hint = f"; did you mean {near[0]}?" if near else ""
                    problems.append(Problem(d.path, d.line, "undeclared-field",
                                            f"{d.tag} has a field {key} that no schema "
                                            f"declares{hint}", f"{d.tag}:{key}", 1))
        for schema in s["schemas"]:
            if not schema_applies(schema, d, defs):
                continue
            spec = {"type": "object", "required": schema.get("require", []),
                    "properties": schema.get("fields", {})}
            for err in jsonschema.Draft202012Validator(spec).iter_errors(d.fields):
                where = "/".join(str(p) for p in err.path) or "fields"
                problems.append(Problem(d.path, d.line, "schema",
                                        f"{d.tag} ({d.name}): {where}: {err.message}",
                                        f"{d.tag}:{where}", 1))
    # Implements [CPO§F10]
    critical = [d for d in defs.values() if d.fields.get(s["importance"]) in s["critical"]]
    if critical:
        _, edges = doc_graph(root, files, defs)
        came = paths_from(master, edges)
        for d in critical:
            depth = 0
            node = d.path
            if node not in came:
                depth = None
            else:
                while came[node] is not None:
                    depth += 1
                    node = came[node]
            if depth is None or depth > s["critical_depth"]:
                how = "unreachable" if depth is None else f"{depth} links from {master}"
                problems.append(Problem(d.path, d.line, "buried",
                                        f"{d.tag} ({d.name}) is critical but {how}; keep it "
                                        f"within {s['critical_depth']}", d.tag, depth or 99))
    # Implements [CPO§F16]
    import datetime
    today = datetime.date.today()
    for d in critical:
        stamp = d.fields.get(s["verified"])
        if s["stale"] in d.fields:
            # Known wrong is not the same as unchecked, and a reader needs
            # to see which.
            problems.append(Problem(d.path, d.line, "stale-critical",
                                    f"{d.tag} ({d.name}) is critical and marked stale: "
                                    f"{d.fields[s['stale']]}", d.tag, 1))
            continue
        if not stamp:
            problems.append(Problem(d.path, d.line, "unverified-critical",
                                    f"{d.tag} ({d.name}) is critical but says nowhere when it was "
                                    f"last checked against the code; add {s['verified']}=<date>",
                                    d.tag, 1))
            continue
        try:
            age = (today - datetime.date.fromisoformat(str(stamp))).days
        except ValueError:
            problems.append(Problem(d.path, d.line, "unverified-critical",
                                    f"{d.tag}: {s['verified']}={stamp} is not a date", d.tag, 1))
            continue
        changed = code_changed_since(root, d, str(stamp))
        if age > s["verify_every_days"] or changed:
            why = (f"code citing it changed since ({changed})" if changed
                   else f"{age} days ago")
            problems.append(Problem(d.path, d.line, "unverified-critical",
                                    f"{d.tag} ({d.name}) was last verified {stamp}, {why}; "
                                    "check it and update the date", d.tag, 1))
    # Implements [CPO§F15]
    for d in defs.values():
        stamp = d.fields.get(s["updated"])
        if not stamp:
            continue
        last = last_changed(root, d)
        if last and last > str(stamp):
            problems.append(Problem(d.path, d.line, "stale-updated",
                                    f"{d.tag} ({d.name}) says {s['updated']}={stamp}, but its "
                                    f"text changed on {last}", d.tag, 1))
    return problems


def last_changed(root, d):
    """The date the statement's lines last changed, by git blame, or today
    if any of them are not yet committed."""
    import datetime
    import subprocess
    end = d.line + max(d.lines, 1) - 1
    out = subprocess.run(["git", "blame", "--porcelain", "-L", f"{d.line},{end}", "--", d.path],
                         cwd=root, capture_output=True, text=True)
    if out.returncode != 0:
        return None
    times = [int(l.split()[1]) for l in out.stdout.splitlines() if l.startswith("author-time ")]
    if "0000000000000000000000000000000000000000" in out.stdout:
        return datetime.date.today().isoformat()
    return datetime.date.fromtimestamp(max(times)).isoformat() if times else None


def names_a_doc(before):
    """Whether the word just before a section number names a document: one
    with several capitals, such as DESIGN or RFC, or with a digit or a dot
    in it, such as notes-2.md. An ordinary word, a capitalized first word,
    or another section number does not."""
    words = before.split()
    if not words:
        return False
    word = words[-1].strip("([,;:")
    if not word or word.startswith("§"):
        return False
    return sum(c.isupper() for c in word) >= 2 or any(c.isdigit() or c in "._-" for c in word)


# Implements [CPO§T43]
def dangling_sections(root, files):
    """Bare section numbers that name no section of their own doc, in the
    docs `.cpo` declares as defining their sections [T39]. Other docs may
    number their own sections yet cite another's bare, so only a declared
    source's bare numbers are known to be its own."""
    out = []
    declared = {src["doc"] for src in docs.sources(root)}
    for f in files:
        if f not in declared:
            continue
        text = (root / f).read_text(errors="replace")
        heads = docs.numbered_headings(text)
        if not heads:
            continue
        linked = re.compile(r"\]\(\s*<?[^)>\s#]+\.(?:md|mdx|markdown)[^)]*\)[\s,]*$")
        prev = (None, "")
        for n, line in docs.prose_lines(text):
            if docs.NUMBERED.match(line):
                prev = (None, "")
                continue
            for m in docs.BARE_SECTION.finditer(line):
                before = line[:m.start()]
                # A number that opens a line may have wrapped away from the
                # doc name that ends the line before it.
                if not before.strip() and prev[0] == n - 1:
                    before = prev[1]
                # Another doc's section, as in "DESIGN §5", "notes.md §3", or a
                # link: the word before it names a document.
                if linked.search(before) or names_a_doc(before):
                    continue
                if m["id"] not in heads:
                    # Keyed by the number, not the line, so a known problem
                    # stays known when edits elsewhere move it.
                    out.append(Problem(f, n, "dangling-section",
                                       f"§{m['id']} names no section of {f}",
                                       f"§{m['id']}", 1))
            prev = (n, line)
    return out


QUOTED_HEADING = re.compile(r"^\s{0,3}(?:>\s*)+(#{1,6})\s+(.*)$")


# Implements [CPO§T60]
def unread_headings(root, files):
    """Headings in a declared source that look numbered but that the
    source's heading pattern does not read, so define no section."""
    out = []
    for src in docs.sources(root):
        if src["doc"] not in files:
            continue
        text = (root / src["doc"]).read_text(errors="replace")
        for n, line in docs.prose_lines(text):
            m = docs.LOOKS_NUMBERED.match(line)
            if m and not src["heading"].search(line):
                out.append(Problem(src["doc"], n, "unread-heading",
                                   f'heading "{line.strip()[:70]}" looks numbered, but the '
                                   f"{src['prefix']} heading pattern in .cpo does not read it, "
                                   f"so §{m.group(2)} is defined nowhere", m.group(2), 1))
    return out


# Implements [CPO§T47]
def quoted_headings(root, defs):
    """Headings hidden in blockquotes, in design docs: not sections, so
    their text counts toward the section above them."""
    out = []
    for f in sorted({d.path for d in defs.values()}):
        text = (root / f).read_text(errors="replace")
        for n, line in docs.prose_lines(text):
            m = QUOTED_HEADING.match(line)
            if m:
                out.append(Problem(f, n, "heading-in-blockquote",
                                   f'heading "{m.group(2)[:70]}" is inside a blockquote, so it '
                                   "is not a section; unquote it", m.group(2)[:60], 1))
    return out


COMMENT_LINE = re.compile(r"^\s*(?:#|//|/?\*|--|;)")


# Implements [CPO§T48]
def retired_terms(root, files, retired):
    """Live docs and code comments that still use a retired term, one
    problem per file and term, valued by how often."""
    if not retired:
        return []
    pats = {t: re.compile(rf"(?<![\w]){re.escape(t)}(?![\w])") for t in retired}
    out = []
    for f in files:
        md = docs.is_doc(f)
        if not md and not f.endswith(CODE_EXTENSIONS):
            continue
        try:
            text = (root / f).read_text(errors="replace")
        except (FileNotFoundError, IsADirectoryError):
            continue
        # A doc's inline code and examples name mechanisms too, so all of
        # a doc is read; of code, only its comments.
        lines = ((n, l) for n, l in enumerate(text.splitlines(), 1)
                 if md or COMMENT_LINE.match(l))
        found = {}
        for n, line in lines:
            for t, pat in pats.items():
                k = len(pat.findall(line))
                if k:
                    first, count = found.get(t, (n, 0))
                    found[t] = (first, count + k)
        for t, (first, count) in sorted(found.items()):
            out.append(Problem(f, first, "retired-term",
                               f'"{t}" is retired ({retired[t]}) but used {count} time'
                               f'{"s" if count > 1 else ""} here', t, count))
        lang = None if md else spans_mod.language_of(f, text)
        if lang:
            live = {}
            for n, name in spans_mod.identifiers(lang, text):
                if name in retired:
                    live.setdefault(name, n)
            for t, n in sorted(live.items()):
                out.append(Problem(f, n, "retired-term-live",
                                   f'"{t}" is listed as retired in .cpo but is still live code '
                                   "here; finish retiring it, or take it off the list", t, 1))
    return out


# Implements [CPO§T42]
def stale_marks(root, files, defs, cfg):
    """Statements, sections, and docs marked stale, with their reasons."""
    s = field_settings(cfg)
    pattern = docs.field_pattern(root)
    out = []
    for d in defs.values():
        if s["stale"] in d.fields:
            out.append({"path": d.path, "line": d.line, "what": f"{d.tag} ({d.name})",
                        "reason": str(d.fields[s["stale"]])})
    for f in files:
        if docs.is_doc(f):
            fields = docs.doc_fields((root / f).read_text(errors="replace"), pattern)
            if s["stale"] in fields:
                out.append({"path": f, "line": 1, "what": f, "reason": str(fields[s["stale"]])})
    return out


# Implements [CPO§M52]
STANDARDS = {
    "completeness": ("orphan",),
    "correctness": ("dangling-section", "stale-updated", "schema", "undeclared-field",
                    "field-syntax", "unverified-critical", "stale-critical",
                    "history-in-heading", "retired-term",
                    "retired-term-live", "unread-heading", "unbacked-claim",
                    "broken-link"),
    "consumability": ("section-length", "statement-length", "breadth", "buried",
                      "heading-in-blockquote"),
}


def standard_of(rule):
    return next((c for c, rules in STANDARDS.items() if rule in rules), "other")


# Implements [CPO§M50]
def audit(root, files, defs, limits, cfg):
    """Every problem, counted by rule, and the debt a project has marked,
    for a score each commit can improve rather than a pass or fail."""
    problems, later = check(root, files, defs, limits, cfg)
    weights = cfg.get("audit", {}).get("weights", {})
    counts = {}
    for p in problems:
        counts[p.rule] = counts.get(p.rule, 0) + 1
    score = sum(n * weights.get(rule, 1) for rule, n in counts.items())
    by_standard = {}
    for rule, n in counts.items():
        c = standard_of(rule)
        by_standard[c] = by_standard.get(c, 0) + n * weights.get(rule, 1)
    return {"score": score, "rules": counts, "standards": by_standard,
            "debt": {"stale": stale_marks(root, files, defs, cfg), "postponed_orphans": later},
            "problems": problems}


CODE_EXTENSIONS = (".c", ".h", ".cc", ".cpp", ".hpp", ".py", ".rb", ".sh", ".bash", ".go",
                   ".rs", ".js", ".ts", ".java")


# Implements [CPO§M51]
# Implements [CPO§T15]
EXEMPT = re.compile(r"^\s*(?:#|//|/?\*|--|;)\s*CPO§exempt:\s*(?P<reason>\S.*?)\s*(?:\*/)?\s*$")


def coverage(root, files, defs, exclude=(), strict=False):
    """How much code its design citations claim: per file, the non-blank
    lines inside declarations that some comment cites [T8], with tests
    counted apart, and files no parser reads reported as unmeasured.
    Strictly, only implementation and test citations cover code [T6]; a
    project still adopting may count every mention. Code a person exempts
    as serving no design is counted apart again, as accounted for but not
    covered [T15]."""
    cited = {}
    for d in defs.values():
        for c in d.citations:
            if not docs.is_doc(c.path) and (not strict or c.role != "reference"):
                cited.setdefault(c.path, set()).add(c.line)
    out = []
    for f in files:
        if any(fnmatch.fnmatch(f, p) for p in exclude):
            continue
        try:
            text = (root / f).read_text(errors="replace")
        except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
            continue
        lang = spans_mod.language_of(f, text)
        if lang is None and not f.endswith(CODE_EXTENSIONS):
            continue
        lines = text.splitlines()
        code = {n for n, l in enumerate(lines, 1) if l.strip()}
        row = {"path": f, "lines": len(code), "covered": 0, "test": spans_mod.is_test(f),
               "measured": lang is not None, "citations": len(cited.get(f, ()))}
        marks = [(n, m["reason"]) for n, l in enumerate(lines, 1)
                 for m in [EXEMPT.search(l)] if m]
        row["exempt"], row["exemptions"] = 0, [{"line": n, "reason": r} for n, r in marks]
        if lang is not None and (f in cited or marks):
            decls = spans_mod.declarations(lang, text)

            def claimed(at):
                hit = set()
                for line in at:
                    node = covered_node(decls, line, lines)
                    if node:
                        hit.update(range(node[0], node[1] + 1))
                return hit & code
            hit = claimed(cited.get(f, ()))
            row["covered"] = len(hit)
            row["exempt"] = len(claimed(n for n, _ in marks) - hit)
        out.append(row)
    return out


def code_changed_since(root, d, stamp):
    """A code file citing the statement that git says changed after the
    date, or None."""
    import subprocess
    for path in sorted({c.path for c in d.citations if not docs.is_doc(c.path)}):
        out = subprocess.run(["git", "log", "-1", "--format=%cs", f"--since={stamp} 23:59:59",
                              "--", path], cwd=root, capture_output=True, text=True)
        if out.stdout.strip():
            return path
    return None


HISTORY_WORDS = ["BUILT", "DESIGNED", "UNSCHEDULED", "SETTLED", "DRAFTED", "RULED",
                 "added", "written down", "built", "unscheduled", "settled", "drafted"]


# Implements [CPO§T45]
def history_in_headings(root, files, defs, words=None):
    """Headings in design docs that record when something was decided, built,
    or found broken. A design says what is true now; its history belongs in
    reports, and its rulings in decisions with reasons [M47]."""
    words = HISTORY_WORDS if words is None else words
    pattern = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|" + "|".join(
        rf"\b{re.escape(w)}\b" for w in words))
    designs = {d.path for d in defs.values()}
    out = []
    for f in sorted(designs):
        text = (root / f).read_text(errors="replace")
        for n, line in docs.prose_lines(text):
            m = HEADING.match(line)
            if m and pattern.search(m.group(2)):
                found = pattern.search(m.group(2)).group(0)
                out.append(Problem(f, n, "history-in-heading",
                                   f'heading "{m.group(2)[:70]}" records history ("{found}"); '
                                   "say what is true now, and move the history out",
                                   m.group(2)[:60], 1))
    return out
