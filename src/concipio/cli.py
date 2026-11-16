"""The cpo command."""

import argparse
import json
import re
import subprocess
import time
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
    au = add("audit", "score the repository; or, with an action, work a named audit")
    au.add_argument("action", nargs="?",
                    choices=["propose", "start", "next", "done", "note", "why", "mine",
                             "status"],
                    help="propose: size a milestone to put to a person; start: record the "
                         "milestone a person approved; "
                         "next: claim a unit and print its brief; done: record its outcome; "
                         "note: add a lead worth checking later; "
                         "why: what changed in a stale unit; mine: what you hold; "
                         "status: where the audit stands")
    au.add_argument("name", nargs="?", help="the audit's name, such as its date")
    au.add_argument("unit", nargs="?", help="for done and why: the unit, such as DESIGN§5c; "
                                            "for note: the lead's text")
    au.add_argument("--budget", type=int, default=6000,
                    help="for next: tokens of code the brief may include (default 6000)")
    au.add_argument("--scope", nargs="*", default=[],
                    help="for next: docs, directories, or tags to draw units from")
    out = au.add_mutually_exclusive_group()
    out.add_argument("--verified", action="store_true", help="for done: the unit's claims hold")
    out.add_argument("--drafted", action="store_true",
                     help="for done: the design now describes this code")
    out.add_argument("--finding", metavar="TEXT", help="for done: what is wrong, and where")
    out.add_argument("--question", metavar="TEXT", help="for done: what a person must decide")
    au.add_argument("--for", dest="to", metavar="WHO", help="for done --question: whom it is for")
    au.add_argument("--where", metavar="PATH:LINE", help="for note: where the lead is")
    au.add_argument("--approved-by", metavar="WHO",
                    help="for start: the person who approved the milestone")
    au.add_argument("--at", metavar="SHA",
                    help="for done: the commit the check was made at, if not HEAD")
    au.add_argument("--against", metavar="REV",
                    help="compare with another commit, and exit 1 if the score got worse")
    au.add_argument("--list", action="store_true", help="list each problem, not just the counts")
    cv = add("coverage", "how much of the code its design citations claim")
    cv.add_argument("paths", nargs="*", help="limit to these files or directories")
    cv.add_argument("--strict", action="store_true",
                    help="count only Implements and Tests citations, not mentions")
    cv.add_argument("--by", choices=["dir", "file"], default="dir",
                    help="group by top-level directory (default) or list every file")
    he = add("helpers", "sort the helpers no citation covers by the design they serve")
    he.add_argument("paths", nargs="*", help="limit to these files or directories")
    he.add_argument("--limit", type=int, default=10,
                    help="helpers to list per group, largest first; 0 lists all (default 10)")
    he.add_argument("--counts", action="store_true", help="only count each group")
    he.add_argument("--macros", action="store_true",
                    help="list function-like macros as helpers too")
    ur = add("unreachable", "find comments claiming a state cannot happen, and what backs them")
    ur.add_argument("paths", nargs="*", help="limit to these files or directories")
    ur.add_argument("--all", action="store_true", help="list backed claims too")
    un = add("unwritten", "find guards whose comments state a rule no design records")
    un.add_argument("paths", nargs="*", help="limit to these files or directories")
    un.add_argument("--all", action="store_true",
                    help="any guard with an explaining comment, not only those naming an incident")
    add("config", "show the settings in effect, with each default marked")
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
    sa = add("add", "add a stated or inferred statement", st)
    sa.add_argument("--quote", help="exact text from the design text (a stated statement)")
    sa.add_argument("--text", help="the statement, if it differs from the quote")
    sa.add_argument("--inferred", action="store_true", help="a statement written from the code")
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
    stp = add("status", "what is in progress, then the score: every problem by rule")
    stp.add_argument("--against", metavar="REV",
                     help="compare with another commit, and exit 1 if the score got worse")
    stp.add_argument("--list", action="store_true", help="list each problem, not just the counts")
    wy = add("why", "explain why a line of code exists")
    wy.add_argument("target", help="path:line")
    wy.add_argument("--at", default="HEAD", help="the commit to read the file at (default HEAD)")
    sub.add_parser("lsp", help="run a language server on stdio for editors")
    add("migrate", "convert a store that filed decisions by review into records")
    hp = sub.add_parser("help", help="print guidance").add_subparsers(dest="sub", required=True)
    hp.add_parser("agent", help="print the guide for an agent: reviews, adoption, audits")
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
        text = resources.files("concipio").joinpath("prompts/agent.md").read_text()
        # The guide's HTML comments are for its maintainers, not for agents.
        print(re.sub(r"<!--.*?-->\n?", "", text, flags=re.S).lstrip("\n"), end="")
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
    elif args.command == "helpers":
        status = cmd_helpers(args, defs, repo)
    elif args.command == "unreachable":
        status = cmd_unreachable(args, defs, repo)
    elif args.command == "unwritten":
        status = cmd_unwritten(args, defs, repo)
    elif args.command == "config":
        status = cmd_config(args, defs, repo)
    elif args.command == "status":
        status = cmd_status(args, defs, repo)
    elif args.command == "audit" and args.action:
        status = cmd_worklist(args, defs, repo)
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


