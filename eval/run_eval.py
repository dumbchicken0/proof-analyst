"""Evaluation harness for proof-carrying data analyst agent.

Usage:
    python eval/run_eval.py [--stub] [--limit N] [--ids q01,q02] [--questions PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd


class StubAgentAnswer:
    """Simulated agent answer for stub testing."""

    def __init__(self, verdict: str, value: Optional[float], reproduced: bool = True, explanation: str = ""):
        self.verdict = verdict
        self.value = value
        self.proof = type("Proof", (), {"reproduced": reproduced, "code": explanation})()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "value": self.value,
            "proof": {"reproduced": self.proof.reproduced, "code": getattr(self.proof, "code", "")},
        }


def stub_agent_run(question_item: Dict[str, Any], dfs: Dict[str, pd.DataFrame]) -> StubAgentAnswer:
    """Deterministic stub agent for testing without local LLM."""
    q_id = question_item.get("id", "")
    expected_verdict = question_item.get("expected_verdict", "ANSWERED")
    expected_val = question_item.get("expected_value")

    # If question is unanswerable, stub correctly refuses
    if expected_verdict in ["REFUSED", "AMBIGUOUS"]:
        return StubAgentAnswer(verdict="REFUSED", value=None, reproduced=True, explanation="Unanswerable or missing data.")

    # Return the clean expected ground-truth value with proof
    return StubAgentAnswer(
        verdict="ANSWERED",
        value=float(expected_val) if expected_val is not None else None,
        reproduced=True,
        explanation=f"Clean computation for {q_id}.",
    )


def extract_agent_response(resp: Any) -> Tuple[str, Optional[float], bool]:
    """Extract verdict, value, and proof reproduced status from agent response object or dict."""
    if isinstance(resp, dict):
        verdict = str(resp.get("verdict", "")).upper()
        raw_val = resp.get("value")
        val = float(raw_val) if raw_val is not None else None
        proof_obj = resp.get("proof", {})
        if isinstance(proof_obj, dict):
            reproduced = bool(proof_obj.get("reproduced", False))
        else:
            reproduced = bool(getattr(proof_obj, "reproduced", False))
        return verdict, val, reproduced

    # Attribute-based response object
    verdict = str(getattr(resp, "verdict", "")).upper()
    raw_val = getattr(resp, "value", None)
    val = float(raw_val) if raw_val is not None else None
    proof_obj = getattr(resp, "proof", None)
    if proof_obj is not None:
        if isinstance(proof_obj, dict):
            reproduced = bool(proof_obj.get("reproduced", False))
        else:
            reproduced = bool(getattr(proof_obj, "reproduced", False))
    else:
        reproduced = False

    return verdict, val, reproduced


def evaluate_question(q: Dict[str, Any], resp: Any) -> Dict[str, Any]:
    """Grade an individual question result."""
    expected_verdict = q.get("expected_verdict", "ANSWERED").upper()
    expected_val = q.get("expected_value")
    tolerance = q.get("tolerance")
    if tolerance is None:
        tolerance = 1e-4

    verdict, val, reproduced = extract_agent_response(resp)

    is_correct = False
    is_confident_wrong = False
    is_correct_refusal = False

    if expected_verdict in ["REFUSED", "AMBIGUOUS"]:
        if verdict in ["REFUSED", "AMBIGUOUS"] and val is None:
            is_correct = True
            is_correct_refusal = True
        else:
            # Answered when REFUSED/AMBIGUOUS was expected
            is_confident_wrong = True
    else:  # expected ANSWERED
        if verdict == "ANSWERED" and val is not None and expected_val is not None:
            if abs(val - float(expected_val)) <= float(tolerance):
                is_correct = True
            else:
                is_confident_wrong = True
        elif verdict in ["REFUSED", "AMBIGUOUS"]:
            # Incorrect refusal
            is_correct = False
            is_confident_wrong = False
        else:
            is_confident_wrong = True

    return {
        "id": q.get("id"),
        "question": q.get("question"),
        "traps": q.get("traps", []),
        "expected_verdict": expected_verdict,
        "actual_verdict": verdict,
        "expected_value": expected_val,
        "actual_value": val,
        "tolerance": tolerance,
        "proof_reproduced": reproduced,
        "is_correct": is_correct,
        "is_confident_wrong": is_confident_wrong,
        "is_correct_refusal": is_correct_refusal,
    }


def run_evaluation(
    questions_path: Path,
    data_dir: Path,
    use_stub: bool = False,
    limit: Optional[int] = None,
    ids: Optional[List[str]] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute evaluation harness across questions and compute benchmark metrics."""
    if not questions_path.exists():
        raise FileNotFoundError(f"Questions file not found: {questions_path}")

    # Load questions
    questions: List[Dict[str, Any]] = []
    with open(questions_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))

    # Apply filters
    if ids:
        target_ids = set(ids)
        questions = [q for q in questions if q.get("id") in target_ids]
    if limit is not None:
        questions = questions[:limit]

    # Load raw DataFrames
    dfs: Dict[str, pd.DataFrame] = {}
    if data_dir.exists():
        for csv_file in data_dir.glob("*.csv"):
            dfs[csv_file.stem] = pd.read_csv(csv_file, keep_default_na=False)

    # Resolve agent runner
    agent_fn = None
    if not use_stub:
        try:
            from src.agent import run_agent  # type: ignore
            agent_fn = run_agent
        except ImportError:
            print("[WARN] src.agent.run_agent not found; falling back to stub agent.")
            agent_fn = stub_agent_run
    else:
        agent_fn = stub_agent_run

    # Execute and score
    results = []
    for q in questions:
        if agent_fn == stub_agent_run:
            resp = stub_agent_run(q, dfs)
        else:
            resp = agent_fn(q["question"], dfs)
        graded = evaluate_question(q, resp)
        results.append(graded)

    total_q = len(results)
    correct_count = sum(1 for r in results if r["is_correct"])
    accuracy = (correct_count / total_q) if total_q > 0 else 0.0

    # Re-run success rate on questions with proofs
    proof_count = sum(1 for r in results if r["actual_verdict"] == "ANSWERED")
    reproduced_count = sum(1 for r in results if r["actual_verdict"] == "ANSWERED" and r["proof_reproduced"])
    rerun_success_rate = (reproduced_count / proof_count) if proof_count > 0 else 1.0

    # Refusal rate on questions where refusal was expected
    refusal_expected_count = sum(1 for r in results if r["expected_verdict"] in ["REFUSED", "AMBIGUOUS"])
    correct_refusals = sum(1 for r in results if r["is_correct_refusal"])
    correct_refusal_rate = (correct_refusals / refusal_expected_count) if refusal_expected_count > 0 else 1.0

    # Confident wrong rate
    confident_wrong_count = sum(1 for r in results if r["is_confident_wrong"])
    confident_wrong_rate = (confident_wrong_count / total_q) if total_q > 0 else 0.0

    summary = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "total_questions": total_q,
        "accuracy": round(accuracy, 4),
        "re_run_success_rate": round(rerun_success_rate, 4),
        "correct_refusal_rate": round(correct_refusal_rate, 4),
        "confident_wrong_rate": round(confident_wrong_rate, 4),
        "correct_count": correct_count,
        "confident_wrong_count": confident_wrong_count,
        "refusal_expected_count": refusal_expected_count,
        "correct_refusals": correct_refusals,
    }

    # Print results table
    print("\n" + "=" * 90)
    print(f"{'ID':<6} {'Exp Verdict':<13} {'Act Verdict':<13} {'Exp Val':<12} {'Act Val':<12} {'Repro':<7} {'Status':<10}")
    print("-" * 90)
    for r in results:
        exp_v = str(r['expected_value']) if r['expected_value'] is not None else "null"
        act_v = str(round(r['actual_value'], 2)) if r['actual_value'] is not None else "null"
        repro = "YES" if r['proof_reproduced'] else "NO"
        if r['is_correct']:
            status = "PASS"
        elif r['is_confident_wrong']:
            status = "CONF-WRONG"
        else:
            status = "FAIL"
        print(f"{r['id']:<6} {r['expected_verdict']:<13} {r['actual_verdict']:<13} {exp_v:<12} {act_v:<12} {repro:<7} {status:<10}")
    print("=" * 90)

    print("\n========================= EVALUATION METRICS =========================")
    print(f"Total Evaluated Questions:   {total_q}")
    print(f"Accuracy:                    {summary['accuracy'] * 100:.2f}% ({correct_count}/{total_q})")
    print(f"Re-run Success Rate:         {summary['re_run_success_rate'] * 100:.2f}% ({reproduced_count}/{proof_count})")
    print(f"Correct Refusal Rate:        {summary['correct_refusal_rate'] * 100:.2f}% ({correct_refusals}/{refusal_expected_count})")
    print(f"Confident-Wrong Rate:        {summary['confident_wrong_rate'] * 100:.2f}% ({confident_wrong_count}/{total_q})")
    print("======================================================================\n")

    # Output to results.json
    out_payload = {
        "summary": summary,
        "results": results,
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(out_payload, f, indent=2)
        print(f"[*] Written benchmark results to {output_path}")

    return out_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evaluation harness for data analyst agent.")
    parser.add_argument("--stub", action="store_true", help="Force stub agent mode for testing without LLM")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of questions to evaluate")
    parser.add_argument("--ids", type=str, default=None, help="Comma-separated question IDs to evaluate (e.g. q01,q02)")
    parser.add_argument("--questions", type=str, default="data/eval/questions.jsonl", help="Path to questions.jsonl")
    parser.add_argument("--data-dir", type=str, default="data/raw", help="Path to raw CSVs")
    parser.add_argument("--output", type=str, default="eval/results.json", help="Path to save results JSON")
    args = parser.parse_args()

    ids_list = [i.strip() for i in args.ids.split(",") if i.strip()] if args.ids else None
    run_evaluation(
        questions_path=Path(args.questions),
        data_dir=Path(args.data_dir),
        use_stub=args.stub,
        limit=args.limit,
        ids=ids_list,
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    main()
