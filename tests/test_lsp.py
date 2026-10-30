import io
import json
import subprocess
import textwrap

import pytest

from concipio.lsp import Server, to_uri


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", tmp_path], check=True)
    (tmp_path / "design.md").write_text(textwrap.dedent("""\
        # Design

        - **X§1:** **Growth.** Volumes grow online.
          - **X§2:** Steps are sized from the fill rate.

        ## Notes

        See [1] and [2, 1].
        """))
    (tmp_path / "grow.rb").write_text("# Implements [X§2]\ndef grow\nend\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return tmp_path


def request(server, method, **params):
    server.out = io.BytesIO()
    server.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    raw = server.out.getvalue().decode()
    return json.loads(raw.split("\r\n\r\n", 1)[1])["result"]


def at(path, line, char):
    return {"textDocument": {"uri": to_uri(path)},
            "position": {"line": line, "character": char}}


def test_definition_from_a_code_comment_and_a_short_form(repo):
    s = Server()
    loc = request(s, "textDocument/definition", **at(repo / "grow.rb", 0, 16))
    assert loc["uri"].endswith("design.md") and loc["range"]["start"]["line"] == 3
    loc = request(s, "textDocument/definition", **at(repo / "design.md", 7, 5))
    assert loc["range"]["start"]["line"] == 2, "[1] is X§1"


def test_references_include_code_and_docs(repo):
    s = Server()
    refs = request(s, "textDocument/references", **at(repo / "design.md", 3, 8),
                   context={"includeDeclaration": False})
    assert sorted((r["uri"].rsplit("/", 1)[1], r["range"]["start"]["line"]) for r in refs) == [
        ("design.md", 7), ("grow.rb", 0)]


def test_hover_names_the_statement_and_its_family(repo):
    s = Server()
    hover = request(s, "textDocument/hover", **at(repo / "grow.rb", 0, 16))["contents"]["value"]
    assert "X§2" in hover and "Refines X§1 (Growth)" in hover


def test_outline_nests_statements_under_headings_and_parents(repo):
    s = Server()
    syms = request(s, "textDocument/documentSymbol",
                   textDocument={"uri": to_uri(repo / "design.md")})
    top = syms[0]
    assert top["name"] == "Design"
    growth = top["children"][0]
    assert growth["name"] == "1 Growth"
    assert [c["name"] for c in growth["children"]] == ["2 Steps are sized from the fill rate."]
    assert [c["name"] for c in top["children"]][-1] == "Notes"


def test_unknown_requests_get_an_error_not_silence(repo):
    s = Server()
    s.out = io.BytesIO()
    s.handle({"jsonrpc": "2.0", "id": 7, "method": "textDocument/rename", "params": {}})
    assert b'"code": -32601' in s.out.getvalue()


def test_ranged_changes_apply_to_the_buffer(repo):
    s = Server()
    uri = to_uri(repo / "grow.rb")
    s.handle({"jsonrpc": "2.0", "method": "textDocument/didOpen",
              "params": {"textDocument": {"uri": uri, "text": "# Implements [X§2]\n"}}})
    s.handle({"jsonrpc": "2.0", "method": "textDocument/didChange", "params": {
        "textDocument": {"uri": uri},
        "contentChanges": [{"range": {"start": {"line": 0, "character": 0},
                                      "end": {"line": 0, "character": 2}}, "text": "#  "}]}})
    assert s.buffers[uri] == "#  Implements [X§2]\n"
