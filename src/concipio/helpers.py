"""A taxonomy of the helpers no citation covers [CPO§T51]: each sorted by
the design points of the cited code that calls it, with the helpers that
look like each other set beside them as candidates for duplication."""

import fnmatch
import hashlib
import math
import re

from . import docs, lint, spans

KINDS = {"function", "method", "macro"}
FUNCTION_MACRO = re.compile(r"^\s*#\s*define\s+\w+\(")


# Implements [CPO§T51]
def functions(root, files, exclude=(), outer=None):
    """Every function, method, and function-like macro, with the names its
    body uses. Names used outside any function are added to
    `outer`."""
    out = []
    outer = set() if outer is None else outer
    for f in files:
        if any(fnmatch.fnmatch(f, p) for p in exclude):
            continue
        try:
            text = (root / f).read_text(errors="replace")
        except (FileNotFoundError, IsADirectoryError):
            continue
        lang = spans.language_of(f, text)
        if lang is None:
            continue
        lines = text.splitlines()
        decls = spans.declarations(lang, text)
        fields, calls = [], []
        names = spans.identifiers(lang, text, fields, calls)
        bodies = [(a, b) for a, b, k, _, _ in decls if k in KINDS]
        # Names used outside every function, as in a table of callbacks or a
        # script's top level, reach a function no caller does.
        outer.update(n for line, n in names
                     if not any(a <= line <= b for a, b in bodies))
        for start, end, kind, name, ancestors in decls:
            if kind not in KINDS or not name:
                continue
            if kind == "macro" and not FUNCTION_MACRO.match(lines[start - 1]):
                continue
            body = "\n".join(lines[start - 1:end])
            out.append({"path": f, "line": start, "end": end, "name": name, "kind": kind,
                        "uses": {n for line, n in names if start <= line <= end} - {name},
                        "fields": {n for line, n in fields if start <= line <= end},
                        "called": {n for line, n in calls if start <= line <= end} - {name},
                        # The body without its own name, so a copy under
                        # another name prints the same.
                        "print": hashlib.sha256(" ".join(
                            re.sub(rf"\b{re.escape(name)}\b", "", body).split()).encode())
                        .hexdigest()[:16],
                        # Only a top-level function's name is unique
                        # enough to mean another file copied it.
                        "top": not ancestors and not name.startswith("_"),
                        "test": spans.is_test(f), "lang": lang, "text": text, "lines": lines,
                        "decls": decls})
    return out


def key(fn):
    # Two short functions may share a line, as shell's often do.
    return (fn["path"], fn["line"], fn["name"])


def claims(root, fns, defs):
    """The tags each function's citations claim, by the declaration a
    citation documents and everything inside it [T8], and the functions
    exempted [T15]."""
    tags = {key(fn): set() for fn in fns}
    exempt = set()
    where = {}
    for fn in fns:
        where.setdefault(fn["path"], []).append(fn)

    def claim(path, line, mark):
        for fn in where.get(path, ()):
            node = lint.covered_node(fn["decls"], line, fn["lines"])
            if node and node[0] <= fn["line"] and fn["end"] <= node[1]:
                mark(fn)

    for d in defs.values():
        for c in d.citations:
            if not docs.is_doc(c.path):
                claim(c.path, c.line, lambda fn, t=d.tag: tags[key(fn)].add(t))
    for path, mine in where.items():
        for n, line in enumerate(mine[0]["text"].splitlines(), 1):
            if lint.EXEMPT.search(line):
                claim(path, n, lambda fn: exempt.add(key(fn)))
    return tags, exempt


