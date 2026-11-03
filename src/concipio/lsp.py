"""A language server that lets any editor navigate Concipio's tags.

It speaks just enough of the Language Server Protocol over stdio for go to
definition, find references, hover, document outline, and workspace symbol
search. Its index is the one `cpo show` uses.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from . import docs

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
SPAN_ID = re.compile(r"\bS\d+\b")
MODULE, CONSTANT = 2, 14


def to_uri(path):
    return "file://" + quote(str(path))


def from_uri(uri):
    return Path(unquote(urlparse(uri).path))


def utf16(line, col):
    return len(line[:col].encode("utf-16-le")) // 2


def from_utf16(line, units):
    count = 0
    for i, ch in enumerate(line):
        if count >= units:
            return i
        count += 2 if ord(ch) > 0xFFFF else 1
    return len(line)


class Index:
    """The definitions and citations under one root, rebuilt when a file
    under it changes."""

    def __init__(self, root, files=None):
        self.root = root
        self.files = files
        self.defs = None

    def stamp(self, files):
        """What the index was built from: the docs' and .cpo's modification
        times, so a change made outside the editor, such as a checkout, is
        noticed on the next request."""
        out = []
        for f in [*files, ".cpo"]:
            if f.endswith(".md") or f == ".cpo":
                try:
                    out.append((f, (self.root / f).stat().st_mtime_ns))
                except FileNotFoundError:
                    pass
        return tuple(out)

    def get(self):
        files = self.files if self.files is not None else docs.tracked_files(self.root)
        now = self.stamp(files)
        if self.defs is None or now != getattr(self, "built_from", None):
            _, self.defs, _ = docs.load(root=self.root, files=files)
            self.built_from = now
            self.sources = docs.sources(self.root)
        return self.defs


class Server:
    def __init__(self, out=sys.stdout.buffer):
        self.out = out
        self.buffers = {}
        self.indexes = {}

    # Transport.

    def send(self, message):
        body = json.dumps(message, ensure_ascii=False).encode()
        self.out.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        self.out.flush()

    def serve(self, stream=sys.stdin.buffer):
        while True:
            length = None
            while True:
                line = stream.readline()
                if not line:
                    return
                line = line.strip()
                if not line:
                    break
                name, _, value = line.decode().partition(":")
                if name.lower() == "content-length":
                    length = int(value)
            if length is None:
                continue
            try:
                message = json.loads(stream.read(length))
            except ValueError:
                continue
            if self.handle(message) == "exit":
                return

    def handle(self, message):
        method = message.get("method")
        params = message.get("params") or {}
        handler = getattr(self, "on_" + (method or "").replace("/", "_").replace("$", "_"), None)
        if method == "exit":
            return "exit"
        try:
            result = handler(params) if handler else None
        except Exception as e:  # An editor should keep its server after one bad request.
            if "id" in message:
                self.send({"jsonrpc": "2.0", "id": message["id"],
                           "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}})
            return None
        if "id" in message and method:
            if handler is None and not method.startswith("$/"):
                self.send({"jsonrpc": "2.0", "id": message["id"],
                           "error": {"code": -32601, "message": f"{method} not supported"}})
            else:
                self.send({"jsonrpc": "2.0", "id": message["id"], "result": result})
        return None

    # Lifecycle and documents.

    def on_initialize(self, params):
        root = params.get("rootUri")
        if root:
            self.index_for(from_uri(root) / "x")
        return {"capabilities": {
            "textDocumentSync": 1,
            "definitionProvider": True,
            "referencesProvider": True,
            "hoverProvider": True,
            "documentSymbolProvider": True,
            "workspaceSymbolProvider": True,
        }, "serverInfo": {"name": "cpo"}}

    def on_shutdown(self, params):
        return None

    def on_textDocument_didOpen(self, params):
        doc = params["textDocument"]
        self.buffers[doc["uri"]] = doc["text"]

    def on_textDocument_didChange(self, params):
        """Apply changes in order. The server asks for whole documents, but
        accepts ranged changes from a client that sends them anyway."""
        uri = params["textDocument"]["uri"]
        for change in params["contentChanges"]:
            if "range" not in change:
                self.buffers[uri] = change["text"]
                continue
            text = self.buffers.get(uri, "")
            lines = text.split("\n")

            def offset(pos):
                line = min(pos["line"], len(lines) - 1)
                before = sum(len(l) + 1 for l in lines[:line])
                return before + from_utf16(lines[line], pos["character"])

            start, end = offset(change["range"]["start"]), offset(change["range"]["end"])
            self.buffers[uri] = text[:start] + change["text"] + text[end:]

    def on_textDocument_didSave(self, params):
        self.index_for(from_uri(params["textDocument"]["uri"])).defs = None

    def on_textDocument_didClose(self, params):
        self.buffers.pop(params["textDocument"]["uri"], None)

    # Resolution.

    def index_for(self, path):
        """The index for a file: its repository's, or for a file outside
        any repository, such as a rendered review in the store, the
        Markdown files beside it."""
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path.parent,
                             capture_output=True, text=True)
        if out.returncode == 0:
            root, files = Path(out.stdout.strip()), None
        else:
            root = path.parent
            files = sorted(p.name for p in root.glob("*.md"))
        key = str(root)
        if key not in self.indexes:
            self.indexes[key] = Index(root, files)
        return self.indexes[key]

    def text(self, uri):
        if uri in self.buffers:
            return self.buffers[uri]
        return from_uri(uri).read_text(errors="replace")

    def link_at(self, path, lines, line, col):
        """The target of a Markdown link under the cursor: an inline link,
        or a reference link with its definition elsewhere in the file. Return
        (path, fragment) or None."""
        targets = []
        for m in re.finditer(r"\[([^\]]*)\]\(\s*<?([^)>\s]+)>?[^)]*\)", line):
            targets.append((m.start(), m.end(), m.group(2)))
        refs = {}
        for l in lines:
            d = re.match(r"^\s{0,3}\[([^\]]+)\]:\s*<?([^>\s]+)>?", l)
            if d:
                refs[d.group(1).lower()] = d.group(2)
        for m in re.finditer(r"\[([^\]]+)\](?:\[([^\]]*)\])?(?![(:])", line):
            key = (m.group(2) or m.group(1)).lower()
            if key in refs:
                targets.append((m.start(), m.end(), refs[key]))
        for start, end, target in targets:
            if start <= col <= end and not re.match(r"^[a-z]+:", target):
                file, _, frag = target.partition("#")
                full = (path.parent / file).resolve() if file else path
                return full, frag
        return None

    def heading_line(self, path, fragment):
        """The line of the heading whose GitHub-style anchor is fragment, or
        the line a section number resolved to."""
        if isinstance(fragment, tuple):
            return fragment[1]
        if not fragment:
            return 1
        try:
            text = path.read_text(errors="replace")
        except (FileNotFoundError, IsADirectoryError):
            return 1
        for n, l in enumerate(text.splitlines(), 1):
            m = HEADING.match(l)
            if m:
                anchor = re.sub(r"[^\w\- ]", "", m.group(2).strip().lower()).replace(" ", "-")
                if anchor == fragment.lower():
                    return n
        return 1

    def word_at(self, uri, position):
        """Return ("tag", tag), ("span", id), or ("link", (path, fragment))
        for the token under the cursor, or None."""
        path = from_uri(uri)
        lines = self.text(uri).splitlines()
        if position["line"] >= len(lines):
            return None
        line = lines[position["line"]]
        col = from_utf16(line, position["character"])
        defs = self.index_for(path).get()
        for m in docs.TAG.finditer(line):
            if m.start() <= col <= m.end() and m.group(0) in defs:
                return "tag", m.group(0)
        index = self.index_for(path)
        for src in getattr(index, "sources", []):
            patterns = [src["cite"]]
            if path.suffix != ".md":
                named = docs.file_default("\n".join(lines), index.sources)
                if src is named or (named is None and src.get("code_default")):
                    patterns.append(docs.BARE_SECTION)
            elif path == index.root / src["doc"]:
                patterns.append(docs.BARE_SECTION)
            for pattern in patterns:
                for m in pattern.finditer(line):
                    tag = f"{src['prefix']}§{m['id']}"
                    if m.start() <= col <= m.end() and tag in defs:
                        return "tag", tag
            hm = src["heading"].match(line) if path == index.root / src["doc"] else None
            if hm and f"{src['prefix']}§{hm['id']}" in defs:
                return "tag", f"{src['prefix']}§{hm['id']}"
        if path.suffix == ".md":
            for m in docs.SHORT_LIST.finditer(line):
                for im in re.finditer(docs.ID, m.group(1)):
                    start = m.start(1) + im.start()
                    if start <= col <= start + len(im.group(0)):
                        own = {d.tag.split("§")[0] for d in defs.values()
                               if Path(self.index_for(path).root, d.path) == path}
                        prefixes = own or {t.split("§")[0] for t in defs}
                        for prefix in prefixes:
                            if f"{prefix}§{im.group(0)}" in defs:
                                return "tag", f"{prefix}§{im.group(0)}"
        for m in SPAN_ID.finditer(line):
            if m.start() <= col <= m.end() and self.review_for(path):
                return "span", m.group(0)
        if path.suffix == ".md":
            link = self.link_at(path, lines, line, col)
            if link:
                return "link", link
            section = self.section_at(path, lines, line, col)
            if section:
                return "link", section
        return None

    def section_at(self, path, lines, line, col):
        """A bare §5c under the cursor: a section of the doc linked just
        before it, as in "[the answers](answers.md), §5", or else of the doc
        it is in [T41]."""
        for m in docs.BARE_SECTION.finditer(line):
            if not m.start() <= col <= m.end():
                continue
            before = line[:m.start()]
            linked = re.search(r"\]\(\s*<?([^)>\s#]+\.md)[^)]*\)[\s,]*$", before)
            target = (path.parent / linked.group(1)).resolve() if linked else path
            try:
                heads = docs.numbered_headings(target.read_text(errors="replace"))
            except (FileNotFoundError, IsADirectoryError):
                return None
            if m["id"] in heads:
                return target, ("#line", heads[m["id"]])
        return None

    def review_for(self, path):
        """For a rendered review in the store, its manifest and spans."""
        if path.parent.name != "gendoc":
            return None
        review = path.parent.parent / "reviews" / path.stem
        try:
            manifest = json.loads((review / "manifest.json").read_text())
            spans = {s["id"]: s for s in json.loads((review / "spans.json").read_text())}
        except FileNotFoundError:
            return None
        return manifest, spans

    def location(self, path, line, col=0, end=None):
        text_line = ""
        try:
            text_line = path.read_text(errors="replace").splitlines()[line - 1]
        except (FileNotFoundError, IndexError):
            pass
        end = len(text_line) if end is None else end
        return {"uri": to_uri(path), "range": {
            "start": {"line": line - 1, "character": utf16(text_line, col)},
            "end": {"line": line - 1, "character": utf16(text_line, end)}}}

    # Requests.

    def on_textDocument_definition(self, params):
        uri = params["textDocument"]["uri"]
        word = self.word_at(uri, params["position"])
        if not word:
            return None
        path = from_uri(uri)
        # Implements [CPO§M43]
        if word[0] == "link":
            target, fragment = word[1]
            return self.location(target, self.heading_line(target, fragment)) \
                if target.exists() else None
        if word[0] == "span":
            manifest, spans = self.review_for(path)
            s = spans.get(word[1])
            if not s:
                return None
            if s["side"] == "old":
                return None
            return self.location(Path(manifest["repo"]) / s["path"], s["start"])
        index = self.index_for(path)
        d = index.get()[word[1]]
        return self.location(index.root / d.path, d.line)

    def on_textDocument_references(self, params):
        uri = params["textDocument"]["uri"]
        word = self.word_at(uri, params["position"])
        if not word or word[0] != "tag":
            return []
        index = self.index_for(from_uri(uri))
        d = index.get()[word[1]]
        out = [self.location(index.root / c.path, c.line, c.col, c.end) for c in d.citations]
        if (params.get("context") or {}).get("includeDeclaration"):
            out.insert(0, self.location(index.root / d.path, d.line))
        return out

    def on_textDocument_hover(self, params):
        uri = params["textDocument"]["uri"]
        word = self.word_at(uri, params["position"])
        if not word:
            return None
        path = from_uri(uri)
        if word[0] == "link":
            target, fragment = word[1]
            if not target.exists() or target.is_dir():
                return None
            head = target.read_text(errors="replace").splitlines()
            title = next((l.lstrip("# ").strip() for l in head if l.startswith("#")), target.name)
            n = self.heading_line(target, fragment)
            at = f" § {head[n - 1].lstrip('# ').strip()}" if fragment and n > 1 else ""
            value = f"**{title}**{at}\n\n`{target.name}`"
        elif word[0] == "span":
            _, spans = self.review_for(path)
            s = spans.get(word[1])
            if not s:
                return None
            value = f"**{s['id']}** `{s['path']}:{s['start']}-{s['end']}`\n\n{s['scope']}"
        else:
            defs = self.index_for(path).get()
            d = defs[word[1]]
            lines = [f"**{d.tag}: {d.name}**", "", d.text, "",
                     f"*{d.path}:{d.line}*"]
            if d.parent in defs:
                lines.append(f"Refines {d.parent} ({defs[d.parent].name})")
            if d.children:
                lines.append("Refined by " + ", ".join(d.children))
            roles = {}
            for c in d.citations:
                roles[c.role] = roles.get(c.role, 0) + 1
            if roles:
                lines.append("Cited: " + ", ".join(f"{n} {r}" for r, n in sorted(roles.items())))
            value = "\n".join(lines)
        return {"contents": {"kind": "markdown", "value": value}}

    def on_textDocument_documentSymbol(self, params):
        uri = params["textDocument"]["uri"]
        path = from_uri(uri)
        text = self.text(uri)
        lines = text.splitlines()
        index = self.index_for(path)
        defs = [d for d in index.get().values() if (index.root / d.path) == path]
        prose = [l for _, l in docs.prose_lines(text)]

        def rng(start, end):
            last = lines[end - 1] if 0 < end <= len(lines) else ""
            return {"start": {"line": start - 1, "character": 0},
                    "end": {"line": end - 1, "character": utf16(last, len(last))}}

        headings = [(i + 1, len(m[1]), m[2]) for i, l in enumerate(prose)
                    if (m := HEADING.match(l))]
        roots, stack = [], []
        for k, (line, level, title) in enumerate(headings):
            end = len(lines)
            for line2, level2, _ in headings[k + 1:]:
                if level2 <= level:
                    end = line2 - 1
                    break
            sym = {"name": title, "kind": MODULE, "range": rng(line, max(end, line)),
                   "selectionRange": rng(line, line), "children": []}
            while stack and stack[-1][0] >= level:
                stack.pop()
            (stack[-1][1]["children"] if stack else roots).append(sym)
            stack.append((level, sym))

        def heading_at(line):
            best = None
            for sym in walk(roots):
                r = sym["range"]
                if sym["kind"] == MODULE and r["start"]["line"] < line <= r["end"]["line"] + 1:
                    best = sym
            return best

        made = {}
        for d in sorted(defs, key=lambda d: d.line):
            sym = {"name": f"{d.tag.split('§')[1]} {d.name}", "kind": CONSTANT,
                   "detail": d.tag, "range": rng(d.line, d.line + d.lines - 1),
                   "selectionRange": rng(d.line, d.line), "children": []}
            made[d.tag] = sym
            parent = made.get(d.parent) or heading_at(d.line)
            (parent["children"] if parent else roots).append(sym)

        def by_line(symbols):
            symbols.sort(key=lambda x: x["range"]["start"]["line"])
            for x in symbols:
                by_line(x["children"])
            return symbols

        return by_line(roots)

    def on_workspace_symbol(self, params):
        query = params.get("query", "").lower()
        out = []
        for index in self.indexes.values():
            for d in index.get().values():
                if query in d.tag.lower() or query in d.name.lower():
                    out.append({"name": f"{d.tag} {d.name}", "kind": CONSTANT,
                                "location": self.location(index.root / d.path, d.line)})
        return out[:200]


def walk(symbols):
    for s in symbols:
        yield s
        yield from walk(s.get("children", []))


# Implements [CPO§M43]
def main():
    Server().serve()
