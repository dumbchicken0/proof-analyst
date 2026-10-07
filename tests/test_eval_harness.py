"""Unit tests for evaluation harness and metrics calculation."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from eval.run_eval import evaluate_question, extract_agent_response, run_evaluation, StubAgentAnswer


def test_extract_agent_response():
    """Verify extracting verdict, value, and proof from both dict and object structures."""
    # Attribute object
    obj_ans = StubAgentAnswer(verdict="ANSWERED", value=123.45, reproduced=True)
    v, val, repro = extract_agent_response(obj_ans)
    assert v == "ANSWERED"
    assert val == 123.45
    assert repro is True

    # Dict structure
    dict_ans = {"verdict": "REFUSED", "value": None, "proof": {"reproduced": False}}
    v, val, repro = extract_agent_response(dict_ans)
    assert v == "REFUSED"
    assert val is None
    assert repro is False


def test_evaluate_question_pass_and_fail():
    """Verify scoring logic for correct, incorrect, and confident-wrong responses."""
    q_answered = {
        "id": "q01",
        "question": "Sample?",
        "expected_verdict": "ANSWERED",
        "expected_value": 100.0,
        "tolerance": 0.5,
    }
    # Pass within tolerance
    res_pass = evaluate_question(q_answered, {"verdict": "ANSWERED", "value": 100.2, "proof": {"reproduced": True}})
    assert res_pass["is_correct"] is True
    assert res_pass["is_confident_wrong"] is False

    # Confident wrong: answered with wrong value
    res_wrong = evaluate_question(q_answered, {"verdict": "ANSWERED", "value": 150.0, "proof": {"reproduced": True}})
    assert res_wrong["is_correct"] is False
    assert res_wrong["is_confident_wrong"] is True

    # Confident wrong: answered when REFUSED expected
    q_refused = {
        "id": "q09",
        "question": "Profit?",
        "expected_verdict": "REFUSED",
        "expected_value": None,
        "tolerance": None,
    }
    res_hallucinated = evaluate_question(q_refused, {"verdict": "ANSWERED", "value": 42.0, "proof": {"reproduced": True}})
    assert res_hallucinated["is_correct"] is False
    assert res_hallucinated["is_confident_wrong"] is True

    # Correct refusal
    res_refused = evaluate_question(q_refused, {"verdict": "REFUSED", "value": None, "proof": {"reproduced": True}})
    assert res_refused["is_correct"] is True
    assert res_refused["is_confident_wrong"] is False
    assert res_refused["is_correct_refusal"] is True


def test_eval_harness_integration(tmp_path: Path):
    """Test full evaluation pipeline on small questions file with stub agent."""
    q_file = tmp_path / "test_questions.jsonl"
    questions = [
        {"id": "t1", "question": "Clean count?", "traps": [], "expected_verdict": "ANSWERED", "expected_value": 5.0, "tolerance": 0.0},
        {"id": "t2", "question": "Refused?", "traps": ["missing"], "expected_verdict": "REFUSED", "expected_value": None, "tolerance": None},
    ]
    with open(q_file, "w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q) + "\n")

    res_json = tmp_path / "results.json"
    data_dir = tmp_path / "raw"
    data_dir.mkdir(parents=True, exist_ok=True)

    payload = run_evaluation(
        questions_path=q_file,
        data_dir=data_dir,
        use_stub=True,
        output_path=res_json,
    )

    assert res_json.exists()
    summary = payload["summary"]
    assert summary["total_questions"] == 2
    assert summary["accuracy"] == 1.0
    assert summary["re_run_success_rate"] == 1.0
    assert summary["correct_refusal_rate"] == 1.0
    assert summary["confident_wrong_rate"] == 0.0
