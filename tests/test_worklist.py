import os
import subprocess

from concipio import docs, worklist
from concipio.store import Store


def project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Top\n\nSee [the design](DESIGN.md).\n")
    (repo / "DESIGN.md").write_text(
        "# Design\n\n## 1. The ring\n\nThe ring cannot be exhausted: `ring_take` refuses.\n\n"
        "## 2. The log\n\nThe log is append-only, in `src/log.c`.\n")
    (repo / ".cpo").write_text(
        '[[source]]\ndoc = "DESIGN.md"\nprefix = "D"\n'
        "heading = '^##\\s+(?P<id>\\d+)\\.\\s'\ncite = 'D\\s*§\\s*(?P<id>\\d+)'\n")
    (repo / "src").mkdir()
    (repo / "src/ring.c").write_text("int ring_take(void) {\n  return 0;\n}\n")
    # Exempt, so the audit offers no code to draft before its units [CPO§W40].
    (repo / "src/log.c").write_text("// CPO§exempt: a fixture's plumbing\n"
                                    "int log_append(void) {\n  return 1;\n}\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "a"],
                   cwd=repo, check=True)
    _, defs, _ = docs.load(root=repo)
    return repo, defs, Store(repo)


def test_agents_claim_distinct_units_and_see_the_code_they_name(tmp_path, monkeypatch):
    repo, defs, store = project(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    first = worklist.next_unit(repo, store, defs, "trial")
    assert first["unit"] == "D§1" and first["code"][0]["where"] == "src/ring.c:1-3"
    assert worklist.next_unit(repo, store, defs, "trial")["unit"] == "D§1", "a1 resumes its claim"
    monkeypatch.setenv("CPO_AGENT", "a2")
    second = worklist.next_unit(repo, store, defs, "trial")
    assert second["unit"] == "D§2" and second["code"] == [] and second["pointers"] == [
        "src/log.c"], "a named file is a pointer, not a claim on the whole file"


def test_a_verified_unit_goes_stale_when_the_code_it_names_changes(tmp_path, monkeypatch):
    repo, defs, store = project(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    worklist.next_unit(repo, store, defs, "trial")
    worklist.record(repo, store, defs, "trial", "D§1", "verified")
    st = worklist.status(repo, store, defs, "trial")
    assert st["counts"] == {"verified": 1, "open": 1} and st["verified_lines"] == 3
    (repo / "src/ring.c").write_text("int ring_take(void) {\n  return -1;\n}\n")
    assert worklist.status(repo, store, defs, "trial")["counts"] == {"stale": 1, "open": 1}
    again = worklist.next_unit(repo, store, defs, "trial")
    assert again["unit"] == "D§1" and again["before"]["status"] == "verified"


def test_an_agent_concipio_cannot_identify_is_told_how_to_name_itself(tmp_path, monkeypatch):
    repo, defs, store = project(tmp_path, monkeypatch)
    monkeypatch.delenv("CPO_AGENT", raising=False)
    monkeypatch.setattr(worklist, "agent", lambda: (None, "no harness found"))
    out = worklist.next_unit(repo, store, defs, "trial")
    assert "export CPO_AGENT=" in out["error"]


def test_a_check_made_at_an_earlier_commit_shows_stale_at_once(tmp_path, monkeypatch):
    repo, defs, store = project(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    first = worklist.head(repo)
    (repo / "src/ring.c").write_text("int ring_take(void) {\n  return -1;\n}\n")
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qam", "b"],
                   cwd=repo, check=True)
    out = worklist.record(repo, store, defs, "trial", "D§1", "verified", at=first)
    assert out["sha"] == first
    assert worklist.status(repo, store, defs, "trial")["counts"]["stale"] == 1
    worklist.record(repo, store, defs, "trial", "D§2", "verified", at=first)
    assert worklist.status(repo, store, defs, "trial")["counts"]["verified"] == 1, \
        "a unit unchanged since the earlier commit stays verified"


def test_a_stale_unit_says_what_changed_and_in_which_commits(tmp_path, monkeypatch):
    repo, defs, store = project(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    worklist.record(repo, store, defs, "trial", "D§1", "verified")
    (repo / "src/ring.c").write_text("int ring_take(void) {\n  return -1;\n}\n")
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qam",
                    "Refuse with -1"], cwd=repo, check=True)
    state = worklist.Audit(store, "trial").load()
    out = worklist.why_stale(repo, defs, state, "D§1")
    [change] = out["changes"]
    assert change["what"] == "code" and change["where"] == "src/ring.c:ring_take"
    assert change["commits"][0].endswith("Refuse with -1")
    assert "-  return 0;" in change["diff"] and "+  return -1;" in change["diff"]
    brief = worklist.next_unit(repo, store, defs, "trial")
    assert brief["unit"] == "D§1" and brief["changed"][0]["where"] == "src/ring.c:ring_take"


def test_why_lists_only_commits_to_the_unit_and_collapses_bare_citations(tmp_path, monkeypatch):
    repo, defs, store = project(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    worklist.record(repo, store, defs, "trial", "D§1", "verified")

    def commit(msg):
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", msg],
                       cwd=repo, check=True)
    text = (repo / "DESIGN.md").read_text()
    (repo / "DESIGN.md").write_text(text.replace("append-only", "append-only, never rewritten"))
    commit("Reword the log")
    (repo / "DESIGN.md").write_text((repo / "DESIGN.md").read_text().replace(
        "`ring_take` refuses.", "`ring_take` refuses, and says so."))
    commit("Say how the ring refuses")
    (repo / "mutants.sh").write_text("# mutant 4: breaks D§1\nexit 0\n")
    commit("Add a mutant")
    _, defs, _ = docs.load(root=repo)
    out = worklist.why_stale(repo, defs, worklist.Audit(store, "trial").load(), "D§1")
    by = {c["what"]: c for c in out["changes"]}
    assert [c.split(" ", 1)[1] for c in by["text"]["commits"]] == ["Say how the ring refuses"]
    assert by["citations"]["where"] == "+mutants.sh:1" and "added" not in by


def test_a_large_declaration_is_claimed_only_where_the_unit_points(tmp_path, monkeypatch):
    repo, defs, store = project(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    body = [f"  x{i} = {i};" for i in range(100)]
    body[50] = "  /* D§2: the log entry: appended here */"
    (repo / "src/big.c").write_text("void big(void) {\n" + "\n".join(body) + "\n}\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "big"],
                   cwd=repo, check=True)
    (repo / ".cpo").write_text((repo / ".cpo").read_text() + "bare_in_code = true\n")
    _, defs, _ = docs.load(root=repo)
    worklist.record(repo, store, defs, "trial", "D§2", "verified")
    body[5] = "  x5 = 500;"
    (repo / "src/big.c").write_text("void big(void) {\n" + "\n".join(body) + "\n}\n")
    assert worklist.status(repo, store, defs, "trial")["counts"].get("verified") == 1, \
        "an edit far from the citing comment does not stale the unit"
    body[52] = "  x52 = 520;"
    (repo / "src/big.c").write_text("void big(void) {\n" + "\n".join(body) + "\n}\n")
    assert worklist.status(repo, store, defs, "trial")["counts"].get("stale") == 1
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qam",
                    "Set x52"], cwd=repo, check=True)
    out = worklist.why_stale(repo, defs, worklist.Audit(store, "trial").load(), "D§2")
    [code] = [c for c in out["changes"] if c["what"] == "code"]
    assert [c.split(" ", 1)[1] for c in code["commits"]] == ["Set x52"], \
        "a window whose first line holds a colon still finds its commits"


