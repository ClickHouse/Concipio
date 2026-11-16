"""Named audits: a worklist of design units that agents claim, check
against the code they name or cite, and record, kept as glue in the
store so it survives an agent's compaction [CPO§W2, CPO§W8, CPO§W21]."""

import contextlib
import os
import re
import subprocess
import time
from pathlib import Path

from . import docs, lint, records, spans

CLAIM_SECONDS = 2 * 3600
# Which rules decide what a unit claims; a record made under older ones is
# fingerprinted again, at its own commit, before it is compared.
RULES = 4
# What a harness sets for the commands it runs, by the name of its process.
HARNESS_IDS = [("claude", "CLAUDE_CODE_SESSION_ID"), ("codex", "CODEX_THREAD_ID"),
               ("pi", "PI_SESSION_ID")]
TICKED = re.compile(r"`([^`\n]+)`")
PATHLIKE = re.compile(r"^[\w./-]+\.\w+$")


# Implements [CPO§W27]
def agent():
    """Who is asking: `$CPO_AGENT`, or else the session of the nearest
    harness among this process's ancestors. A harness passes its own
    variables to the harnesses it starts, so the nearest one decides.
    Returns (id, where it came from), or (None, why not)."""
    if os.environ.get("CPO_AGENT"):
        return os.environ["CPO_AGENT"], "CPO_AGENT"
    pid = os.getppid()
    for _ in range(32):
        try:
            out = subprocess.run(["ps", "-o", "ppid=,command=", "-p", str(pid)],
                                 capture_output=True, text=True).stdout.split()
        except OSError:
            # A sandbox may forbid `ps`. Codex marks what runs in its
            # sandbox, and a command in it has Codex as its nearest harness.
            if os.environ.get("CODEX_SANDBOX") and os.environ.get("CODEX_THREAD_ID"):
                return os.environ["CODEX_THREAD_ID"], "CODEX_THREAD_ID"
            return None, "cannot see this process's ancestors"
        if len(out) < 2:
            break
        # A harness written in Node runs as `node .../bin/pi`, so its
        # script's name counts as well as the executable's.
        names = {Path(w).name for w in out[1:3]}
        for harness, var in HARNESS_IDS:
            if any(n == harness or n.startswith(harness + "-") for n in names):
                value = os.environ.get(var)
                return (value, var) if value else (None, f"{harness} sets no {var}")
        if names & {"antigravity", "agy"}:
            return None, "Antigravity sets no session ID"
        pid = int(out[0])
        if pid <= 1:
            break
    return None, "no harness found among this process's ancestors"


def contact():
    """How another agent can reach the claimant, where the harness says."""
    return os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET")


def code_index(root, files):
    """Every declaration in the code, by name, as (path, first, last)."""
    out = {}
    for f in files:
        if docs.is_doc(f):
            continue
        found = decls_of(root, f)
        for start, end, kind, name, _ in found[0] if found else ():
            if name and not kind.endswith("scope"):
                out.setdefault(name.split()[-1], []).append((f, start, end))
    return out


TAGGED = re.compile(r"^(?:struct|union|enum|class)\s+")


def named(text):
    """The declaration a backticked name gives: `f()` names `f`, and
    `struct s` names `s`, as the code index files a record by its name."""
    return TAGGED.sub("", text.strip().rstrip("()")).strip()


# Implements [CPO§Y12, CPO§Y18]
def claimed_code(root, d, index, tracked):
    """The code a unit claims: declarations its text names in backticks,
    and the code citing it. A name defined in many places names none of
    them. A file the text names is a pointer, not a claim on the whole
    file [CPO§W2]."""
    regions = set()
    names = {named(m.group(1)) for m in TICKED.finditer(d.text)}
    names = {n for n in names if re.fullmatch(r"[A-Za-z_]\w*", n)}
    for token in names:
        if 0 < len(index.get(token, ())) <= 3:
            for path, start, end in index[token]:
                regions.update(windows(root, path, start, end, names - {token}))
    for c in d.citations:
        if docs.is_doc(c.path):
            continue
        # A citation covers the declaration its comment documents [T8].
        found = decls_of(root, c.path)
        node = lint.covered_node(found[0], c.line, found[1]) if found else None
        if not node:
            regions.add((c.path, c.line, c.line))
        elif node[0] < c.line <= node[1] and node[1] - node[0] >= LARGE:
            # A comment inside a large declaration cites what follows it.
            regions.add((c.path, c.line, min(c.line + WINDOW - 1, node[1])))
        else:
            regions.update(windows(root, c.path, node[0], node[1], names))
    return sorted(regions, key=lambda r: (r[0], r[1] or 0))


LARGE = 80
WINDOW = 24


# Implements [CPO§W39]
def windows(root, path, start, end, names):
    """The parts of a declaration a unit claims. A small one is claimed
    whole; of a large one, the stretches that start at a line using a
    name the unit's text gives, or else its head, so an edit elsewhere in
    a long function does not stale every unit that mentions it."""
    if end - start < LARGE:
        return [(path, start, end)]
    lines = decls_of(root, path)[1]
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, sorted(names))) + r")\b") \
        if names else None
    out = [(path, n, min(n + WINDOW - 1, end)) for n in range(start + 1, end + 1)
           if pattern and pattern.search(lines[n - 1])]
    return out or [(path, start, min(start + WINDOW - 1, end))]


_decls = {}
_lines = {}


def stamp(root, path):
    """What changes when a file does, so a cache read once per process
    still sees an edit made since."""
    try:
        st = (root / path).stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    return st.st_mtime_ns, st.st_size


def lines_in(root, path):
    """A file's lines, read once until it changes."""
    key = (str(root), path)
    now = stamp(root, path)
    if key not in _lines or _lines[key][0] != now:
        try:
            text = (root / path).read_text(errors="replace")
        except (FileNotFoundError, IsADirectoryError):
            text = None
        _lines[key] = (now, text)
    return _lines[key][1]


