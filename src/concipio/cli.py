"""The cpo command."""

import argparse
import json
import re
import subprocess
import sys
import textwrap
from dataclasses import asdict
from importlib import resources

from pathlib import Path

from . import docs, lint as lint_mod, review


def emit(data, human, as_json):
    if as_json:
        json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        print(human)


def describe(d, defs):
    lines = [f"{d.tag}: {d.name}", f"  {d.path}:{d.line}"]
    if d.parent in defs:
        lines.append(f"  Refines {d.parent} ({defs[d.parent].name})")
    lines.append("")
    lines += textwrap.wrap(d.text, 76, initial_indent="  ",
                           subsequent_indent="  ")
    if d.children:
        lines.append("")
        lines.append("  Refined by:")
        lines += [f"    {c}  {defs[c].name}" for c in d.children]
    if d.citations:
        lines.append("")
        lines.append("  Cited by:")
        for c in d.citations:
            lines.append(f"    {c.path}:{c.line}  ({c.role})")
    return "\n".join(lines)


# Implements [CPO§V15]
def cmd_show(args, defs):
    queries = [q for arg in args.tags for q in re.split(r"[,\s]+", arg.strip("[]")) if q]
    found, missing = [], []
    for q in queries:
        tags = docs.resolve(q, defs)
        if len(tags) == 1:
            found.append(defs[tags[0]])
        elif tags:
            missing.append(f"{q} is ambiguous: {', '.join(sorted(tags))}")
        else:
            missing.append(f"{q} is not defined")
    emit([asdict(d) for d in found],
         "\n\n".join(describe(d, defs) for d in found), args.json)
    for m in missing:
        print(f"cpo: {m}", file=sys.stderr)
    return 1 if missing else 0


# Implements [CPO§F7]
def matches_where(d, wheres):
    for w in wheres or []:
        key, _, value = w.partition("=")
        if str(d.fields.get(key)) != value:
            return False
    return True


def cmd_list(args, defs):
    want = args.namespaces
    defs = {t: d for t, d in defs.items() if matches_where(d, getattr(args, "where", None))}
    rows = [defs[t] for t in sorted(defs, key=docs.sort_key)
            if (d := defs[t])
            and (not want or any(d.tag.split("§")[1].startswith(w) or
                               d.tag.startswith(w) for w in want))]
    emit([{"tag": d.tag, "name": d.name, "path": d.path, "line": d.line}
          for d in rows],
         "\n".join(f"{d.tag:<10} {d.name}" for d in rows), args.json)
    return 0


def cmd_tree(args, defs):
    if args.tags:
        roots = []
        for q in args.tags:
            roots += docs.resolve(q, defs)
    else:
        roots = [t for t in defs if defs[t].parent is None]
    rows = []

    def walk(tag, depth):
        rows.append((depth, defs[tag]))
        for c in defs[tag].children:
            walk(c, depth + 1)

    for r in roots:
        walk(r, 0)
    emit([{"tag": d.tag, "name": d.name, "depth": n, "parent": d.parent}
          for n, d in rows],
         "\n".join(f"{'  ' * n}{d.tag}  {d.name}" for n, d in rows), args.json)
    return 0


