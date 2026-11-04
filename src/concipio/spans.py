"""Find the spans a change touches."""

import re
import subprocess
from dataclasses import dataclass

import tree_sitter_bash
import tree_sitter_c
import tree_sitter_python
import tree_sitter_ruby
from tree_sitter import Language, Parser

LANGUAGES = {
    "ruby": Language(tree_sitter_ruby.language()),
    "bash": Language(tree_sitter_bash.language()),
    "c": Language(tree_sitter_c.language()),
    "python": Language(tree_sitter_python.language()),
}
RSPEC_SPANS = {"it", "specify", "example", "before", "after", "around",
               "let", "let!", "subject"}
RSPEC_SCOPES = {"describe", "context", "shared_examples", "shared_context",
                "feature", "scenario"}
DEFAULT_LIMIT = 80
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class Span:
    id: str
    path: str
    side: str      # "new" for added or modified code, "old" for deletions
    start: int
    end: int
    scope: str
    kind: str
    quote: str
    test: bool


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, check=True).stdout


def file_at(repo, rev, path):
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=repo,
                         capture_output=True)
    return out.stdout.decode(errors="replace") if out.returncode == 0 else None


def language_of(path, text):
    if path.endswith((".rb", ".rake", ".ru", "Gemfile", "Rakefile")):
        return "ruby"
    if path.endswith((".c", ".h")):
        return "c"
    if path.endswith(".py"):
        return "python"
    if path.endswith((".sh", ".bash")):
        return "bash"
    first = text.split("\n", 1)[0] if text else ""
    if first.startswith("#!"):
        if "ruby" in first:
            return "ruby"
        if "python" in first:
            return "python"
        if re.search(r"\b(ba)?sh\b", first):
            return "bash"
    return None


def is_test(path):
    name = path.rsplit("/", 1)[-1]
    return (path.startswith(("spec/", "test/", "tests/")) or "/spec/" in path
            or "/test/" in path or "/tests/" in path
            or path.endswith(("_spec.rb", "_test.rb", "_test.py", "_test.c"))
            or (name.startswith("test_") and name.endswith((".py", ".c"))))


def node_text(node):
    return node.text.decode(errors="replace") if node else ""


def first_arg(node):
    args = node.child_by_field_name("arguments")
    if not args or not args.named_children:
        return ""
    text = node_text(args.named_children[0])
    return text if len(text) <= 60 else text[:57] + "..."


# Implements [CPO§V9]
def classify(lang, node):
    """Return (kind, name) if the node is a named declaration or a scope
    that names its contents, else None. Kinds that end in "scope" give
    names but are never spans."""
    t = node.type
    if lang == "c":
        return classify_c(node)
    if lang == "python":
        if t == "class_definition":
            return "class scope", node_text(node.child_by_field_name("name"))
        if t == "function_definition":
            return "function", node_text(node.child_by_field_name("name"))
        return None
    if lang == "bash":
        if t == "function_definition":
            return "function", node_text(node.child_by_field_name("name"))
        return None
    if t in ("class", "module"):
        return f"{t} scope", node_text(node.child_by_field_name("name"))
    if t in ("method", "singleton_method"):
        return "method", node_text(node.child_by_field_name("name"))
    if t == "call" and node.child_by_field_name("block"):
        method = node_text(node.child_by_field_name("method"))
        arg = first_arg(node)
        label = f"{method} {arg}".strip()
        if method in RSPEC_SCOPES:
            return "rspec scope", label
        if method in RSPEC_SPANS:
            return "rspec", label
        parent = node.parent
        if parent is not None and parent.type in ("program", "body_statement"):
            return "block", label
    return None


def declarator_name(node):
    """The identifier inside a C declarator, through pointers, arrays, and
    parameter lists."""
    while node is not None and node.type not in ("identifier", "field_identifier",
                                                   "type_identifier"):
        node = node.child_by_field_name("declarator")
    return node_text(node)