def decls_of(root, path):
    """A code file's declarations and lines, parsed once until it changes."""
    key = (str(root), path)
    now = stamp(root, path)
    if key not in _decls or _decls[key][0] != now:
        text = lines_in(root, path)
        lang = spans.language_of(path, text) if text is not None else None
        _decls[key] = (now, (spans.declarations(lang, text), text.splitlines())
                       if lang else None)
    return _decls[key][1]


def pointers(d, tracked):
    """The files a unit's text names, for the brief to point at."""
    return sorted({m.group(1).strip() for m in TICKED.finditer(d.text)
                   if PATHLIKE.match(m.group(1).strip()) and m.group(1).strip() in tracked})


def region_text(root, region):
    path, start, end = region
    lines = (lines_in(root, path) or "").splitlines()
    return "\n".join(lines[(start or 1) - 1:end or len(lines)])


def unit_print(root, d, regions):
    """A fingerprint of a unit's text and of the code it claims, which
    changes when either does."""
    parts = [d.text] + [f"{r[0]}\n{region_text(root, r)}" for r in regions]
    return records.fingerprint("\n\0\n".join(parts))


def units(root, defs, scope=()):
    """The units of an audit: the sections of declared sources, and the
    statements of other design docs, in the order the docs give them."""
    sources = {s["doc"] for s in docs.sources(root)}
    out = [d for d in defs.values()
           if (d.path in sources and d.heading) or (d.path not in sources and not d.children)]
    if scope:
        out = [d for d in out if any(d.path == s or d.path.startswith(s.rstrip("/") + "/")
                                     or d.tag == s for s in scope)]
    return sorted(out, key=lambda d: (d.path, d.line))


class Audit:
    """One named audit's state in the store."""

    def __init__(self, store, name):
        self.store, self.name = store, name
        self.rel = f"audits/{name}.json"

    def load(self):
        return self.store.read(self.rel, {"units": {}, "claims": {}})

    def save(self, state):
        self.store.write(self.rel, state)
        return state

    def log(self, record):
        self.store.append(f"audits/{self.name}.log.jsonl", dict(record, at=int(time.time())))


def standing(state, tag, fp, now=None):
    """Where a unit stands: verified, stale, finding, question, claimed,
    or open."""
    now = now or int(time.time())
    out = state["units"].get(tag)
    claim = state["claims"].get(tag)
    if claim and claim["until"] > now:
        held = "claimed"
    else:
        held = None
    if out:
        if out.get("print") != fp:
            return held or "stale"
        return out["status"]
    return held or "open"


def unit_name(defs, name):
    """A unit as the agent wrote it, which a shell makes awkward to type
    with a `§`: `DESIGN1b` or `DESIGN:1b` for `DESIGN§1b`, or `1b` alone
    when one doc numbers a section so. Anything else is left as it is."""
    if name in defs or "§" in name or "/" in name:
        return name
    plain = name.replace(":", "")
    match = [t for t in defs if t.replace("§", "") == plain] or \
        [t for t in defs if t.split("§", 1)[1] == name]
    return match[0] if len(match) == 1 else name


def head(root):
    return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=root,
                          capture_output=True, text=True).stdout.strip()


def survey(root, defs, scope=(), files=None):
    """Every unit with the code it claims and its fingerprint."""
    files = files if files is not None else docs.tracked_files(root)
    index, tracked = code_index(root, files), set(files)
    out = []
    for d in units(root, defs, scope):
        regions = claimed_code(root, d, index, tracked)
        d.pointers = pointers(d, tracked)
        out.append((d, regions, unit_print(root, d, regions)))
    return out


def lines_of(root, regions):
    """The lines of code regions claim, as (path, line), so that code two
    units both claim counts once."""
    out = set()
    for path, start, end in regions:
        if start is None:
            found = decls_of(root, path)
            start, end = 1, len(found[1]) if found else len(region_text(root, (path, None, None))
                                                             .splitlines())
        out.update((path, n) for n in range(start, end + 1))
    return out


# Implements [CPO§W40]
DRAFT_LINES = 300


class Draft:
    """A run of one file's declarations that no unit claims, for an agent
    to describe in the design [CPO§W40]."""

    def __init__(self, root, path, decls):
        self.path, self.decls = path, decls
        self.line = decls[0][0]
        self.tag = f"draft:{path}:{decls[0][3] or decls[0][0]}"
        names = [d[3] for d in decls if d[3]]
        self.name = ", ".join(names) if len(names) <= 6 else \
            ", ".join(names[:5]) + f", and {len(names) - 5} more"
        self.regions = [(path, a, b) for a, b, _, _ in decls]
        self.print = records.fingerprint("\n\0\n".join(region_text(root, r)
                                                       for r in self.regions))


def outermost(found):
    """A file's top-level declarations; a scope too large for one unit,
    such as a long class, gives its members instead."""
    out = []

    def take(d):
        if d[2].endswith("scope") and d[1] - d[0] >= DRAFT_LINES:
            inner = [c for c in found if len(c[4]) == len(d[4]) + 1
                     and c[4][-1] == (d[2], d[3]) and d[0] <= c[0] <= d[1]]
            if inner:
                for c in inner:
                    take(c)
                return
        out.append(d)

    for d in found:
        if not d[4]:
            take(d)
    return sorted(out)


SCRIPTS = {"bash", "perl"}


def guard(d, lines):
    """Whether a declaration is a header's include guard, which no design
    describes."""
    return d[2] == "macro" and bool(d[3]) and lines[d[0] - 1].split() == ["#define", d[3]] \
        and any(line.split() == ["#ifndef", d[3]] for line in lines[:d[0]])


