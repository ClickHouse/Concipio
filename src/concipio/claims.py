"""Comments that claim a state cannot happen, and whether anything backs
them [CPO§T63]. A claim of impossibility is the comment most likely to
hide a defect: once written, nobody tests the state it rules out."""

import re

from . import helpers, lint, spans

CLAIMS = [r"unreachable", r"can ?not happen", r"can't happen", r"cannot be exhausted",
          r"should never (?:fire|happen|occur|be reached)", r"never (?:fires|happens|occurs)",
          r"impossible", r"sizing says", r"by construction", r"cannot (?:overflow|fail)",
          r"never reach(?:ed|es)?", r"can never"]
# Code that asserts a branch is dead, with or without a comment saying so.
MARKERS = [r"__builtin_unreachable\s*\(", r"\bunreachable!\s*\(", r"\bBUG\s*\(\s*\)",
           r"\b\w*ASSERT\w*\s*\(\s*(?:0|false)\s*[,)]"]
# What backs a claim: a test it names, or an assertion the compiler checks.
TESTS = [r"\btests?/[\w./-]*\w", r"\b[\w-]*tests?[\w-]*\.(?:c|h|py|rb|sh|go|rs)\b",
         r"\bscenario_\w+", r"\btest_\w+"]
STATIC = re.compile(r"\b(?:static_assert|_Static_assert|BUILD_BUG_ON\w*)\s*\(")


def comments(lang, text):
    """A file's comments as (first line, last line, text), with runs of
    line comments joined into one."""
    tree = spans.parse(lang, text)
    found, stack = [], [tree.root_node]
    while stack:
        node = stack.pop()
        if "comment" in node.type:
            found.append((node.start_point[0] + 1, node.end_point[0] + 1, spans.node_text(node)))
        else:
            stack.extend(node.children)
    found.sort()
    out = []
    for c in found:
        if out and c[0] == out[-1][1] + 1 and c[2].lstrip().startswith(("//", "#")) \
                and out[-1][2].lstrip().startswith(("//", "#")):
            out[-1] = (out[-1][0], c[1], out[-1][2] + "\n" + c[2])
        else:
            out.append(c)
    return out


def sentence(text, start, end):
    """The sentence around a match, flattened."""
    a = max(text.rfind(".", 0, start), text.rfind("\n\n", 0, start)) + 1
    b = text.find(".", end)
    return " ".join(re.sub(r"(/\*+|\*+/|^\s*\*|//+|#)", " ", text[a:b + 1 if b >= 0 else None],
                           flags=re.M).split())


# Implements [CPO§T63]
def impossibility_claims(root, files, defs, exclude=(), cfg=None):
    """Every comment that claims a state cannot happen, and every branch
    the code asserts is dead, each with the evidence that backs it: a test
    the comment names, a static assertion beside it, or a cited design
    point that tests cite. One with none is unbacked."""
    cfg = cfg or {}
    claim = re.compile("|".join(CLAIMS + cfg.get("claims", [])), re.I)
    marker = re.compile("|".join(MARKERS + cfg.get("markers", [])))
    named = re.compile("|".join(TESTS + cfg.get("evidence", [])))
    tested = {t for t, d in defs.items() if any(c.role == "test" for c in d.citations)}
    cited = {}
    for t, d in defs.items():
        for c in d.citations:
            cited.setdefault(c.path, []).append((c.line, t))
    fns = [fn for fn in helpers.functions(root, files, exclude) if not fn["test"]]
    by_path = {}
    for fn in fns:
        by_path.setdefault(fn["path"], []).append(fn)
    out = []
    for path, mine in by_path.items():
        text, lang, lines = mine[0]["text"], mine[0]["lang"], mine[0]["lines"]

        def owner(line, last=None):
            """The function a line is in, or the one a comment ending on
            `last` sits just above."""
            inside = [f for f in mine if f["line"] <= line <= f["end"]]
            if inside:
                return min(inside, key=lambda f: f["end"] - f["line"])["name"]
            below = [f for f in mine if last is not None and last < f["line"] <= last + 3]
            return min(below, key=lambda f: f["line"])["name"] if below else None

        def evidence(first, last, body):
            m = named.search(body)
            if m:
                return f"names {m.group(0)}"
            near = "\n".join(lines[max(0, first - 4):min(len(lines), last + 3)])
            m = STATIC.search(near)
            if m:
                return f"beside {m.group(0).rstrip('(').strip()}"
            for line, tag in cited.get(path, ()):
                if first <= line <= last and tag in tested:
                    return f"cites {tag}, which tests cite"
            return None

        blocks = comments(lang, text)
        for first, last, body in blocks:
            for m in claim.finditer(body):
                line = first + body.count("\n", 0, m.start())
                out.append({"path": path, "line": line, "function": owner(line, last),
                            "claim": m.group(0), "text": sentence(body, m.start(), m.end()),
                            "evidence": evidence(first, last, body)})
        for n, code in enumerate(lines, 1):
            m = marker.search(code)
            if not m or any(a <= n <= b and code.lstrip().startswith(("/*", "*", "//", "#"))
                            for a, b, _ in blocks):
                continue
            # The comment just above a dead branch says why it is dead.
            above = [b for b in blocks if n - 3 <= b[1] < n or b[0] <= n <= b[1]]
            first, last, body = above[-1] if above else (n, n, "")
            out.append({"path": path, "line": n, "function": owner(n), "claim": m.group(0),
                        "text": " ".join(code.split()),
                        "evidence": evidence(first, max(last, n), body)})
    # A claim and the marker its comment explains are one claim.
    seen, merged = set(), []
    for r in sorted(out, key=lambda r: (r["path"], r["line"])):
        k = (r["path"], r["function"], r["text"])
        if k not in seen:
            seen.add(k)
            merged.append(r)
    return merged


# Implements [CPO§T64]
def lint_problems(root, files, defs, cfg):
    """Unbacked claims as lint problems, when `.cpo` opts in, keyed by
    function and claim so a baseline keeps them across edits."""
    opts = cfg.get("unreachable", {})
    if not opts.get("lint"):
        return []
    rows = impossibility_claims(root, files, defs, cfg.get("exclude", []), opts)
    out, count = [], {}
    for r in rows:
        if r["evidence"]:
            continue
        k = f"{r['function'] or '(file scope)'}: {r['claim'].lower()}"
        count[k] = count.get(k, 0) + 1
        out.append(lint.Problem(r["path"], r["line"], "unbacked-claim",
                                f'"{r["claim"]}" is claimed but backed by no named test, static '
                                "assertion, or tested design point",
                                k if count[k] == 1 else f"{k} #{count[k]}", 1))
    return out
