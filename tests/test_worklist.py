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
    (repo / "src/log.c").write_text("int log_append(void) {\n  return 1;\n}\n")
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
