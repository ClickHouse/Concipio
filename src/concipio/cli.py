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


def cmd_list(args, defs):
    want = args.namespaces
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
    tree = add("tree", "show how statements refine one another")
    tree.add_argument("tags", nargs="*", help="roots to start from (default: all)")

    ln = add("lint", "check that every design fits on a screen")
    ln.add_argument("paths", nargs="*", help="Markdown files or directories (default: the repository)")
    ln.add_argument("--statement-limit", type=int, default=lint_mod.STATEMENT_LIMIT)
    ln.add_argument("--section-limit", type=int, default=lint_mod.SECTION_LIMIT)

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
    if args.command == "help":
        print(resources.files("concipio").joinpath("prompts/agent.md").read_text())
        return 0
    repo = docs.repo_root()
    key = (args.command, getattr(args, "sub", None))
    if args.command in ("review", "reviewable") or key in REVIEW_COMMANDS:
        with review.Store(repo).lock():
            return run_review_command(repo, key, args)
    _, defs, errors = docs.load()

    for e in errors:
        print(f"cpo: {e}", file=sys.stderr)
    if args.command == "lint":
        status = cmd_lint(args, defs, repo)
    elif args.command == "show":
        status = show_mixed(args, defs, repo)
    else:
        status = {"list": cmd_list, "tree": cmd_tree}[args.command](args, defs)
    return status or (1 if errors else 0)


def run_review_command(repo, key, args):
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


def cmd_lint(args, defs, repo):
    files = docs.tracked_files(repo)
    if args.paths:
        want = [str(Path(p).resolve().relative_to(repo)) for p in args.paths]
        files = [f for f in files if any(f == w or f.startswith(w.rstrip("/") + "/")
                                         for w in want)]
        defs = {t: d for t, d in defs.items() if d.path in files}
    problems = lint_mod.lint(repo, files, defs, args.statement_limit, args.section_limit)
    emit([asdict(p) for p in problems],
         "\n".join(f"{p.path}:{p.line}: {p.rule}: {p.message}" for p in problems)
         or "Every design fits on a screen.", args.json)
    return 1 if problems else 0


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
