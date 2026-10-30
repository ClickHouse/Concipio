"""Review mode: the commands an agent uses to sweep a change."""

import json
import re
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from . import docs, spans as spans_mod
from .store import Store

MUTATING = {"statement add", "statement edit", "concept add", "concept edit", "concept merge",
            "attach", "detach", "unjustified"}
STALL_WINDOW = 15
SPAN_ID = re.compile(r"\bS\d+\b")


class ReviewError(Exception):
    pass


def rev(repo, ref):
    out = subprocess.run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
                         cwd=repo, capture_output=True, text=True)
    if out.returncode != 0:
        raise ReviewError(f"{ref} is not a commit")
    return out.stdout.strip()


def split_range(repo, text):
    if ".." not in text:
        raise ReviewError(f"expected <base>..<head>, got {text}")
    base, head = text.split("..", 1)
    return rev(repo, base), rev(repo, head or "HEAD")


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


class Review:
    """The active review in a project's store, and the project's graph."""

    def __init__(self, repo, review_id=None):
        self.repo = Path(repo)
        self.store = Store(repo)
        self.id = review_id or self.store.current
        if not self.id:
            raise ReviewError("no review; run cpo review init <base>..<head>")
        self.dir = f"reviews/{self.id}"
        self.manifest = self.store.read(f"{self.dir}/manifest.json", None)
        if self.manifest is None:
            raise ReviewError(f"review {self.id} has no manifest")
        self.spans = {s["id"]: s for s in self.store.read(f"{self.dir}/spans.json", [])}
        self.state = self.store.read(f"{self.dir}/state.json",
                                     {"attachments": [], "unjustified": {}, "marks": []})
        self.graph = self.store.read("graph.json",
                                     {"statements": {}, "concepts": {}, "next": {}})

    def save(self):
        self.store.write(f"{self.dir}/state.json", self.state)
        self.store.write("graph.json", self.graph)

    def mint(self, letter):
        n = self.graph["next"].get(letter, 1)
        self.graph["next"][letter] = n + 1
        return f"{letter}{n}"

    def log(self, command, args):
        self.store.append(f"{self.dir}/log.jsonl", {
            "t": time.time(), "command": command, "args": args,
            "remaining": self.remaining()})

    # Queries over the graph.

    def statements(self):
        """Statements that belong to this review, including those carried
        over from an earlier review of the same change."""
        return [s for s in self.graph["statements"].values()
                if self.id in s.get("reviews", [s.get("review")])]

    def concept(self, cid):
        c = self.graph["concepts"].get(cid)
        if not c or c.get("merged_into"):
            raise ReviewError(f"{cid} is not a concept")
        return c

    def span(self, sid):
        if sid not in self.spans:
            raise ReviewError(f"{sid} is not a span in review {self.id}")
        return self.spans[sid]

    def attached(self, sid):
        return [a for a in self.state["attachments"] if a[0] == sid]

    def chain(self, cid):
        """Return the ancestors of a concept, nearest first, stopping at a
        statement or at a parent that does not exist."""
        seen, out = set(), []
        node = self.graph["concepts"].get(cid, {}).get("parent")
        while node and node not in seen:
            seen.add(node)
            out.append(node)
            if node.startswith("D"):
                break
            node = self.graph["concepts"].get(node, {}).get("parent")
        return out

    def used_concepts(self):
        used = set()
        for _, cid, _ in self.state["attachments"]:
            used.add(cid)
            used.update(c for c in self.chain(cid) if c.startswith("C"))
        return used

    def evidence(self, cid):
        """Spans attached to a concept or its descendants."""
        found = set()
        for sid, c, _ in self.state["attachments"]:
            if c == cid or cid in self.chain(c):
                found.add(sid)
        return found

    def uncovered(self):
        """Spans with neither an attachment nor an unjustified mark, and
        carried spans whose code changed and that nobody has looked at
        since."""
        flagged = set(self.state.get("changed_since_carried", []))
        return [sid for sid in self.spans
                if sid in flagged
                or (not self.attached(sid) and sid not in self.state["unjustified"])]

    def confirm(self, sid):
        flagged = self.state.get("changed_since_carried", [])
        if sid in flagged:
            flagged.remove(sid)

    def unexplained(self):
        out = []
        for cid in sorted(self.used_concepts(), key=lambda c: int(c[1:])):
            c = self.graph["concepts"][cid]
            cited = set(SPAN_ID.findall(c.get("claim", "")))
            if not c.get("claim", "").strip():
                out.append((cid, "has no claim"))
            elif not cited & self.evidence(cid):
                out.append((cid, "claim cites none of its attached spans"))
        return out

    def remaining(self):
        return len(self.uncovered()) + len(self.unexplained())