REVIEW_COMMANDS = {
    ("statement", "add"): review.cmd_statement_add,
    ("statement", "edit"): review.cmd_statement_edit,
    ("concept", "add"): review.cmd_concept_add,
    ("concept", "edit"): review.cmd_concept_edit,
    ("concept", "merge"): review.cmd_concept_merge,
    ("attach", None): review.cmd_attach,
    ("detach", None): review.cmd_detach,
    ("unjustified", None): review.cmd_unjustified,
    ("next", None): review.cmd_next,
    ("check", None): review.cmd_check,
    ("status", None): review.cmd_status,
    ("record", None): review.cmd_record,
    ("render", None): review.cmd_render,
}


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    fmt = common.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", default=None,
                     help="print JSON (the default when output is not a terminal)")
    fmt.add_argument("--human", dest="json", action="store_false",
                     help="print text (the default on a terminal)")
    parser = argparse.ArgumentParser(
        prog="cpo", description="Map every changed line of code to the concept it serves.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, help_, parent=sub):
        return parent.add_parser(name, parents=[common], help=help_)

    show = add("show", "show tags, spans, concepts, or statements")
    show.add_argument("tags", nargs="+", help="tags, IDs, or lists such as '[M3, R4]'")
    lst = add("list", "list defined tags with their names")
    lst.add_argument("namespaces", nargs="*", help="limit to these namespaces, such as M or R")
    lst.add_argument("--where", action="append", metavar="KEY=VALUE",
                     help="only statements whose field has this value")
    add("brief", "print what no agent or person may lose: critical statements and active work")
    au = add("audit", "score the repository: every problem by rule, and its marked debt")
    au.add_argument("--against", metavar="REV",
                    help="compare with another commit, and exit 1 if the score got worse")
    au.add_argument("--list", action="store_true", help="list each problem, not just the counts")
    cv = add("coverage", "how much of the code its design citations claim")
    cv.add_argument("paths", nargs="*", help="limit to these files or directories")
    cv.add_argument("--strict", action="store_true",
                    help="count only Implements and Tests citations, not mentions")
    cv.add_argument("--by", choices=["dir", "file"], default="dir",
                    help="group by top-level directory (default) or list every file")
    pa = add("path", "show the chain of links from the master to a doc or tag")
    pa.add_argument("target", help="a doc's path, a tag, or an ID")
    tree = add("tree", "show how statements refine one another")
    tree.add_argument("tags", nargs="*", help="roots to start from (default: all)")

    ln = add("lint", "check that every design fits on a screen")
    ln.add_argument("paths", nargs="*", help="Markdown files or directories (default: the repository)")
    ln.add_argument("--statement-limit", type=int)
    ln.add_argument("--section-limit", type=int)
    ln.add_argument("--breadth-limit", type=int, help="0 turns the breadth rule off")
    ln.add_argument("--write-baseline", action="store_true",
                    help="record today's problems, so later runs fail only on new or worse ones")
    ln.add_argument("--all", action="store_true", help="report problems the baseline knows too")

    rv = sub.add_parser("review", help="start a review").add_subparsers(dest="sub", required=True)
    init = add("init", "pin a change and list its spans", rv)
    init.add_argument("range", help="<base>..<head>")
    init.add_argument("--stacked-on", action="append", metavar="BASE..HEAD",
                      help="a change this one is stacked on, as context")
    init.add_argument("--pr", action="append", metavar="PR",
                      help="snapshot a pull request's title and description as design "
                           "text: OWNER/REPO#N, a URL, or N for the default repository")
    init.add_argument("--design-file", action="append", metavar="PATH",
                      help="snapshot a file as design text")
    init.add_argument("--limit", type=int, default=review.spans_mod.DEFAULT_LIMIT,
                      help="longest declaration a hunk widens to (default %(default)s lines)")

    st = sub.add_parser("statement", help="design statements").add_subparsers(dest="sub", required=True)
    sa = add("add", "add a given or drafted statement", st)
    sa.add_argument("--quote", help="exact text from the design text (a given statement)")
    sa.add_argument("--text", help="the statement, if it differs from the quote")
    sa.add_argument("--drafted", action="store_true", help="a statement written from the code")
    sa.add_argument("--parent", help="the statement this one refines, keeping the source's structure")
    sa.add_argument("--kind", choices=review.KINDS, default="claim",
                    help="claim (must be implemented), context, planned, or descriptive")
    se = add("edit", "change a statement's parent or kind", st)
    se.add_argument("statement")
    se.add_argument("--parent", help="the statement it refines; an empty string clears it")
    se.add_argument("--kind", choices=review.KINDS)

    co = sub.add_parser("concept", help="concepts").add_subparsers(dest="sub", required=True)
    ca = add("add", "add a concept", co)
    ca.add_argument("--name", required=True)
    ca.add_argument("--claim", help="a checkable claim citing its evidence spans, such as S12")
    ca.add_argument("--parent", help="a statement (D1) or broader concept (C1)")
    ce = add("edit", "change a concept", co)
    ce.add_argument("concept")
    ce.add_argument("--name")
    ce.add_argument("--claim")
    ce.add_argument("--parent")
    cm = add("merge", "merge one concept into another", co)
    cm.add_argument("source")
    cm.add_argument("into")

    at = add("attach", "attach a span to a concept")
    at.add_argument("span")
    at.add_argument("concept")
    at.add_argument("--role", choices=["implementation", "test"], default="implementation")
    de = add("detach", "detach a span from a concept")
    de.add_argument("span")
    de.add_argument("concept")
    un = add("unjustified", "mark a span unjustified")
    un.add_argument("span")
    un.add_argument("--reason", required=True)
    un.add_argument("--see", action="append", metavar="D#",
                    help="a context or planned statement that explains the span")
    nx = add("next", "give the next piece of work")
    nx.add_argument("--path", help="only spans in paths that start with this")
    nx.add_argument("--brief", action="store_true",
                    help="omit the concept list, for an agent that already has it")
    rc = add("record", "record tokens an agent spent on the review")
    rc.add_argument("--model", required=True)
    rc.add_argument("--tokens", type=int, default=0, help="total, when no split is known")
    rc.add_argument("--input-tokens", type=int, default=0)
    rc.add_argument("--output-tokens", type=int, default=0)
    rc.add_argument("--spans", type=int, default=0, help="spans the tokens covered")
    rc.add_argument("--note")
    rv2 = add("reviewable", "exit 0 if a change is ready for human review")
    rv2.add_argument("target", help="a pull request (OWNER/REPO#N, URL, or N) or <base>..<head>")
    rv2.add_argument("--stacked-on", action="append", metavar="BASE..HEAD")
    rv2.add_argument("--design-file", action="append", metavar="PATH")
    rv2.add_argument("--limit", type=int, default=review.spans_mod.DEFAULT_LIMIT)
    rv2.add_argument("--strict", action="store_true",
                     help="fail on undeclared behavior too")
    ck = add("check", "give the verdicts")
    ck.add_argument("--strict", action="store_true",
                    help="fail on undeclared behavior too: every span must reach a statement")
    rd = add("render", "write the review as a design doc in the store and lint it")
    rd.add_argument("--statement-limit", type=int, default=lint_mod.STATEMENT_LIMIT)
    rd.add_argument("--section-limit", type=int, default=lint_mod.SECTION_LIMIT)
    add("status", "report progress and stalls")
    wy = add("why", "explain why a line of code exists")
    wy.add_argument("target", help="path:line")
    wy.add_argument("--at", default="HEAD", help="the commit to read the file at (default HEAD)")
    sub.add_parser("lsp", help="run a language server on stdio for editors")
    add("migrate", "convert a store that filed decisions by review into records")
    hp = sub.add_parser("help", help="print guidance").add_subparsers(dest="sub", required=True)
    hp.add_parser("agent", help="print the protocol for an agent running a review")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, "json", None) is None:
        args.json = not sys.stdout.isatty()
    try:
        return dispatch(args)
    except (review.ReviewError, subprocess.CalledProcessError) as e:
        msg = e.stderr.strip() if isinstance(e, subprocess.CalledProcessError) else str(e)
        print(f"cpo: {msg}", file=sys.stderr)
        return 1


