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
        "# Design\n\n## 1. Scope\n\nWhat it covers; see §1a.\n\n### 1a. Limits *(Josh, 2026-08-04)*\n\n"
        + "detail\n" * 5)
    (tmp_path / "x.c").write_text("/* See DESIGN.md §1a; not §1. */\nint x;\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    _, defs, errors = docs.load(root=tmp_path)
    assert errors == []
    assert defs["DESIGN§1a"].parent == "DESIGN§1" and defs["DESIGN§1a"].name == "Limits"
    assert sorted((c.path, c.line) for c in defs["DESIGN§1a"].citations) == [
        ("DESIGN.md", 5), ("x.c", 1)], "a bare §1a counts inside DESIGN.md only"
    assert defs["DESIGN§1"].citations == [], "x.c's bare §1 is not a citation"
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


def test_path_walks_from_the_master_to_a_tag(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n\nSee [the design](docs/design.md).\n",
        "docs/design.md": "# Design\n\n- **X§1:** Outer.\n  - **X§2:** Inner.\n",
    })
    from concipio import docs as d_, lint as l_
    _, defs, _ = d_.load(root=tmp_path)
    chain, inner = l_.path_to(tmp_path, d_.tracked_files(tmp_path), defs, "X§2")
    assert chain == ["README.md", "docs/design.md"] and inner == ["X§1", "X§2"]
    assert l_.path_to(tmp_path, d_.tracked_files(tmp_path), defs, "nowhere.md") is None


def test_fields_schemas_importance_and_freshness(tmp_path):
    import os, subprocess
    cpo = (
        '[fields]\nknown = ["Owner", "Status"]\n\n'
        '[brief]\nactive = { field = "Status", values = ["active"] }\n\n'
        '[[schema]]\nunder = "X§1"\nrequire = ["Owner"]\n'
        '[schema.fields]\nPriority = { enum = ["high", "low"] }\n')
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n- **X§1:** Roadmap. See [deep](a.md).\n"
                     "  - **X§2:** Grow online. {Owner=Ann Priority=urgent Status=active}\n"
                     "  - **X§3:** Shrink. {owner=Ann}\n",
        "a.md": "Links on to [b](b.md).\n",
        "b.md": "And to [c](c.md).\n",
        "c.md": "- **X§4:** Writes may be reordered. {Importance=critical}\n",
    }, cpo)
    env = dict(os.environ, GIT_AUTHOR_DATE="2026-01-02T00:00:00", GIT_COMMITTER_DATE="2026-01-02T00:00:00")
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "docs"],
                   cwd=tmp_path, check=True, env=env)
    (tmp_path / "a.md").write_text("Links on to [b](b.md).\n\n- **X§5:** Updated claim. {Updated=2025-12-01}\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "more"],
                   cwd=tmp_path, check=True, env=env)
    _, d = run_lint(tmp_path)
    rules = sorted((p["rule"], p["key"]) for p in d["problems"])
    assert ("schema", "X§2:Priority") in rules, "urgent is not in the enum"
    assert ("schema", "X§3:fields") in rules, "Owner is required, owner is a typo"
    assert ("undeclared-field", "X§3:owner") in rules
    assert ("buried", "X§4") in rules, "critical, but three links deep"
    assert ("stale-updated", "X§5") in rules, "changed in 2026, claims 2025-12-01"
    from concipio import cli
    import contextlib, io, json
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["list", "--json", "--where", "Owner=Ann"])
        assert [r["tag"] for r in json.loads(out.getvalue())] == ["X§2"]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["brief", "--json"])
        brief = json.loads(out.getvalue())
        assert [c["tag"] for c in brief["critical"]] == ["X§4"]
        assert [a["tag"] for a in brief["active"]] == ["X§2"]
    finally:
        os.chdir(old)


def test_fields_are_not_read_from_code_or_sets():
    from concipio.docs import attribute_fields, statement_fields
    assert attribute_fields("Record `{seq_mark = tail}` and return.")[0] == {}
    assert attribute_fields("at {N=32, N=1} x {B=1, B=2} under load")[0] == {}
    assert attribute_fields('Ship it. {Owner="Ann, Bo" Due=2026-12-01}')[0] == {
        "Owner": "Ann, Bo", "Due": "2026-12-01"}
    fields, _ = statement_fields(["- **X§1:** A.", "  ```toml", "  {Owner=Nope}", "  ```"])
    assert fields == {}


def test_audit_scores_problems_and_reports_marked_debt(tmp_path):
    import subprocess
    lint_repo(tmp_path, {
        "README.md": "# Top\n\nSee [the design](DESIGN.md) and [old](old.md).\n",
        "DESIGN.md": "# Design\n\n## 1. Scope\n\nAs §1 says, and §9 claims.\n\n"
                     "## 2. Roster\n\n{Stale=\"five reviewers now\"}\n\nEight of them.\n",
        "old.md": "# Old notes\n\n{Stale=\"superseded by the design\"}\n\nText.\n",
        "lost.md": "Nothing links here.\n",
    }, cpo='[[source]]\ndoc = "DESIGN.md"\nprefix = "D"\n'
           "heading = '^##\\s+(?P<id>\\d+)\\.\\s'\ncite = 'D\\s*§\\s*(?P<id>\\d+)'\n")
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "a"],
                   cwd=tmp_path, check=True)
    status, d = run_audit(tmp_path)
    assert d["rules"] == {"dangling-section": 1, "orphan": 1}, "§9 and lost.md"
    assert d["score"] == 2 and status == 0
    assert sorted(m["reason"] for m in d["debt"]["stale"]) == [
        "five reviewers now", "superseded by the design"]
    (tmp_path / "README.md").write_text("# Top\n\nSee [the design](DESIGN.md), [old](old.md), "
                                        "and [lost](lost.md).\n")
    status, d = run_audit(tmp_path, "--against", "HEAD")
    assert d["score"] == 1 and d["against"]["score"] == 2 and status == 0
    (tmp_path / "DESIGN.md").write_text("# Design\n\n## 1. Scope\n\n§7, §8, and §9.\n")
    status, d = run_audit(tmp_path, "--against", "HEAD")
    assert d["score"] > d["against"]["score"] and status == 1, "worse than HEAD fails"


