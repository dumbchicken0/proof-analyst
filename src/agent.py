"""LLM-driven analyst agent with deterministic tool guards."""

from __future__ import annotations

import argparse
import json

from pydantic import ValidationError

from src import prompts
from src.llm import chat
from src.schemas import (
    Action,
    Answer,
    FinishArgs,
    Refusal,
    TraceStep,
    Verdict,
    parse_action,
)
from src.tools import inspect_schema, profile_column_tool, run_code, sample_rows
from src.verifier import finalize


def _tool_key(action: Action) -> str:
    return json.dumps(
        {"tool": action.tool, "args": action.args},
        sort_keys=True,
    )


def _execute_tool(
    action: Action,
    data_dir: str,
):
    """Execute one validated action and return (observation, successful_code)."""
    if action.tool == "inspect_schema":
        return inspect_schema(data_dir), None

    if action.tool == "sample_rows":
        return (
            sample_rows(
                data_dir,
                action.args["table"],
                action.args["n"],
            ),
            None,
        )

    if action.tool == "profile_column":
        return (
            profile_column_tool(
                data_dir,
                action.args["table"],
                action.args["column"],
            ),
            None,
        )

    if action.tool == "run_code":
        result = run_code(data_dir, action.args["code"])

        if not result.ok:
            raise RuntimeError(result.error or "code execution failed")

        return (
            json.dumps(
                {
                    "result": result.result,
                    "stdout": result.stdout,
                },
                default=str,
            ),
            action.args["code"],
        )

    if action.tool == "ask_clarification":
        options = action.args.get("options", [])
        text = action.args["question"]

        if options:
            text += "\nOptions:\n" + "\n".join(f"- {x}" for x in options)

        return text, None

    if action.tool == "cross_check":
        return "cross_check is not implemented yet.", None

    raise ValueError(f"unsupported tool: {action.tool}")


def _refused(
    question: str,
    reason: str,
    trace: list[TraceStep],
) -> Answer:
    return Answer(
        question=question,
        verdict=Verdict.REFUSED,
        text=reason,
        refusal=Refusal(reason=reason),
        trace=trace,
    )


def run_agent(
    question: str,
    data_dir: str = "data/raw",
    max_steps: int = 8,
) -> Answer:
    """Run the analyst agent until it finishes or a guard forces refusal."""
    profile_report = inspect_schema(data_dir)

    messages = [
        {"role": "system", "content": prompts.SYSTEM_PROMPT},
        {
            "role": "user",
            "content": prompts.build_user_prompt(question, profile_report),
        },
    ]

    trace: list[TraceStep] = []
    last_code: str | None = None
    consecutive_code_errors = 0
    consecutive_parse_errors = 0
    previous_key: str | None = None
    repeated_actions = 0

    for step in range(1, max_steps + 1):
        try:
            raw = chat(messages, json_mode=True)
        except RuntimeError as exc:
            return _refused(
                question,
                f"LLM call failed: {exc}",
                trace,
            )

        messages.append({"role": "assistant", "content": raw})

        try:
            action = parse_action(raw)
            consecutive_parse_errors = 0
        except ValueError as exc:
            consecutive_parse_errors += 1
            observation = prompts.retry_message(str(exc))

            trace.append(
                TraceStep(
                    step=step,
                    tool="parse_error",
                    observation=observation,
                )
            )

            messages.append(
                {
                    "role": "user",
                    "content": prompts.observation_message(observation),
                }
            )

            if consecutive_parse_errors >= 3:
                return _refused(
                    question,
                    "The model produced invalid actions three times in a row.",
                    trace,
                )

            continue

        key = _tool_key(action)

        if key == previous_key:
            repeated_actions += 1
        else:
            repeated_actions = 1
            previous_key = key

        if repeated_actions >= 3:
            return _refused(
                question,
                "The agent repeated the same action three times in a row.",
                trace,
            )

        if action.tool == "finish":
            try:
                finish = FinishArgs.model_validate(action.args)
            except ValidationError as exc:
                observation = f"Invalid finish arguments: {exc}"

                trace.append(
                    TraceStep(
                        step=step,
                        tool="finish",
                        args=action.args,
                        observation=observation,
                    )
                )

                messages.append(
                    {
                        "role": "user",
                        "content": prompts.observation_message(observation),
                    }
                )

                continue

            if (
                finish.verdict
                in (Verdict.ANSWERED, Verdict.ANSWERED_WITH_ASSUMPTIONS)
                and last_code is None
            ):
                observation = (
                    "Cannot finish with an answered verdict before a successful "
                    "run_code. Run code first."
                )

                trace.append(
                    TraceStep(
                        step=step,
                        thought=action.thought,
                        tool=action.tool,
                        args=action.args,
                        observation=observation,
                    )
                )

                messages.append(
                    {
                        "role": "user",
                        "content": prompts.observation_message(observation),
                    }
                )

                continue

            trace.append(
                TraceStep(
                    step=step,
                    thought=action.thought,
                    tool=action.tool,
                    args=action.args,
                    observation="finish requested",
                )
            )

            return finalize(
                question,
                finish,
                last_code,
                data_dir,
                trace,
            )

        try:
            observation, successful_code = _execute_tool(action, data_dir)
            consecutive_code_errors = 0

            if successful_code is not None:
                last_code = successful_code

        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            observation = f"Tool error: {exc}"

            if action.tool == "run_code":
                consecutive_code_errors += 1
            else:
                consecutive_code_errors = 0

            if consecutive_code_errors >= 3:
                trace.append(
                    TraceStep(
                        step=step,
                        thought=action.thought,
                        tool=action.tool,
                        args=action.args,
                        observation=observation,
                    )
                )

                return _refused(
                    question,
                    "run_code failed three times in a row.",
                    trace,
                )

        trace.append(
            TraceStep(
                step=step,
                thought=action.thought,
                tool=action.tool,
                args=action.args,
                observation=observation,
            )
        )

        messages.append(
            {
                "role": "user",
                "content": prompts.observation_message(observation),
            }
        )

        if action.tool == "ask_clarification":
            return _refused(
                question,
                "The question is ambiguous and requires clarification.",
                trace,
            )

    return _refused(
        question,
        f"Agent reached max_steps={max_steps} without finishing.",
        trace,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/raw")
    parser.add_argument("--q", required=True)
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()

    answer = run_agent(
        args.q,
        data_dir=args.data,
        max_steps=args.max_steps,
    )

    print(answer.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
