import json
import subprocess
import textwrap

import pytest

from concipio import cli, spans


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "T")
    (r / "app.rb").write_text(textwrap.dedent("""\
        class Grower
          def keep
            1
          end

          def doomed
            2
          end
        end
        """))
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "base")
    (r / "app.rb").write_text(textwrap.dedent("""\
        class Grower
          def keep
            10
          end

          # Grows the volume.
          label def grow
            nap 5
          end

          def shrink
            3
          end
        end
        """))
    (r / "app_spec.rb").write_text(textwrap.dedent("""\
        RSpec.describe Grower do
          it "grows" do
            expect(1).to eq 1
          end
        end
        """))
    (r / "design.md").write_text("Volumes grow online.\n")
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "head")
    monkeypatch.chdir(r)
    return r


def run(capsys, *argv):
    """Run cpo with JSON output; --json goes after the leaf command."""
    leaf = 2 if argv[0] in ("review", "statement", "concept") else 1
    status = cli.main([*argv[:leaf], "--json", *argv[leaf:]])
    out = capsys.readouterr().out
    return status, (json.loads(out) if out.strip() else None)


def test_spans_widen_split_and_record_deletions(repo):
    found = spans.find_spans(repo, "HEAD~1", "HEAD")
    by = {(s.path, s.scope): s for s in found}
    keep = by[("app.rb", "Grower#keep")]
    assert (keep.start, keep.end, keep.kind) == (2, 4, "method")
    grow = by[("app.rb", "Grower#grow")]
    assert grow.start == 6, "a comment above a declaration joins it"
    assert by[("app.rb", "Grower#shrink")].kind == "method"
    spec = [s for s in found if s.path == "app_spec.rb"]
    assert [s.scope for s in spec] == ['app_spec.rb > describe Grower > it "grows"']
    assert spec[0].test and spec[0].start == 1, "a describe header joins its example"
    doomed = [s for s in found if s.side == "old"]
    assert [s.scope for s in doomed] == [], "doomed was replaced in place, not deleted"


def test_given_statements_must_quote_the_design_text(repo, capsys):
    run(capsys, "review", "init", "HEAD~1..HEAD", "--design-file", "design.md")
    status, _ = run(capsys, "statement", "add", "--quote", "Volumes shrink.")
    assert status == 1
    status, d = run(capsys, "statement", "add", "--quote", "Volumes   grow online.")
    assert status == 0 and d["provenance"] == "given"


def test_check_fails_only_on_uncovered_spans(repo, capsys):
    run(capsys, "review", "init", "HEAD~1..HEAD", "--design-file", "design.md")
    run(capsys, "statement", "add", "--quote", "Volumes grow online.")
    all_spans = spans.find_spans(repo, "HEAD~1", "HEAD")
    run(capsys, "concept", "add", "--name", "Online growth", "--parent", "D1",
        "--claim", "grow naps until done (S1)")
    run(capsys, "concept", "add", "--name", "Unmentioned", "--claim", "see S2")
    for s in all_spans:
        target = "C1" if s.id == "S1" else "C2"
        run(capsys, "attach", s.id, target)
    status, d = run(capsys, "check")
    assert d["traced"] and d["explained"]
    assert d["undeclared_behavior"] == ["C2"], "reported, not failed"
    assert status == 0


def test_status_reports_flapping_attachments(repo, capsys):
    run(capsys, "review", "init", "HEAD~1..HEAD")
    run(capsys, "concept", "add", "--name", "Anything", "--claim", "S1")
    for _ in range(3):
        run(capsys, "attach", "S1", "C1")
        run(capsys, "detach", "S1", "C1")
    _, d = run(capsys, "status")
    assert d["stall"] and "S1 on C1" in d["stall"]


def test_reviewable_reuses_the_pinned_review(repo, capsys):
    status, d = run(capsys, "reviewable", "HEAD~1..HEAD")
    assert status == 1 and d["created"] and d["next"]["work"] == "span"
    run(capsys, "concept", "add", "--name", "All of it", "--claim", "S1")
    for s in spans.find_spans(repo, "HEAD~1", "HEAD"):
        run(capsys, "attach", s.id, "C1")
    status, d = run(capsys, "reviewable", "HEAD~1..HEAD")
    assert status == 0 and d["reviewable"] and not d["created"]


def test_record_reports_tokens_per_span(repo, capsys):
    run(capsys, "review", "init", "HEAD~1..HEAD")
    run(capsys, "record", "--model", "haiku", "--input-tokens", "900",
        "--output-tokens", "100", "--spans", "4")
    _, d = run(capsys, "status")
    assert d["cost"]["haiku"] == {"tokens": 1000, "input_tokens": 900,
                                  "output_tokens": 100, "spans": 4}


def test_concurrent_attaches_are_not_lost(repo, capsys):
    import concurrent.futures, os, sys
    run(capsys, "review", "init", "HEAD~1..HEAD")
    run(capsys, "concept", "add", "--name", "All of it", "--claim", "S1")
    ids = [s.id for s in spans.find_spans(repo, "HEAD~1", "HEAD")]
    env = dict(os.environ)
    cmd = [sys.executable, "-m", "concipio.cli"]
    with concurrent.futures.ThreadPoolExecutor(len(ids)) as pool:
        list(pool.map(lambda i: subprocess.run(cmd + ["attach", i, "C1", "--json"],
                                               cwd=repo, env=env, check=True,
                                               capture_output=True), ids))
    _, d = run(capsys, "check")
    assert d["traced"], d["uncovered_spans"]