def test_code_a_unit_stops_naming_is_no_longer_claimed_not_removed(tmp_path, monkeypatch):
    repo, defs, store = project(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    worklist.record(repo, store, defs, "trial", "D§1", "verified")
    (repo / "DESIGN.md").write_text((repo / "DESIGN.md").read_text().replace(
        "`ring_take` refuses.", "taking refuses."))
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qam", "x"],
                   cwd=repo, check=True)
    _, defs, _ = docs.load(root=repo)
    out = worklist.why_stale(repo, defs, worklist.Audit(store, "trial").load(), "D§1")
    assert {c["what"] for c in out["changes"]} == {"text", "no longer claimed"}


def test_a_reworded_sentence_shows_only_its_changed_words():
    out = worklist.prose_diff(
        "The ring is sized per slot. It cannot be exhausted. Takers wait.",
        "The ring is sized per slot. It cannot be exhausted by fills. Takers wait.")
    assert out == "~ It cannot be [-exhausted.-] {+exhausted by fills.+}"


def test_short_unit_names_and_a_findings_note_while_it_is_fixed(tmp_path, monkeypatch):
    repo, defs, store = project(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    assert worklist.unit_name(defs, "D1") == "D§1" and worklist.unit_name(defs, "2") == "D§2"
    brief = worklist.next_unit(repo, store, defs, "trial")
    assert "cpo audit done trial D§1" in brief["next"] and brief["until_utc"].endswith("Z")
    worklist.record(repo, store, defs, "trial", "D§1", "finding", "refuses nothing")
    (repo / "src/ring.c").write_text("int ring_take(void) {\n  return -1;\n}\n")
    [row] = [r for r in worklist.status(repo, store, defs, "trial")["rows"] if r["unit"] == "D§1"]
    assert row["standing"] == "stale" and row["note"] == "was a finding: refuses nothing"


def bare(tmp_path, monkeypatch):
    """A repository with code and no design."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "README.md").write_text("# Top\n")
    (repo / "src/ring.c").write_text(
        "int ring_take(void) {\n  return 0;\n}\n\n"
        "int ring_put(int x) {\n  /* This can never be negative. */\n  return x;\n}\n")
    (repo / "src/glue.c").write_text("int glue(void) {\n  return 2;\n}\n")
    (repo / "tests").mkdir()
    (repo / "tests/test_ring.c").write_text("int test_ring(void) {\n  return 0;\n}\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "a"],
                   cwd=repo, check=True)
    return repo, Store(repo)


def load(repo):
    worklist._decls.clear()
    return docs.load(root=repo)[1]


def test_code_no_design_claims_is_drafted_before_anything_is_checked(tmp_path, monkeypatch):
    repo, store = bare(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    brief = worklist.next_unit(repo, store, load(repo), "boot")
    assert brief["kind"] == "draft" and brief["unit"].startswith("draft:src/")
    assert "declares no design doc yet" in brief["text"], "the first brief says to start one"
    tags = {r["unit"] for r in worklist.status(repo, store, load(repo), "boot")["drafting"]["rows"]}
    assert tags == {"draft:src/glue.c:glue", "draft:src/ring.c:ring_take"}, \
        "a file's declarations make one unit, and tests are not drafted"


def test_drafted_needs_every_declaration_described_or_exempted(tmp_path, monkeypatch):
    repo, store = bare(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    brief = worklist.next_unit(repo, store, load(repo), "boot", scope=["src/ring.c"])
    assert brief["unit"] == "draft:src/ring.c:ring_take"
    (repo / ".cpo").write_text('[[source]]\ndoc = "DESIGN.md"\n')
    (repo / "DESIGN.md").write_text("# Design\n\n## 1. The ring\n\n`ring_take` refuses.\n")
    out = worklist.record(repo, store, load(repo), "boot", brief["unit"], "drafted")
    assert "no section: ring_put (src/ring.c:5)." in out["error"]
    (repo / "DESIGN.md").write_text(
        "# Design\n\n## 1. The ring\n\n`ring_take` refuses; `ring_put` stores.\n")
    out = worklist.record(repo, store, load(repo), "boot", brief["unit"], "drafted")
    assert out["status"] == "drafted" and out["sections"] == ["DESIGN§1"]


def test_the_drafter_does_not_check_its_own_section(tmp_path, monkeypatch):
    repo, store = bare(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    (repo / "src/glue.c").write_text("// CPO§exempt: plumbing\nint glue(void) {\n  return 2;\n}\n")
    brief = worklist.next_unit(repo, store, load(repo), "boot")
    (repo / ".cpo").write_text('[[source]]\ndoc = "DESIGN.md"\n')
    (repo / "DESIGN.md").write_text(
        "# Design\n\n## 1. The ring\n\n`ring_take` refuses; `ring_put` stores.\n")
    worklist.record(repo, store, load(repo), "boot", brief["unit"], "drafted")
    for lead in worklist.status(repo, store, load(repo), "boot")["leads"]["rows"]:
        worklist.record(repo, store, load(repo), "boot", lead["unit"], "verified")
    mine = worklist.next_unit(repo, store, load(repo), "boot")
    assert mine.get("done") and "DESIGN§1" in mine["message"] and "CPO_AGENT" in mine["message"]
    monkeypatch.setenv("CPO_AGENT", "a2")
    theirs = worklist.next_unit(repo, store, load(repo), "boot")
    assert theirs["unit"] == "DESIGN§1" and theirs["drafted"] == "a1"
    worklist.record(repo, store, load(repo), "boot", "DESIGN§1", "verified")
    assert worklist.status(repo, store, load(repo), "boot")["ready"], \
        "drafted whole, checked by a second agent, and no lead open: ready for a person"


def test_leads_start_from_unbacked_claims_and_agents_add_more(tmp_path, monkeypatch):
    repo, store = bare(tmp_path, monkeypatch)
    monkeypatch.setenv("CPO_AGENT", "a1")
    worklist.next_unit(repo, store, load(repo), "boot")
    leads = worklist.status(repo, store, load(repo), "boot")["leads"]
    assert leads["open"] == 1 and leads["rows"][0]["where"] == "src/ring.c:6"
    audit = worklist.Audit(store, "boot")
    state = audit.load()
    tag = worklist.add_lead(state, "ring_put never checks x", "src/ring.c:5", "a1")
    assert worklist.add_lead(state, "ring_put never checks x", "src/ring.c:5") == tag
    audit.save(state)
    out = worklist.record(repo, store, load(repo), "boot", tag, "finding", "x may be negative")
    assert out["status"] == "finding"
    rows = worklist.status(repo, store, load(repo), "boot")["leads"]["rows"]
    assert [r["standing"] for r in rows] == ["open", "finding"]


def test_an_audit_begun_on_a_design_checks_before_it_drafts(tmp_path, monkeypatch):
    repo, defs, store = project(tmp_path, monkeypatch)
    (repo / "src/extra.c").write_text("int extra(void) {\n  return 3;\n}\n")
    monkeypatch.setenv("CPO_AGENT", "a1")
    assert worklist.next_unit(repo, store, load(repo), "trial")["unit"] == "D§1"
    assert worklist.status(repo, store, load(repo), "trial")["drafting"]["units"] == 1
