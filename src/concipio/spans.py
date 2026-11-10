"""Find the spans a change touches."""

import functools
import importlib
import re
import subprocess
from dataclasses import dataclass

import warnings
from pathlib import Path

from tree_sitter import Language, Parser, Query, QueryCursor

# Each language's grammar is its own package. One that is missing, as after
# an update that added a language but no reinstall, costs only that
# language, not every command.
GRAMMARS = {"ruby": "tree_sitter_ruby", "bash": "tree_sitter_bash", "c": "tree_sitter_c",
            "cpp": "tree_sitter_cpp", "go": "tree_sitter_go", "perl": "tree_sitter_perl",
            "python": "tree_sitter_python", "rust": "tree_sitter_rust"}
LANGUAGES, MISSING = {}, []
with warnings.catch_warnings():
    # The Perl grammar still hands its language over as a bare pointer.
    warnings.simplefilter("ignore", DeprecationWarning)
    for _lang, _module in GRAMMARS.items():
        try:
            LANGUAGES[_lang] = Language(importlib.import_module(_module).language())
        except ImportError:
            MISSING.append(_module)
if MISSING:
    import sys
    print(f"cpo: {', '.join(MISSING)} not installed, so those languages are read as plain "
          "text; reinstall Concipio to add them.", file=sys.stderr)
QUERIES = Path(__file__).parent / "queries"
INHERITS = re.compile(r"^; inherits: ([\w,]+)")
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
    """The language Concipio parses a file as, if its grammar is installed."""
    lang = guess_language(path, text)
    return lang if lang in LANGUAGES else None


def guess_language(path, text):
    if path.endswith((".rb", ".rake", ".ru", "Gemfile", "Rakefile")):
        return "ruby"
    if path.endswith((".c", ".h")):
        return "c"
    if path.endswith((".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx")):
        return "cpp"
    if path.endswith((".pl", ".pm", ".t")):
        return "perl"
    if path.endswith(".go"):
        return "go"
    if path.endswith(".rs"):
        return "rust"
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
        if "perl" in first:
            return "perl"
        if re.search(r"\b(ba)?sh\b", first):
            return "bash"
    return None