# Implements [CPO§T51]
def taxonomy(root, files, defs, exclude=(), depth=3, macros=False):
    outer = set()
    fns = functions(root, files, exclude, outer)
    by_name = {}
    for fn in fns:
        by_name.setdefault(fn["name"], []).append(fn)

    tags, exempt = claims(root, fns, defs)
    # Calls, by name: a function uses another's name, preferring one
    # defined in its own file, as a C static helper is.
    def callees(fn):
        out = []
        for n in fn["uses"]:
            targets = by_name.get(n, [])
            local = [t for t in targets if t["path"] == fn["path"]]
            out += local or targets
        return out
    callers = {key(fn): [] for fn in fns}
    for fn in fns:
        for t in callees(fn):
            callers[key(t)].append(fn)

    def serves(fn):
        """The tags of the nearest cited code that calls it, each with how
        many of those callers cite it, and how far away they are."""
        seen, frontier = {key(fn)}, [fn]
        for hop in range(1, depth + 1):
            nxt, found = [], {}
            for g in frontier:
                for c in callers[key(g)]:
                    # A test exercises a helper; it is not a design the
                    # helper serves.
                    if key(c) in seen or c["test"]:
                        continue
                    seen.add(key(c))
                    for t in tags[key(c)]:
                        found[t] = found.get(t, 0) + 1
                    if not tags[key(c)]:
                        nxt.append(c)
            if found:
                return found, hop
            frontier = nxt
        return {}, None

    # Macros stay in the call graph, so a guard one copy asserts and another
    # skips still shows, but are not listed unless asked for.
    helpers = [fn for fn in fns if not tags[key(fn)] and key(fn) not in exempt
               and not fn["test"] and (macros or fn["kind"] != "macro")]
    rows = []
    for fn in helpers:
        found, hop = serves(fn)
        rows.append({"path": fn["path"], "line": fn["line"], "name": fn["name"],
                     "lines": fn["end"] - fn["line"] + 1,
                     # The design point most of its cited callers serve
                     # first, as the one it most likely belongs to.
                     "serves": sorted(found, key=lambda t: (-found[t], t)), "hops": hop,
                     "callers": sum(not c["test"] for c in callers[key(fn)]),
                     "tested": any(c["test"] for c in callers[key(fn)]),
                     "outer": fn["name"] in outer,
                     "calls": sorted({t["name"] for t in callees(fn)})})
    # Copies may be cited or not: a cited copy tells a reader which of the
    # differences the design intends [T56].
    copies = [fn for fn in fns if key(fn) not in exempt and not fn["test"]
              and (macros or fn["kind"] != "macro")]

    def through(fn):
        """The cited functions it calls, as {name: tags}."""
        return {t["name"]: tags[key(t)] for t in callees(fn) if tags[key(t)] and t is not fn}
    return rows, look_alikes(copies, key, tags, through)


