"""Check that every design fits on a screen."""

import re
from dataclasses import dataclass

from . import docs

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
STATEMENT_LIMIT = 20
SECTION_LIMIT = 60


@dataclass
class Problem:
    path: str
    line: int
    rule: str
    message: str


def sections(text):
    """Yield (line, level, title, own_lines) for each section, where
    own_lines counts the section's text up to the next heading of any
    level, so subsections are measured on their own. Text before the first
    heading is a section of level 0."""
    lines = [line for _, line in docs.prose_lines(text)]
    raw = text.splitlines()
    marks = [(i, len(m[1]), m[2]) for i, line in enumerate(lines)
             if (m := HEADING.match(line))]
    starts = [(-1, 0, "(top)")] + marks
    for k, (i, level, title) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(raw)
        body = raw[i + 1:end]
        while body and not body[-1].strip():
            body.pop()
        while body and not body[0].strip():
            body.pop(0)
        if i >= 0 or body:
            yield i + 1, level, title, len(body)


# Implements [CPO§M41]
def lint(root, files, defs, statement_limit=STATEMENT_LIMIT, section_limit=SECTION_LIMIT):
    problems = []
    for d in defs.values():
        if d.lines > statement_limit:
            problems.append(Problem(
                d.path, d.line, "statement-length",
                f"{d.tag} ({d.name}) is {d.lines} lines; split it into nested "
                f"statements of at most {statement_limit}"))
    designs = {d.path for d in defs.values()}
    for path in files:
        # A doc that defines no statements is not a design: notes, reports,
        # and records of consultations are free to run long.
        if not path.endswith(".md") or path not in designs:
            continue
        text = (root / path).read_text(errors="replace")
        for line, level, title, n in sections(text):
            if n > section_limit:
                problems.append(Problem(
                    path, line, "section-length",
                    f'section "{title}" has {n} lines of its own; split it into '
                    f"subsections or a child doc of at most {section_limit}"))
    return sorted(problems, key=lambda p: (p.path, p.line))
