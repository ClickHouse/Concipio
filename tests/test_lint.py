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


def test_adopting_a_check_is_not_a_regression_but_loosening_one_is(tmp_path):
    import subprocess
    lint_repo(tmp_path, {"README.md": "# Top\n\nThe legacy_gate and the legacy_gate.\n"})
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "a"],
                   cwd=tmp_path, check=True)
    (tmp_path / ".cpo").write_text('[retired]\nlegacy_gate = "gone"\n')
    status, d = run_audit(tmp_path, "--against", "HEAD")
    assert (d["score"], d["against"]["score"], d["against"]["own_config_score"], status) == \
        (1, 1, 0, 0), "the old docs are scored under the new check too"
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "b"],
                   cwd=tmp_path, check=True)
    (tmp_path / ".cpo").write_text("")
    status, d = run_audit(tmp_path, "--against", "HEAD")
    assert (d["score"], status) == (0, 1), "dropping the check fails"


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


def test_a_section_number_wrapped_away_from_its_doc_name_is_not_dangling(tmp_path):
    lint_repo(tmp_path, {"README.md": "# Top\n\nSee [the design](DESIGN.md).\n",
                         "DESIGN.md": "# Design\n\n## 1. One\n\nAs [NOTES\n"
                                      "§9](NOTES.md) says, and as\n§8 does not.\n"},
              cpo='[[source]]\ndoc = "DESIGN.md"\nprefix = "D"\n'
                  "heading = '^##\\s+(?P<id>\\d+)\\.\\s'\ncite = 'D\\s*§\\s*(?P<id>\\d+)'\n")
    _, d = run_lint(tmp_path)
    assert [p["key"] for p in d["problems"] if p["rule"] == "dangling-section"] == ["§8"]


def test_exempt_code_is_accounted_for_apart_from_cited_code(tmp_path):
    from concipio import docs, lint
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n- **X§1:** Sum.\n",
        "a.py": "# Implements [X§1]\ndef add(a, b):\n    return a + b\n\n\n"
                "# CPO§exempt: argument plumbing\ndef parse(argv):\n    return argv[1:]\n\n\n"
                "def odd():\n    return 1\n",
    })
    _, defs, _ = docs.load(root=tmp_path, files=docs.tracked_files(tmp_path))
    [row] = [r for r in lint.coverage(tmp_path, ["a.py"], defs, strict=True)]
    assert (row["covered"], row["exempt"]) == (2, 2)
    assert row["exemptions"] == [{"line": 6, "reason": "argument plumbing"}]


def test_hidden_headings_retired_terms_and_archives(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n- **X§1:** The `legacy_gate` holds. See [old](old/a.md).\n\n"
                     "> ### 1.1 Hidden\n\nText.\n",
        "a.c": "// legacy_gate is gone\nint legacy_gate_count;\n",
        "old/a.md": "# Old\n\n- **X§1:** The legacy_gate, verbatim. See [lost](../lost.md).\n",
        "lost.md": "# Lost\n",
    }, cpo='archive = ["old/*"]\n[retired]\nlegacy_gate = "the gate was removed"\n')
    _, d = run_lint(tmp_path)
    got = sorted((p["rule"], p["path"], p["key"]) for p in d["problems"])
    assert got == [("heading-in-blockquote", "README.md", "1.1 Hidden"),
                   ("orphan", "lost.md", "lost.md"),
                   ("retired-term", "README.md", "legacy_gate"),
                   ("retired-term", "a.c", "legacy_gate")], "the archive defines and reaches nothing"


def test_a_retired_term_still_live_in_code_is_reported(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n",
        "a.c": '#define QUEUE_MAX 8\n/* QUEUE_MAX */\nconst char *s = "legacy_gate";\n',
    }, cpo='[retired]\nQUEUE_MAX = "unbounded now"\nlegacy_gate = "removed"\n')
    _, d = run_lint(tmp_path)
    live = [(p["key"], p["line"]) for p in d["problems"] if p["rule"] == "retired-term-live"]
    assert live == [("QUEUE_MAX", 1)], "comments and strings are not live"


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


