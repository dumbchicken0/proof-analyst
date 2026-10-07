from src import agent


def test_agent_finishes_with_scripted_llm(monkeypatch, tmp_path):
    responses = iter(
        [
            '{"thought":"inspect","tool":"inspect_schema","args":{}}',
            '{"thought":"compute","tool":"run_code","args":{"code":"result = {\\"n\\": 3}"}}',
            (
                '{"thought":"done","tool":"finish","args":{'
                '"verdict":"ANSWERED",'
                '"answer_text":"There are 3 rows.",'
                '"values":[{"label":"n","value":3}],'
                '"assumptions":[],"interpretations":[],"refusal":null'
                '}}'
            ),
        ]
    )

    def fake_chat(messages, json_mode=True):
        return next(responses)

    monkeypatch.setattr(agent, "chat", fake_chat)

    class FakeRun:
        ok = True
        result = {"n": 3}
        stdout = ""
        error = None

    monkeypatch.setattr(agent, "run_code", lambda data_dir, code: FakeRun())

    monkeypatch.setattr(
        agent,
        "finalize",
        lambda question, finish, last_code, data_dir, trace: finish,
    )

    result = agent.run_agent("How many rows?", str(tmp_path))

    assert result.verdict == "ANSWERED"
    assert result.values[0].value == 3


def test_answered_finish_requires_run_code(monkeypatch, tmp_path):
    responses = iter(
        [
            (
                '{"thought":"done","tool":"finish","args":{'
                '"verdict":"ANSWERED",'
                '"answer_text":"There are 3 rows.",'
                '"values":[{"label":"n","value":3}],'
                '"assumptions":[],"interpretations":[],"refusal":null'
                '}}'
            ),
            (
                '{"thought":"done","tool":"finish","args":{'
                '"verdict":"REFUSED",'
                '"answer_text":"Cannot answer yet.",'
                '"values":[],"assumptions":[],"interpretations":[],"refusal":'
                '{"reason":"missing computation"}'
                '}}'
            ),
        ]
    )

    monkeypatch.setattr(
        agent,
        "chat",
        lambda messages, json_mode=True: next(responses),
    )

    monkeypatch.setattr(
        agent,
        "inspect_schema",
        lambda data_dir: "orders: 3 rows",
    )

    result = agent.run_agent("How many rows?", str(tmp_path))

    assert result.verdict == "REFUSED"