def dispatch(args):
    if args.command == "lsp":
        from . import lsp
        lsp.main()
        return 0
    if args.command == "help":
        print(resources.files("concipio").joinpath("prompts/agent.md").read_text())
        return 0
    repo = docs.repo_root()
    key = (args.command, getattr(args, "sub", None))
    if args.command == "why":
        from . import why
        data = why.why(repo, args.target, args.at)
        emit(data, why.describe(data), args.json)
        return 0
    if args.command in ("review", "reviewable", "migrate") or key in REVIEW_COMMANDS:
        with review.Store(repo).lock():
            return run_review_command(repo, key, args)
    _, defs, errors = docs.load()

    for e in errors:
        print(f"cpo: {e}", file=sys.stderr)
    if args.command == "coverage":
        status = cmd_coverage(args, defs, repo)
    elif args.command == "audit":
        status = cmd_audit(args, defs, repo)
    elif args.command == "path":
        status = cmd_path(args, defs, repo)
    elif args.command == "brief":
        status = cmd_brief(args, defs, repo)
    elif args.command == "lint":
        status = cmd_lint(args, defs, repo)
    elif args.command == "show":
        status = show_mixed(args, defs, repo)
    else:
        status = {"list": cmd_list, "tree": cmd_tree}[args.command](args, defs)
    return status or (1 if errors else 0)