def test_helpers_are_sorted_by_the_design_their_callers_serve(tmp_path):
    from concipio import docs, helpers
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n- **X§1:** Do it.\n",
        "a.c": "static int twice(int x) {\n  return x + x;\n}\n\n"
               "static int again(int x) {\n  return x + x;\n}\n\n"
               "// Implements [X§1]\nint run(void) {\n  return twice(1);\n}\n\n"
               "static int probe(void) {\n  return 0;\n}\n\n"
               "static int on_load(void) {\n  return 1;\n}\n\n"
               "static int unused(void) {\n  return 2;\n}\n\n"
               "struct ops { int (*load)(void); } ops = { .load = on_load };\n",
        "test/test_a.c": "int check(void) {\n  return probe();\n}\n",
    })
    files = docs.tracked_files(tmp_path)
    _, defs, _ = docs.load(root=tmp_path, files=files)
    rows, alike = helpers.taxonomy(tmp_path, files, defs)
    got = {r["name"]: (r["serves"], r["callers"], r["tested"], r["outer"]) for r in rows}
    assert got == {"twice": (["X§1"], 1, False, False), "again": ([], 0, False, False),
                   "probe": ([], 0, True, False), "on_load": ([], 0, False, True),
                   "unused": ([], 0, False, False)}
    assert [a["helpers"] for a in alike if "the same body" in a["why"]] == [
        ["a.c:1 twice", "a.c:5 again"]]


def test_look_alikes_list_what_their_copies_do_not_share(tmp_path):
    from concipio import docs, helpers
    body = "  lock(n);\n  unlink(n);\n  push_free(n);\n  unlock(n);\n"
    lint_repo(tmp_path, {
        "README.md": "# Top\n",
        "a.c": "#define ASSERT(x) do { } while (0)\n\n"
               "void release_buffer(struct node *n) {\n  ASSERT(n->parent);\n" + body + "}\n\n"
               "void release_page(struct node *n) {\n" + body + "  n->coverage = 0;\n}\n",
    })
    files = docs.tracked_files(tmp_path)
    _, defs, _ = docs.load(root=tmp_path, files=files)
    rows, alike = helpers.taxonomy(tmp_path, files, defs)
    assert "ASSERT" not in {r["name"] for r in rows}, "macros are not listed as helpers"
    [cluster] = alike
    assert cluster["differ"] == [
        {"where": "only in release_buffer", "role": "guard", "names": ["->parent", "ASSERT"]},
        {"where": "only in release_page", "role": "body", "names": ["->coverage"]}]


def test_differences_explained_by_an_output_or_a_parameter_rank_below_guards(tmp_path):
    from concipio import docs, helpers
    body = "".join(f"  step{i}(n);\n" for i in range(8))
    lint_repo(tmp_path, {
        "README.md": "# Top\n",
        "a.c": "void claim(struct node *n) {\n" + body + "}\n\n"
               "void claim_member(struct node *n, struct node **parent) {\n" + body +
               "  if (parent) *parent = n->parent;\n}\n\n"
               "void claim_ends(struct node *n, struct ends *e) {\n" + body +
               "  ASSERT(ends_ok(e));\n}\n\n"
               "void claim_checked(struct node *n) {\n  if (!mine(n)) return;\n" + body + "}\n",
    })
    files = docs.tracked_files(tmp_path)
    _, defs, _ = docs.load(root=tmp_path, files=files)
    _, [cluster] = helpers.taxonomy(tmp_path, files, defs)
    assert [(d["role"], d["names"]) for d in cluster["differ"]] == [
        ("guard", ["mine"]), ("guard (signature)", ["ASSERT", "ends_ok"]),
        ("output", ["->parent"])]


def test_a_call_inside_an_unparsed_iterator_macro_still_counts():
    from concipio import spans
    calls = []
    spans.identifiers("c", "static int total(struct s *s)\n{\n\tint n = 0, cpu;\n"
                      "\tfor_each_possible_cpu(cpu)\n\t\tn += READ_ONCE(s->v);\n"
                      "\treturn n;\n}\n", [], calls)
    assert {"for_each_possible_cpu", "READ_ONCE"} <= {n for _, n in calls}


def test_guards_whose_comments_name_an_incident_are_unwritten_rules(tmp_path):
    from concipio import docs, helpers
    guard = ("  /* Re-check the owner under the head lock: skipping it lost\n"
             "   * a write (tk-12, 2026-08-03). */\n  if (!ours(n))\n    return;\n")
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n- **X§1:** Owners are re-checked.\n",
        "a.c": "void loose(struct n *n) {\n" + guard + "  go(n);\n}\n\n"
               "// Implements [X§1]\nvoid cited(struct n *n) {\n" + guard + "  go(n);\n}\n\n"
               "void plain(struct n *n) {\n  /* nothing to do */\n  if (!n)\n    return;\n}\n",
    }, cpo='[unwritten]\nincident = ["tk-\\\\d+"]\n')
    files = docs.tracked_files(tmp_path)
    _, defs, _ = docs.load(root=tmp_path, files=files)
    rows = helpers.unwritten_rules(tmp_path, files, defs, incident=[r"tk-\d+"])
    assert [(r["function"], r["line"], r["markers"]) for r in rows] == [
        ("loose", 4, ["2026-08-03", "tk-12"])]


