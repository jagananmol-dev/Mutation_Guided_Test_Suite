import pytest
from tools.ast_parser import analyse_code


def test_ast_parser_finds_function_and_branch_count():
    result = analyse_code("def f(x):\n    if x > 0:\n        return x\n    return -x\n")
    assert result["function_name"] == "f"
    assert result["parameters"] == ["x"]
    assert result["branch_count"] == 1
    assert result["decision_complexity_estimate"] >= 2


def test_ast_parser_requires_name_for_multiple_functions():
    source = "def first(): return 1\ndef second(): return 2\n"
    with pytest.raises(ValueError, match="multiple functions"):
        analyse_code(source)
    assert analyse_code(source, "second")["function_name"] == "second"


def test_ast_parser_does_not_execute_source():
    # Parsing this must not create the marker file.
    source = "import pathlib\npathlib.Path('SHOULD_NOT_EXIST').write_text('x')\ndef f(): return 1\n"
    result = analyse_code(source, "f")
    assert result["function_name"] == "f"