def run_review_command(repo, key, args):
    if args.command == "migrate":
        data, human = review.cmd_migrate(repo, args)
        emit(data, human, args.json)
        return 0
    if args.command == "review":
        data, human = review.cmd_init(repo, args)
        emit(data, human, args.json)
        return 0
    if args.command == "reviewable":
        data, human, status = review.cmd_reviewable(repo, args)
        emit(data, human, args.json)
        return status
    data, human = REVIEW_COMMANDS[key](review.Review(repo), args)
    emit(data, human, args.json)
    if args.command == "check":
        return 0 if data["traced"] and data["explained"] else 1
    return 0


# Implements [CPO§F11]
def cmd_brief(args, defs, repo):
    import datetime
    cfg = docs.config(repo)
    s = lint_mod.field_settings(cfg)
    active = cfg.get("brief", {}).get("active", {})
    today = datetime.date.today()
    critical = [d for t, d in sorted(defs.items(), key=lambda kv: docs.sort_key(kv[0]))
                if d.fields.get(s["importance"]) in s["critical"]]
    working = [d for t, d in sorted(defs.items(), key=lambda kv: docs.sort_key(kv[0]))
               if active and str(d.fields.get(active.get("field"))) in active.get("values", [])]

    def stale(d):
        stamp = d.fields.get(s["updated"])
        try:
            age = (today - datetime.date.fromisoformat(str(stamp))).days
        except ValueError:
            return None
        return age if age > s["stale_after_days"] else None

    def short(text, n=160):
        return text if len(text) <= n else text[:n - 3].rstrip() + "..."

    lines = []
    if critical:
        lines.append("Critical:")
        lines += [f"  {d.tag} {d.name} ({d.path}:{d.line})"
                  + (f"  [STALE: {d.fields[s['stale']]}]" if s["stale"] in d.fields else "") + (
            "" if short(d.text).startswith(d.name.rstrip('.')) else f"\n    {short(d.text)}")
            for d in critical]
    if working:
        lines.append("Active:")
        for d in working:
            extra = ", ".join(f"{k}={v}" for k, v in d.fields.items()
                              if k not in (active.get("field"), s["importance"]))
            flag = f"  [no update in {stale(d)} days]" if stale(d) else ""
            lines.append(f"  {d.tag} {d.name}" + (f" ({extra})" if extra else "") + flag)
    if not lines:
        lines.append("Nothing is marked critical or active.")
    emit({"critical": [{"tag": d.tag, "name": d.name, "text": d.text, "path": d.path,
                        "line": d.line, "fields": d.fields} for d in critical],
          "active": [{"tag": d.tag, "name": d.name, "fields": d.fields,
                      "stale_days": stale(d)} for d in working]},
         "\n".join(lines), args.json)
    return 0


