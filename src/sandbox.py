from typing import Optional, Union

from pydantic import BaseModel


class SandboxResult(BaseModel):
    ok: bool
    result: Optional[dict[str, Union[int, float, str]]] = None
    stdout: str = ""
    error: Optional[str] = None


def run_code(code: str, data_dir: str, timeout: int = 20) -> SandboxResult:
    return SandboxResult(ok=False, error="sandbox stub")