def exempted(found, lines, rules=(), path=None):
    """The declarations marked as serving no design: by a `CPO§exempt`
    comment, or by an `[[exempt]]` rule in `.cpo` [CPO§T76], which may
    exempt a whole file."""
    out = {(a, b) for a, b, _ in lint.config_exemptions(rules, path, found)} if path else set()
    if (1, 10 ** 9) in out:
        return {(d[0], d[1]) for d in found}
    for n, line in enumerate(lines, 1):
        if lint.EXEMPT.search(line):
            node = lint.covered_node(found, n, lines)
            if node:
                out.add((node[0], node[1]))
    return out


def drafts(root, files, everything, exclude=()):
    """The code no unit of the design claims and nobody exempts, in runs
    of a file's top-level declarations that fit a brief. Tests are not
    drafted; they are evidence for the design, not part of it."""
    import fnmatch
    claimed = lines_of(root, [r for _, regions, _ in everything for r in regions])
    rules = docs.config(root).get("exempt", [])
    out, seen = [], set()
    for f in files:
        if docs.is_doc(f) or spans.is_test(f) or any(fnmatch.fnmatch(f, p) for p in exclude):
            continue
        got = decls_of(root, f)
        if not got:
            continue
        found, lines = got
        skip = exempted(found, lines, rules, f)
        run, size = [], 0
        for d in outermost(found):
            a, b = d[0], d[1]
            if (a, b) in skip or guard(d, lines) or \
                    any((f, n) in claimed for n in range(a, b + 1)):
                continue
            if run and size + b - a + 1 > DRAFT_LINES:
                out.append(Draft(root, f, run))
                run, size = [], 0
            run.append((a, b, d[2], d[3]))
            size += b - a + 1
        if run:
            out.append(Draft(root, f, run))
    # Scripts that drive the code come after it.
    out.sort(key=lambda x: spans.language_of(x.path, "") in SCRIPTS)
    for x in out:
        # Overloads can give two runs one name; the line tells them apart.
        if x.tag in seen:
            x.tag += f"@{x.line}"
        seen.add(x.tag)
    return out


def under_scope(path, scope):
    return not scope or any(path == s or path.startswith(s.rstrip("/") + "/") for s in scope)


# Implements [CPO§W44]
def add_lead(state, text, where=None, by=None):
    """Add a lead, unless one with the same text and place exists."""
    leads = state.setdefault("leads", {})
    for tag, lead in leads.items():
        if lead["text"] == text and lead.get("where") == where:
            return tag
    tag = f"lead-{len(leads) + 1}"
    leads[tag] = {"text": text, "where": where, "by": by, "at": int(time.time())}
    return tag


def seed_leads(root, defs, state, files):
    """An audit's first leads: every claim that a state cannot happen that
    nothing backs, and every rule a guard keeps that no design records."""
    from . import claims, helpers
    cfg = docs.config(root)
    exclude = cfg.get("exclude", [])
    for r in claims.impossibility_claims(root, files, defs, exclude, cfg.get("unreachable", {})):
        if not r["evidence"]:
            add_lead(state, f"Nothing backs this claim that a state cannot happen "
                            f"[{r['claim']}]: {r['text']}", f"{r['path']}:{r['line']}",
                     "cpo unreachable")
    for r in helpers.unwritten_rules(root, files, defs, exclude,
                                     cfg.get("unwritten", {}).get("incident", [])):
        add_lead(state, f"A guard keeps a rule no design records, `{r['guard'][:100]}`: "
                        f"{r['comment']}", f"{r['path']}:{r['line']}", "cpo unwritten")


def lead_print(lead):
    return records.fingerprint(lead["text"] + "\0" + (lead.get("where") or ""))


def lead_code(root, where):
    """The code around a lead: its declaration if small, else the lines
    around it."""
    if not where or ":" not in where:
        return []
    path, _, line = where.rpartition(":")
    if not line.isdigit() or not (root / path).is_file():
        return []
    line = int(line)
    found = decls_of(root, path)
    node = lint.covered_node(found[0], line, found[1]) if found else None
    if node and node[1] - node[0] < LARGE:
        return [(path, node[0], node[1])]
    return [(path, max(1, line - 12), line + 12)]


def outline(defs, root):
    """The headings of the design so far, for a drafting brief."""
    sources = {s["doc"] for s in docs.sources(root)}
    return [f"{d.tag} {d.name}" for d in sorted(defs.values(), key=lambda d: (d.path, d.line))
            if d.path in sources and d.heading]


NO_AGENT = ("Concipio cannot tell which agent is asking ({why}). Run\n"
            "  export CPO_AGENT={token}\n"
            "and keep that line in any summary of your work, so a compacted context can "
            "resume its claims. A helper you start needs its own CPO_AGENT.")


def items(root, defs, state, scope=(), files=None):
    """Every item of an audit: the design's units to check, the code no
    unit claims to draft, and the leads, each as (kind, tag, print, what)."""
    files = files if files is not None else docs.tracked_files(root)
    everything = survey(root, defs, (), files)
    code_scope = [s for s in scope if s not in defs]
    tags = {d.tag for d in units(root, defs, scope)} if scope else None
    if tags is not None and code_scope:
        # A scope of code takes in the sections that claim code in it, as
        # those drafted for it do.
        tags |= {u[0].tag for u in everything
                 if any(not docs.is_doc(r[0]) and under_scope(r[0], code_scope) for r in u[1])}
    out = [("check", u[0].tag, u[2], u) for u in everything if tags is None or u[0].tag in tags]
    # A scope of tags alone holds no code to draft.
    if not scope or code_scope:
        scoped = [f for f in files if under_scope(f, code_scope)]
        out += [("draft", x.tag, x.print, x) for x in
                drafts(root, scoped, everything, docs.config(root).get("exclude", []))]
    return out + lead_items(state, scope, defs, scoped_lines(root, out) if scope else frozenset())