def cmd_coverage(args, defs, repo):
    files = docs.tracked_files(repo)
    if args.paths:
        want = [str(Path(p).resolve().relative_to(repo)).rstrip("/") for p in args.paths]
        files = [f for f in files if any(f == w or f.startswith(w + "/") for w in want)]
    rows = lint_mod.coverage(repo, files, defs, docs.config(repo).get("exclude", []),
                             strict=args.strict)

    def total(rs):
        return sum(r["covered"] for r in rs), sum(r["lines"] for r in rs)

    def pct(c, n):
        return f"{100 * c / n:5.1f}%" if n else "    -"

    measured = [r for r in rows if r["measured"]]
    impl = [r for r in measured if not r["test"]]
    tests = [r for r in measured if r["test"]]
    lines = ["Covered by " + ("Implements and Tests citations" if args.strict
                              else "any citation, mentions included") + ":"]
    for label, rs in (("implementation", impl), ("tests", tests)):
        c, n = total(rs)
        lines.append(f"{label:15} {c:7} of {n:7} lines covered  {pct(c, n)}")
        x = sum(r["exempt"] for r in rs)
        if x:
            lines.append(f"{'':15} {x:7} more exempt, {pct(c + x, n)} accounted for")
    un = [r for r in rows if not r["measured"]]
    if un:
        lines.append(f"{'unmeasured':15} {sum(r['lines'] for r in un):7} lines in {len(un)} "
                     f"files no parser reads ({', '.join(sorted({Path(r['path']).suffix for r in un}))})")
    groups = {}
    for r in measured:
        key = r["path"] if args.by == "file" else (r["path"].split("/", 1)[0] if "/" in r["path"] else ".")
        groups.setdefault(key, []).append(r)
    lines.append("")
    for key in sorted(groups, key=lambda k: -total(groups[k])[1]):
        c, n = total(groups[key])
        lines.append(f"  {pct(c, n)}  {c:7} / {n:<7} {key}")
    marks = [(r["path"], e) for r in rows for e in r["exemptions"]]
    if marks:
        lines.append("")
        lines.append(f"Exempt, as serving no design [T15]:")
        lines += [f"  {path}:{e['line']}: {e['reason']}" for path, e in marks]
    emit({"implementation": {**dict(zip(("covered", "lines"), total(impl))),
                             "exempt": sum(r["exempt"] for r in impl)},
          "tests": {**dict(zip(("covered", "lines"), total(tests))),
                    "exempt": sum(r["exempt"] for r in tests)},
          "unmeasured": sum(r["lines"] for r in un), "files": rows},
         "\n".join(lines), args.json)
    return 0


def audit_at(repo, args, defs=None):
    files = docs.tracked_files(repo)
    if defs is None:
        _, defs, _ = docs.load(root=repo, files=files)
    result = lint_mod.audit(repo, files, defs, lint_limits(repo, args), docs.config(repo))
    exclude = docs.config(repo).get("exclude", [])
    result["coverage"] = {}
    for key, strict in (("any", False), ("strict", True)):
        rows = [r for r in lint_mod.coverage(repo, files, defs, exclude, strict)
                if r["measured"] and not r["test"]]
        n = sum(r["lines"] for r in rows)
        result["coverage"][key] = 100 * sum(r["covered"] for r in rows) / n if n else 0.0
        if key == "strict":
            done = sum(r["covered"] + r["exempt"] for r in rows)
            result["coverage"]["accounted"] = 100 * done / n if n else 0.0
    return result


def audit_rev(repo, rev, args, config=None):
    """The audit of another commit, in a temporary worktree removed after,
    under the given `.cpo` text or the commit's own."""
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="cpo-audit-")) / "tree"
    subprocess.run(["git", "worktree", "add", "--quiet", "--detach", str(tmp), rev],
                   cwd=repo, check=True, capture_output=True)
    try:
        if config is not None:
            (tmp / ".cpo").write_text(config)
        return audit_at(tmp, args)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(tmp)], cwd=repo,
                       capture_output=True)


