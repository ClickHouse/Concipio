import pytest

from concipio import docs, spans


@pytest.mark.parametrize("lang", sorted(spans.LANGUAGES))
def test_each_vendored_query_compiles_against_its_installed_grammar(lang):
    assert spans.query(lang) is not None


def names(lang, text):
    return [(kind, name) for _, _, kind, name, _ in spans.declarations(lang, text)]


def test_cpp_classes_with_methods_are_scopes_and_out_of_class_methods_keep_their_owner():
    text = ("class Ring {\n public:\n  int take() { return 0; }\n};\n"
            "int Ring::put(int x) { return x; }\nstruct Plain { int a; };\n")
    assert names("cpp", text) == [("class scope", "Ring"), ("function", "take"),
                                  ("function", "Ring::put"), ("struct", "struct Plain")]


def test_perl_subroutines_and_packages():
    text = "package Ring {\n  sub take { return 0; }\n}\nsub helper { 1 }\n"
    assert names("perl", text) == [("package scope", "Ring"), ("function", "take"),
                                   ("function", "helper")]


def test_c_structs_inside_include_guards_count_and_loop_macros_do_not():
    text = ("#ifndef RING_H\n#define RING_H\nstruct ring { int n; };\n#endif\n"
            "int sum(void) {\n  int s = 0;\n  for_each_cpu(cpu) {\n    s++;\n  }\n"
            "  return s;\n}\n")
    got = names("c", text)
    assert ("struct", "struct ring") in got and ("function", "sum") in got
    assert all(name for _, name in got), "a loop macro is not a nameless function"


def test_mdx_docs_define_statements(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "guide.mdx").write_text("# Guide\n\n- **G§1:** Metrics flush every second.\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    _, defs, _ = docs.load(root=tmp_path)
    assert "G§1" in defs


def test_go_methods_carry_their_receiver_and_types_are_records():
    text = ("package ring\n\ntype Ring struct {\n\tn int\n}\n\n"
            "func (r *Ring) Take() int { return r.n }\n\nfunc New() *Ring { return &Ring{} }\n")
    assert names("go", text) == [("type", "type Ring"), ("method", "Ring.Take"),
                                 ("function", "New")]


def test_rust_impls_are_scopes_named_by_type_and_trait():
    text = ("struct Ring { n: usize }\n\ntrait Take { fn take(&mut self) -> usize; }\n\n"
            "impl Take for Ring {\n    fn take(&mut self) -> usize { self.n }\n}\n\n"
            "impl Ring {\n    fn new() -> Self { Ring { n: 0 } }\n}\n")
    assert names("rust", text) == [("struct", "struct Ring"), ("trait scope", "Take"),
                                   ("impl scope", "Take for Ring"), ("function", "take"),
                                   ("impl scope", "Ring"), ("function", "new")]


def test_a_missing_grammar_disables_only_its_language():
    import subprocess, sys
    code = ("import sys; sys.modules['tree_sitter_go'] = None\n"
            "from concipio import spans\n"
            "print('go' in spans.LANGUAGES, spans.language_of('a.go', ''), "
            "spans.language_of('a.c', ''))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.split() == ["False", "None", "c"]
    assert "tree_sitter_go not installed" in out.stderr