def under(repo, files, paths):
    """The files at or below the given paths, or all of them."""
    if not paths:
        return files
    want = [str(Path(p).resolve().relative_to(repo)).rstrip("/") for p in paths]
    return [f for f in files if any(f == w or f.startswith(w + "/") for w in want)]


def named_lines(repo, defs):
    """The lines of code each file's design units claim, by name or by
    citation [CPO§T77]."""
    from . import worklist
    out = {}
    for _, regions, _ in worklist.survey(repo, defs):
        for path, n in worklist.lines_of(repo, regions):
            out.setdefault(path, set()).add(n)
    return out


def cmd_coverage(args, defs, repo):
    files = docs.tracked_files(repo)
    files = under(repo, files, args.paths)
    rows = lint_mod.coverage(repo, files, defs, docs.config(repo).get("exclude", []),
                             strict=args.strict, named=named_lines(repo, defs))

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
        k = sum(r["claimed"] for r in rs)
        if k > c:
            lines.append(f"{'':15} {k:7} claimed by citations or the design naming them, "
                         f"{pct(k, n)}")
        x = sum(r["exempt"] for r in rs)
        if x:
            lines.append(f"{'':15} {x:7} more exempt, {pct(max(c, k) + x, n)} accounted for")
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
        lines += [f"  {path}" + (f":{e['line']}" if e["line"] else "")
                  + (" (in .cpo)" if e.get("by") else "") + f": {e['reason']}"
                  for path, e in marks]
    emit({"implementation": {**dict(zip(("covered", "lines"), total(impl))),
                             "claimed": sum(r["claimed"] for r in impl),
                             "exempt": sum(r["exempt"] for r in impl)},
          "tests": {**dict(zip(("covered", "lines"), total(tests))),
                    "claimed": sum(r["claimed"] for r in tests),
                    "exempt": sum(r["exempt"] for r in tests)},
          "unmeasured": sum(r["lines"] for r in un), "files": rows},
         "\n".join(lines), args.json)
    return 0


def describe_changes(changes):
    out = []
    for c in changes:
        out.append(f"{c['what']}: {c['where']}")
        out += [f"  {line}" for line in c["commits"][:8]]
        if len(c["commits"]) > 8:
            out.append(f"  ... and {len(c['commits']) - 8} more commits")
        out += [c["diff"], ""] if c["diff"] else []
    return out


