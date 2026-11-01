"""Why is this line here? The record of its region, the design above it,
and the mechanism it belongs to."""

import subprocess
import tomllib
from pathlib import Path

from . import spans as spans_mod
from .records import Records, evidence, fingerprint
from .review import ReviewError, load_graph
from .store import Store


def regions_at(repo, rev, path, limit=spans_mod.DEFAULT_LIMIT):
    """Cut a whole file at a commit into regions, as a review cuts a diff."""
    text = spans_mod.file_at(repo, rev, path)
    if text is None:
        raise ReviewError(f"{path} does not exist at {rev}")
    lines = text.splitlines()
    lang = spans_mod.language_of(path, text)
    out = []
    for n, (start, end, kind, scope) in enumerate(
            spans_mod.cut(path, lang, text, 1, max(len(lines), 1), limit)):
        body = lines[start - 1:end]
        out.append({"id": f"r{n}", "path": path, "side": "new", "start": start, "end": end,
                    "kind": kind, "scope": scope, "fingerprint": fingerprint("\n".join(body)),
                    "first": evidence(body)[0]})
    return out


def statement_chain(graph, sid):
    out, seen = [], set()
    while sid and sid not in seen and sid in graph["statements"]:
        seen.add(sid)
        st = graph["statements"][sid]
        out.append({"id": sid, "text": st["text"], "kind": st.get("kind", "claim")})
        sid = st.get("parent")
    return out


def concept_chain(graph, cid):
    """A concept and its ancestors, nearest first, then the statements above
    them up to the root."""
    concepts, seen = [], set()
    node = cid
    while node and node.startswith("C") and node not in seen and node in graph["concepts"]:
        seen.add(node)
        c = graph["concepts"][node]
        concepts.append({"id": node, "name": c["name"], "claim": c.get("claim", "")})
        node = c.get("parent")
    statements = statement_chain(graph, node) if node and node.startswith("D") else []
    return concepts, statements


def mechanism(records, cid, exclude):
    """Every current region, anywhere in the project, serving a concept."""
    out = []
    if not records.dir.exists():
        return out
    for p in sorted(records.dir.rglob("*.toml")):
        code_path = str(p.relative_to(records.dir))[:-len(".toml")]
        for r in records.current(code_path):
            if any(c["id"] == cid for c in r.get("concepts", [])) and \
                    (code_path, r["scope"]) != exclude:
                out.append({"path": code_path, "scope": r["scope"], "lines": r["lines"],
                            "role": next(c["role"] for c in r["concepts"] if c["id"] == cid)})
    return out


# Implements [CPO§M46]
def why(repo, target, rev="HEAD"):
    path, _, line = target.rpartition(":")
    if not path or not line.isdigit():
        raise ReviewError("expected path:line")
    line = int(line)
    root = Path(repo)
    full = (Path.cwd() / path).resolve()
    if full.is_relative_to(root):
        path = str(full.relative_to(root))
    store = Store(repo)
    records = Records(store)
    graph = load_graph(store)
    regions = regions_at(repo, rev, path)
    here = next((r for r in regions if r["start"] <= line <= r["end"]), None)
    if here is None:
        raise ReviewError(f"line {line} is outside {path}")
    matches = records.match_all(regions)
    applies, stale = matches[here["id"]]
    record = applies or stale
    data = {"path": path, "line": line, "at": rev,
            "region": {k: here[k] for k in ("scope", "kind", "start", "end")},
            "record": None, "stale": bool(stale and not applies), "concepts": []}
    if record:
        data["record"] = {"id": record["id"], "reviewed_at": record.get("reviewed_at"),
                          "review": record.get("review"),
                          "unjustified": record.get("unjustified")}
        for c in record.get("concepts", []):
            concepts, statements = concept_chain(graph, c["id"])
            data["concepts"].append({
                "role": c["role"], "chain": concepts, "statements": statements,
                "mechanism": mechanism(records, c["id"], (path, here["scope"]))})
    # The concepts the rest of the enclosing scope serves.
    parent_scope = here["scope"].rsplit("#", 1)[0].rsplit(" > ", 1)[0]
    around = {}
    for r in regions:
        a, _ = matches[r["id"]]
        if a and r is not here and r["scope"].startswith(parent_scope):
            for c in a.get("concepts", []):
                around[c["id"]] = around.get(c["id"], 0) + 1
    data["enclosing"] = {"scope": parent_scope, "concepts": [
        {"id": cid, "name": graph["concepts"].get(cid, {}).get("name", "?"), "regions": n}
        for cid, n in sorted(around.items(), key=lambda kv: -kv[1])]}
    return data


def describe(data):
    out = [f"{data['path']}:{data['line']}  {data['region']['scope']} "
           f"[{data['region']['kind']} {data['region']['start']}-{data['region']['end']}]"]
    if not data["record"]:
        out.append("  No record covers this region.")
    else:
        rec = data["record"]
        note = " (stale: the code changed since it was reviewed)" if data["stale"] else ""
        out.append(f"  Record {rec['id']}, reviewed in {rec['review']}{note}")
        if rec.get("unjustified"):
            out.append(f"  Unjustified: {rec['unjustified']['reason']}")
    for c in data["concepts"]:
        first = c["chain"][0] if c["chain"] else {"id": "?", "name": "?", "claim": ""}
        out.append(f"\n{first['id']} {first['name']} ({c['role']})")
        if first["claim"]:
            out.append(f"  {first['claim']}")
        for anc in c["chain"][1:]:
            out.append(f"  within {anc['id']} {anc['name']}")
        for st in c["statements"]:
            kind = "" if st["kind"] == "claim" else f" ({st['kind']})"
            out.append(f"  because {st['id']}{kind}: {st['text']}")
        if c["mechanism"]:
            out.append(f"  Mechanism, {len(c['mechanism'])} other regions:")
            for m in c["mechanism"][:12]:
                scope = m["scope"] if m["scope"].startswith(m["path"]) else f"{m['path']}  {m['scope']}"
                if m["scope"] == m["path"]:
                    scope += f" lines {m['lines']}"
                out.append(f"    {scope}  ({m['role']})")
            if len(c["mechanism"]) > 12:
                out.append(f"    ...and {len(c['mechanism']) - 12} more")
    if data["enclosing"]["concepts"]:
        out.append(f"\nAround it, {data['enclosing']['scope']} serves: " + ", ".join(
            f"{c['id']} {c['name']} ({c['regions']})" for c in data["enclosing"]["concepts"][:6]))
    return "\n".join(out)