def run_audit(tmp_path, *flags):
    import json, os, subprocess, sys
    out = subprocess.run([sys.executable, "-m", "concipio.cli", "audit", "--json", *flags],
                         cwd=tmp_path, capture_output=True, text=True,
                         env=dict(os.environ, XDG_DATA_HOME=str(tmp_path / "data")))
    return out.returncode, json.loads(out.stdout)


def test_code_names_what_its_bare_section_numbers_mean(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n\nSee [the design](DESIGN.md) and [the spec](SPEC.md).\n",
        "DESIGN.md": "# Design\n\n## 1. One\n\n## 2. Two\n",
        "SPEC.md": "# Spec\n\n## 1. Wire format\n",
        "a.c": "/* Routing, per §2. */\nint a(void) { return 0; }\n",
        "b.c": "/* cpo-default: SPEC */\n/* Encodes §1. */\nint b(void) { return 0; }\n",
    }, cpo=("[[source]]\ndoc = \"DESIGN.md\"\nprefix = \"DESIGN\"\nbare_in_code = true\n"
            "heading = '^##\\s+(?P<id>\\d+)\\.\\s'\ncite = 'DESIGN\\s*§\\s*(?P<id>\\d+)'\n\n"
            "[[source]]\ndoc = \"SPEC.md\"\nprefix = \"SPEC\"\n"
            "heading = '^##\\s+(?P<id>\\d+)\\.\\s'\ncite = 'SPEC\\s*§\\s*(?P<id>\\d+)'\n"))
    _, defs, _ = docs.load(root=tmp_path)
    assert [c.path for c in defs["DESIGN§2"].citations] == ["a.c"], "the project's default"
    assert [c.path for c in defs["SPEC§1"].citations] == ["b.c"], "the file's own default"
    assert defs["DESIGN§1"].citations == [], "b.c's §1 is SPEC's, not DESIGN's"


def test_implements_works_without_brackets_for_numbered_sections(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n\nSee [the design](DESIGN.md).\n",
        "DESIGN.md": "# Design\n\n## 5. Drain\n",
        "a.c": "/* Implements §5 */\nint a(void) { return 0; }\n"
               "/* Implements DESIGN §5 */\nint b(void) { return 0; }\n"
               "/* See §5. */\nint c(void) { return 0; }\n",
    }, cpo=("[[source]]\ndoc = \"DESIGN.md\"\nprefix = \"DESIGN\"\nbare_in_code = true\n"
            "heading = '^##\\s+(?P<id>\\d+)\\.\\s'\ncite = 'DESIGN\\s*§\\s*(?P<id>\\d+)'\n"))
    _, defs, _ = docs.load(root=tmp_path)
    assert sorted((c.line, c.role) for c in defs["DESIGN§5"].citations) == [
        (1, "implementation"), (3, "implementation"), (5, "reference")]


def test_a_known_dangling_reference_survives_edits_that_move_it(tmp_path):
    lint_repo(tmp_path, {"README.md": "# Top\n\nSee [the design](DESIGN.md).\n",
                         "DESIGN.md": "# Design\n\n## 1. One\n\nSee §9.\n"},
              cpo='[[source]]\ndoc = "DESIGN.md"\nprefix = "D"\n'
                  "heading = '^##\\s+(?P<id>\\d+)\\.\\s'\ncite = 'D\\s*§\\s*(?P<id>\\d+)'\n")
    assert run_lint(tmp_path, "--write-baseline")[0] == 0
    (tmp_path / "DESIGN.md").write_text("# Design\n\nNew text.\n\n## 1. One\n\nSee §9.\n")
    assert run_lint(tmp_path)[0] == 0


def test_critical_statements_must_say_when_they_were_verified(tmp_path):
    import subprocess
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n- **X§1:** Never lose data. {Importance=critical}\n"
                     "- **X§2:** Checked. {Importance=critical Verified=2099-01-01}\n"
                     "- **X§3:** Old. {Importance=critical Verified=2000-01-01}\n",
    })
    _, d = run_lint(tmp_path)
    flagged = sorted(p["key"] for p in d["problems"] if p["rule"] == "unverified-critical")
    assert flagged == ["X§1", "X§3"]


def test_headings_that_record_history_are_flagged(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n## The drain\n\n- **X§1:** A point.\n\n"
                     "## The journal *(designed 2026-07-03, unscheduled)*\n\n- **X§2:** Another.\n"
                     "\n## Notes\n",
        "notes.md": "## Dated 2026-01-01, but not a design\n",
    })
    _, d = run_lint(tmp_path)
    assert [p["line"] for p in d["problems"] if p["rule"] == "history-in-heading"] == [7]


def test_a_critical_statement_can_be_known_stale(tmp_path):
    lint_repo(tmp_path, {"README.md": '# Top\n\n- **X§1:** Write order. {Importance=critical Stale="rewrite pending"}\n'})
    _, d = run_lint(tmp_path)
    assert [p["rule"] for p in d["problems"]] == ["stale-critical"]