def lead_items(state, scope, defs, within=frozenset()):
    """An audit's leads as items, those in its scope: under a path it
    names, or in the code its tags' units claim, `within`."""
    code_scope = [s for s in scope if s not in defs]

    def inside(lead):
        path, _, line = (lead.get("where") or "").rpartition(":")
        return (code_scope and under_scope(path, code_scope)) or \
            (line.isdigit() and (path, int(line)) in within)

    return [("lead", tag, lead_print(lead), lead) for tag, lead in state.get("leads", {}).items()
            if not scope or inside(lead)]


def scoped_lines(root, found):
    """The lines of code the units to check claim, as (path, line)."""
    return frozenset(lines_of(root, [r for kind, _, _, u in found if kind == "check"
                                     for r in u[1]]))


def item_standing(state, kind, tag, fp, now):
    st = standing(state, tag, fp, now)
    # Drafted code no unit claims any more, as when its section was cut, is
    # to be drafted again.
    return "open" if kind == "draft" and st in ("drafted", "stale") else st


# Implements [CPO§W48, CPO§W49]
def milestone(root, state, name):
    """The milestone a person approved for an audit: one recorded with
    `cpo audit start`, or else one `.cpo` declares, approved by the review
    of the commit that added it. None if nobody has approved one."""
    if state.get("milestone"):
        return state["milestone"]
    for a in docs.config(root).get("milestone", []):
        if a.get("name") == name:
            scope = a.get("scope", [])
            return {"scope": [scope] if isinstance(scope, str) else scope,
                    "approved_by": ".cpo", "goal": "in order"}
    return None


# Implements [CPO§W47]
def propose(root, store, defs, name, scope=()):
    """An audit's size, before anyone starts it, as a person would judge
    it: the code to draft, the sections to check, and the leads."""
    state = Audit(store, name).load()
    files = docs.tracked_files(root)
    if not state.get("seeded") and not state["units"]:
        state = dict(state, leads=dict(state.get("leads", {})))
        seed_leads(root, defs, state, files)
    now = int(time.time())
    found = items(root, defs, state, scope, files)
    count = {"draft": [0, 0], "check": [0, 0], "lead": [0, 0]}
    for kind, tag, fp, what in found:
        if item_standing(state, kind, tag, fp, now) in ("open", "stale", "claimed"):
            count[kind][0] += 1
            count[kind][1] += (sum(b - a + 1 for _, a, b in what.regions) if kind == "draft"
                               else len(lines_of(root, what[1])) if kind == "check" else 0)
    where = ", ".join(f"`{s}`" for s in scope) if scope else "the whole repository"
    parts = []
    if count["draft"][0]:
        parts.append(f"{count['draft'][0]} units of code ({count['draft'][1]} lines) to describe "
                     "in a design, each section then checked by a second agent")
    if count["check"][0]:
        parts.append(f"{count['check'][0]} design sections to check against "
                     f"{count['check'][1]} lines of code")
    if count["lead"][0]:
        parts.append(f"{count['lead'][0]} leads to look into")
    if not parts:
        return {"audit": name, "scope": list(scope), "counts": count,
                "sentence": f"Nothing in {where} needs work in {name}."}
    approve = (f"cpo audit start {name}" + "".join(f" --scope {s}" for s in scope)
               + " --approved-by \"<who>\"")
    sentence = (f"Proposed milestone: the design of {where} drafted, checked, and in order. "
                "That is " + "; ".join(parts) + ". I would work until it is in order, or until "
                "a question only you can answer blocks me. Shall I go ahead, or take a smaller "
                "scope?")
    return {"audit": name, "scope": list(scope), "counts": count, "sentence": sentence,
            "approve": approve}


def start(root, store, name, scope, who):
    """Record the milestone a person approved [CPO§W48]."""
    audit = Audit(store, name)
    with store.lock():
        state = audit.load()
        state["milestone"] = {"scope": list(scope), "approved_by": who, "goal": "in order",
                              "at": int(time.time()), "sha": head(root)}
        audit.save(state)
    audit.log({"event": "start", "scope": list(scope), "approved_by": who, "by": agent()[0]})
    return {"audit": name, **state["milestone"]}