def test_a_guard_may_take_its_reason_from_its_predicates_header(tmp_path):
    from concipio import docs, helpers
    lint_repo(tmp_path, {
        "README.md": "# Top\n",
        "a.c": "/* Whether the page is still this head's: a claim under the\n"
               " * wrong head lost a write (2026-10-21). */\n"
               "static int ours(struct n *n) {\n  return n->head == 0;\n}\n\n"
               "void claim(struct n *n) {\n  if (!ours(n))\n    return;\n  go(n);\n}\n\n"
               "void claim_member(struct n *n) {\n  if (!ours(n))\n    return;\n  go(n);\n}\n",
    })
    files = docs.tracked_files(tmp_path)
    _, defs, _ = docs.load(root=tmp_path, files=files)
    [row] = helpers.unwritten_rules(tmp_path, files, defs)
    assert (row["function"], row["evidence"], row["also"]) == (
        "claim", "a.c:3 ours", ["a.c:14 claim_member"])


def test_a_citation_atop_a_long_header_comment_covers_the_function(tmp_path):
    from concipio import docs, lint
    header = "/* Implements [X§1]\n" + "".join(" * why, at length.\n" for _ in range(10)) + " */\n"
    lint_repo(tmp_path, {"README.md": "# Top\n\n- **X§1:** Own.\n",
                         "a.c": header + "int ours(void) {\n  return 1;\n}\n"})
    files = docs.tracked_files(tmp_path)
    _, defs, _ = docs.load(root=tmp_path, files=files)
    [row] = lint.coverage(tmp_path, ["a.c"], defs, strict=True)
    assert row["covered"] == 3


def test_a_numbered_heading_its_pattern_misses_is_reported(tmp_path):
    lint_repo(tmp_path, {"README.md": "# Top\n\nSee [the design](DESIGN.md).\n",
                         "DESIGN.md": "# Design\n\n## 5. Five\n\nText.\n\n"
                                      "### 5d.1 Hidden\n\nMore.\n"},
              cpo='[[source]]\ndoc = "DESIGN.md"\nprefix = "D"\n'
                  "heading = '^#+\\s+(?P<id>\\d+)\\.\\s'\ncite = 'D\\s*§\\s*(?P<id>\\d+)'\n")
    _, d = run_lint(tmp_path)
    assert [(p["rule"], p["key"]) for p in d["problems"]] == [("unread-heading", "5d.1")]


def test_lint_says_when_concipio_changed_since_the_baseline(tmp_path):
    lint_repo(tmp_path, {"README.md": "# Top\n", "lost.md": "# Lost\n"})
    assert run_lint(tmp_path, "--write-baseline")[0] == 0
    base = tmp_path / ".cpo-baseline.toml"
    base.write_text(base.read_text().replace("measure = ", 'measure = "old" #'))
    (tmp_path / "also.md").write_text("# Also lost\n")
    status, d = run_lint(tmp_path)
    assert status == 1 and d["measure"]["baseline"] == "old"


def test_a_section_number_after_another_docs_name_is_that_docs(tmp_path):
    from concipio import docs
    lint_repo(tmp_path, {
        "README.md": "# Top\n\nSee [the design](DESIGN.md) and [notes](notes.md).\n",
        "DESIGN.md": "# Design\n\n## 10. Sparse map\n\nText.\n",
        "notes.md": "# Notes\n\n## 10. Temp partition\n\nText.\n",
        "a.c": "/* notes.md §10: the temp partition */\nint a;\n"
               "/* As notes §10 says */\nint b;\n"
               "/* Per the restructure, docs/notes.md\n * §10 */\nint c;\n"
               "/* SEE §10 */\nint d;\n/* §10: the sparse map */\nint e;\n"
               "int f; /* a closed comment */\n/* §10 again */\nint g;\n",
    }, cpo='[[source]]\ndoc = "DESIGN.md"\nprefix = "DESIGN"\nbare_in_code = true\n'
           "heading = '^##\\s+(?P<id>\\d+)\\.\\s'\n"
           "cite = 'DESIGN\\s*§\\s*(?P<id>\\d+)'\n")
    files = docs.tracked_files(tmp_path)
    _, defs, _ = docs.load(root=tmp_path, files=files)
    assert [c.line for c in defs["DESIGN§10"].citations if c.path == "a.c"] == [8, 10, 13]