# Implements [CPO§W8]
def audit_extras(r, name):
    """The lines of an audit's status about drafting, leads, and whether
    the draft is ready for a person [CPO§W40, CPO§W43, CPO§W44]."""
    lines = []
    dr = r["drafting"]
    if dr["units"]:
        held = [x for x in dr["rows"] if x["standing"] in ("claimed", "question")]
        # An audit begun on a design drafts last [CPO§W40], so say when.
        ahead = sum(1 for x in r["rows"] if x["standing"] in ("open", "stale")) + \
            sum(1 for x in r["leads"]["rows"] if x["standing"] == "open")
        when = "first" if r["drafts_first"] else \
            f"after the {ahead} checks and leads still open" if ahead else "next"
        lines.append(f"  to draft: {dr['units']} units of code, {dr['lines']} lines, that no "
                     f"design claims; cpo audit next {name} hands them out {when}.")
        for x in held:
            extra = (f" by {x['holder']}" if x["holder"] else "") + (
                f": {x['note']}" if x["note"] else "")
            lines.append(f"  {x['standing']:9} {x['unit']}{extra}")
    open_leads = [x for x in r["leads"]["rows"] if x["standing"] in ("open", "claimed")]
    if open_leads:
        lines.append(f"  leads: {len(open_leads)} open")
        for x in open_leads[:12]:
            lines.append(f"  {x['standing']:9} {x['unit']} {x['where'] or ''}: {x['name']}")
        if len(open_leads) > 12:
            lines.append(f"  ... and {len(open_leads) - 12} more; --json lists them all.")
    for x in r["leads"]["rows"]:
        if x["standing"] in ("finding", "question"):
            lines.append(f"  {x['standing']:9} {x['unit']} {x['where'] or ''}: {x['note']}"
                         + (f" (for {x['for']})" if x["for"] else ""))
    busy = ("open", "claimed", "stale")
    if r.get("questions") and not any(x["standing"] in busy
                                      for x in r["rows"] + dr["rows"] + r["leads"]["rows"]):
        lines.append(f"  Only questions for a person remain: {', '.join(r['questions'])}. The "
                     "milestone is reached when they are answered.")
    if r["ready"]:
        lines.append(("  The milestone is reached" if r.get("milestone") else
                      "  The draft is in order") + ": every unit is drafted and checked, and "
                     "every lead closed. Ask a person to sign its outline, the docs, sections, "
                     "and headings, not every line.")
    return lines