# Implements [CPO§W8]
def next_unit(root, store, defs, name, budget=6000, scope=()):
    """Claim the next item that needs work, or resume the agent's own
    claim, and return its brief: stale units first, then code to draft
    [CPO§W40], then leads [CPO§W44], then units to check. An audit begun
    on a design checks its units before its leads, and drafts last. No
    agent is offered a section it drafted, since checking one's own draft
    is no second read [CPO§W42]."""
    import uuid
    me, why = agent()
    if not me:
        return {"error": NO_AGENT.format(why=why, token=uuid.uuid4().hex[:12])}
    audit = Audit(store, name)
    now = int(time.time())
    reprint(root, store, name)
    files = docs.tracked_files(root)
    with store.lock():
        state = audit.load()
        goal = milestone(root, state, name)
        # Helpers ask with the audit's name alone; the approved scope holds.
        scope = scope or (goal["scope"] if goal else ())
        found = items(root, defs, state, scope, files)
        if not state.get("seeded"):
            # An audit begun with no design claiming code drafts one before
            # checking it; one begun on a design checks it first [CPO§W40].
            # One with outcomes already recorded gets no seeded leads, which
            # would divert an audit under way.
            state["drafts_first"] = not state["units"] and \
                not any(i[0] == "check" and i[3][1] for i in found)
            if not state["units"]:
                seed_leads(root, defs, state, files)
            state["seeded"] = True
            found += lead_items(state, scope, defs,
                                scoped_lines(root, found) if scope else frozenset())
        drafted = state.get("drafted", {})
        mine = {t for t, c in state["claims"].items() if c["holder"] == me and c["until"] > now}
        st = {i[1]: item_standing(state, i[0], i[1], i[2], now) for i in found}
        pick = next((i for i in found if i[1] in mine), None)
        order = [("check", "stale"), ("draft", "open"), ("lead", "open"), ("check", "open")]
        if not state.get("drafts_first", True):
            order = [("check", "stale"), ("check", "open"), ("lead", "open"), ("draft", "open")]
        for kind, want in order:
            if pick is None:
                pick = next((i for i in found if i[0] == kind and st[i[1]] == want
                             and not (kind == "check" and drafted.get(i[1]) == me)), None)
        if pick is None:
            audit.save(state)
            if not found:
                return {"done": True, "message": (
                    "This repository has no design units for an audit to check: no doc "
                    ".cpo declares as a source, and no tagged statements. Declare a "
                    "design doc in .cpo, or write one first; `cpo help agent` says how.")}
            own = [i[1] for i in found if i[0] == "check" and st[i[1]] == "open"]
            if own:
                return {"done": True, "message": (
                    f"What is left in {name} you drafted: {', '.join(own[:8])}"
                    + (", ..." if len(own) > 8 else "") + ". A second agent must check "
                    "them; start a helper with its own CPO_AGENT and have it run "
                    f"cpo audit next {name}.")}
            return {"done": True, "message": f"Nothing in {name} needs checking."}
        kind, tag, fp, what = pick
        claim = {"holder": me, "contact": contact(), "at": now, "until": now + CLAIM_SECONDS}
        if kind == "draft":
            claim["decls"] = [[what.path, a, b, n] for a, b, _, n in what.decls]
        state["claims"][tag] = claim
        audit.save(state)
    audit.log({"event": "claim", "unit": tag, "by": me})
    if kind == "check":
        d, regions, _ = what
        text, where, title = d.text, f"{d.path}:{d.line}", d.name
    elif kind == "draft":
        regions, title, where = what.regions, what.name, f"{what.path}:{what.line}"
        text = draft_text(root, defs, name, tag)
    else:
        regions, title, where = lead_code(root, what.get("where")), "lead", what.get("where")
        text = what["text"] + (f"\n\n(Noted by {what['by']}.)" if what.get("by") else "")
    code, left = [], budget * 4
    for r in regions:
        body = region_text(root, r)
        at = f"{r[0]}:{r[1]}-{r[2]}" if r[1] else r[0]
        if len(body) > left:
            code.append({"where": at, "text": None, "omitted": len(body.splitlines())})
            continue
        left -= len(body)
        code.append({"where": at, "text": body})
    before = state["units"].get(tag) if kind == "check" else None
    # A stale unit's brief carries what changed, so the re-check reads that.
    changed = why_stale(root, defs, state, tag)["changes"] if before and \
        before["print"] != fp else None
    if kind == "draft":
        hint = (f"Describe this code in the design, then run: cpo audit done {name} {tag} "
                "--drafted, or --question \"<what a person must decide>\" --for <whom>")
    elif kind == "lead":
        hint = (f"Check the lead, then run: cpo audit done {name} {tag} --verified if "
                "nothing is wrong, or --finding \"<what is wrong, and where>\", or "
                "--question \"<what a person must decide>\" --for <whom>")
    else:
        hint = (f"Check each claim against the code, then run: cpo audit done {name} "
                f"{tag} --verified, or --finding \"<what is wrong, and where>\", or "
                "--question \"<what a person must decide>\" --for <whom>")
    return {"audit": name, "kind": kind, "unit": tag, "changed": changed, "name": title,
            "milestone": goal,
            "where": where, "text": text, "code": code, "before": before, "holder": me,
            # A drafted section may be wrong where the code is right.
            "drafted": drafted.get(tag) if kind == "check" else None,
            # A file the brief already shows code from needs no pointer to it.
            "pointers": [p for p in (what[0].pointers if kind == "check" else []) if not any(
                c["where"].split(":", 1)[0] == p for c in code)],
            "until": now + CLAIM_SECONDS,
            "until_utc": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(now + CLAIM_SECONDS)),
            # The brief says what to do next, in JSON as on a terminal.
            "next": hint + f". Record anything else worth checking with: cpo audit note "
                           f"{name} \"<what, and where>\""}


# Implements [CPO§W41]
def draft_text(root, defs, name, tag):
    """What a drafting brief asks of the agent."""
    heads = outline(defs, root)
    out = ["No design claims this code. Describe it: add sections to a design doc that "
           ".cpo declares, or extend them, saying what the code does now in claims a "
           "reader could check, and naming each declaration in backticks. Mark plumbing "
           "that serves no design with a `CPO§exempt: <why>` comment instead. Do not stop "
           "to fix what looks wrong; note it and go on."]
    if not docs.sources(root):
        out.append("This repository declares no design doc yet. Start one beside the README, "
                   "link it from there, and declare it in .cpo: [[source]] then "
                   "doc = \"DESIGN.md\". Under its title, say that an agent drafted it from "
                   "the code and nobody has signed it yet. `cpo help agent` shows the layout.")
    if heads:
        out.append("The design so far:\n" + "\n".join("  " + h for h in heads[:60])
                   + ("\n  ..." if len(heads) > 60 else ""))
    return "\n\n".join(out)