def classify_c(node):
    t = node.type
    if t == "function_definition":
        return "function", declarator_name(node.child_by_field_name("declarator"))
    if t in ("struct_specifier", "union_specifier", "enum_specifier") and \
            node.child_by_field_name("body") is not None and \
            node.parent is not None and node.parent.type in ("translation_unit", "declaration",
                                                             "type_definition"):
        word = t.split("_")[0]
        return word, f"{word} {node_text(node.child_by_field_name('name')) or '(anonymous)'}"
    if t == "type_definition":
        return "typedef", declarator_name(node.child_by_field_name("declarator"))
    if t in ("preproc_def", "preproc_function_def"):
        return "macro", node_text(node.child_by_field_name("name"))
    return None


def declarations(lang, text):
    """Return a list of (start, end, kind, name, ancestors) for every
    classified node, with 1-based inclusive line numbers."""
    tree = Parser(LANGUAGES[lang]).parse(text.encode())
    found = []

    def walk(node, ancestors):
        c = classify(lang, node)
        here = ancestors
        if c:
            kind, name = c
            # A node that ends at column 0, as a #define does by taking its
            # newline, ends on the line before.
            end_row, end_col = node.end_point
            end = end_row + 1 if end_col > 0 or end_row == node.start_point[0] else end_row
            found.append((node.start_point[0] + 1, end, kind, name, ancestors))
            here = ancestors + [(kind, name)]
        for child in node.children:
            walk(child, here)

    walk(tree.root_node, [])
    return found


IDENTIFIER_NODES = {"identifier", "field_identifier", "type_identifier", "constant",
                    "property_identifier"}


def identifiers(lang, text):
    """Every name the code itself uses, as (line, name), leaving out its
    comments and strings."""
    tree = Parser(LANGUAGES[lang]).parse(text.encode())
    out = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in IDENTIFIER_NODES or (
                node.type == "word" and node.parent is not None
                and node.parent.type == "command_name"):
            out.append((node.start_point[0] + 1, node_text(node)))
        elif "comment" not in node.type and "string" not in node.type:
            stack.extend(node.children)
    return out


def scope_name(path, ancestors, kind=None, name=None):
    parts = []
    for k, n in ancestors + ([(kind, n)] if (kind and (n := name)) else []):
        if k in ("class scope", "module scope"):
            parts.append(("::", n))
        elif k == "method":
            parts.append(("#", n))
        else:
            parts.append((" > ", n))
    if not parts:
        return path
    if parts[0][0] == "::":
        out = parts.pop(0)[1]
    else:
        out = path
    for sep, n in parts:
        out += sep + n
    return out


TRIVIAL = re.compile(r"^\s*(#.*|end|\}|fi|done|esac|;;)?\s*$")


def is_trivial(lines, numbers=(), headers=frozenset()):
    """Blank lines, comments, block ends, and the opening lines of scopes
    such as classes and describe blocks carry no meaning of their own."""
    return all(TRIVIAL.match(line) or n in headers
               for line, n in zip(lines, numbers or [None] * len(lines)))