def cmd_worklist(args, defs, repo):
    from . import worklist
    from .store import Store
    if not args.name:
        raise SystemExit(f"cpo audit {args.action} needs the audit's name")
    store = Store(repo)
    if args.action == "propose":
        r = worklist.propose(repo, store, defs, args.name,
                             [worklist.unit_name(defs, x) for x in args.scope])
        text = r["sentence"] + (f"\n\nOnce they agree: {r['approve']}" if r.get("approve") else "")
        emit(r, text, args.json)
        return 0
    if args.action == "start":
        if not args.approved_by:
            raise SystemExit("cpo audit start NAME needs --approved-by: the person who agreed "
                             "to the milestone. Propose one first with cpo audit propose NAME.")
        r = worklist.start(repo, store, args.name,
                           [worklist.unit_name(defs, x) for x in args.scope], args.approved_by)
        where = ", ".join(r["scope"]) or "the whole repository"
        emit(r, f"{args.name}: milestone recorded, {where} in order, approved by "
             f"{r['approved_by']}. Work it with cpo audit next {args.name}.", args.json)
        return 0
    if args.action == "note":
        if not args.unit:
            raise SystemExit("cpo audit note NAME TEXT needs the lead's text")
        with store.lock():
            audit = worklist.Audit(store, args.name)
            state = audit.load()
            tag = worklist.add_lead(state, args.unit, args.where, worklist.agent()[0])
            audit.save(state)
        audit.log({"event": "note", "unit": tag, "by": worklist.agent()[0], "note": args.unit})
        emit({"audit": args.name, "unit": tag}, f"{tag}: noted in {args.name}; any agent can "
             f"claim it with cpo audit next {args.name}.", args.json)
        return 0
    if args.unit:
        args.unit = worklist.unit_name(defs, args.unit)
    args.scope = [worklist.unit_name(defs, s) for s in args.scope]
    if args.action == "next":
        b = worklist.next_unit(repo, store, defs, args.name, args.budget, args.scope)
        if b.get("error") or b.get("done"):
            emit(b, b.get("error") or b["message"], args.json)
            return 2 if b.get("error") else 0
        what = {"draft": "Code to draft", "lead": "A lead"}.get(b["kind"])
        lines = [(f"{what}, {b['unit']}" if what else f"{b['unit']} ({b['name']})")
                 + (f", {b['where']}" if b["where"] else "")
                 + f", claimed by {b['holder']} for two hours.", ""]
        if not b.get("milestone"):
            lines += ["No person has approved a milestone for this audit. If you were given "
                      f"room to drive, propose one first: cpo audit propose {args.name}.", ""]
        if b.get("drafted"):
            lines += ["An agent drafted this section from the code, so a mismatch may be a "
                      "defect in the code or in the draft; check both, and say which.", ""]
        if b["before"]:
            lines += [f"It was {b['before']['status']} at {b['before']['sha']}"
                      + (f": {b['before']['note']}" if b["before"].get("note") else "")
                      + "; it has changed since.", ""]
        if b.get("changed"):
            lines += ["What changed since it was checked:", ""] + describe_changes(b["changed"])
            lines.append("")
        lines += [b["text"], ""]
        for c in b["code"]:
            if c["text"] is None:
                lines.append(f"--- {c['where']} ({c['omitted']} lines, over the budget; read it "
                             "yourself)")
            else:
                lines += [f"--- {c['where']}", c["text"]]
        if b["pointers"]:
            lines.append("It points to: " + ", ".join(b["pointers"]))
        if not b["code"] and b["kind"] == "check":
            lines.append("It names and cites no code Concipio can find; check it against the "
                         "code yourself.")
        lines += ["", b["next"] + "."]
        emit(b, "\n".join(lines), args.json)
        return 0
    if args.action == "done":
        if not args.unit or not (args.verified or args.drafted or args.finding or args.question):
            raise SystemExit("cpo audit done NAME UNIT needs --verified, --drafted, --finding, "
                             "or --question")
        st = "verified" if args.verified else "drafted" if args.drafted else \
            "finding" if args.finding else "question"
        r = worklist.record(repo, store, defs, args.name, args.unit, st,
                            args.finding or args.question, args.to, args.at)
        emit(r, r.get("error") or f"{args.unit}: {st} at {r['sha']}" + (
            f", in {', '.join(r['sections'])}" if r.get("sections") else "") + ".", args.json)
        return 1 if r.get("error") else 0
    if args.action == "why":
        if not args.unit:
            raise SystemExit("cpo audit why NAME UNIT needs the unit")
        state = worklist.Audit(store, args.name).load()
        r = worklist.why_stale(repo, defs, state, args.unit)
        if r.get("error"):
            emit(r, r["error"], args.json)
            return 1
        lines = [f"{r['unit']} was {r['status']} at {r['checked']}."]
        lines += describe_changes(r["changes"]) if r["changes"] else [
            "Nothing it claims has changed since."]
        emit(r, "\n".join(lines), args.json)
        return 0
    r = worklist.status(repo, store, defs, args.name, only_me=args.action == "mine")
    goal = r.get("milestone")
    lines = [(f"{r['audit']}: {r['verified_units']} of {r['units']} units verified, "
              f"{r['verified_lines']} of {r['lines']} lines of the code they claim."
              if r["units"] else f"{r['audit']}: no design units to check yet.")
             if args.action == "status" else f"Yours in {r['audit']}:"]
    if args.action == "status":
        lines.append(f"  milestone: {', '.join(goal['scope']) or 'the whole repository'} in "
                     f"order, approved by {goal['approved_by']}" if goal else
                     f"  milestone: none approved; cpo audit propose {args.name} sizes one")
    if r["counts"]:
        lines.append("  " + ", ".join(f"{n} {k}" for k, n in sorted(r["counts"].items())))
    for row in r["rows"]:
        if row["standing"] in ("claimed", "finding", "question", "stale"):
            extra = (f" by {row['holder']}" if row["holder"] else "") + (
                f": {row['note']}" if row["note"] else "") + (
                f" (for {row['for']})" if row["for"] else "")
            lines.append(f"  {row['standing']:9} {row['unit']} {row['name']}{extra}")
    quiet = sum(1 for row in r["rows"] if row["standing"] in ("open", "verified"))
    if quiet:
        lines.append(f"  ({quiet} open or verified units are not listed; --json lists every "
                     "unit.)")
    lines += audit_extras(r, args.name)
    emit(r, "\n".join(lines), args.json)
    return 0