# Implements [CPO§W10]
def record(root, store, defs, name, tag, status, note=None, to=None, at=None):
    """Record a unit's outcome against the fingerprints it was checked at,
    and release its claim. With `at`, the check was made at an earlier
    commit: the unit is fingerprinted there, so it shows stale at once if
    it has changed since [CPO§W21]."""
    me, _ = agent()
    audit = Audit(store, name)
    if tag.startswith("draft:"):
        return record_draft(root, store, defs, name, tag, status, note, to)
    if tag.startswith("lead-"):
        return record_lead(root, store, name, tag, status, note, to)
    if status == "drafted":
        return {"error": f"{tag} is a unit to check, not code to draft; record it --verified, "
                         "--finding, or --question"}
    fp, sha, err = print_at(root, defs, tag, at)
    if err:
        return {"error": err}
    with store.lock():
        state = audit.load()
        state["units"][tag] = {"status": status, "print": fp, "sha": sha, "rules": RULES,
                               "by": me or "unknown", "note": note, "for": to,
                               "at": int(time.time())}
        state["claims"].pop(tag, None)
        audit.save(state)
    audit.log({"event": status, "unit": tag, "by": me, "note": note, "sha": sha})
    return {"audit": name, "unit": tag, "status": status, "sha": sha}


def record_lead(root, store, name, tag, status, note, to):
    """Close a lead: nothing wrong, a finding, or a question [CPO§W44]."""
    me, _ = agent()
    audit = Audit(store, name)
    if status == "drafted":
        return {"error": f"{tag} is a lead; record it --verified, --finding, or --question"}
    with store.lock():
        state = audit.load()
        lead = state.get("leads", {}).get(tag)
        if not lead:
            return {"error": f"{name} has no {tag}"}
        sha = head(root)
        state["units"][tag] = {"status": status, "print": lead_print(lead), "sha": sha,
                               "rules": RULES, "by": me or "unknown", "note": note, "for": to,
                               "at": int(time.time())}
        state["claims"].pop(tag, None)
        audit.save(state)
    audit.log({"event": status, "unit": tag, "by": me, "note": note, "sha": sha})
    return {"audit": name, "unit": tag, "status": status, "sha": sha}


# Implements [CPO§W41, CPO§W42]
def record_draft(root, store, defs, name, tag, status, note, to):
    """Close a unit of code to draft. Drafted, it must be claimed now by
    the design or exempted, declaration by declaration; the sections that
    claim it are recorded as the agent's, so another agent checks them."""
    me, _ = agent()
    audit = Audit(store, name)
    if status not in ("drafted", "question"):
        return {"error": f"{tag} is code to draft: describe it and record --drafted, or record "
                         "--question; note what is wrong with cpo audit note"}
    files = docs.tracked_files(root)
    state = audit.load()
    claim = state["claims"].get(tag)
    everything = survey(root, defs, (), files)
    pool = drafts(root, files, everything, docs.config(root).get("exclude", []))
    if claim and claim.get("decls"):
        wanted = [tuple(d) for d in claim["decls"]]
    else:
        match = [x for x in pool if x.tag == tag]
        if not match:
            return {"error": f"{tag} is not code to draft in {name}; run cpo audit mine {name}"}
        wanted = [(match[0].path, a, b, n) for a, b, _, n in match[0].decls]
    sha = head(root)
    rec = {"status": status, "sha": sha, "rules": RULES, "by": me or "unknown", "note": note,
           "for": to, "at": int(time.time())}
    if status == "question":
        match = [x for x in pool if x.tag == tag]
        rec["print"] = match[0].print if match else None
    else:
        # Declarations are matched by name, since a comment added above one
        # moves it; one without a name, by where it starts.
        left = {(x.path, n or a) for x in pool for a, _, _, n in x.decls}
        missing = [(p, a, n) for p, a, _, n in wanted if (p, n or a) in left]
        if missing:
            return {"error": f"{tag} is not drafted yet. Still claimed by no section: "
                    + ", ".join(f"{n or 'the declaration'} ({p}:{a})" for p, a, n in missing)
                    + ". Name each in backticks in a section of a declared design doc, mark "
                      "it `CPO§exempt: <why>`, or record --question."}
        names = {n for _, _, _, n in wanted if n}
        paths = {p for p, _, _, _ in wanted}
        sections = sorted({d.tag for d, regions, _ in everything for r in regions
                           if r[0] in paths and covers_any(root, r, names)})
        rec["sections"] = sections
    with store.lock():
        state = audit.load()
        state["units"][tag] = rec
        if status == "drafted":
            for t in rec["sections"]:
                state.setdefault("drafted", {}).setdefault(t, me or "unknown")
        state["claims"].pop(tag, None)
        audit.save(state)
    audit.log({"event": status, "unit": tag, "by": me, "note": note, "sha": sha,
               "sections": rec.get("sections")})
    out = {"audit": name, "unit": tag, "status": status, "sha": sha}
    if rec.get("sections"):
        out["sections"] = rec["sections"]
    return out


def covers_any(root, region, names):
    """Whether a region of code overlaps a declaration of one of these names."""
    path, start, end = region
    found = decls_of(root, path)
    return bool(found) and any(n in names and (start or 1) <= b and a <= (end or b)
                               for a, b, _, n, _ in found[0])


@contextlib.contextmanager
def snapshot_at(root, sha):
    """The tree of a commit, extracted from git's objects into a temporary
    directory, with the list of files it holds. Nothing is added to the
    repository, so it is safe while other work, such as a gate, runs in
    it [CPO§W38]."""
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="cpo-at-"))
    try:
        archive = subprocess.run(["git", "archive", sha], cwd=root, capture_output=True,
                                 check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tmp)], input=archive, check=True)
        names = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", sha], cwd=root,
                               capture_output=True, text=True, check=True).stdout.split("\0")
        files = [f for f in names if f and f.rsplit("/", 1)[-1] not in docs.OWN_FILES
                 and (tmp / f).is_file()]
        yield tmp, files
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def resolve(root, rev):
    return subprocess.run(["git", "rev-parse", "--short=12", "--verify", f"{rev}^{{commit}}"],
                          cwd=root, capture_output=True, text=True).stdout.strip()