# Implements [CPO§V8]
def cut(path, lang, text, start, end, limit):
    """Cut lines start..end into spans. A hunk inside one declaration widens
    to it, unless the declaration is a scope or longer than the limit. A
    hunk spanning several declarations splits at them, and leftover lines
    that are only comments, blanks, or block ends join a neighbor. Return a
    list of (start, end, kind, scope)."""
    decls = declarations(lang, text) if lang else []
    spans_ = [d for d in decls if not d[2].endswith("scope")]
    scopes = [d for d in decls if d[2].endswith("scope")]

    def container_of(s, e):
        best = None
        for d in scopes:
            if d[0] <= s and e <= d[1] and (best is None or d[1] - d[0] < best[1] - best[0]):
                best = d
        return best[4] + [(best[2], best[3])] if best else []

    inside = [d for d in spans_ if d[0] <= start and end <= d[1]]
    if inside:
        d = min(inside, key=lambda d: d[1] - d[0])
        if d[1] - d[0] + 1 <= limit:
            return [(d[0], d[1], d[2], scope_name(path, d[4], d[2], d[3]))]
        return [(start, end, "hunk", scope_name(path, d[4] + [(d[2], d[3])]))]

    # Outermost declarations that overlap the hunk.
    overlapping = [d for d in spans_ if d[0] <= end and start <= d[1]]
    outer = [d for d in overlapping
             if not any(o is not d and o[0] <= d[0] and d[1] <= o[1] for o in overlapping)]
    pieces = []
    for d in sorted(outer):
        s_, e_ = max(d[0], start), min(d[1], end)
        if d[1] - d[0] + 1 <= limit:
            s_, e_ = d[0], d[1]
        pieces.append([s_, e_, d[2], scope_name(path, d[4], d[2], d[3])])

    lines = text.splitlines()
    headers = {d[0] for d in scopes}
    covered = set()
    for p in pieces:
        covered.update(range(p[0], p[1] + 1))
    gap = []
    for n in range(start, end + 2):
        if n <= end and n not in covered:
            gap.append(n)
            continue
        if gap:
            g_start, g_end = gap[0], gap[-1]
            body = lines[g_start - 1:g_end]
            nxt = next((p for p in pieces if p[0] == g_end + 1), None)
            prv = next((p for p in pieces if p[1] == g_start - 1), None)
            trivial = is_trivial(body, range(g_start, g_end + 1), headers)
            if trivial and nxt:
                nxt[0] = g_start
            elif trivial and prv:
                prv[1] = g_end
            else:
                pieces.append([g_start, g_end, "hunk",
                               scope_name(path, container_of(g_start, g_end))])
            gap = []
    return [tuple(p) for p in sorted(pieces)]


def hunks(repo, base, head, path):
    out = git(repo, "diff", "--no-color", "--unified=0", base, head, "--", path)
    for line in out.splitlines():
        m = HUNK.match(line)
        if m:
            a, b, c, d = m.groups()
            yield (int(a), int(b) if b is not None else 1,
                   int(c), int(d) if d is not None else 1)


def changed_lines(repo, base, head, path, side):
    """Line numbers the change touched: added or modified lines on the head
    side, or removed lines on the base side."""
    out = set()
    for a, b, c, d in hunks(repo, base, head, path):
        if side == "new":
            out.update(range(c, c + d))
        else:
            out.update(range(a, a + b))
    return out


def quote_of(text, start, end):
    lines = text.splitlines()[start - 1:end]
    for line in lines:
        if line.strip():
            return line.strip()
    return ""


def changed_files(repo, base, head):
    out = git(repo, "diff", "--no-color", "--name-only", "-z", base, head)
    return [p for p in out.split("\0") if p]


def find_spans(repo, base, head, limit=DEFAULT_LIMIT):
    """Return the spans of the change base..head, in path and line order."""
    raw = []
    for path in changed_files(repo, base, head):
        new = file_at(repo, head, path)
        old = file_at(repo, base, path)
        lang = language_of(path, new if new is not None else old)
        for a, b, c, d in hunks(repo, base, head, path):
            if d > 0 and new is not None:
                for s, e, kind, scope in cut(path, lang, new, c, c + d - 1, limit):
                    raw.append((path, "new", s, e, kind, scope, quote_of(new, s, e)))
            elif b > 0 and old is not None:
                for s, e, kind, scope in cut(path, lang, old, a, a + b - 1, limit):
                    raw.append((path, "old", s, e, kind, scope, quote_of(old, s, e)))
    merged = []
    for item in sorted(set(raw), key=lambda r: (r[0], r[1] == "old", r[2], r[3])):
        prev = merged[-1] if merged else None
        if (prev and prev[0] == item[0] and prev[1] == item[1]
                and item[2] <= prev[3] + 1 and "hunk" in (prev[4], item[4])
                and prev[5] == item[5]):
            merged[-1] = (prev[0], prev[1], prev[2], max(prev[3], item[3]),
                          prev[4], prev[5], prev[6])
        elif prev and prev[:4] == item[:4]:
            continue
        else:
            merged.append(item)
    return [Span(f"S{i}", p, side, s, e, scope, kind, q, is_test(p))
            for i, (p, side, s, e, kind, scope, q) in enumerate(merged, 1)]