# Implements [CPO§T52]
def look_alikes(helpers, key, tags=None, through=None):
    """Clusters of functions that may duplicate one another: the same body,
    the same top-level name in other files, or mostly the same rare calls,
    each with what it cites. The clusters claiming the most lines come
    first."""
    tags = tags or {}
    parent = {key(fn): key(fn) for fn in helpers}
    why = {}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def join(a, b, reason):
        ra, rb = find(key(a)), find(key(b))
        if ra != rb:
            parent[rb] = ra
            why.setdefault(ra, set()).update(why.pop(rb, set()))
        why.setdefault(ra, set()).add(reason)

    groups = {}
    for fn in helpers:
        # A shell script and a C file may share a name or a call by chance.
        groups.setdefault(("the same body", fn["lang"], fn["print"]), []).append(fn)
        if fn["top"]:
            groups.setdefault(("the same name", fn["lang"], fn["name"]), []).append(fn)
    for (reason, _, _), fs in groups.items():
        if len(fs) > 1 and (reason == "the same body" or len({f["path"] for f in fs}) > 1):
            for f in fs[1:]:
                join(fs[0], f, reason)
    # What each one calls, defined in the project or not, as the kernel's
    # own API is not.
    calls = {key(fn): fn["called"] for fn in helpers}
    # A call many helpers make, such as a logger, says little; a rare one
    # two helpers share says much. Each name weighs as its inverse document
    # frequency, gently, so that one guard a single copy adds does not
    # outweigh all the calls the copies share.
    freq = {}
    for c in calls.values():
        for n in c:
            freq[n] = freq.get(n, 0) + 1

    def weight(names):
        return sum(math.log(1 + len(helpers) / freq[n]) for n in names)
    # Only pairs sharing a call are compared, found through each call's
    # callers, so a large project is not compared all against all.
    by_call = {}
    for i, fn in enumerate(helpers):
        if len(calls[key(fn)]) >= 3:
            for n in calls[key(fn)]:
                by_call.setdefault(n, []).append(i)
    pairs = set()
    for idx in by_call.values():
        if len(idx) <= 200:
            pairs.update((x, y) for j, x in enumerate(idx) for y in idx[j + 1:])
    for i, j in sorted(pairs):
        a, b = helpers[i], helpers[j]
        ca, cb = calls[key(a)], calls[key(b)]
        if a["lang"] == b["lang"] and weight(ca & cb) >= 0.6 * weight(ca | cb):
            join(a, b, "mostly the same calls")
    clusters = {}
    for fn in helpers:
        clusters.setdefault(find(key(fn)), []).append(fn)

    def cites(f):
        # A copy that cites nothing may still call one that does, as a
        # claim calls the ownership check that implements the rule.
        if tags.get(key(f)):
            return f" (cites {', '.join(sorted(tags[key(f)]))})"
        via = through(f) if through else {}
        if not via:
            return ""
        return " (calls cited " + "; ".join(f"{n}: {', '.join(sorted(t))}"
                                            for n, t in sorted(via.items())) + ")"
    out = [{"why": sorted(why[k]), "lines": sum(f["end"] - f["line"] + 1 for f in fs),
            "helpers": [f"{f['path']}:{f['line']} {f['name']}" + cites(f) for f in fs],
            "cited": sum(bool(tags.get(key(f))) for f in fs),
            "differ": differences(fs, calls, key)}
           for k, fs in clusters.items() if len(fs) > 1]
    return sorted(out, key=lambda c: -c["lines"])


# Implements [CPO§T53]
def differences(fs, calls, key):
    """What some copies in a cluster do and others do not: the calls and
    fields only some use, grouped by which copies use them and by the role
    they play there, guards first. Copies that have drifted apart are where
    a guard one has and another lacks hides; an output or a parameter only
    one copy has explains a difference without drift [T55]."""
    used = [calls[key(f)] | {"->" + n for n in f["fields"]} for f in fs]
    every = set.intersection(*used)
    # A parameter is this copy's own when no other copy has one of its
    # type, so a renamed parameter is still shared.
    params = []
    for f in fs:
        fn = spans.function_node(spans.parse(f["lang"], f["text"]), f["line"])
        params.append(spans.parameters(fn) if fn else {})
    roles = []
    for i, f in enumerate(fs):
        others = [t for j, ps in enumerate(params) if j != i for t in ps.values()]
        unique = {n for n, t in params[i].items() if t not in others}
        roles.append(spans.roles(f["lang"], f["text"], f["line"], unique))
    rank = spans.ROLES
    holders = {}
    for name in set.union(*used) - every:
        who = tuple(i for i, u in enumerate(used) if name in u)
        role = min((roles[i].get(name, "body") for i in who), key=rank.index)
        holders.setdefault((who, role), []).append(name)
    out = []
    for (who, role), names in sorted(holders.items(),
                                     key=lambda h: (rank.index(h[0][1]), len(h[0][0]), h[0][0])):
        if len(who) <= len(fs) / 2:
            label = "only in " + ", ".join(fs[i]["name"] for i in who)
        else:
            label = "missing from " + ", ".join(
                fs[i]["name"] for i in range(len(fs)) if i not in who)
        out.append({"where": label, "role": role, "names": sorted(names)})
    return out


