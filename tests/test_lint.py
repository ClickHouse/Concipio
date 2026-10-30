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