def unit_at(root, tag, files=None):
    """A unit as it stands in a tree: (definition, regions, print), or
    None if it is no unit there."""
    _, defs, _ = docs.load(root=root, files=files)
    match = [u for u in survey(root, defs, (tag,), files) if u[0].tag == tag]
    return match[0] if match else None


def print_at(root, defs, tag, at=None):
    """A unit's fingerprint and commit, here or at an earlier commit, read
    from a temporary checkout of it. Returns (print, sha, error)."""
    if not at:
        match = [u for u in survey(root, defs, (tag,)) if u[0].tag == tag]
        return (match[0][2], head(root), None) if match else \
            (None, None, f"{tag} is not a unit of this audit")
    sha = resolve(root, at)
    if not sha:
        return None, None, f"{at} is not a commit"
    with snapshot_at(root, sha) as (tmp, files):
        then = unit_at(tmp, tag, files)
    if not then:
        return None, None, f"{tag} was not a unit at {sha}"
    return then[2], sha, None


def parts(root, unit):
    """A unit's text, its code by file and declaration with the lines each
    spans, and the lone comment lines that cite it, so two versions can be
    compared piece by piece."""
    d, regions, _ = unit
    code, mentions = {}, set()
    for path, start, end in regions:
        found = decls_of(root, path)
        name = next((n for a, b, k, n, _ in found[0] if a == start), None) if found else None
        if name is None and found and start < end:
            # A window into a large declaration is known by the declaration
            # and the line it starts at, which survive the code moving.
            around = [x for x in found[0] if x[0] <= start <= x[1] and x[3]]
            if around:
                inner = min(around, key=lambda x: x[1] - x[0])[3]
                name = f"{inner}~{found[1][start - 1].strip()[:48]}"
        if name is None and start == end:
            # A citation in a comment that documents no declaration, such
            # as a line of metadata, is a mention, not code [W38].
            mentions.add(f"{path}:{start}")
            continue
        code[f"{path}:{name or start}"] = (region_text(root, (path, start, end)), start, end)
    return d.text, code, d.path, span_of(root, d), mentions


def span_of(root, d):
    """The lines a unit's own text spans: a section's heading through the
    line before the next heading, or a statement's own lines."""
    if not d.heading:
        return d.line, d.line + d.lines - 1
    lines = (root / d.path).read_text(errors="replace").splitlines()
    for n, line in docs.prose_lines("\n".join(lines)):
        if n > d.line and docs.HEADING.match(line):
            return d.line, n - 1
    return d.line, len(lines)


SENTENCE = re.compile(r"(?<=[.;:!?])\s+(?=\S)|\n+")


def prose_diff(old, new):
    """What changed in a unit's text, sentence by sentence, with the words
    changed marked as `git diff --word-diff` marks them: a sentence kept
    is left out, one removed or added is shown whole, and one reworded is
    shown with [-old-]{+new+} around its changes."""
    import difflib
    a = [x for x in SENTENCE.split(old) if x.strip()]
    b = [x for x in SENTENCE.split(new) if x.strip()]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        if op == "delete":
            out += [f"- {x}" for x in a[i1:i2]]
        elif op == "insert":
            out += [f"+ {x}" for x in b[j1:j2]]
        else:
            out.append("~ " + word_diff(" ".join(a[i1:i2]), " ".join(b[j1:j2])))
    return "\n".join(out)


def word_diff(old, new):
    import difflib
    a, b = old.split(), new.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out += a[i1:i2]
            continue
        if i2 > i1:
            out.append("[-" + " ".join(a[i1:i2]) + "-]")
        if j2 > j1:
            out.append("{+" + " ".join(b[j1:j2]) + "+}")
    return " ".join(out)


def declared(root, key):
    """Whether the declaration a part's key names exists in a tree."""
    path, _, rest = key.partition(":")
    name = rest.split("~", 1)[0]
    found = decls_of(root, path)
    return bool(found) and any(n == name for _, _, _, n, _ in found[0])


def commits_since(root, sha, path, lines=None):
    """The commits since `sha` that changed these lines of a file, as they
    stand now, or the whole file. Merges that only carried a change are
    left out."""
    if lines:
        args = ["git", "log", "--no-merges", "--format=%h %s", "-s",
                f"-L{lines[0]},{lines[1]}:{path}", f"{sha}..HEAD"]
    else:
        args = ["git", "log", "--no-merges", "--format=%h %s", f"{sha}..HEAD", "--", path]
    out = subprocess.run(args, cwd=root, capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l.strip()]



# Implements [CPO§W38]
def why_stale(root, defs, state, tag, context=3):
    """What changed in a unit since it was checked: its text, its code by
    declaration, each with the commits that touched it and a diff, so a
    re-check reads the change, not the whole unit again."""
    import difflib
    rec = state["units"].get(tag)
    if not rec:
        return {"error": f"{tag} has not been checked in this audit"}
    now = [u for u in survey(root, defs, (tag,)) if u[0].tag == tag]
    if not now:
        return {"error": f"{tag} is not a unit of this audit"}
    behind = subprocess.run(["git", "merge-base", "--is-ancestor", rec["sha"], "HEAD"],
                            cwd=root, capture_output=True).returncode
    if behind:
        return {"error": f"{tag} was checked at {rec['sha']}, which this checkout does not "
                         "contain; run from a checkout that does, or it reads as changed"}
    new = parts(root, now[0])
    with snapshot_at(root, rec["sha"]) as (tmp, files):
        then = unit_at(tmp, tag, files)
        old = parts(tmp, then) if then else ("", {}, now[0][0].path, None, set())
        # Whether each declaration exists in the old tree, so a unit that
        # stopped claiming code still there is not reported as code removed.
        existed = {k for k in set(new[1]) - set(old[1]) if declared(tmp, k)}

    def diff(a, b, label):
        return "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(),
                                               f"{label} at {rec['sha']}", f"{label} now",
                                               n=context, lineterm=""))
    changes = []
    if old[0] != new[0]:
        changes.append({"what": "text", "where": f"{new[2]} {tag}",
                        "commits": commits_since(root, rec["sha"], new[2], new[3]),
                        "diff": prose_diff(old[0], new[0])})
    for key in sorted(set(old[1]) | set(new[1])):
        a, b = old[1].get(key), new[1].get(key)
        if (a and a[0]) == (b and b[0]):
            continue
        path = key.split(":", 1)[0]
        if a and b:
            what = "code"
        elif b:
            what = "newly claimed" if key in existed else "added"
        else:
            what = "no longer claimed" if declared(root, key) else "removed"
        commits = commits_since(root, rec["sha"], path, b[1:] if b else None)
        changes.append({"what": what,
                        "where": key,
                        "commits": commits,
                        "diff": diff(a[0] if a else "", b[0] if b else "", key)})
    added, gone = sorted(new[4] - old[4]), sorted(old[4] - new[4])
    if added or gone:
        changes.append({"what": "citations", "where": ", ".join(
            [f"+{m}" for m in added] + [f"-{m}" for m in gone]), "commits": [], "diff": ""})
    return {"unit": tag, "checked": rec["sha"], "status": rec["status"], "changes": changes}