def test_next_marks_the_lines_the_change_touched(repo, capsys):
    run(capsys, "review", "init", "HEAD~1..HEAD")
    _, d = run(capsys, "next", "--path", "app.rb")
    lines = d["code"].splitlines()
    assert d["span"]["scope"] == "Grower#keep"
    assert [l.split()[1] for l in lines if "+" in l.split()[:2]] == ["+"]
    assert any(l.split()[0] == "3" and l.split()[1] == "+" for l in lines), "the 1 -> 10 line"


def test_strict_check_fails_on_undeclared_behavior(repo, capsys):
    run(capsys, "review", "init", "HEAD~1..HEAD")
    run(capsys, "concept", "add", "--name", "No statement", "--claim", "S1")
    for s in spans.find_spans(repo, "HEAD~1", "HEAD"):
        run(capsys, "attach", s.id, "C1")
    assert run(capsys, "check")[0] == 0
    status, d = run(capsys, "check", "--strict")
    assert status == 1 and d["undeclared_behavior"] == ["C1"]


def test_render_writes_a_design_the_lint_can_measure(repo, capsys):
    run(capsys, "review", "init", "HEAD~1..HEAD", "--design-file", "design.md")
    run(capsys, "statement", "add", "--quote", "Volumes grow online.")
    run(capsys, "concept", "add", "--name", "Growth", "--parent", "D1", "--claim", "S1")
    run(capsys, "attach", "S1", "C1")
    _, d = run(capsys, "render", "--section-limit", "3")
    text = open(d["path"]).read()
    assert "**REVIEW§D1:**" in text and "**REVIEW§C1:**" in text
    assert [p["rule"] for p in d["problems"]] == ["section-length"]


def test_a_new_head_carries_the_review(repo, capsys):
    (repo / "pr.md").write_text("Volumes grow online.\n")
    run(capsys, "reviewable", "HEAD~1..HEAD", "--design-file", "pr.md")
    run(capsys, "statement", "add", "--quote", "Volumes grow online.")
    run(capsys, "concept", "add", "--name", "Growth", "--parent", "D1", "--claim", "S1")
    for s in spans.find_spans(repo, "HEAD~1", "HEAD"):
        run(capsys, "attach", s.id, "C1")
    # A new head that changes one method and leaves the rest alone.
    text = (repo / "app.rb").read_text().replace("nap 5", "nap 6")
    (repo / "app.rb").write_text(text)
    git(repo, "commit", "-q", "-am", "amend")
    status, d = run(capsys, "reviewable", "HEAD~2..HEAD", "--design-file", "pr.md")
    c = d["carried"]
    assert c["changed"] == 1 and c["new"] == 0 and len(c["flagged"]) == 1
    assert status == 1 and d["check"]["uncovered_spans"] == c["flagged"]
    _, nxt = run(capsys, "next")
    assert nxt["span"]["carried"] == ["C1 (implementation)"]
    assert sorted(c["flagged"]) == [nxt["span"]["id"]]
    old_ids = {s.id for s in spans.find_spans(repo, "HEAD~2", "HEAD~1")}
    assert nxt["span"]["id"] in old_ids, "a carried span keeps its ID"
    run(capsys, "attach", c["flagged"][0], "C1")
    assert run(capsys, "reviewable", "HEAD~2..HEAD")[0] == 0


def test_statement_structure_and_kinds(repo, capsys):
    (repo / "pr.md").write_text(
        "Grow volumes. Users ran out of disk. Shrinking comes later. Online growth.\n")
    run(capsys, "review", "init", "HEAD~1..HEAD", "--design-file", "pr.md")
    run(capsys, "statement", "add", "--quote", "Grow volumes.")
    run(capsys, "statement", "add", "--quote", "Users ran out of disk.", "--parent", "D1",
        "--kind", "context")
    run(capsys, "statement", "add", "--quote", "Shrinking comes later.", "--parent", "D1",
        "--kind", "planned")
    run(capsys, "statement", "add", "--quote", "Online growth.")
    run(capsys, "statement", "edit", "D4", "--parent", "D1")
    assert run(capsys, "statement", "edit", "D1", "--parent", "D4")[0] == 1, "no cycles"
    run(capsys, "concept", "add", "--name", "Growth", "--parent", "D4", "--claim", "S1")
    ids = [s.id for s in spans.find_spans(repo, "HEAD~1", "HEAD")]
    run(capsys, "attach", ids[0], "C1")
    assert run(capsys, "unjustified", ids[1], "--reason", "x", "--see", "D4")[0] == 1, \
        "a claim is implemented, not cited for context"
    run(capsys, "unjustified", ids[1], "--reason", "for later", "--see", "D3")
    for i in ids[2:]:
        run(capsys, "attach", i, "C1")
    _, d = run(capsys, "check")
    assert d["unimplemented_claims"] == [], "D1 is reached through D4; D2 and D3 need no code"
    assert d["coverage_by_provenance"]["given"] == {"claims": 2, "other": 2, "implemented": 2}
    assert d["explained_by_context"] == {ids[1]: ["D3"]}
    _, r = run(capsys, "render")
    text = open(r["path"]).read()
    cornerstone = text.split("## Cornerstone")[1].split("\n## ")[0]
    assert cornerstone.index("[D2]") < cornerstone.index("[D3]") < cornerstone.index("[D4]")
    assert "Explains unjustified code" in text
