import pytest
from archaeologist.ingestion.symbol_parser import FUNCTION_REGEX, extract_modified_line_numbers_from_diff
from archaeologist.ingestion.link_resolver import SHA_REF
from archaeologist.ingestion.revert_detector import _escape_like
from archaeologist.utils.security import SHA_REGEX

def test_sha_ref_ignores_pure_decimal_numbers():
    text = "Fixed in build 20240115, ticket 9876543, commit abc12345"
    matches = SHA_REF.findall(text)
    assert "abc12345" in matches
    assert "20240115" not in matches
    assert "9876543" not in matches

def test_function_regex_requires_explicit_keywords():
    call_line = "    doSomethingRandom(x, y);"
    def_line = "def my_python_func(a, b):"
    js_func = "function myJsFunc(x) {"
    
    assert FUNCTION_REGEX.match(call_line) is None
    assert FUNCTION_REGEX.match(def_line) is not None
    assert FUNCTION_REGEX.match(def_line).group(1) == "my_python_func"
    assert FUNCTION_REGEX.match(js_func) is not None
    assert FUNCTION_REGEX.match(js_func).group(1) == "myJsFunc"

def test_sql_like_wildcard_escaping():
    raw_subject = "Fix 100% CPU_usage & memory"
    escaped = _escape_like(raw_subject)
    assert escaped == "Fix 100\\% CPU\\_usage & memory"

def test_diff_parser_handles_deleted_file():
    diff_text = (
        "--- a/old_file.py\n"
        "+++ b/old_file.py\n"
        "@@ -1,3 +1,3 @@\n"
        "+line 1\n"
        "--- a/deleted.py\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-deleted line 1\n"
        "--- a/new_file.py\n"
        "+++ b/new_file.py\n"
        "@@ -1,2 +1,2 @@\n"
        "+new line\n"
    )
    res = extract_modified_line_numbers_from_diff(diff_text)
    assert "old_file.py" in res
    assert "new_file.py" in res
    assert "/dev/null" not in res
    assert None not in res

def test_sha_regex_misrouting_guard():
    assert not SHA_REGEX.match("issue1234")
    assert SHA_REGEX.match("a1b2c3d")
    assert SHA_REGEX.match("4970a09")
