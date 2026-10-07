from src.schemas import Answer, FinishArgs, Refusal, TraceStep, Verdict


def hash_data_dir(data_dir: str) -> str:
    return "sha256:stub"


def finalize(
    question: str,
    finish: FinishArgs,
    last_code: str | None,
    data_dir: str,
    trace: list[TraceStep],
) -> Answer:
    return Answer(
        question=question,
        verdict=Verdict.REFUSED,
        text="verifier stub",
        refusal=Refusal(reason="verifier stub"),
        trace=trace,
    )