def test_a_tracked_file_deleted_from_disk_is_not_read(tmp_path):
    import subprocess
    lint_repo(tmp_path, {"README.md": "# Top\n", "notes.md": "# Notes\n"})
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    (tmp_path / "notes.md").unlink()
    status, d = run_lint(tmp_path)
    assert status == 0 and d["new"] == 0


def test_claims_of_impossibility_need_evidence(tmp_path):
    from concipio import claims, docs
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n- **X§1:** The ring is sized to its slots.\n",
        "a.c": "/* The ring is sized per slot, so it cannot be exhausted. */\n"
               "int take(void) {\n  return 0;\n}\n\n"
               "/* Unreachable: driven by test/ring_full.c. */\nint put(void) {\n  return 1;\n}\n\n"
               "// Implements [X§1]: impossible by construction.\nint size(void) {\n  return 2;\n}\n\n"
               "int pick(int k) {\n  switch (k) {\n  case 0: return 1;\n"
               "  default: ASSERT(0);\n  }\n  return 0;\n}\n",
        "test/t.c": "// Tests [X§1]\nint t(void) { return 0; }\n",
    }, cpo="[unreachable]\nlint = true\n")
    files = docs.tracked_files(tmp_path)
    _, defs, _ = docs.load(root=tmp_path, files=files)
    rows = claims.impossibility_claims(tmp_path, files, defs)
    got = [(r["function"], r["claim"], r["evidence"]) for r in rows if r["path"] == "a.c"]
    assert got == [("take", "cannot be exhausted", None),
                   ("put", "Unreachable", "names test/ring_full.c"),
                   ("size", "impossible", "cites X§1, which tests cite"),
                   ("pick", "ASSERT(0)", None)], "one sentence is one claim"
    _, d = run_lint(tmp_path)
    assert sorted(p["key"] for p in d["problems"] if p["rule"] == "unbacked-claim") == [
        "pick: assert(0)", "take: cannot be exhausted"]


def test_a_source_needs_only_its_doc(tmp_path):
    from concipio import docs
    lint_repo(tmp_path, {
        "README.md": "# Top\n\nSee [the design](DESIGN.md).\n",
        "DESIGN.md": "# Design\n\n## 5. Drain\n\n### 5a′.1 Pressure\n\nText.\n",
        "a.c": "/* As DESIGN §5a′.1 says, and DESIGN.md §5 too. */\nint a;\n",
    }, cpo='[[source]]\ndoc = "DESIGN.md"\n')
    _, defs, _ = docs.load(root=tmp_path)
    assert {"DESIGN§5", "DESIGN§5a′.1"} <= set(defs)
    assert [c.path for c in defs["DESIGN§5a′.1"].citations] == ["a.c"]
    assert [c.path for c in defs["DESIGN§5"].citations] == ["a.c"], "the doc's name cites it too"


def test_config_shows_each_default_as_one(tmp_path):
    import json, os, subprocess, sys
    lint_repo(tmp_path, {"README.md": "# Top\n"}, cpo='[lint]\nsection_limit = 80\n')
    out = subprocess.run([sys.executable, "-m", "concipio.cli", "config", "--json"],
                         cwd=tmp_path, capture_output=True, text=True,
                         env=dict(os.environ, XDG_DATA_HOME=str(tmp_path / "data")))
    d = json.loads(out.stdout)
    assert d["lint.section_limit"] == {"value": 80, "default": False}
    assert d["lint.statement_limit"] == {"value": 20, "default": True}


def test_broken_links_agent_files_and_site_pages(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n\nSee [the guide](docs/guide.md) and [setup](INSTALL.md).\n",
        "CLAUDE.md": "# For agents\n",
        ".claude/skills/x/SKILL.md": "# A skill\n",
        "docs/docs.json": '{"navigation": {"pages": ["get-started/intro"]}}',
        "docs/get-started/intro.mdx": "# Intro\n",
        "INSTALL.md": "# Install\n",
    })
    _, d = run_lint(tmp_path)
    got = sorted((p["rule"], p["path"]) for p in d["problems"])
    assert got == [("broken-link", "README.md")], \
        "agent files are not docs, and a site's pages are reached through its navigation"


def test_sections_nest_by_their_numbers_and_links_name_real_headings(tmp_path):
    from concipio import docs
    lint_repo(tmp_path, {
        "README.md": "# Top\n\nSee [the design](DESIGN.md#1-the-queue), "
                     "[nothing](DESIGN.md#gone), and [here](#top).\n",
        "DESIGN.md": "# Design\n\n## 1. The queue\n\nText.\n\n## 1a. Layout\n\nMore.\n",
    }, cpo='[[source]]\ndoc = "DESIGN.md"\n')
    _, defs, _ = docs.load(root=tmp_path)
    assert defs["DESIGN§1a"].parent == "DESIGN§1"
    _, d = run_lint(tmp_path)
    assert [p["key"] for p in d["problems"] if p["rule"] == "broken-link"] == ["DESIGN.md#gone"]


