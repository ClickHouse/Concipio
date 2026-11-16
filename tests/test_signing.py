import difflib
import subprocess

import pytest

from concipio import doc_model, signing

DESIGN = """# Design

{Owner=Josh}

## 1. The ring

The ring refuses when full.

### 1a. Its size

Sixty-four slots.

## 2. The log

Append-only.
"""


def git(repo, *args):
    subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=T", *args], cwd=repo,
                   check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "DESIGN.md").write_text(DESIGN)
    key = tmp_path / "key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "", "-f", str(key)],
                   check=True)
    public = (tmp_path / "key.pub").read_text().split()
    (repo / ".cpo-signers").write_text(f"Josh {public[0]} {public[1]}\n")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "a")
    return repo, str(key)


def target(repo, kind="doc", title=None):
    doc = doc_model.parse((repo / "DESIGN.md").read_bytes())
    ts = signing.targets("DESIGN.md", doc, sections=True)
    t = next(t for t in ts if t.kind == kind and (title is None or t.title == title))
    return doc, t


def standing(repo, kind="doc", title=None, require=None):
    doc, t = target(repo, kind, title)
    return signing.standing(repo, "DESIGN.md", doc, t, require)


def test_signing_writes_one_line_and_proves_the_text(repo):
    repo, key = repo
    before = (repo / "DESIGN.md").read_text()
    signed = signing.sign(repo, "DESIGN.md", target(repo)[1], "Josh", key,
                          when="2026-11-16T21:03:07Z")
    after = (repo / "DESIGN.md").read_text()
    changed = [l for l in difflib.ndiff(before.splitlines(), after.splitlines())
               if l[:2] in ("- ", "+ ")]
    assert signed == "Josh 2026-11-16T21:03:07Z"
    assert len(changed) == 2 and changed[0] == "- {Owner=Josh}"
    assert changed[1].startswith('+ {Owner=Josh Signed="Josh 2026-11-16T21:03:07Z" Sig="ssh:')
    assert standing(repo) == "proven"


def test_the_covered_text_leaves_out_every_sig_and_nested_signatures(repo):
    repo, key = repo
    signing.sign(repo, "DESIGN.md", target(repo, "section", "1a. Its size")[1], "Josh", key)
    signing.sign(repo, "DESIGN.md", target(repo)[1], "Josh", key)
    doc, t = target(repo)
    text = signing.covered(doc, t).decode()
    assert "Sig=" not in text and text.count("Signed=") == 1, "only the doc's own Signed"
    assert "### 1a. Its size\n\nSixty-four slots." in text, "the emptied line is gone"


def test_signing_a_section_later_keeps_the_parent_signature(repo):
    repo, key = repo
    signing.sign(repo, "DESIGN.md", target(repo)[1], "Josh", key)
    git(repo, "commit", "-qam", "sign the doc")
    signing.sign(repo, "DESIGN.md", target(repo, "section", "1a. Its size")[1], "Josh", key)
    assert standing(repo) == "proven"
    assert standing(repo, "section", "1a. Its size") == "proven"


def test_a_change_after_signing_makes_it_stale_and_a_forged_sig_invalid(repo):
    repo, key = repo
    signing.sign(repo, "DESIGN.md", target(repo)[1], "Josh", key)
    git(repo, "commit", "-qam", "sign")
    path = repo / "DESIGN.md"
    path.write_text(path.read_text().replace("Sixty-four slots.", "Thirty-two slots."))
    assert standing(repo) == "stale"
    path.write_text(path.read_text().replace("Thirty-two slots.", "Sixty-four slots."))
    text = path.read_text()
    sig = text.split('Sig="')[1].split('"')[0]
    path.write_text(text.replace(sig, sig[:-8] + "AAAAAAA="))
    assert standing(repo) == "invalid"


def test_a_signature_an_agent_wrote_without_proof(repo):
    repo, _ = repo
    path = repo / "DESIGN.md"
    path.write_text(path.read_text().replace("{Owner=Josh}",
                                             '{Owner=Josh Signed="Josh 2026-11-16T21:03:07Z"}'))
    assert standing(repo) == "signed", "trusted as written, as Verified is"
    assert standing(repo, require="ssh") == "unproven"
    assert standing(repo, "section", "2. The log") == "unsigned"


def test_signing_refuses_a_file_that_changed_meanwhile(repo, monkeypatch):
    repo, key = repo
    path = repo / "DESIGN.md"
    real = signing.sign_bytes

    def edit_then_sign(data, key):
        path.write_text(path.read_text() + "\nMore.\n")
        return real(data, key)

    monkeypatch.setattr(signing, "sign_bytes", edit_then_sign)
    with pytest.raises(signing.SigningError):
        signing.sign(repo, "DESIGN.md", target(repo)[1], "Josh", key)
    assert "Signed=" not in path.read_text()