# Implements [CPO§T63]
def cmd_unreachable(args, defs, repo):
    from . import claims
    cfg = docs.config(repo)
    files = under(repo, docs.tracked_files(repo), args.paths)
    rows = claims.impossibility_claims(repo, files, defs, cfg.get("exclude", []),
                                       cfg.get("unreachable", {}))
    bare = [r for r in rows if not r["evidence"]]
    lines = [f"{len(rows)} claims that a state cannot happen; {len(bare)} name no test, sit "
             "beside no static assertion, and cite no tested design point."]
    for r in rows if args.all else bare:
        where = f"{r['path']}:{r['line']}" + (f" {r['function']}" if r["function"] else "")
        lines += ["", f"{where}  [{r['claim']}]" + (f"  backed: {r['evidence']}"
                                                   if r["evidence"] else ""),
                  f"  {r['text'][:200]}"]
    if bare:
        lines += ["", "Each needs a test that drives the state, named in the comment, a static "
                  "assertion, or a disposition."]
    emit({"claims": rows, "unbacked": len(bare)}, "\n".join(lines), args.json)
    return 0


# Implements [CPO§T58]
def cmd_unwritten(args, defs, repo):
    from . import helpers
    cfg = docs.config(repo)
    files = under(repo, docs.tracked_files(repo), args.paths)
    rows = helpers.unwritten_rules(repo, files, defs, cfg.get("exclude", []),
                                   cfg.get("unwritten", {}).get("incident", []), args.all)
    lines = [f"{len(rows)} rules, kept by guards in code citing no design, are explained by "
             "a comment" + ("" if args.all else " that names an incident") + "."]
    for r in rows:
        mark = f"  [{', '.join(r['markers'])}]" if r["markers"] else ""
        text = r["comment"] if len(r["comment"]) <= 160 else r["comment"][:157] + "..."
        lines += ["", f"{r['path']}:{r['line']} {r['function']}{mark}",
                  f"  {r['guard'][:100]}"]
        if r["evidence"]:
            lines.append(f"  The predicate's header says why, at {r['evidence']}:")
        lines.append(f"  {text}")
        if r["also"]:
            lines.append(f"  Guards relying on it too: {', '.join(r['also'])}")
    if rows:
        lines += ["", "Each states a rule the code enforces. Write it into the design, "
                  "and cite it from here."]
    emit({"guards": rows}, "\n".join(lines), args.json)
    return 0


