"""The cpo command."""

import argparse
import json
import re
import sys
import textwrap
from dataclasses import asdict

from . import docs


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


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    fmt = common.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", default=None,
                     help="print JSON (the default when output is not a terminal)")
    fmt.add_argument("--text", dest="json", action="store_false",
                     help="print text (the default on a terminal)")
    parser = argparse.ArgumentParser(prog="cpo")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show", parents=[common],
                          help="show tags with their names, text, and citations")
    show.add_argument("tags", nargs="+", help="tags, IDs, or lists such as '[M3, R4]'")
    lst = sub.add_parser("list", parents=[common],
                         help="list defined tags with their names")
    lst.add_argument("namespaces", nargs="*", help="limit to these namespaces, such as M or R")
    tree = sub.add_parser("tree", parents=[common],
                          help="show how statements refine one another")
    tree.add_argument("tags", nargs="*", help="roots to start from (default: all)")
    args = parser.parse_args(argv)
    if args.json is None:
        args.json = not sys.stdout.isatty()

    _, defs, errors = docs.load()
    for e in errors:
        print(f"cpo: {e}", file=sys.stderr)
    status = {"show": cmd_show, "list": cmd_list, "tree": cmd_tree}[args.command](args, defs)
    return status or (1 if errors else 0)


if __name__ == "__main__":
    sys.exit(main())