INCIDENT = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|#\d+\b|\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,12}\b|"
    # Words a storage system's design uses for its own subject, such as
    # crash or torn, would mark every guard, so only the words of an
    # incident report are here.
    r"\b(bugs?|races?|racy|corrupt(s|ed|ion)?|regression|deadlocks?|"
    r"use[- ]after[- ]free|double[- ]free|data[- ]integrity|postmortem)\b", re.I)


# Implements [CPO§T58]
def unwritten_rules(root, files, defs, exclude=(), incident=(), everything=False):
    """Guards in code citing no design whose comment says why they exist:
    each is a rule someone found and wrote down only where it is enforced.
    A comment naming an incident, a date, a bug, an issue, or a commit,
    is the surest sign; with `everything`, any comment of a dozen words
    beside a guard counts."""
    marker = re.compile("|".join([INCIDENT.pattern, *incident]), re.I)
    fns = [fn for fn in functions(root, files, exclude)
           if not fn["test"] and fn["kind"] != "macro"]
    tags, exempt = claims(root, fns, defs)
    by_name = {}
    for fn in fns:
        by_name.setdefault(fn["name"], []).append(fn)

    def flat(text):
        return " ".join(text.replace("/*", " ").replace("*/", " ").replace("//", " ")
                        .replace("*", " ").replace("#", " ").split())

    def predicate(fn, names):
        """A function the guard calls whose header comment names an
        incident, cites nothing itself, and so is the guard's evidence."""
        for n in sorted(names):
            targets = by_name.get(n, [])
            for t in [t for t in targets if t["path"] == fn["path"]] or targets:
                if tags[key(t)] or key(t) in exempt:
                    continue
                head = flat(spans.header_comment(t["text"], t["line"]))
                found = sorted({m.group(0) for m in marker.finditer(head)}, key=str.lower)
                if found:
                    return t, head, found
        return None

    out = []
    for fn in fns:
        if tags[key(fn)] or key(fn) in exempt:
            continue
        guards, comments = spans.guards_and_comments(fn["lang"], fn["text"], fn["line"])
        lines = fn["text"].splitlines()
        told = set()
        for g0, g1, names in guards:
            # A predicate's own header may say why the check exists, as a
            # long "why" comment above a short `if (!ours(...)) goto out;`.
            via = predicate(fn, names - {fn["name"]})
            if via:
                t, head, found = via
                out.append({"path": fn["path"], "line": g0, "function": fn["name"],
                            "guard": lines[g0 - 1].strip(), "comment": head, "markers": found,
                            "evidence": f"{t['path']}:{t['line']} {t['name']}"})
                continue
            # A comment explains a guard when it ends just above it, or
            # sits on its lines, as a trailing note on an early return does.
            # One comment over two guards is reported once.
            near = [c for c in comments
                    if (g0 - 3 <= c[1] < g0 or g0 <= c[0] <= g1) and c[0] not in told]
            if not near:
                continue
            told.update(c[0] for c in near)
            words = flat(" ".join(c[2] for c in near))
            found = sorted({m.group(0) for m in marker.finditer(words)}, key=str.lower)
            if found or (everything and len(words.split()) >= 12):
                out.append({"path": fn["path"], "line": g0, "function": fn["name"],
                            "guard": lines[g0 - 1].strip(), "comment": words,
                            "markers": found, "evidence": None})
    # A predicate's rule is one rule however many guards call it: report
    # it once, with every guard that relies on it.
    merged, seen = [], {}
    for r in sorted(out, key=lambda r: (not r["markers"], r["path"], r["line"])):
        if r["evidence"] in seen:
            seen[r["evidence"]]["also"].append(f"{r['path']}:{r['line']} {r['function']}")
            continue
        r["also"] = []
        if r["evidence"]:
            seen[r["evidence"]] = r
        merged.append(r)
    return merged
