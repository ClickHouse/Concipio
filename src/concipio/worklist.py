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
        if f.endswith(".md"):
            continue
        try:
            text = (root / f).read_text(errors="replace")
        except (FileNotFoundError, IsADirectoryError):
            continue
        lang = spans.language_of(f, text)
        if not lang:
            continue
        for start, end, kind, name, _ in spans.declarations(lang, text):
            if name and not kind.endswith("scope"):
                out.setdefault(name.split()[-1], []).append((f, start, end))
    return out


# Implements [CPO§Y12, CPO§Y18]
def claimed_code(root, d, index, tracked):
    """The code a unit claims: declarations its text names in backticks,
    and the code citing it. A name defined in many places names none of
    them. A file the text names is a pointer, not a claim on the whole
    file [CPO§W2]."""
    regions = set()
    for m in TICKED.finditer(d.text):
        token = m.group(1).strip().rstrip("()")
        if re.fullmatch(r"[A-Za-z_]\w*", token) and 0 < len(index.get(token, ())) <= 3:
            regions.update(index[token])
    for c in d.citations:
        if c.path.endswith(".md"):
            continue
        # A citation covers the declaration its comment documents [T8].
        found = decls_of(root, c.path)
        node = lint.covered_node(found[0], c.line, found[1]) if found else None
        regions.add((c.path, node[0], node[1]) if node else (c.path, c.line, c.line))
    return sorted(regions, key=lambda r: (r[0], r[1] or 0))


_decls = {}


def decls_of(root, path):
    """A code file's declarations and lines, read once per checkout."""
    key = (str(root), path)
    if key not in _decls:
        try:
            text = (root / path).read_text(errors="replace")
        except (FileNotFoundError, IsADirectoryError):
            _decls[key] = None
            return None
        lang = spans.language_of(path, text)
        _decls[key] = (spans.declarations(lang, text), text.splitlines()) if lang else None
    return _decls[key]


def pointers(d, tracked):
    """The files a unit's text names, for the brief to point at."""
    return sorted({m.group(1).strip() for m in TICKED.finditer(d.text)
                   if PATHLIKE.match(m.group(1).strip()) and m.group(1).strip() in tracked})


def region_text(root, region):
    path, start, end = region
    lines = (root / path).read_text(errors="replace").splitlines()
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
        if out["print"] != fp:
            return held or "stale"
        return out["status"]
    return held or "open"


def head(root):
    return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=root,
                          capture_output=True, text=True).stdout.strip()


def survey(root, defs, scope=()):
    """Every unit with the code it claims and its fingerprint."""
    files = docs.tracked_files(root)
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


NO_AGENT = ("Concipio cannot tell which agent is asking ({why}). Run\n"
            "  export CPO_AGENT={token}\n"
            "and keep that line in any summary of your work, so a compacted context can "
            "resume its claims. A helper you start needs its own CPO_AGENT.")


# Implements [CPO§W8]
def next_unit(root, store, defs, name, budget=6000, scope=()):
    """Claim the next unit that needs checking, or resume the agent's own
    claim, and return its brief."""
    import uuid
    me, why = agent()
    if not me:
        return {"error": NO_AGENT.format(why=why, token=uuid.uuid4().hex[:12])}
    audit = Audit(store, name)
    now = int(time.time())
    with store.lock():
        state = audit.load()
        found = survey(root, defs, scope)
        mine = [t for t, c in state["claims"].items() if c["holder"] == me and c["until"] > now]
        pick = next((u for u in found if u[0].tag in mine), None)
        if pick is None:
            # Stale verifications first: they were right once and may not be now.
            order = sorted(found, key=lambda u: standing(state, u[0].tag, u[2], now) != "stale")
            pick = next((u for u in order
                         if standing(state, u[0].tag, u[2], now) in ("stale", "open")), None)
        if pick is None:
            return {"done": True, "message": f"Nothing in {name} needs checking."}
        d, regions, fp = pick
        state["claims"][d.tag] = {"holder": me, "contact": contact(), "at": now,
                                  "until": now + CLAIM_SECONDS}
        audit.save(state)
    audit.log({"event": "claim", "unit": d.tag, "by": me})
    code, left = [], budget * 4
    for r in regions:
        text = region_text(root, r)
        where = f"{r[0]}:{r[1]}-{r[2]}" if r[1] else r[0]
        if len(text) > left:
            code.append({"where": where, "text": None, "omitted": len(text.splitlines())})
            continue
        left -= len(text)
        code.append({"where": where, "text": text})
    before = state["units"].get(d.tag)
    # A stale unit's brief carries what changed, so the re-check reads that.
    changed = why_stale(root, defs, state, d.tag)["changes"] if before and \
        before["print"] != fp else None
    return {"audit": name, "unit": d.tag, "changed": changed, "name": d.name, "where": f"{d.path}:{d.line}",
            "text": d.text, "code": code, "pointers": d.pointers, "before": before,
            "holder": me,
            "until": now + CLAIM_SECONDS}