def test_lint_reports_stale_invalid_and_unproven_signatures(repo):
    repo, key = repo
    (repo / ".cpo").write_text('[signing]\nrequire = "ssh"\n')
    signing.sign(repo, "DESIGN.md", target(repo, "section", "1. The ring")[1], "Josh", key)
    git(repo, "commit", "-qam", "sign")
    path = repo / "DESIGN.md"
    path.write_text(path.read_text().replace("## 2. The log\n",
                                             '## 2. The log\n\n{Signed="Josh 2026-11-16T21:03:07Z"}\n')
                    .replace("Sixty-four", "Thirty-two"))
    rules = {(p.rule, p.line) for p in signing.lint_problems(repo, ["DESIGN.md"])}
    assert rules == {("stale-signature", 5), ("unproven-signature", 14)}


UNDERLINED = """Design
======

{Owner=Josh}

The ring
--------

Refuses when full.
"""


def test_signing_an_underlined_heading_keeps_it_whole(repo):
    repo, key = repo
    (repo / "DESIGN.md").write_text(UNDERLINED.replace("{Owner=Josh}\n\n", ""))
    signing.sign(repo, "DESIGN.md", target(repo)[1], "Josh", key)
    lines = (repo / "DESIGN.md").read_text().splitlines()
    assert lines[:2] == ["Design", "======"] and lines[2].startswith('{Signed="Josh ')
    assert standing(repo) == "proven"
    doc = target(repo)[0]
    assert [t.title for t in signing.targets("DESIGN.md", doc, sections=True)] == [
        "Design", "The ring"], "both headings survive signing"


def test_a_heading_with_its_own_attributes_signs_and_a_rename_is_stale(repo):
    repo, key = repo
    path = repo / "DESIGN.md"
    path.write_text(path.read_text().replace("## 2. The log\n", "## 2. The log {Owner=Ada}\n"))
    t = target(repo, "section", "2. The log {Owner=Ada}")[1]
    signing.sign(repo, "DESIGN.md", t, "Josh", key)
    assert '## 2. The log {Owner=Ada Signed="Josh ' in path.read_text()
    assert standing(repo, "section", next(
        x.title for x in signing.targets("DESIGN.md", target(repo)[0], sections=True)
        if x.title.startswith("2."))) == "proven"
    git(repo, "commit", "-qam", "sign")
    path.write_text(path.read_text().replace("## 2. The log", "## 2. The journal"))
    renamed = next(x.title for x in signing.targets("DESIGN.md", target(repo)[0], sections=True)
                   if x.title.startswith("2."))
    assert standing(repo, "section", renamed) == "stale"


def test_a_name_with_spaces_verifies(repo, tmp_path):
    repo, key = repo
    signers = repo / ".cpo-signers"
    signers.write_text(signers.read_text().replace("Josh ", "Josh_Ventura ", 1))
    signing.sign(repo, "DESIGN.md", target(repo)[1], "Josh Ventura", key)
    assert standing(repo) == "proven"


def test_a_signature_not_yet_committed_covers_the_text_as_it_stands(repo):
    repo, _ = repo
    path = repo / "DESIGN.md"
    path.write_text(path.read_text().replace("Sixty-four slots.", "Thirty-two slots."))
    signing.sign(repo, "DESIGN.md", target(repo)[1], "Josh")
    assert standing(repo) == "signed", "signed for the edited text, before any commit"
    git(repo, "commit", "-qam", "edit and sign")
    assert standing(repo) == "signed"
    path.write_text(path.read_text().replace("Thirty-two", "Sixteen"))
    assert standing(repo) == "stale"


def test_signing_refuses_a_heading_gone_from_the_file(repo):
    repo, key = repo
    t = target(repo, "section", "2. The log")[1]
    path = repo / "DESIGN.md"
    path.write_text(path.read_text().replace("## 2. The log", "## 2. The journal"))
    with pytest.raises(signing.SigningError):
        signing.sign(repo, "DESIGN.md", t, "Josh", key)
    with pytest.raises(signing.SigningError):
        signing.directive(repo, "DESIGN.md", t, "split it")
    assert "Signed=" not in path.read_text() and "Restructure=" not in path.read_text()