# Implements [CPO§T57]
def cmd_helpers(args, defs, repo):
    from . import helpers
    # Callers outside the paths asked about still count, so the whole
    # repository is read and only the report is narrowed.
    files = docs.tracked_files(repo)
    rows, alike = helpers.taxonomy(repo, files, defs, docs.config(repo).get("exclude", []),
                                   macros=args.macros)
    if args.paths:
        mine = set(under(repo, files, args.paths))
        rows = [r for r in rows if r["path"] in mine]
        alike = [a for a in alike
                 if any(h.split(":", 1)[0] in mine for h in a["helpers"])]
    groups = {}
    for r in rows:
        if len(r["serves"]) >= 4:
            label = (1, "Serving four or more design points: shared infrastructure, "
                        "or a mechanism awaiting its own citation")
        elif r["serves"]:
            label = (0, "Serving " + r["serves"][0])
        elif r["callers"]:
            label = (2, "Called only by code nothing cites")
        elif r["tested"]:
            label = (3, "Called only by tests")
        elif r["outer"]:
            label = (4, "Named only outside any function: callbacks, tables, entry points")
        else:
            label = (5, "Called by nothing Concipio can see: dead, or called indirectly")
        groups.setdefault(label, []).append(r)
    lines = [f"{len(rows)} helpers no citation covers, in "
             f"{len({r['path'] for r in rows})} files."]
    limit = args.limit or None
    order = sorted(groups, key=lambda g: (g[0], -len(groups[g]), g[1]))
    for label in order:
        rs, label = groups[label], label[1]
        cut = "" if args.counts else ":" if not limit or len(rs) <= limit else \
            f", {limit} largest:"
        lines += ([] if args.counts else [""]) + [
            f"{label} ({len(rs)}, {sum(r['lines'] for r in rs)} lines){cut}"]
        if args.counts:
            continue
        for r in sorted(rs, key=lambda r: -r["lines"])[:limit]:
            far = f", {r['hops']} calls away" if r["hops"] and r["hops"] > 1 else ""
            also = f", also {', '.join(r['serves'][1:])}" if 1 < len(r["serves"]) < 4 else ""
            lines.append(f"  {r['path']}:{r['line']} {r['name']} ({r['lines']} lines{far}{also})")
    if alike:
        lines += ([] if args.counts else [""]) + [
            f"Look alike, so may duplicate one another ({len(alike)} clusters, "
            f"{sum(a['lines'] for a in alike)} lines)" + ("" if args.counts else ":")]
        for a in [] if args.counts else alike[:limit and limit * 2]:
            lines.append(f"  {a['lines']} lines with {' and '.join(a['why'])}:")
            lines += [f"    {h}" for h in a["helpers"]]
            if a["differ"]:
                lines.append("    They differ:")
                lines += [f"      {d['role']:17} {d['where']}: {', '.join(d['names'])}"
                          for d in a["differ"]]
        if not args.counts and any(a["differ"] for a in alike):
            lines += ["", "Roles are read from the syntax of each copy: a check made inside a "
                      "callee shows as body,", "so body never proves a check is absent."]
    if args.counts:
        data = {"helpers": len(rows),
                "groups": [{"group": g[1], "helpers": len(groups[g]),
                            "lines": sum(r["lines"] for r in groups[g])} for g in order],
                "look_alikes": {"clusters": len(alike),
                                "lines": sum(a["lines"] for a in alike)}}
    else:
        data = {"helpers": rows, "look_alikes": alike}
    emit(data, "\n".join(lines), args.json)
    return 0


def audit_at(repo, args, defs=None):
    files = docs.tracked_files(repo)
    if defs is None:
        _, defs, _ = docs.load(root=repo, files=files)
    result = lint_mod.audit(repo, files, defs, lint_limits(repo, args), docs.config(repo))
    exclude = docs.config(repo).get("exclude", [])
    result["coverage"] = {}
    named = named_lines(repo, defs)
    for key, strict in (("any", False), ("strict", True)):
        rows = [r for r in lint_mod.coverage(repo, files, defs, exclude, strict, named)
                if r["measured"] and not r["test"]]
        n = sum(r["lines"] for r in rows)
        result["coverage"][key] = 100 * sum(r["covered"] for r in rows) / n if n else 0.0
        if key == "any":
            result["coverage"]["claimed"] = 100 * sum(r["claimed"] for r in rows) / n \
                if n else 0.0
        if key == "strict":
            done = sum(r["covered"] + r["exempt"] for r in rows)
            result["coverage"]["accounted"] = 100 * done / n if n else 0.0
    return result


# Implements [CPO§M50]
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


def score_report(args, defs, repo):
    """The score, by standard and rule, as data, lines, and exit status."""
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
                    "accounted for with exemptions"
                    + (f", {cov['claimed']:.1f}% claimed counting the code the design names"
                       if cov.get("claimed", 0) > cov["any"] else "") + ")")
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
    worse = before and now["score"] > before["score"]
    looser = own and before["score"] < own["score"]
    return data, lines, 1 if worse or looser else 0


def cmd_audit(args, defs, repo):
    """The score, as `cpo audit` gave it before `cpo status` took it over."""
    data, lines, status = score_report(args, defs, repo)
    print("cpo audit with no action now lives in cpo status, which also lists the work in "
          "flight; this form will go away.", file=sys.stderr)
    emit(data, "\n".join(lines), args.json)
    return status


