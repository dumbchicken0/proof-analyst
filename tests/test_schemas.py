from src.schemas import parse_action


def test_parse_run_code():
    a = parse_action('```json\n{"tool": "run_code", "args": {"code": "result = {\'n\': 1}"}}\n```')
    assert a.tool == "run_code"


def test_bad_tool_raises():
    try:
        parse_action('{"tool": "nope", "args": {}}')
    except ValueError:
        return
    raise AssertionError("expected ValueError")