def cmd_audit(args, defs, repo):
    now = audit_at(repo, args, defs)
    before = own = None
    if args.against:
        # The docs are compared under today's checks, so adopting a check
        # is not a regression; the checks themselves are compared apart.
        mine = repo / ".cpo"
        config = mine.read_text() if mine.exists() else None
        theirs = subprocess.run(["git", "show", f"{args.against}:.cpo"], cwd=repo,
                                capture_output=True, text=True)
        before = audit_rev(repo, args.against, args, config)
        if config is not None and (theirs.returncode or theirs.stdout != config):
            own = audit_rev(repo, args.against, args)

    def delta(a, b):
        return f"{'+' if a >= b else ''}{a - b}"
    rules = set(now["rules"]) | set(before["rules"] if before else [])
    lines = [f"Score {now['score']}" + (
        f" (was {before['score']} at {args.against}, {delta(now['score'], before['score'])})"
        if before else "")]
    if own:
        tighter = before["score"] - own["score"]
        lines.append(f"  .cpo changed since {args.against}, which scores {own['score']} under "
                     f"its own: the checks are {'stricter' if tighter >= 0 else 'looser'} "
                     f"by {abs(tighter)}" + ("" if tighter >= 0 else "; that fails the audit"))
    for c in [*lint_mod.STANDARDS, "other"]:
        mine = sorted(r for r in rules if lint_mod.standard_of(r) == c)
        if not mine and c == "other":
            continue
        note = ""
        if c == "completeness":
            cov = now["coverage"]
            note = (f"  (implementation coverage {cov['any']:.1f}%, "
                    f"{cov['strict']:.1f}% strictly, {cov['accounted']:.1f}% "
                    "accounted for with exemptions)")
        lines.append(f"  {c.capitalize()}: {now['standards'].get(c, 0)}{note}")
        for r in mine:
            n = now["rules"].get(r, 0)
            was = f"  (was {before['rules'].get(r, 0)})" if before else ""
            lines.append(f"    {n:5}  {r}{was}")
    stale = now["debt"]["stale"]
    lines.append(f"Debt, not scored: {len(stale)} marked stale, "
                 f"{len(now['debt']['postponed_orphans'])} orphans postponed")
    for m in stale:
        lines.append(f"  stale: {m['path']}:{m['line']} {m['what']}: {m['reason']}")
    if args.list:
        lines += [f"{p.path}:{p.line}: {p.rule}: {p.message}" for p in now["problems"]]
    data = {"score": now["score"], "standards": now["standards"], "rules": now["rules"],
            "coverage": now["coverage"], "debt": now["debt"],
            "problems": [asdict(p) for p in now["problems"]] if args.list else None}
    if before:
        data["against"] = {"rev": args.against, "score": before["score"], "rules": before["rules"],
                           "own_config_score": own["score"] if own else before["score"]}
    emit(data, "\n".join(lines), args.json)
    worse = before and now["score"] > before["score"]
    looser = own and before["score"] < own["score"]
    return 1 if worse or looser else 0


def cmd_path(args, defs, repo):
    target = args.target
    if target not in defs:
        tags = docs.resolve(target, defs)
        if len(tags) == 1:
            target = tags[0]
        elif tags:
            print(f"cpo: {target} is ambiguous: {', '.join(sorted(tags))}", file=sys.stderr)
            return 1
        else:
            full = (Path.cwd() / target).resolve()
            target = str(full.relative_to(repo)) if full.is_relative_to(repo) else target
    limits = lint_limits(repo, args)
    found = lint_mod.path_to(repo, docs.tracked_files(repo), defs, target, limits["master"])
    if found is None:
        print(f"cpo: {args.target} is not reachable from {limits['master']}", file=sys.stderr)
        return 1
    chain, inner = found
    lines = [f"{'  ' * i}{doc}" for i, doc in enumerate(chain)]
    lines += [f"{'  ' * (len(chain) + i)}{t}  {defs[t].name}" for i, t in enumerate(inner)]
    emit({"docs": chain, "statements": inner, "depth": len(chain) - 1},
         "\n".join(lines), args.json)
    return 0