def reprint(root, store, name):
    """Fingerprint again, at their own commits, the records made under
    older rules for what a unit claims, so a change to the rules does not
    make every record look stale. One snapshot serves each commit."""
    audit = Audit(store, name)
    state = audit.load()
    old = {}
    for tag, rec in state["units"].items():
        if rec.get("rules") != RULES:
            old.setdefault(rec["sha"], []).append(tag)
    for sha, tags in old.items():
        with snapshot_at(root, sha) as (tmp, files):
            _, then, _ = docs.load(root=tmp, files=files)
            found = {u[0].tag: u[2] for u in survey(tmp, then, tuple(tags), files)}
        for tag in tags:
            if tag in found:
                state["units"][tag].update(print=found[tag], rules=RULES)
    if old:
        with store.lock():
            current = audit.load()
            for tag, rec in state["units"].items():
                if tag in current["units"] and current["units"][tag]["sha"] == rec["sha"]:
                    current["units"][tag].update(print=rec["print"], rules=rec.get("rules"))
            audit.save(current)
    return sum(len(t) for t in old.values())


# Implements [CPO§W13]
def status(root, store, defs, name, only_me=False):
    """Where an audit stands: each unit's standing, the verified share by
    units and by the lines they claim, what is open, the code left to
    draft, the leads, and whether the draft is ready for a person."""
    me, _ = agent()
    reprint(root, store, name)
    state = Audit(store, name).load()
    goal = milestone(root, state, name)
    now = int(time.time())
    rows, drafting, leads = [], [], []
    found = items(root, defs, state, goal["scope"] if goal else ())
    # Until its first `next`, an audit's order is what that `next` will
    # choose.
    first = state.get("drafts_first") if state.get("seeded") else \
        not state["units"] and not any(i[0] == "check" and i[3][1] for i in found)
    for kind, tag, fp, what in found:
        st = item_standing(state, kind, tag, fp, now)
        claim = state["claims"].get(tag)
        out = state["units"].get(tag) or {}
        if only_me and not ((claim and claim["holder"] == me and claim["until"] > now)
                            or (out.get("by") == me and st in ("finding", "question"))):
            continue
        holder = claim["holder"] if st == "claimed" else None
        note = (f"was a {out['status']}: {out['note']}" if st == "stale" else
                out.get("note")) if out.get("status") in ("finding", "question") \
            and out.get("note") else None
        if kind == "draft":
            drafting.append({"unit": tag, "name": what.name, "standing": st,
                             "lines": sum(b - a + 1 for _, a, b in what.regions),
                             "holder": holder, "note": note, "for": out.get("for")})
            continue
        if kind == "lead":
            leads.append({"unit": tag, "name": what["text"][:160], "where": what.get("where"),
                          "standing": st, "holder": holder, "note": note,
                          "for": out.get("for")})
            continue
        d, regions, _ = what
        rows.append({"unit": d.tag, "name": d.name, "standing": st,
                     "lines": lines_of(root, regions), "holder": holder,
                     # A finding stays visible while it is being fixed, when
                     # the edits that fix it make the unit stale.
                     "note": note, "for": out.get("for"),
                     "drafted_by": state.get("drafted", {}).get(d.tag)})
    counts = {}
    for r in rows:
        counts[r["standing"]] = counts.get(r["standing"], 0) + 1
    total = len(set().union(*(r["lines"] for r in rows))) if rows else 0
    done = len(set().union(*(r["lines"] for r in rows if r["standing"] == "verified"))) \
        if counts.get("verified") else 0
    for r in rows:
        r["lines"] = len(r["lines"])
    busy = ("open", "claimed", "stale")
    # A draft is in order when all of it is drafted and checked, and every
    # lead is closed; a question still waiting on a person blocks it [CPO§W43].
    everything = rows + drafting + leads
    waiting = [r["unit"] for r in everything if r["standing"] == "question"]
    ready = bool(rows) and not only_me and not waiting and \
        not any(r["standing"] in busy for r in everything)
    return {"audit": name, "units": len(rows), "counts": counts,
            "verified_units": counts.get("verified", 0),
            "verified_lines": done, "lines": total, "rows": rows,
            "drafting": {"units": len(drafting), "lines": sum(r["lines"] for r in drafting),
                         "rows": drafting},
            "leads": {"open": sum(1 for r in leads if r["standing"] in busy), "rows": leads},
            "drafts_first": first if first is not None else True, "ready": ready,
            "questions": waiting,
            "milestone": goal}
