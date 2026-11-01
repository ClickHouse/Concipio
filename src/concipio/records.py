"""Records: decisions about regions of code, keyed to the code itself."""

import hashlib
import re
import tomllib

import tomli_w


# Implements [CPO§K2]
def fingerprint(text):
    """A hash of the region's text with every run of whitespace, line breaks
    included, collapsed to one space, so reindenting or reflowing it leaves
    the fingerprint alone."""
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()[:20]


def evidence(lines):
    """The region's first non-blank line. It tells apart regions that share
    a scope [K21] and shows a person which code a record means; the rest of
    the text is in git at the reviewed commit, where the language server
    and `cpo show` read it."""
    kept = [l.strip() for l in lines if l.strip()]
    return kept[:1], []


def drop_none(value):
    """TOML has no null, so absent values are left out."""
    if isinstance(value, dict):
        return {k: drop_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [drop_none(v) for v in value]
    return value


def compact(code_path, records):
    """The on-disk form of a file's records: scopes relative to the file,
    the provenance most records share as file-level defaults, and one line
    of evidence each."""
    pairs = {}
    for r in records:
        key = (r.get("reviewed_at"), r.get("review"))
        pairs[key] = pairs.get(key, 0) + 1
    common = max(pairs, key=pairs.get) if pairs else (None, None)
    out = []
    for r in records:
        r = dict(r)
        scope = r["scope"]
        if scope == code_path:
            r["scope"] = ""
        elif scope.startswith(code_path + " > "):
            r["scope"] = ">" + scope[len(code_path) + 2:]
        if (r.get("reviewed_at"), r.get("review")) == common:
            r.pop("reviewed_at", None)
            r.pop("review", None)
        first = r.pop("first", None) or []
        if first:
            r["first"] = first[0]
        r.pop("last", None)
        out.append(r)
    data = {"defaults": {"reviewed_at": common[0], "review": common[1]}, "record": out}
    return drop_none(data)


def expand(code_path, data):
    """The in-memory form of a file's records, undoing compact()."""
    defaults = data.get("defaults", {})
    out = []
    for r in data.get("record", []):
        r = dict(defaults, **r)
        scope = r["scope"]
        if scope == "":
            r["scope"] = code_path
        elif scope.startswith(">"):
            r["scope"] = code_path + " >" + scope[1:]
        first = r.get("first")
        r["first"] = [first] if isinstance(first, str) else (first or [])[:1]
        r.pop("last", None)
        out.append(r)
    return out


def out_used(out):
    return [m[0] for m in out.values() if m[0] is not None]


class Records:
    """The records of one project, one TOML file per code file under
    regions/, mirroring the repository's paths [K8]."""

    def __init__(self, store):
        self.store = store
        self.dir = store.dir / "regions"
        self.cache = {}

    def path_for(self, code_path):
        return self.dir / (code_path + ".toml")

    def of(self, code_path):
        if code_path not in self.cache:
            p = self.path_for(code_path)
            self.cache[code_path] = expand(code_path, tomllib.loads(p.read_text())) \
                if p.exists() else []
        return self.cache[code_path]

    def save(self, code_path):
        records = self.of(code_path)
        p = self.path_for(code_path)
        if not records:
            if p.exists():
                p.unlink()
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        # Implements [CPO§K21]
        records.sort(key=lambda r: (r["side"], int(r["lines"].split("-")[0]),
                                    r.get("superseded", False)))
        body = f"# {code_path}\n\n" + tomli_w.dumps(compact(code_path, records))
        tmp = p.with_suffix(".tmp")
        tmp.write_text(body)
        tmp.replace(p)

    def current(self, code_path):
        """Records nothing has superseded."""
        return [r for r in self.of(code_path) if not r.get("superseded")]

    # Implements [CPO§K4]
    def match_all(self, spans):
        """Match spans to records, a scope at a time: first every span whose
        fingerprint a record has, then the changed spans left over, paired
        with the leftover records of their scope as a diff pairs hunks, by
        position [K21]. Return {span id: (record that applies, stale record)}."""
        out = {}
        groups = {}
        for sp in spans:
            groups.setdefault((sp["path"], sp["side"], sp["scope"]), []).append(sp)
        for (path, side, scope), members in groups.items():
            every = [r for r in self.of(path) if r["side"] == side and r["scope"] == scope]
            # A superseded record still applies where its old text still
            # stands, such as at the commit it was reviewed at; superseding
            # only says that a newer version of the region exists.
            pool = [r for r in every if not r.get("superseded")]
            left = []
            for sp in members:
                hit = next((r for r in every if r["fingerprint"] == sp["fingerprint"]
                            and r not in out_used(out)), None)
                if hit is not None:
                    if hit in pool:
                        pool.remove(hit)
                    out[sp["id"]] = (hit, None)
                else:
                    left.append(sp)
            for sp in left:
                stale = self.predecessor(sp, pool) if len(left) > 1 or len(pool) > 1 else \
                    (pool[0] if pool else None)
                if stale is not None:
                    pool.remove(stale)
                out[sp["id"]] = (None, stale)
        return out

    def match(self, span):
        return self.match_all([span])[span["id"]]

    @staticmethod
    def predecessor(span, candidates):
        """Among several leftover records in a scope, the one a changed span
        most likely was: the record whose lines overlap the span's most, or
        failing that, the only one whose first line it shares."""
        def overlap(r):
            a, b = (int(x) for x in r["lines"].split("-"))
            return min(b, span["end"]) - max(a, span["start"]) + 1

        best = sorted(candidates, key=overlap, reverse=True)
        if best and overlap(best[0]) > 0 and (len(best) == 1 or overlap(best[1]) < overlap(best[0])):
            return best[0]
        same_first = [r for r in candidates
                      if r.get("first") and r["first"][:1] == span.get("first", [])[:1]]
        return same_first[0] if len(same_first) == 1 else None

    # Implements [CPO§K16]
    def decide(self, span, review, commit, concepts, unjustified, match=None):
        """Write a span's decisions as its current record, superseding the
        stale record it replaces, or remove the record if nothing is
        decided. The caller passes the span's match when it has one, since
        matching is decided for a whole scope at once."""
        records = self.of(span["path"])
        applies, stale = match if match is not None else self.match(span)
        if applies is not None:
            records.remove(applies)
        if not concepts and not unjustified:
            self.save(span["path"])
            return None
        record = {
            "id": span["id"], "side": span["side"], "scope": span["scope"],
            "fingerprint": span["fingerprint"], "lines": f"{span['start']}-{span['end']}",
            "first": span.get("first", [])[:1],
            "reviewed_at": commit, "review": review,
            "concepts": [{"id": c, "role": role} for c, role in concepts],
        }
        if unjustified:
            record["unjustified"] = unjustified
        if stale is not None and stale is not applies:
            stale["superseded"] = True
            record["supersedes"] = stale["fingerprint"]
        elif applies is not None and applies.get("supersedes"):
            record["supersedes"] = applies["supersedes"]
        records.append(record)
        self.save(span["path"])
        return record

    def highest_id(self):
        top = 0
        if self.dir.exists():
            for p in self.dir.rglob("*.toml"):
                for r in tomllib.loads(p.read_text()).get("record", []):
                    top = max(top, int(r["id"][1:]))
        return top