def lint_limits(repo, args):
    """Limits from `.cpo`'s [lint] table, overridden by flags [T33]."""
    cfg = docs.config(repo)
    table = cfg.get("lint", {})
    limits = {"statement_limit": table.get("statement_limit", lint_mod.STATEMENT_LIMIT),
              "section_limit": table.get("section_limit", lint_mod.SECTION_LIMIT),
              "breadth_limit": table.get("breadth_limit", lint_mod.BREADTH_LIMIT),
              "master": cfg.get("master", "README.md"),
              "postponed": [p if isinstance(p, str) else p["path"]
                            for p in table.get("postponed", [])]}
    for key in ("statement_limit", "section_limit", "breadth_limit"):
        if getattr(args, key, None) is not None:
            limits[key] = getattr(args, key)
    return limits


def baseline_path(repo):
    where = docs.config_path(repo)
    if where is not None and where.name == "cpo.toml":
        return where.parent / "lint-baseline.toml"
    return Path(repo) / ".cpo-baseline.toml"


# Implements [CPO§T40]
def cmd_lint(args, defs, repo):
    import tomllib

    import tomli_w
    files = docs.tracked_files(repo)
    limits = lint_limits(repo, args)
    if args.paths:
        want = [str(Path(p).resolve().relative_to(repo)) for p in args.paths]
        files_in = [f for f in files if any(f == w or f.startswith(w.rstrip("/") + "/")
                                            for w in want)]
    else:
        files_in = files
    problems, later = lint_mod.check(repo, files, defs, limits, docs.config(repo))
    problems = [p for p in problems if p.path in files_in]
    base_file = baseline_path(repo)
    if args.write_baseline:
        base_file.write_text("# Problems known when the baseline was written. cpo lint fails\n"
                             "# only on problems that are new, or worse than recorded here.\n\n"
                             + tomli_w.dumps({"problem": [
                                 {"rule": p.rule, "path": p.path, "key": p.key, "value": p.value}
                                 for p in problems]}))
        emit({"baseline": str(base_file), "problems": len(problems)},
             f"Recorded {len(problems)} problems in {base_file}.", args.json)
        return 0
    baseline = (tomllib.loads(base_file.read_text()).get("problem", [])
                if base_file.exists() else [])
    fresh = [p for p in problems if not lint_mod.known(p, baseline)]
    shown = problems if args.all else fresh
    lines = [f"{p.path}:{p.line}: {p.rule}: {p.message}" for p in shown]
    if baseline:
        lines.append(f"{len(problems) - len(fresh)} known problems recorded in the baseline"
                     + (", shown" if args.all else ", not shown"))
    if later:
        lines.append(f"{len(later)} orphans postponed in .cpo")
    if not problems:
        lines.insert(0, "Every design fits on a screen, reaches the master, and claims "
                        "no more code than its limit.")
    emit({"problems": [asdict(p) for p in shown], "new": len(fresh), "known":
          len(problems) - len(fresh), "postponed_orphans": later, "limits": limits},
         "\n".join(lines), args.json)
    return 1 if fresh else 0


def show_mixed(args, defs, repo):
    """Show review items (S, C, and D IDs) from the store, and tags from
    the docs."""
    try:
        r = review.Review(repo)
    except review.ReviewError:
        r = None
    queries = [q for arg in args.tags for q in re.split(r"[,\s]+", arg.strip("[]")) if q]
    rest, out, status = [], [], 0
    for q in queries:
        item = review.show_item(r, q) if r and re.fullmatch(r"[SCD]\d+", q) else None
        if item:
            out.append(item)
        else:
            rest.append(q)
    if out:
        emit([d for d, _ in out], "\n\n".join(h for _, h in out), args.json)
    if rest:
        args.tags = rest
        status = cmd_show(args, defs)
    return status


if __name__ == "__main__":
    sys.exit(main())
