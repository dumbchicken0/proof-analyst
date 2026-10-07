"""Tests for sandbox code execution and safety validation."""
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.sandbox import run_code


@pytest.fixture
def sample_data_dir():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        df1 = pd.DataFrame({"id": [1, 2, 3], "val": [10.0, 20.0, 30.0]})
        df1.to_csv(p / "items.csv", index=False)
        yield p


def test_sandbox_good_result(sample_data_dir):
    code = """
total = float(dfs['items']['val'].sum())
result = {'total_val': total, 'count': 3, 'label': 'items'}
"""
    res = run_code(code, sample_data_dir, timeout=10)
    assert res.ok is True
    assert res.error is None
    assert res.result == {"total_val": 60.0, "count": 3, "label": "items"}


def test_sandbox_numpy_scalars(sample_data_dir):
    code = """
import numpy as np
val = np.int64(42)
result = {'answer': val}
"""
    res = run_code(code, sample_data_dir, timeout=10)
    assert res.ok is True
    assert res.result == {"answer": 42}
    assert isinstance(res.result["answer"], int)


def test_sandbox_timeout_kill(sample_data_dir):
    code = """
while True:
    pass
"""
    res = run_code(code, sample_data_dir, timeout=1)
    assert res.ok is False
    assert "timed out" in res.error.lower()


def test_sandbox_blocked_imports(sample_data_dir):
    blocked_snippets = [
        "import os\nresult = {'a': 1}",
        "import sys\nresult = {'a': 1}",
        "import subprocess\nresult = {'a': 1}",
        "import socket\nresult = {'a': 1}",
        "from pathlib import Path\nresult = {'a': 1}",
        "import shutil\nresult = {'a': 1}",
        "import requests\nresult = {'a': 1}",
        "import urllib.request\nresult = {'a': 1}",
        "import ctypes\nresult = {'a': 1}",
        "import importlib\nresult = {'a': 1}",
    ]
    for code in blocked_snippets:
        res = run_code(code, sample_data_dir, timeout=5)
        assert res.ok is False
        assert "forbidden import" in res.error.lower()


def test_sandbox_blocked_calls(sample_data_dir):
    blocked_calls = [
        "open('test.txt')\nresult = {'a': 1}",
        "eval('1 + 1')\nresult = {'a': 1}",
        "exec('a = 1')\nresult = {'a': 1}",
        "__import__('os')\nresult = {'a': 1}",
    ]
    for code in blocked_calls:
        res = run_code(code, sample_data_dir, timeout=5)
        assert res.ok is False
        assert "forbidden" in res.error.lower()


def test_sandbox_nan_result(sample_data_dir):
    code = """
result = {'val': float('nan')}
"""
    res = run_code(code, sample_data_dir, timeout=5)
    assert res.ok is False
    assert "nan" in res.error.lower()


def test_sandbox_inf_result(sample_data_dir):
    code = """
result = {'val': float('inf')}
"""
    res = run_code(code, sample_data_dir, timeout=5)
    assert res.ok is False
    assert "inf" in res.error.lower()


def test_sandbox_empty_result(sample_data_dir):
    code = """
result = {}
"""
    res = run_code(code, sample_data_dir, timeout=5)
    assert res.ok is False
    assert "non-empty" in res.error.lower()


def test_sandbox_no_result_variable(sample_data_dir):
    code = """
x = 10
"""
    res = run_code(code, sample_data_dir, timeout=5)
    assert res.ok is False
    assert "result" in res.error.lower()


def test_sandbox_stdout_capture(sample_data_dir):
    code = """
print("hello from sandbox")
result = {'status': 'ok'}
"""
    res = run_code(code, sample_data_dir, timeout=5)
    assert res.ok is True
    assert "hello from sandbox" in res.stdout