def test_a_doc_with_no_title_offers_its_sections(repo):
    repo, _ = repo
    path = repo / "DESIGN.md"
    path.write_text(path.read_text().replace("# Design\n\n{Owner=Josh}\n\n", ""))
    doc = doc_model.parse(path.read_bytes())
    assert [(t.kind, t.title) for t in signing.targets("DESIGN.md", doc)] == [
        ("section", "1. The ring"), ("section", "2. The log")]
    (repo / "notes.markdown").write_text('# Notes\n\n{Signed="Josh 2026-11-16T21:03:07Z"}\n\nA.\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "notes")
    (repo / "notes.markdown").write_text('# Notes\n\n{Signed="Josh 2026-11-16T21:03:07Z"}\n\nB.\n')
    assert [p.rule for p in signing.lint_problems(repo, ["notes.markdown"])] == ["stale-signature"]


def test_two_sections_headed_alike_are_signed_apart(repo):
    repo, key = repo
    path = repo / "DESIGN.md"
    path.write_text(path.read_text() + "\n## Notes\n\nFirst.\n\n## Notes\n\nSecond.\n")
    doc = doc_model.parse(path.read_bytes())
    second = [t for t in signing.targets("DESIGN.md", doc, sections=True) if t.title == "Notes"][1]
    signing.sign(repo, "DESIGN.md", second, "Josh", key)
    text = path.read_text()
    assert text.count("Signed=") == 1 and text.index("Signed=") > text.rindex("## Notes"), \
        "the second Notes is the one signed"


def test_a_tag_on_the_title_signs_the_doc(tmp_path):
    import argparse
    from concipio import cli, docs
    (tmp_path / "DESIGN.md").write_text("# 1. Design\n\nText.\n\n## 1a. Part\n\nMore.\n")
    (tmp_path / ".cpo").write_text('[[source]]\ndoc = "DESIGN.md"\n'
                                   "heading = '^#+\\s+(?P<id>\\d+[a-z]?)\\.\\s'\n")
    _, defs, _ = docs.load(root=tmp_path, files=["DESIGN.md"])
    tag = next(t for t, d in defs.items() if d.line == 1)
    args = argparse.Namespace(targets=[tag], sections=False)
    assert [t.kind for _, _, t in cli.sign_targets(args, defs, tmp_path)] == ["doc"]


def test_lint_reports_markdown_it_could_not_parse(tmp_path, monkeypatch):
    from concipio import docs, lint
    (tmp_path / "a.md").write_text("# A\n\nText.\n")
    real = docs.model

    def broken(text):
        doc = real(text)
        doc.errors = [(3, 3)]
        return doc

    monkeypatch.setattr(docs, "model", broken)
    assert [(p.rule, p.line) for p in lint.unparsed(tmp_path, ["a.md"])] == [("unparsed-markdown", 3)]


def test_an_uncommitted_signature_edited_since_is_stale(repo):
    repo, key = repo
    signing.sign(repo, "DESIGN.md", target(repo)[1], "Josh", key)
    path = repo / "DESIGN.md"
    path.write_text(path.read_text().replace("Sixty-four", "Thirty-two"))
    assert standing(repo) == "stale"


def test_lint_reads_a_single_quoted_signature(repo):
    repo, _ = repo
    (repo / ".cpo").write_text('[signing]\nrequire = "ssh"\n')
    path = repo / "DESIGN.md"
    path.write_text(path.read_text().replace("{Owner=Josh}", "{Owner=Josh Signed='Josh 2026-11-16T21:03:07Z'}"))
    assert [p.rule for p in signing.lint_problems(repo, ["DESIGN.md"])] == ["unproven-signature"]


def test_an_unproven_signature_goes_stale_on_rename_and_when_single_quoted(repo):
    repo, _ = repo
    path = repo / "DESIGN.md"
    path.write_text(path.read_text().replace("## 2. The log\n", "## 2. The log\n\n{Signed='Josh 2026-11-16T21:03:07Z'}\n"))
    git(repo, "commit", "-qam", "sign by hand")
    assert standing(repo, "section", "2. The log") == "signed"
    path.write_text(path.read_text().replace("Append-only.", "Append-only, mostly."))
    assert standing(repo, "section", "2. The log") == "stale", "found though single-quoted"
    path.write_text(path.read_text().replace("Append-only, mostly.", "Append-only.")
                    .replace("## 2. The log", "## 2. The journal"))
    assert standing(repo, "section", "2. The journal") == "stale", "renamed since it was signed"


def test_a_sig_with_no_signers_file_is_unverifiable_not_forged(repo):
    repo, key = repo
    signing.sign(repo, "DESIGN.md", target(repo)[1], "Josh", key)
    (repo / ".cpo-signers").unlink()
    assert standing(repo) == "unverifiable"
    assert [p.rule for p in signing.lint_problems(repo, ["DESIGN.md"])] == ["unverifiable-signature"]