# Implements [CPO§T70]
def cmd_config(args, defs, repo):
    """The settings Concipio uses here, `.cpo`'s and its defaults, each
    default marked, so a person sees what was inferred without a file of
    defaults that would go stale as they improve."""
    cfg = docs.config(repo)
    path = docs.config_path(repo)
    lines = [f"# Settings for {repo.name}, from {path or 'no .cpo: every value is a default'}.",
             "# Lines marked (default) are not in .cpo; add one there to change it.", ""]
    data = {}

    def show(key, value, given):
        data[key] = {"value": value, "default": not given}
        rendered = json.dumps(value, ensure_ascii=False)
        lines.append(f"{key} = {rendered}" + ("" if given else "   # (default)"))
    show("master", cfg.get("master", "README.md"), "master" in cfg)
    table = cfg.get("lint", {})
    for key, default in (("statement_limit", lint_mod.STATEMENT_LIMIT),
                         ("section_limit", lint_mod.SECTION_LIMIT),
                         ("breadth_limit", lint_mod.BREADTH_LIMIT)):
        show(f"lint.{key}", table.get(key, default), key in table)
    show("lint.postponed", table.get("postponed", []), "postponed" in table)
    for key in ("archive", "exclude"):
        show(key, cfg.get(key, []), key in cfg)
    show("retired", cfg.get("retired", {}), "retired" in cfg)
    show("unwritten.incident", cfg.get("unwritten", {}).get("incident", []),
         "incident" in cfg.get("unwritten", {}))
    unreach = cfg.get("unreachable", {})
    show("unreachable.lint", unreach.get("lint", False), "lint" in unreach)
    fields = cfg.get("fields", {})
    for key, default in lint_mod.FIELD_DEFAULTS.items():
        show(f"fields.{key}", fields.get(key, default), key in fields)
    given = cfg.get("source", [])
    if given:
        lines += ["", "# Docs whose numbered headings define sections:"]
    data["sources"] = []
    for raw, src in zip(given, docs.sources(repo)):
        lines.append("[[source]]")
        entry = {}
        # A default pattern is shown by what it matches, not as a regex.
        said = {"heading": "any numbered heading, as `## 5.`, `### 5d.1`, `#### §5a′`",
                "cite": f"`{src['prefix']} §5c`, or the doc's name then a section number"}
        for key in ("doc", "prefix", "heading", "cite"):
            value = src[key].pattern if hasattr(src[key], "pattern") else src[key]
            entry[key] = {"value": value, "default": key not in raw}
            if key in raw or key not in said:
                lines.append(f"{key} = {json.dumps(value, ensure_ascii=False)}"
                             + ("" if key in raw else "   # (default)"))
            else:
                lines.append(f"# {key}: {said[key]}   (default)")
        entry["bare_in_code"] = bool(raw.get("bare_in_code"))
        if raw.get("bare_in_code"):
            lines.append("bare_in_code = true")
        data["sources"].append(entry)
    emit(data, "\n".join(lines), args.json)
    return 0