def test_a_citation_of_a_tag_no_doc_defines_is_dangling(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n\n- **X§1:** One.\n- **X§2:** Two, after [X§1] and [X§9].\n\n"
                     "See [the design](DESIGN.md).\n",
        "DESIGN.md": "# Design\n\n## 1. Scope\n\nText.\n",
        "a.c": "/* Implements X§7, and DESIGN §4, but not TPC-C 5.11 §3.3.2, nor OTHER§3,\n"
               " * nor VENDOR§T3@v1.2. */\nint a;\n",
    }, cpo='[[source]]\ndoc = "DESIGN.md"\nbare_in_code = true\n')
    _, d = run_lint(tmp_path)
    got = sorted((p["path"], p["key"]) for p in d["problems"] if p["rule"] == "dangling-tag")
    assert got == [("README.md", "X§9"), ("a.c", "DESIGN§4"), ("a.c", "X§7")]


def test_ranges_other_docs_sections_and_list_items_are_not_dangling(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n\nSee [the design](DESIGN.md) and [notes](notes.md).\n",
        "DESIGN.md": "# Design\n\n## 1. Scope\n\nA queue of [1, 64] slots.\n\n## 15. Lessons\n\n"
                     "1. One.\n",
        "notes.md": "# Notes\n\n## 8b. Bands\n\nText.\n",
        "a.c": "/* docs §8b; notes.md §6, §11c; DESIGN §15.10; §9z */\nint a;\n",
    }, cpo='[[source]]\ndoc = "DESIGN.md"\nbare_in_code = true\n')
    _, d = run_lint(tmp_path)
    got = {p["key"]: p["message"] for p in d["problems"] if p["rule"] == "dangling-tag"}
    assert sorted(got) == ["DESIGN§15.10", "DESIGN§9z"], \
        "a range, another doc's section, and numbers after a named doc are not dangling"
    assert "DESIGN§15 exists" in got["DESIGN§15.10"]


def test_every_line_citing_a_dangling_tag_is_named(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# Top\n\nSee [the design](DESIGN.md).\n",
        "DESIGN.md": "# Design\n\n## 5. Drain\n\nText.\n",
        "a.c": "/* the §5d′ marker */\nint a;\n/* Angels-first, §5d′, rebuilt */\nint b;\n"
               "/* §5d′. */\nint c;\n",
    }, cpo='[[source]]\ndoc = "DESIGN.md"\nbare_in_code = true\n')
    _, d = run_lint(tmp_path)
    [p] = [p for p in d["problems"] if p["rule"] == "dangling-tag"]
    assert (p["line"], p["value"]) == (1, 3) and "Also at lines 3, 5." in p["message"]


def test_a_full_tag_with_a_section_suffix_resolves(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# R\n\n[d](DESIGN.md)\n",
        "DESIGN.md": "# D\n\n## 5c. Part\n\nText.\n",
        "a.c": "/* Implements DESIGN§5c, and DESIGN§5d. */\nint a;\n",
    }, cpo='[[source]]\ndoc = "DESIGN.md"\n')
    _, d = run_lint(tmp_path)
    got = sorted(p["key"] for p in d["problems"] if p["rule"] == "dangling-tag")
    assert got == ["DESIGN§5d"], "5c resolves, and 5d is reported whole"


def test_a_bare_number_after_a_source_citation_is_that_sources(tmp_path):
    lint_repo(tmp_path, {
        "README.md": "# R\n\n[d](DESIGN.md) [c](CAVEATS.md)\n",
        "DESIGN.md": "# D\n\n## 1. One\n\nText.\n",
        "CAVEATS.md": "# C\n\n## 2. Two\n\nText.\n\n## 3. Three\n\nText.\n",
        "a.c": "/* See DESIGN §1 and CAVEATS §2, §3. */\nint a;\n",
    }, cpo='[[source]]\ndoc = "DESIGN.md"\nbare_in_code = true\n\n[[source]]\ndoc = "CAVEATS.md"\n')
    _, d = run_lint(tmp_path)
    assert [p for p in d["problems"] if p["rule"] in ("dangling-tag", "dangling-section")] == [], \
        "§3 is CAVEATS', not DESIGN's"