def is_test(path):
    name = path.rsplit("/", 1)[-1]
    # `t/` and `.t` are Perl's convention, which PostgreSQL's TAP tests follow.
    return (path.startswith(("spec/", "test/", "tests/", "t/")) or "/spec/" in path
            or "/test/" in path or "/tests/" in path or "/t/" in path
            or path.endswith(("_spec.rb", "_test.rb", "_test.py", "_test.c", ".t"))
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
@functools.lru_cache(maxsize=None)
def query_text(lang):
    """A language's text-object query, with the queries it inherits."""
    text = (QUERIES / f"{lang}.scm").read_text()
    m = INHERITS.match(text)
    if m:
        text = "\n".join(query_text(x) for x in m.group(1).split(",")) + "\n" + text
    return text


@functools.lru_cache(maxsize=None)
def query(lang):
    return Query(LANGUAGES[lang], query_text(lang))


# Implements [CPO§T66]
def marks(lang, root):
    """The declarations a language's text-object query finds in a tree,
    as {(start, end, type): (kind, name)}, mapped onto Concipio's kinds: a
    function, or a method where the grammar says so; a class that holds
    functions, or any class or module of a language whose classes hold
    them, as a scope that names its contents; and a C-family record type
    holding only data, as a span named by its keyword."""
    caps = QueryCursor(query(lang)).captures(root)
    fns = {key(n): n for n in caps.get("function.outer", [])}
    out = {}
    for k, node in fns.items():
        inner = next((c for c in node.named_children if key(c) in fns), None)
        if node.type in SIGNATURES:
            continue  # a prototype or signature declares a function; it is not one
        if node.parent is not None and key(node.parent) in fns:
            continue  # the decorated definition around it stands for it
        target = inner or node
        name = declared_name(target)
        if name:
            out[k] = ("method" if "method" in target.type else "function", name)
    for node in caps.get("class.outer", []):
        record = node.type.endswith("_specifier") or node.type in RECORDS
        if record and within(node, ("field_declaration", "function_definition",
                                    "function_item", "function_declaration",
                                    "method_declaration")):
            continue  # a record in another's fields, or in a function, is part of it
        word = node.type.split("_")[0]
        holds = any(node.start_byte <= f.start_byte and f.end_byte <= node.end_byte
                    for f in fns.values() if f is not node)
        name = declared_name(node)
        if record and not holds:
            out[key(node)] = (word, f"{word} {name or '(anonymous)'}")
        elif name:
            out[key(node)] = (f"{word} scope", name)
    return out


# Record types that hold only data, named by their keyword: C's and C++'s are
# `*_specifier`; these are the other languages'.
RECORDS = {"struct_item", "enum_item", "union_item",   # Rust
           "type_declaration"}                          # Go, whose name is inside
# Declarations of a function that has no body here.
SIGNATURES = {"declaration", "function_signature_item"}


def key(node):
    return node.start_byte, node.end_byte, node.type


def walk_nodes(node):
    """A node and everything below it."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def within(node, types):
    """Whether any node around this one is of one of these types."""
    p = node.parent
    while p is not None:
        if p.type in types:
            return True
        p = p.parent
    return False


def declared_name(node):
    """A declaration's name: its `name` field, or the identifier inside its
    declarator."""
    name = node.child_by_field_name("name")
    if name is not None:
        # A Go method is known by its receiver's type, as `Ring.Take`, since
        # many types have a `String` or a `Close`.
        receiver = node.child_by_field_name("receiver") if node.type == "method_declaration" \
            else None
        owner = receiver and next((n for n in walk_nodes(receiver)
                                   if n.type == "type_identifier"), None)
        return f"{node_text(owner)}.{node_text(name)}" if owner else node_text(name)
    d = node.child_by_field_name("declarator")
    if d is not None:
        return declarator_name(d)
    # Rust names an `impl` by its type; Go names a type inside its spec.
    t = node.child_by_field_name("type")
    if node.type == "impl_item" and t is not None:
        trait = node.child_by_field_name("trait")
        return f"{node_text(trait)} for {node_text(t)}" if trait is not None else node_text(t)
    spec = next((c for c in node.named_children if c.type == "type_spec"), None)
    if spec is not None and spec.child_by_field_name("name") is not None:
        return node_text(spec.child_by_field_name("name"))
    return None


# Implements [CPO§T68]
def classify(lang, node, found=None):
    """Return (kind, name) if the node is a named declaration or a scope
    that names its contents, else None, from the language's query [T66]
    and the few things a query does not mark: C's macros and typedefs, and
    Ruby's blocks, such as RSpec's."""
    if found is not None and key(node) in found:
        return found[key(node)]
    if lang in ("c", "cpp"):
        t = node.type
        if t == "type_definition":
            return "typedef", declarator_name(node.child_by_field_name("declarator"))
        if t in ("preproc_def", "preproc_function_def"):
            return "macro", node_text(node.child_by_field_name("name"))
        return None
    if lang == "ruby" and node.type == "call" and node.child_by_field_name("block"):
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
                                                   "type_identifier", "qualified_identifier",
                                                   "destructor_name", "operator_name"):
        node = node.child_by_field_name("declarator")
    return node_text(node)


def declarations(lang, text):
    """Return a list of (start, end, kind, name, ancestors) for every
    classified node, with 1-based inclusive line numbers."""
    tree = Parser(LANGUAGES[lang]).parse(text.encode())
    marked = marks(lang, tree.root_node)
    found = []

    def walk(node, ancestors):
        c = classify(lang, node, marked)
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


# Inside a parse error, a keyword before a parenthesis looks like a call.
KEYWORDS = {"if", "for", "while", "switch", "return", "sizeof", "do", "case", "elif",
            "until", "unless", "typeof", "__typeof__", "defined"}
IDENTIFIER_NODES = {"identifier", "field_identifier", "type_identifier", "constant",
                    "property_identifier"}


# Implements [CPO§T50]
def called(node):
    """Whether an identifier names what a call calls: `f` in `f(x)` and
    `o.f(x)`, or a shell command."""
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "attribute" and parent.child_by_field_name("attribute") == node:
        node, parent = parent, parent.parent
        if parent is None:
            return False
    if parent.type in ("call_expression", "call"):
        target = parent.child_by_field_name("function") or parent.child_by_field_name("method")
        return target == node
    return parent.type == "command_name"


def identifiers(lang, text, fields=None, calls=None):
    """Every name the code itself uses, as (line, name), leaving out its
    comments and strings. Names that are a struct's fields, as in
    `node->parent`, are also added to `fields`, and names that are called
    to `calls`, both as (line, name)."""
    source = text.encode()
    tree = Parser(LANGUAGES[lang]).parse(source)
    out = []
    stack = [tree.root_node]

    def calling(node):
        # A kernel iterator macro, `for_each_possible_cpu(cpu)` with no
        # braces after it, parses as an error, not a call; a name followed
        # by a parenthesis is called all the same.
        return called(node) or (node_text(node) not in KEYWORDS and source[
            node.end_byte:node.end_byte + 64].lstrip()[:1] == b"(")
    while stack:
        node = stack.pop()
        if node.type in IDENTIFIER_NODES or (
                node.type == "word" and node.parent is not None
                and node.parent.type == "command_name"):
            out.append((node.start_point[0] + 1, node_text(node)))
            if fields is not None and node.type in ("field_identifier", "property_identifier") \
                    and not calling(node):
                fields.append(out[-1])
            if calls is not None and calling(node):
                calls.append(out[-1])
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


ASSERTS = re.compile(r"assert|BUG_ON|WARN_ON|BUILD_BUG|CHECK|ensure|must", re.I)
EXITS = {"return_statement", "goto_statement", "break_statement", "continue_statement",
         "return", "raise_statement", "raise", "break", "next"}
STATEMENT = re.compile(r"(_statement|^assignment|^call)$")


@functools.lru_cache(maxsize=32)
def parse(lang, text):
    """A parse tree, kept for the few files a report asks about again."""
    return Parser(LANGUAGES[lang]).parse(text.encode())


ROLES = ["guard", "guard (signature)", "body", "output", "signature"]


def function_node(tree, line):
    """The function or method that starts on a line."""
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.start_point[0] + 1 == line and node.type in (
                "function_definition", "method", "singleton_method", "preproc_function_def"):
            return node
        if node.start_point[0] + 1 <= line <= node.end_point[0] + 1:
            stack.extend(node.children)
    return None


def parameters(node):
    """A function's parameters, {name: type}: a C parameter's type is its
    declaration without the name, and other languages' are their names."""
    plist = None
    stack = [node]
    while stack and plist is None:
        n = stack.pop(0)
        if n.type in ("parameter_list", "parameters", "method_parameters"):
            plist = n
        elif n.type != "compound_statement" and n.type != "block":
            stack.extend(n.children)
    out = {}
    for p in plist.named_children if plist else ():
        if p.type == "parameter_declaration":
            name = declarator_name(p.child_by_field_name("declarator"))
            if name:
                out[name] = " ".join(node_text(p).replace(name, "").split())
        else:
            name = node_text(p).split("=")[0].strip(" *&:")
            out[name] = name
    return out


def roles(lang, text, line, unique):
    """What each call and field in the function on a line does, by name
    (fields as `->name`): a guard, an output through a pointer parameter,
    a use of a parameter only this copy has (`unique`), or body. A name
    used several ways takes the role most likely to be a bug."""
    fn = function_node(parse(lang, text), line)
    if fn is None:
        return {}
    params = set(parameters(fn))
    source = text.encode()

    def names_in(node):
        out, stack = set(), [node]
        while stack:
            n = stack.pop()
            if n.type == "identifier":
                out.add(node_text(n))
            stack.extend(n.children)
        return out

    def role(node):
        n, conds = node, set()
        while n is not None and n != fn:
            p = n.parent
            if p is None:
                break
            if p.type in ("assignment_expression", "assignment") and \
                    (left := p.child_by_field_name("left")) is not None and \
                    left.type == "pointer_expression" and names_in(left) & params:
                return "output"
            if p.type in ("if_statement", "if", "unless"):
                cond = p.child_by_field_name("condition")
                if cond is not None:
                    conds |= names_in(cond)
                    if cond.start_byte <= node.start_byte < cond.end_byte and any(
                            c.type in EXITS for c in walk_types(p, cond)):
                        return "guard (signature)" if names_in(cond) & unique else "guard"
            # A check over a parameter only this copy takes may still be
            # drift, so it stays a guard, marked as such.
            if p.type in ("call_expression", "call") and ASSERTS.search(
                    node_text(p.child_by_field_name("function")
                              or p.child_by_field_name("method") or p)[:40]):
                return "guard (signature)" if names_in(p) & unique else "guard"
            if p.type == "assert_statement":
                return "guard (signature)" if names_in(p) & unique else "guard"
            if STATEMENT.search(p.type) and names_in(p) & unique:
                return "signature"
            n = p
        return "signature" if conds & unique else "body"

    rank = {r: i for i, r in enumerate(ROLES)}
    out = {}
    stack = [fn.child_by_field_name("body") or fn]
    while stack:
        node = stack.pop()
        if node.type in IDENTIFIER_NODES:
            after = node_text(node) not in KEYWORDS and \
                source[node.end_byte:node.end_byte + 64].lstrip()[:1] == b"("
            if called(node) or after:
                name = node_text(node)
            elif node.type in ("field_identifier", "property_identifier"):
                name = "->" + node_text(node)
            else:
                continue
            r = role(node)
            if name not in out or rank[r] < rank[out[name]]:
                out[name] = r
        elif "comment" not in node.type and "string" not in node.type:
            stack.extend(node.children)
    return out


def walk_types(node, skip):
    """The descendants of a node, leaving out one subtree."""
    stack = [c for c in node.children if c != skip]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(n.children)


def guards_and_comments(lang, text, line):
    """In the function on a line: its guards, as (first line, last line,
    names the check calls), for conditions that leave early and
    assertions; and its comments, as (first line, last line, text)."""
    fn = function_node(parse(lang, text), line)
    if fn is None:
        return [], []
    guards, comments = [], []
    stack = [fn]
    while stack:
        node = stack.pop()
        rows = (node.start_point[0] + 1, node.end_point[0] + 1)
        if "comment" in node.type:
            comments.append((*rows, node_text(node)))
            continue
        if node.type in ("if_statement", "if", "unless"):
            cond = node.child_by_field_name("condition")
            if cond is not None and any(c.type in EXITS for c in walk_types(node, cond)):
                guards.append((*rows, calls_in(cond)))
        elif node.type == "assert_statement" or (
                node.type == "expression_statement" and node.named_children and
                node.named_children[0].type in ("call_expression", "call") and
                ASSERTS.search(node_text(node.named_children[0])[:40].split("(")[0])):
            guards.append((*rows, calls_in(node)))
        stack.extend(node.children)
    return sorted(guards), sorted(comments)


def calls_in(node):
    """The names a piece of code calls."""
    out, stack = set(), [node]
    while stack:
        n = stack.pop()
        if n.type in IDENTIFIER_NODES and called(n):
            out.add(node_text(n))
        stack.extend(n.children)
    return out


# A line inside a comment block, in the languages Concipio parses.
COMMENT_LINE = re.compile(r"^\s*(/\*|\*|//|#(?!\s*(define|include|if|endif|else)))|\*/\s*$")


def header_comment(text, line):
    """The comment block just above a declaration, as text."""
    lines = text.splitlines()
    out = []
    n = line - 2
    while n >= 0 and COMMENT_LINE.search(lines[n]):
        out.append(lines[n])
        n -= 1
    return "\n".join(reversed(out))