# Implements [CPO§W37]
def cmd_status(args, defs, repo):
    """Where a person or agent stands: the work in flight first, then the
    score, as `git status` reports a rebase before the tree."""
    from . import worklist
    from .store import Store
    flight, lines = {"audits": [], "review": None}, []
    store = Store(repo)
    me, _ = worklist.agent()
    for path in sorted((store.dir / "audits").glob("*.json")):
        name = path.stem
        r = worklist.status(repo, store, defs, name)
        state = worklist.Audit(store, name).load()
        now = int(time.time())
        mine = sorted(t for t, c in state["claims"].items()
                      if c["holder"] == me and c["until"] > now)
        flight["audits"].append({"name": name, "units": r["units"], "counts": r["counts"],
                                 "verified_lines": r["verified_lines"], "lines": r["lines"],
                                 "yours": mine})
        flight["audits"][-1].update(to_draft=r["drafting"]["units"],
                                    open_leads=r["leads"]["open"], ready=r["ready"])
        counts = ", ".join(f"{n} {k}" for k, n in sorted(r["counts"].items()))
        lines.append(f"  audit {name}: {r['verified_units']} of {r['units']} units verified"
                     + (f" ({counts})" if counts else "")
                     + (f", {r['drafting']['units']} to draft" if r["drafting"]["units"] else "")
                     + (f", {r['leads']['open']} open leads" if r["leads"]["open"] else "")
                     + (f"; you hold {', '.join(mine)}" if mine else ""))
    try:
        with review.Store(repo).lock():
            data, human = review.cmd_status(review.Review(repo), args)
        flight["review"] = data
        lines.append("  " + human.replace("\n", "\n  "))
    except review.ReviewError:
        pass
    data, score, status = score_report(args, defs, repo)
    cited = data["coverage"]["any"]
    claimed = max(cited, data["coverage"].get("claimed", 0))
    if claimed < 100:
        # A low score with little traced reads as done; say what it leaves out.
        score.insert(1, f"  The score counts problems lint can see, not coverage: {cited:.1f}% "
                        "of the code cites a design" + (
                            f", and {claimed:.1f}% is claimed by one, cited or named"
                            if claimed > cited else "") + ".")
    out = (["In progress:"] + lines + [""] if lines else ["Nothing in progress."]) + score
    nxt = None
    if claimed == 0 and not flight["audits"]:
        # Undocumented code matters more than the docs' score [CPO§W45].
        nxt = ("No design claims any of this code. Draft one with an audit: cpo audit next "
               f"{time.strftime('%Y-%m-%d')}. It hands out the code, a file's declarations at a "
               "time, to describe, then the sections to check; `cpo help agent` says how.")
        out = [nxt, ""] + out
    emit({"in_progress": flight, "next": nxt, **data}, "\n".join(out), args.json)
    return status


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
    files_in = under(repo, files, args.paths)
    problems, later = lint_mod.check(repo, files, defs, limits, docs.config(repo))
    problems = [p for p in problems if p.path in files_in]
    base_file = baseline_path(repo)
    if args.write_baseline:
        base_file.write_text("# Problems known when the baseline was written. cpo lint fails\n"
                             "# only on problems that are new, or worse than recorded here.\n\n"
                             + tomli_w.dumps({"measure": lint_mod.measure(), "problem": [
                                 {"rule": p.rule, "path": p.path, "key": p.key, "value": p.value}
                                 for p in problems]}))
        emit({"baseline": str(base_file), "problems": len(problems)},
             f"Recorded {len(problems)} problems in {base_file}.", args.json)
        return 0
    recorded = tomllib.loads(base_file.read_text()) if base_file.exists() else {}
    baseline = recorded.get("problem", [])
    fresh = [p for p in problems if not lint_mod.known(p, baseline)]
    shown = problems if args.all else fresh
    lines = [f"{p.path}:{p.line}: {p.rule}: {p.message}" for p in shown]
    # New problems after Concipio itself changed may come from a new rule
    # or a changed measure rather than from the docs or code [T61].
    then, now = recorded.get("measure"), lint_mod.measure()
    if fresh and baseline and then != now:
        lines.append(f"Concipio has changed since the baseline was written ({then or 'unrecorded'}"
                     f" -> {now}), so some of these {len(fresh)} may come from its rules, not "
                     "from this change. Re-record the baseline in a commit of its own, "
                     "before this change: stash the change, run cpo lint --write-baseline, "
                     "commit the baseline alone, and unstash.")
    if baseline:
        lines.append(f"{len(problems) - len(fresh)} known problems recorded in the baseline"
                     + (", shown" if args.all else ", not shown"))
    if later:
        lines.append(f"{len(later)} orphans postponed in .cpo")
    if not problems:
        cites = any(not docs.is_doc(c.path) for d in defs.values() for c in d.citations)
        lines.insert(0, "Every design fits on a screen, reaches the master, and claims "
                        "no more code than its limit." if cites else
                        "No problems in the docs. Nothing in the code cites the design "
                        "yet, so lint has checked the docs alone.")
    emit({"problems": [asdict(p) for p in shown], "new": len(fresh),
          "measure": {"baseline": then, "now": now}, "known":
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