# Implements [CPO§W10]
def record(root, store, defs, name, tag, status, note=None, to=None, at=None):
    """Record a unit's outcome against the fingerprints it was checked at,
    and release its claim. With `at`, the check was made at an earlier
    commit: the unit is fingerprinted there, so it shows stale at once if
    it has changed since [CPO§W21]."""
    me, _ = agent()
    audit = Audit(store, name)
    fp, sha, err = print_at(root, defs, tag, at)
    if err:
        return {"error": err}
    with store.lock():
        state = audit.load()
        state["units"][tag] = {"status": status, "print": fp, "sha": sha,
                               "by": me or "unknown", "note": note, "for": to,
                               "at": int(time.time())}
        state["claims"].pop(tag, None)
        audit.save(state)
    audit.log({"event": status, "unit": tag, "by": me, "note": note, "sha": sha})
    return {"audit": name, "unit": tag, "status": status, "sha": sha}


@contextlib.contextmanager
def checkout_at(root, sha):
    """A temporary checkout of a commit, removed afterwards."""
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="cpo-at-")) / "tree"
    subprocess.run(["git", "worktree", "add", "--quiet", "--detach", str(tmp), sha],
                   cwd=root, check=True, capture_output=True)
    try:
        yield tmp
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(tmp)], cwd=root,
                       capture_output=True)


def resolve(root, rev):
    return subprocess.run(["git", "rev-parse", "--short=12", "--verify", f"{rev}^{{commit}}"],
                          cwd=root, capture_output=True, text=True).stdout.strip()


def unit_at(root, tag):
    """A unit as it stands in a checkout: (definition, regions, print), or
    None if it is no unit there."""
    _, defs, _ = docs.load(root=root)
    match = [u for u in survey(root, defs, (tag,)) if u[0].tag == tag]
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
    with checkout_at(root, sha) as tmp:
        then = unit_at(tmp, tag)
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
    with checkout_at(root, rec["sha"]) as tmp:
        then = unit_at(tmp, tag)
        old = parts(tmp, then) if then else ("", {}, now[0][0].path, None, set())
    new = parts(root, now[0])

    def diff(a, b, label):
        return "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(),
                                               f"{label} at {rec['sha']}", f"{label} now",
                                               n=context, lineterm=""))
    changes = []
    if old[0] != new[0]:
        changes.append({"what": "text", "where": f"{new[2]} {tag}",
                        "commits": commits_since(root, rec["sha"], new[2], new[3]),
                        "diff": diff(old[0], new[0], tag)})
    for key in sorted(set(old[1]) | set(new[1])):
        a, b = old[1].get(key), new[1].get(key)
        if (a and a[0]) == (b and b[0]):
            continue
        path = key.rsplit(":", 1)[0]
        changes.append({"what": "code" if a and b else "added" if b else "removed",
                        "where": key,
                        "commits": commits_since(root, rec["sha"], path, b[1:] if b else None),
                        "diff": diff(a[0] if a else "", b[0] if b else "", key)})
    added, gone = sorted(new[4] - old[4]), sorted(old[4] - new[4])
    if added or gone:
        changes.append({"what": "citations", "where": ", ".join(
            [f"+{m}" for m in added] + [f"-{m}" for m in gone]), "commits": [], "diff": ""})
    return {"unit": tag, "checked": rec["sha"], "status": rec["status"], "changes": changes}


# Implements [CPO§W13]
def status(root, store, defs, name, only_me=False):
    """Where an audit stands: each unit's standing, the verified share by
    units and by the lines they claim, and what is open."""
    me, _ = agent()
    state = Audit(store, name).load()
    now = int(time.time())
    rows = []
    for d, regions, fp in survey(root, defs):
        st = standing(state, d.tag, fp, now)
        claim = state["claims"].get(d.tag)
        out = state["units"].get(d.tag) or {}
        if only_me and not ((claim and claim["holder"] == me and claim["until"] > now)
                            or (out.get("by") == me and st in ("finding", "question"))):
            continue
        rows.append({"unit": d.tag, "name": d.name, "standing": st,
                     "lines": lines_of(root, regions),
                     "holder": claim["holder"] if st == "claimed" else None,
                     "note": out.get("note") if st in ("finding", "question") else None,
                     "for": out.get("for")})
    counts = {}
    for r in rows:
        counts[r["standing"]] = counts.get(r["standing"], 0) + 1
    total = len(set().union(*(r["lines"] for r in rows))) if rows else 0
    done = len(set().union(*(r["lines"] for r in rows if r["standing"] == "verified"))) \
        if counts.get("verified") else 0
    for r in rows:
        r["lines"] = len(r["lines"])
    return {"audit": name, "units": len(rows), "counts": counts,
            "verified_units": counts.get("verified", 0),
            "verified_lines": done, "lines": total, "rows": rows}
