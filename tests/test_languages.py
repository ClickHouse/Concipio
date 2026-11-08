import pytest

from concipio import spans


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

