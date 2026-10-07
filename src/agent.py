from src.schemas import Answer, Refusal, Verdict


def run_agent(question: str, data_dir: str = "data/raw", max_steps: int = 8) -> Answer:
    return Answer(
        question=question,
        verdict=Verdict.REFUSED,
        text="agent stub",
        refusal=Refusal(reason="agent stub"),
    )
