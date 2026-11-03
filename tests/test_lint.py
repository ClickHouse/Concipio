from pathlib import Path

from concipio import docs, lint


def check(tmp_path, text, **limits):
    (tmp_path / "design.md").write_text(text)
    defs, _ = docs.find_definitions(Path(tmp_path), ["design.md"])
    return [p.rule for p in lint.lint(Path(tmp_path), ["design.md"], defs, **limits)]


def test_a_long_statement_must_be_split(tmp_path):
    body = "\n".join(f"  line {i}" for i in range(5))
    assert check(tmp_path, f"- **X§1:** start\n{body}\n", statement_limit=3) == [
        "statement-length"]


def test_nested_statements_are_measured_on_their_own(tmp_path):
    text = "- **X§1:** parent\n  - **X§2:** child\n    more\n  - **X§3:** child\n"
    assert check(tmp_path, text, statement_limit=2) == []


def test_sections_are_measured_without_their_subsections(tmp_path):
    text = "# A\n\n**X§1:** one\n\n## B\n\n" + "\n".join(["text"] * 5) + "\n"
    assert check(tmp_path, text, section_limit=4) == ["section-length"]
    assert check(tmp_path, text, section_limit=5) == []


def test_docs_without_statements_are_exempt(tmp_path):
    assert check(tmp_path, "# Notes\n\n" + "words\n" * 100, section_limit=5) == []


def test_numbered_headings_can_be_definitions(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", tmp_path], check=True)
    (tmp_path / ".cpo").write_text(
        "[[source]]\n"
        'doc = "DESIGN.md"\n'
        'prefix = "DESIGN"\n'
        "heading = '^#{2,4}\\s+§?(?P<id>\\d+[a-z]?[′″]*)\\.?\\s'\n"
        "cite = 'DESIGN(?:\\.md)?\\s*§\\s*(?P<id>\\d+[a-z]?[′″]*)'\n")
    (tmp_path / "DESIGN.md").write_text(
        "# Design\n\n## 1. Scope\n\nWhat it covers.\n\n### 1a. Limits *(Josh, 2026-08-04)*\n\n"
        + "detail\n" * 5)
    (tmp_path / "x.c").write_text("/* See DESIGN.md §1a. */\nint x;\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    _, defs, errors = docs.load(root=tmp_path)
    assert errors == []
    assert defs["DESIGN§1a"].parent == "DESIGN§1" and defs["DESIGN§1a"].name == "Limits"
    assert [(c.path, c.line) for c in defs["DESIGN§1a"].citations] == [("x.c", 1)]
    files = docs.tracked_files(tmp_path)
    assert [p.rule for p in lint.lint(Path(tmp_path), files, defs, section_limit=4)] == [
        "section-length"]


def lint_repo(tmp_path, files, cpo=""):
    import subprocess
    subprocess.run(["git", "init", "-q", tmp_path], check=True)
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    if cpo:
        (tmp_path / ".cpo").write_text(cpo)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)


def run_lint(tmp_path, *flags):
    import json, os, subprocess, sys
    out = subprocess.run([sys.executable, "-m", "concipio.cli", "lint", "--json", *flags],
                         cwd=tmp_path, capture_output=True, text=True,
                         env=dict(os.environ, XDG_DATA_HOME=str(tmp_path / "data")))
    return out.returncode, json.loads(out.stdout)


def test_orphans_are_docs_no_link_reaches(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n- **X§1:** A point. See [the notes](docs/).\n",
        "docs/notes.md": "Reached through the directory link.\n",
        "docs/cited.md": "Cites [X§1] in prose, as X§1.\n",
        "old/history.md": "Nothing links here.\n",
        "old/rounds.md": "Nor here.\n",
    }, cpo='[lint]\npostponed = ["old/rounds.md"]\n')
    status, d = run_lint(tmp_path)
    assert [p["path"] for p in d["problems"] if p["rule"] == "orphan"] == ["old/history.md"]
    assert d["postponed_orphans"] == ["old/rounds.md"] and status == 1


def test_the_baseline_fails_only_new_or_worse_problems(tmp_path):
    lint_repo(tmp_path, {"README.md": "# Top\n\n**X§1:** A point.\n\n" + "words\n" * 8},
              cpo="[lint]\nsection_limit = 4\n")
    assert run_lint(tmp_path)[0] == 1
    assert run_lint(tmp_path, "--write-baseline")[0] == 0
    status, d = run_lint(tmp_path)
    assert status == 0 and d["known"] == 1
    (tmp_path / "README.md").write_text("# Top\n\n**X§1:** A point.\n\n" + "words\n" * 12)
    status, d = run_lint(tmp_path)
    assert status == 1 and d["new"] == 1, "a section that grew is worse than recorded"


def test_breadth_counts_the_code_a_point_claims(tmp_path):
    body = "\n".join(f"    x += {i};" for i in range(30))
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n- **X§1:** Growth.\n",
        "grow.c": f"/* Implements [X§1] */\nint grow(int x)\n{{\n{body}\n    return x;\n}}\n",
        "test/grow_test.c": "/* Tests [X§1] */\nint t(void) { return 0; }\n",
    })
    from concipio import docs as d_, lint as l_
    _, defs, _ = d_.load(root=tmp_path)
    b = l_.breadth(tmp_path, defs)["X§1"]
    assert b == {"implementation": 34, "tests": 1, "regions": 2}
    status, d = run_lint(tmp_path, "--breadth-limit", "20")
    assert [p["rule"] for p in d["problems"]] == ["breadth"]