def gh_pr(repo, pr, fields):
    cmd = ["gh", "pr", "view", pr, "--json", fields]
    m = re.fullmatch(r"([\w.-]+/[\w.-]+)#(\d+)", pr)
    if m:
        cmd = ["gh", "pr", "view", m[2], "--repo", m[1], "--json", fields]
    out = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    if out.returncode != 0:
        raise ReviewError(f"could not read pull request {pr}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def pr_range(repo, pr):
    """Return base..head for a pull request, using the merge base as GitHub
    does, so commits on the base branch since the fork are not in scope."""
    data = gh_pr(repo, pr, "baseRefOid,headRefOid")
    for oid in (data["baseRefOid"], data["headRefOid"]):
        if subprocess.run(["git", "cat-file", "-e", oid], cwd=repo).returncode != 0:
            raise ReviewError(f"{oid[:10]} from {pr} is not in this repository; fetch it first")
    base = subprocess.run(["git", "merge-base", data["baseRefOid"], data["headRefOid"]],
                          cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    return f"{base}..{data['headRefOid']}"


# Implements [CPO§V4]
def cmd_init(repo, args):
    base, head = split_range(repo, args.range)
    store = Store(repo)
    review_id = f"{base[:10]}..{head[:10]}"
    design = []
    for path in args.design_file or []:
        design.append({"source": str(path), "text": Path(path).read_text()})
    for pr in args.pr or []:
        data = gh_pr(repo, pr, "title,body,url")
        design.append({"source": data["url"],
                       "text": f"{data['title']}\n\n{data['body']}"})
    stacked = [dict(zip(("base", "head"), split_range(repo, r)))
               for r in args.stacked_on or []]
    # Implements [CPO§V23]
    _, defs, _ = docs.load(repo)
    adopted = (Path(repo) / ".cpo").exists() or bool(defs)
    found = spans_mod.find_spans(repo, base, head, args.limit)
    manifest = {
        "id": review_id, "repo": str(repo), "base": base, "head": head,
        "stacked_on": stacked, "design": design, "adopted": adopted,
        "span_limit": args.limit, "parsers": parser_versions(),
        "created": time.time(),
    }
    store.write(f"reviews/{review_id}/manifest.json", manifest)
    store.write(f"reviews/{review_id}/spans.json", [asdict(s) for s in found])
    store.current = review_id
    by_file = {}
    for s in found:
        by_file[s.path] = by_file.get(s.path, 0) + 1
    data = {"review": review_id, "store": str(store.dir), "adopted": adopted,
            "design_sources": [d["source"] for d in design],
            "spans": len(found), "spans_by_file": by_file}
    human = [f"Review {review_id}: {len(found)} spans in {len(by_file)} files.",
             f"Store: {store.dir}",
             "The repository has adopted Concipio; concepts are checked against its docs."
             if adopted else
             "The repository has not adopted Concipio; the review runs from the store.",
             "Design text: " + (", ".join(data["design_sources"]) or "none")]
    human += [f"  {n:4}  {p}" for p, n in sorted(by_file.items())]
    return data, "\n".join(human)


def parser_versions():
    from importlib.metadata import version, PackageNotFoundError
    out = {}
    for pkg in ("tree-sitter", "tree-sitter-ruby", "tree-sitter-bash"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            pass
    return out


# Implements [CPO§V6]
def cmd_statement_add(r, args):
    if args.drafted:
        if not args.text:
            raise ReviewError("a drafted statement needs --text")
        statement = {"text": args.text, "provenance": "drafted"}
    else:
        if not args.quote:
            raise ReviewError("a given statement needs --quote, or use --drafted")
        quote = normalize(args.quote)
        sources = [d for d in r.manifest["design"] if quote in normalize(d["text"])]
        if not sources:
            raise ReviewError("the quote appears in none of the review's design text")
        statement = {"text": args.text or args.quote, "provenance": "given",
                     "quote": args.quote, "source": sources[0]["source"]}
    check_statement_parent(r, args.parent)
    statement["kind"] = args.kind
    statement["parent"] = args.parent
    sid = r.mint("D")
    statement.update(id=sid, review=r.id, reviews=[r.id])
    r.graph["statements"][sid] = statement
    r.log("statement add", statement)
    r.save()
    return statement, f"{sid} ({statement['provenance']} {args.kind}): {statement['text']}"


KINDS = ("claim", "context", "planned", "descriptive")


def check_statement_parent(r, parent, child=None):
    if parent is None:
        return
    if parent not in r.graph["statements"]:
        raise ReviewError(f"{parent} is not a statement")
    node = parent
    while node:
        if node == child:
            raise ReviewError("a statement cannot be its own ancestor")
        node = r.graph["statements"][node].get("parent")


# Implements [CPO§V6]
def cmd_statement_edit(r, args):
    st = r.graph["statements"].get(args.statement)
    if not st:
        raise ReviewError(f"{args.statement} is not a statement")
    if args.parent is not None:
        parent = args.parent or None
        check_statement_parent(r, parent, args.statement)
        st["parent"] = parent
    if args.kind is not None:
        st["kind"] = args.kind
    r.log("statement edit", st)
    r.save()
    return st, f"{st['id']} ({st.get('kind', 'claim')}): {st['text']}"


def check_parent(r, parent):
    if parent is None:
        return
    if parent.startswith("D") and parent in r.graph["statements"]:
        return
    if parent.startswith("C"):
        r.concept(parent)
        return
    raise ReviewError(f"{parent} is neither a statement nor a concept")


def cmd_concept_add(r, args):
    if not args.name.strip():
        raise ReviewError("a concept needs a name")
    check_parent(r, args.parent)
    cid = r.mint("C")
    c = {"id": cid, "name": args.name, "claim": args.claim or "", "parent": args.parent}
    r.graph["concepts"][cid] = c
    r.log("concept add", c)
    r.save()
    return c, f"{cid}: {c['name']}"


def cmd_concept_edit(r, args):
    c = r.concept(args.concept)
    if args.parent is not None:
        check_parent(r, args.parent)
        if args.parent == args.concept or args.concept in r.chain(args.parent):
            raise ReviewError("a concept cannot be its own ancestor")
    for key in ("name", "claim", "parent"):
        value = getattr(args, key)
        if value is not None:
            c[key] = value
    r.log("concept edit", c)
    r.save()
    return c, f"{c['id']}: {c['name']}"


def cmd_concept_merge(r, args):
    source, target = r.concept(args.source), r.concept(args.into)
    if source is target:
        raise ReviewError("a concept cannot merge into itself")
    for a in r.state["attachments"]:
        if a[1] == args.source:
            a[1] = args.into
    r.state["attachments"] = [list(a) for a in {tuple(a) for a in r.state["attachments"]}]
    for c in r.graph["concepts"].values():
        if c.get("parent") == args.source:
            c["parent"] = args.into
    source["merged_into"] = args.into
    r.log("concept merge", {"source": args.source, "into": args.into})
    r.save()
    return target, f"{args.source} merged into {args.into}: {target['name']}"


# Implements [CPO§V13]
def cmd_attach(r, args):
    r.span(args.span)
    r.concept(args.concept)
    entry = [args.span, args.concept, args.role]
    if entry not in r.state["attachments"]:
        r.state["attachments"].append(entry)
    r.confirm(args.span)
    r.state["unjustified"].pop(args.span, None)
    r.log("attach", {"span": args.span, "concept": args.concept, "role": args.role})
    r.save()
    return {"attached": entry}, f"{args.span} -> {args.concept} ({args.role})"


def cmd_detach(r, args):
    before = len(r.state["attachments"])
    r.state["attachments"] = [a for a in r.state["attachments"]
                              if not (a[0] == args.span and a[1] == args.concept)]
    if len(r.state["attachments"]) == before:
        raise ReviewError(f"{args.span} is not attached to {args.concept}")
    r.log("detach", {"span": args.span, "concept": args.concept})
    r.save()
    return {"detached": [args.span, args.concept]}, f"{args.span} -/-> {args.concept}"


# Implements [CPO§V14]
def cmd_unjustified(r, args):
    r.span(args.span)
    if not args.reason.strip():
        raise ReviewError("an unjustified mark needs a reason")
    if r.attached(args.span) and args.span not in r.state.get("changed_since_carried", []):
        raise ReviewError(f"{args.span} is attached; detach it first")
    for a in r.attached(args.span):
        r.state["attachments"].remove(a)
    r.state["unjustified"][args.span] = args.reason
    see = [d for d in (getattr(args, "see", None) or [])]
    for d in see:
        if d not in r.graph["statements"]:
            raise ReviewError(f"{d} is not a statement")
        if r.graph["statements"][d].get("kind", "claim") == "claim":
            raise ReviewError(f"{d} is a claim; attach the span to a concept under it instead")
    explained = r.state.setdefault("explained_by", {})
    if see:
        explained[args.span] = see
    else:
        explained.pop(args.span, None)
    r.confirm(args.span)
    r.log("unjustified", {"span": args.span, "reason": args.reason, "see": see})
    r.save()
    return {"span": args.span, "reason": args.reason}, f"{args.span} unjustified: {args.reason}"


def span_code(r, s):
    """The span's code with line numbers, marking the lines the change
    touched with + (or - for deleted code), so an agent classifies the
    change rather than the whole declaration around it."""
    rev_ = r.manifest["head"] if s["side"] == "new" else r.manifest["base"]
    text = spans_mod.file_at(r.repo, rev_, s["path"]) or ""
    changed = spans_mod.changed_lines(r.repo, r.manifest["base"], r.manifest["head"],
                                      s["path"], s["side"])
    mark = "+" if s["side"] == "new" else "-"
    lines = text.splitlines()[s["start"] - 1:s["end"]]
    return "\n".join(f"{n:5} {mark if n in changed else ' '} {line}"
                     for n, line in enumerate(lines, s["start"]))


def concept_list(r):
    """Concepts as one line each; `cpo show` gives the rest."""
    return [f"{c['id']} {c['name']}"
            for c in r.graph["concepts"].values() if not c.get("merged_into")]


# Implements [CPO§V24]
def cmd_next(r, args):
    uncovered = r.uncovered()
    prefix = getattr(args, "path", None)
    if prefix:
        uncovered = [s for s in uncovered if r.spans[s]["path"].startswith(prefix)]
    if uncovered:
        s = r.spans[uncovered[0]]
        span = {k: s[k] for k in ("id", "path", "start", "end", "scope", "kind", "test")}
        if s["side"] == "old":
            span["deleted"] = True
        if s["id"] in r.state.get("changed_since_carried", []):
            span["carried"] = [f"{c} ({role})" for _, c, role in r.attached(s["id"])] or \
                [f"unjustified: {r.state['unjustified'].get(s['id'])}"]
            span["note"] = ("carried from an earlier head, and its code has changed; "
                            "attach it again to confirm, or detach and reclassify")
        data = {"work": "span", "span": span, "code": span_code(r, s),
                "remaining_spans": len(uncovered)}
        if not getattr(args, "brief", False):
            data["concepts"] = concept_list(r)
        side = "deleted from base" if s["side"] == "old" else "head"
        human = (f"{s['id']}  {s['path']}:{s['start']}-{s['end']} ({side})\n"
                 f"  {s['scope']}  [{s['kind']}{', test' if s['test'] else ''}]"
                 f"  {len(uncovered)} spans left\n\n{data['code']}")
        return data, human
    unexplained = [] if prefix else r.unexplained()
    if unexplained:
        cid, why = unexplained[0]
        c = r.graph["concepts"][cid]
        data = {"work": "concept", "concept": c, "problem": why,
                "evidence": sorted(r.evidence(cid), key=lambda s: int(s[1:]))}
        return data, f"{cid} {why}: {c['name']}\n  attached spans: {', '.join(data['evidence'])}"
    return {"work": None}, "Nothing remains. Run cpo check."


# Implements [CPO§V17]
def cmd_check(r, args):
    uncovered = r.uncovered()
    unexplained = r.unexplained()
    used = r.used_concepts()
    undeclared = sorted((c for c in used if not any(p.startswith("D") for p in r.chain(c))),
                        key=lambda c: int(c[1:]))
    reached = {p for c in used for p in r.chain(c) if p.startswith("D")}
    # A statement is implemented when it, or a statement refining it, is.
    for d in list(reached):
        node = r.graph["statements"].get(d, {}).get("parent")
        while node and node not in reached:
            reached.add(node)
            node = r.graph["statements"].get(node, {}).get("parent")
    mine = r.statements()
    unimplemented = [s["id"] for s in mine
                     if s.get("kind", "claim") == "claim" and s["id"] not in reached]
    explained_by = {s: d for s, d in r.state.get("explained_by", {}).items()
                    if s in r.state["unjustified"]}
    coverage = {}
    for prov in ("given", "drafted"):
        claims = [s["id"] for s in mine
                  if s["provenance"] == prov and s.get("kind", "claim") == "claim"]
        others = [s["id"] for s in mine
                  if s["provenance"] == prov and s.get("kind", "claim") != "claim"]
        coverage[prov] = {"claims": len(claims), "other": len(others),
                          "implemented": len([i for i in claims if i in reached])}
    strict = getattr(args, "strict", False)
    data = {
        "traced": not uncovered and not (strict and undeclared),
        "explained": not unexplained, "strict": strict,
        "uncovered_spans": uncovered,
        "unexplained_concepts": [{"concept": c, "problem": p} for c, p in unexplained],
        "undeclared_behavior": undeclared,
        "unimplemented_claims": unimplemented,
        "unjustified": r.state["unjustified"],
        "explained_by_context": explained_by,
        "coverage_by_provenance": coverage,
    }
    names = {c["id"]: c["name"] for c in r.graph["concepts"].values()}
    human = [f"Traced:    {'pass' if data['traced'] else 'FAIL'}"
             f" ({len(r.spans) - len(uncovered)}/{len(r.spans)} spans covered)",
             f"Explained: {'pass' if data['explained'] else 'FAIL'}"]
    if uncovered:
        human.append(f"  Uncovered: {', '.join(uncovered[:20])}"
                     f"{' ...' if len(uncovered) > 20 else ''}")
    for c, p in unexplained:
        human.append(f"  {c} ({names[c]}) {p}")
    if undeclared:
        human.append("Undeclared behavior: " +
                     ", ".join(f"{c} ({names[c]})" for c in undeclared))
    if unimplemented:
        human.append("Unimplemented claims: " + ", ".join(unimplemented))
    if r.state["unjustified"]:
        human.append(f"Unjustified: {len(r.state['unjustified'])} spans"
                     + (f", {len(explained_by)} explained by context or planned work"
                        if explained_by else ""))
    for prov, v in coverage.items():
        if v["claims"] or v["other"]:
            human.append(f"{prov.capitalize()} claims: {v['implemented']}/{v['claims']} implemented"
                         + (f"; {v['other']} context, planned, or descriptive"
                            if v["other"] else ""))
    return data, "\n".join(human)


# Implements [CPO§V19]
def cmd_record(r, args):
    entry = {"model": args.model, "input_tokens": args.input_tokens,
             "output_tokens": args.output_tokens, "tokens": args.tokens,
             "spans": args.spans, "note": args.note}
    r.store.append(f"{r.dir}/log.jsonl", {"t": time.time(), "command": "record",
                                          "args": entry, "remaining": r.remaining()})
    total = args.tokens or args.input_tokens + args.output_tokens
    return entry, f"recorded {total} tokens for {args.model}"


def cost(r):
    totals = {}
    for e in r.store.lines(f"{r.dir}/log.jsonl"):
        if e["command"] != "record":
            continue
        a = e["args"]
        t = totals.setdefault(a["model"], {"tokens": 0, "input_tokens": 0,
                                           "output_tokens": 0, "spans": 0})
        t["input_tokens"] += a["input_tokens"]
        t["output_tokens"] += a["output_tokens"]
        t["tokens"] += a.get("tokens") or a["input_tokens"] + a["output_tokens"]
        t["spans"] += a.get("spans") or 0
    return totals


# Implements [CPO§V18]
def cmd_status(r, args):
    log = [e for e in r.store.lines(f"{r.dir}/log.jsonl") if e["command"] in MUTATING]
    now = r.remaining()
    stall = None
    if len(log) >= STALL_WINDOW:
        window = log[-STALL_WINDOW:]
        before = log[-STALL_WINDOW - 1]["remaining"] if len(log) > STALL_WINDOW else None
        if before is not None and min(e["remaining"] for e in window) >= before:
            stall = f"what remains has not shrunk in {STALL_WINDOW} commands"
    toggles = {}
    for e in log[-2 * STALL_WINDOW:]:
        if e["command"] == "detach":
            key = (e["args"]["span"], e["args"]["concept"])
            toggles[key] = toggles.get(key, 0) + 1
    flapping = [f"{s} on {c}" for (s, c), n in toggles.items() if n >= 2]
    if flapping and not stall:
        stall = "spans attached and detached repeatedly: " + ", ".join(flapping)
    last = log[-1]["remaining"] if log else None
    data = {"review": r.id, "remaining": now,
            "uncovered_spans": len(r.uncovered()),
            "unexplained_concepts": len(r.unexplained()),
            "commands": len(log), "stall": stall, "cost": cost(r)}
    human = (f"Review {r.id}: {now} remaining "
             f"({data['uncovered_spans']} spans, {data['unexplained_concepts']} concepts) "
             f"after {len(log)} commands")
    for model, t in data["cost"].items():
        total = t["tokens"]
        per = f", {total // t['spans']} per span" if t["spans"] else ""
        human += f"\n  {model}: {total} tokens over {t['spans']} spans{per}"
    if stall:
        human += f"\nSTALLED: {stall}. Stop and report what is stuck."
    return data, human


def show_item(r, ident):
    if ident in r.spans:
        s = r.spans[ident]
        att = r.attached(ident)
        data = dict(s, code=span_code(r, s), attachments=att,
                    unjustified=r.state["unjustified"].get(ident))
        human = (f"{ident}  {s['path']}:{s['start']}-{s['end']}  {s['scope']}\n"
                 + "".join(f"  -> {c} ({r.graph['concepts'][c]['name']}, {role})\n"
                           for _, c, role in att)
                 + (f"  unjustified: {data['unjustified']}\n" if data["unjustified"] else "")
                 + "\n" + data["code"])
        return data, human
    if ident in r.graph["concepts"]:
        c = r.graph["concepts"][ident]
        kids = [k["id"] for k in r.graph["concepts"].values() if k.get("parent") == ident
                and not k.get("merged_into")]
        ev = sorted(r.evidence(ident), key=lambda s: int(s[1:]))
        data = dict(c, children=kids, spans=ev, ancestors=r.chain(ident))
        human = (f"{ident}: {c['name']}\n  parent: {c.get('parent')}\n  claim: {c['claim']}\n"
                 f"  children: {', '.join(kids) or 'none'}\n  spans: {', '.join(ev) or 'none'}")
        return data, human
    if ident in r.graph["statements"]:
        s = r.graph["statements"][ident]
        return s, f"{ident} ({s['provenance']}): {s['text']}"
    return None


def span_key(s):
    return (s["path"], s["side"], s["scope"], s["quote"])


# Implements [CPO§V11]
def carry(store, old_id, new_id):
    """Carry an earlier review's statements, attachments, and marks to a
    review of a new head. A span carries when its path, scope, and quote
    match one in the old review; if its code changed, the carried
    attachment is flagged for a fresh look."""
    old = Review(store.repo, old_id)
    new = Review(store.repo, new_id)
    by_key = {span_key(s): s for s in old.spans.values()}
    by_scope = {}
    for s in old.spans.values():
        by_scope.setdefault((s["path"], s["side"], s["scope"]), []).append(s)
    old_code = {}

    def code(rv, s):
        rev_ = rv.manifest["head"] if s["side"] == "new" else rv.manifest["base"]
        text = spans_mod.file_at(rv.repo, rev_, s["path"]) or ""
        return "\n".join(text.splitlines()[s["start"] - 1:s["end"]])

    # A span that matches one in the old review keeps its ID, so claims
    # that cite it stay true; only new spans get new numbers.
    matches, used = {}, set()
    for s in new.spans.values():
        match = by_key.get(span_key(s))
        if match is None:
            same_scope = by_scope.get((s["path"], s["side"], s["scope"]), [])
            match = same_scope[0] if len(same_scope) == 1 else None
        if match is not None and match["id"] not in used:
            matches[s["id"]] = match
            used.add(match["id"])
    next_id = max([int(i[1:]) for i in old.spans] + [0]) + 1
    renamed = []
    for s in new.spans.values():
        if s["id"] in matches:
            s["id"] = matches[s["id"]]["id"]
        else:
            s["id"] = f"S{next_id}"
            next_id += 1
        renamed.append(s)
    new.spans = {s["id"]: s for s in renamed}
    new.store.write(f"{new.dir}/spans.json", renamed)
    matches = {matches[k]["id"]: matches[k] for k in matches}

    counts = {"unchanged": 0, "changed": 0, "new": 0}
    flagged = []
    for s in new.spans.values():
        match = matches.get(s["id"])
        if match is None:
            counts["new"] += 1
            continue
        if match["id"] not in old_code:
            old_code[match["id"]] = code(old, match)
        changed = old_code[match["id"]] != code(new, s)
        counts["changed" if changed else "unchanged"] += 1
        for _, cid, role in old.attached(match["id"]):
            new.state["attachments"].append([s["id"], cid, role])
        if match["id"] in old.state["unjustified"]:
            new.state["unjustified"][s["id"]] = old.state["unjustified"][match["id"]]
        if changed and (old.attached(match["id"]) or match["id"] in old.state["unjustified"]):
            flagged.append(s["id"])
    new.state["changed_since_carried"] = flagged
    new.state["carried_from"] = old_id
    snapshots = [normalize(d["text"]) for d in new.manifest["design"]]
    dropped = []
    for st in old.statements():
        if st["provenance"] == "given" and not any(normalize(st["quote"]) in t for t in snapshots):
            dropped.append(st["id"])
            continue
        st.setdefault("reviews", [st.get("review")])
        if new_id not in st["reviews"]:
            st["reviews"].append(new_id)
    new.graph = old.graph
    new.save()
    new.log("carry", {"from": old_id, **counts, "flagged": len(flagged), "dropped": dropped})
    return {"from": old_id, **counts, "flagged": flagged, "dropped_statements": dropped}


def previous_review(store, design_sources, exclude):
    """The latest earlier review whose design text came from the same
    sources, such as the same pull request."""
    best = None
    for m in sorted((store.dir / "reviews").glob("*/manifest.json")):
        manifest = json.loads(m.read_text())
        if manifest["id"] == exclude:
            continue
        if {d["source"] for d in manifest["design"]} & set(design_sources):
            if best is None or manifest["created"] > best["created"]:
                best = manifest
    return best["id"] if best else None


def cmd_reviewable(repo, args):
    """Pin the change, reusing a review already pinned to the same commits,
    and report whether it is ready for a human: exit 0 if both verdicts
    pass, or show the first unmet obligation and exit 1."""
    target = args.target
    is_range = ".." in target
    rng = target if is_range else pr_range(repo, target)
    base, head = split_range(repo, rng)
    store = Store(repo)
    review_id = f"{base[:10]}..{head[:10]}"
    created = None
    if store.read(f"reviews/{review_id}/manifest.json", None) is None:
        init_args = type("A", (), {"range": rng, "pr": [] if is_range else [target],
                                   "design_file": args.design_file, "limit": args.limit,
                                   "stacked_on": args.stacked_on})()
        created, _ = cmd_init(repo, init_args)
        new_manifest = store.read(f"reviews/{review_id}/manifest.json", {})
        prior = previous_review(store, [d["source"] for d in new_manifest.get("design", [])],
                                review_id)
        if prior:
            created["carried"] = carry(store, prior, review_id)
    store.current = review_id
    r = Review(repo, review_id)
    verdict, summary = cmd_check(r, args)
    ready = verdict["traced"] and verdict["explained"]
    data = {"review": review_id, "reviewable": ready, "check": verdict, "created": bool(created)}
    human = summary
    carried = (created or {}).get("carried")
    if carried:
        data["carried"] = carried
        human = (f"New head; carried review {carried['from']}: {carried['unchanged']} spans "
                 f"unchanged, {carried['changed']} changed, {carried['new']} new; "
                 f"{len(carried['flagged'])} carried spans changed and need a fresh look"
                 + (f"; statements no longer in the design text: {', '.join(carried['dropped_statements'])}"
                    if carried["dropped_statements"] else "") + "\n\n" + human)
    if not ready:
        nxt, nxt_human = cmd_next(r, type("A", (), {"path": None, "brief": False})())
        data["next"] = nxt
        human += "\n\nFirst unmet obligation:\n" + nxt_human
    return data, human, 0 if ready else 1


def spans_summary(r, ids):
    """Group span IDs by file as path:start-end lists."""
    by = {}
    for sid in sorted(ids, key=lambda s: int(s[1:])):
        sp = r.spans[sid]
        by.setdefault(sp["path"], []).append(f"{sid} {sp['start']}-{sp['end']}")
    return [f"`{p}` {', '.join(v)}" for p, v in by.items()]


# Implements [CPO§V29]
def cmd_render(r, args):
    """Write the review's statements and concepts as a design doc in the
    store, one section per statement, so the size rules can check it."""
    import textwrap
    pr = next((re.search(r"/pull/(\d+)", d["source"]) for d in r.manifest["design"]
               if "/pull/" in d["source"]), None)
    prefix = f"PR{pr[1]}" if pr else "REVIEW"
    title = (r.manifest["design"][0]["text"].splitlines()[0]
             if r.manifest["design"] else f"Review {r.id}")
    concepts = {c["id"]: c for c in r.graph["concepts"].values() if not c.get("merged_into")}
    kids = {}
    for c in concepts.values():
        kids.setdefault(c.get("parent"), []).append(c["id"])
    direct = {}
    for sid, cid, role in r.state["attachments"]:
        direct.setdefault(cid, set()).add(sid)

    def wrap(text, indent):
        # List items hang their continuation lines; paragraphs do not.
        hang = indent + "  " if text.lstrip().startswith("- ") else indent
        return textwrap.fill(text, 78, initial_indent=indent, subsequent_indent=hang,
                             break_long_words=False, break_on_hyphens=False)

    link_defs = {}

    repo = Path(r.manifest["repo"])

    def span_links(ids):
        by = {}
        for sid in sorted(ids, key=lambda s: int(s[1:])):
            sp = r.spans[sid]
            if sp["side"] == "new":
                link_defs[sid] = f"<{(repo / sp['path']).as_posix()}#L{sp['start']}>"
                by.setdefault(sp["path"], []).append(f"[{sid}] {sp['start']}-{sp['end']}")
            else:
                by.setdefault(sp["path"], []).append(f"{sid} (deleted) {sp['start']}-{sp['end']}")
        return [f"`{p}` {', '.join(v)}" for p, v in by.items()]

    def concept_lines(cid, depth):
        c = concepts[cid]
        pad = "  " * depth
        out = [wrap(f"- **{prefix}§{cid}:** **{c['name']}.** {c['claim']}", pad)]
        for line in span_links(direct.get(cid, ())):
            out.append(wrap(f"- Spans: {line}", pad + "  "))
        for k in sorted(kids.get(cid, []), key=lambda x: int(x[1:])):
            out += concept_lines(k, depth + 1)
        return out

    mine = r.statements()
    ids = {st["id"] for st in mine}
    st_kids = {}
    for st in mine:
        parent = st.get("parent") if st.get("parent") in ids else None
        st_kids.setdefault(parent, []).append(st["id"])
    by_num = lambda x: int(x[1:])
    statements = {st["id"]: st for st in mine}
    explained = {}
    for sid, ds in r.state.get("explained_by", {}).items():
        if sid in r.state["unjustified"]:
            for d in ds:
                explained.setdefault(d, []).append(sid)

    def short(text):
        sentence = re.split(r"(?<=[^\d\s][.!?])\s", text, maxsplit=1)[0].rstrip(".")
        return sentence if len(sentence) <= 70 else sentence[:67].rstrip() + "..."

    def slug(heading):
        # The anchor GitHub, VS Code, and most viewers give a heading.
        text = re.sub(r"[^\w\- ]", "", heading.lower())
        return text.replace(" ", "-")

    # Statements follow the design text's own order; drafted ones follow it.
    snapshot = " ".join(normalize(d["text"]) for d in r.manifest["design"])

    def in_source_order(sid):
        quote = statements[sid].get("quote")
        at = snapshot.find(normalize(quote)) if quote else -1
        return (at if at >= 0 else len(snapshot), by_num(sid))

    order = []

    def walk_statements(sid, depth):
        order.append((sid, depth))
        for k in sorted(st_kids.get(sid, []), key=in_source_order):
            walk_statements(k, depth + 1)

    for root in sorted(st_kids.get(None, []), key=in_source_order):
        walk_statements(root, 0)

    # Implements [CPO§V30]
    doc = [f"# {title}", "",
           f"Generated by Concipio from review {r.id}. Statements quote the "
           "design text; concepts and claims are the agents'.", "",
           "## Cornerstone", ""]
    heading_of = {}
    for sid, depth in order:
        heading_of[sid] = f"{sid}: {short(statements[sid]['text'])}"
        kind = statements[sid].get("kind", "claim")
        note = "" if kind == "claim" else f" *({kind})*"
        doc.append(f"{'  ' * depth}- [{sid}] {short(statements[sid]['text'])}{note}")
        link_defs[sid] = "#" + slug(heading_of[sid])
    doc.append("")
    for sid, depth in order:
        st = statements[sid]
        kind = st.get("kind", "claim")
        doc += [f"{'#' * min(2 + depth, 6)} {heading_of[sid]}", "",
                wrap(f"**{prefix}§{sid}:** {st['text']} *({st['provenance']}"
                     f"{'' if kind == 'claim' else ', ' + kind})*", ""), ""]
        for cid in sorted(kids.get(sid, []), key=by_num):
            doc += concept_lines(cid, 0)
        if explained.get(sid):
            doc.append(wrap("- Explains unjustified code: " + ", ".join(
                f"{x} `{r.spans[x]['path']}` ({r.state['unjustified'][x]})"
                for x in sorted(explained[sid], key=by_num)), ""))
        doc.append("")
    orphans = [c for c in kids.get(None, []) if c in concepts]
    if orphans:
        doc += ["## Undeclared behavior", ""]
        for cid in orphans:
            doc += concept_lines(cid, 0)
        doc.append("")
    loose = {k: v for k, v in r.state["unjustified"].items()
             if k not in r.state.get("explained_by", {})}
    if loose:
        doc += ["## Unjustified", ""]
        for sid, why in loose.items():
            sp = r.spans[sid]
            doc.append(wrap(f"- {sid} `{sp['path']}`: {why}", ""))
        doc.append("")
    if link_defs:
        doc += [f"[{sid}]: {target}" for sid, target in
                sorted(link_defs.items(), key=lambda kv: (kv[0][0], int(kv[0][1:])))]
        doc.append("")
    out = r.store.dir / "gendoc" / f"{r.id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(doc))
    from . import lint as lint_mod
    defs, errors = docs.find_definitions(out.parent, [out.name])
    problems = lint_mod.lint(out.parent, [out.name], defs,
                             args.statement_limit, args.section_limit)
    data = {"path": str(out), "statements": len(mine), "concepts": len(concepts),
            "problems": [p.__dict__ for p in problems], "errors": errors}
    human = [f"Wrote {out}", f"  {len(mine)} statements, {len(concepts)} concepts"]
    human += [f"  {p.rule}: {p.message}" for p in problems] or ["  Every design fits on a screen."]
    return data, "\n".join(human)
