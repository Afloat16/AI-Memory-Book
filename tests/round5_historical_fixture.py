"""Explicit input snapshots for historical round-five registration unit tests.

Current product tests may evolve after a benchmark is frozen. The old evaluator
still requires their original bytes, which are data here and are never executed.
No production hash, input inventory, registration, or acceptance gate is changed.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch


_ROOT = Path(__file__).resolve().parents[1]
_ARCHIVED_ROOT = _ROOT / "tests/fixtures/round5_frozen_inputs"
_ARCHIVED_FILES = {
    "tests/test_round5_covering_index.py",
    "tests/test_round5_candidate_c4.py",
    *(f"tests/test_round5_c{number}_performance.py" for number in range(4, 8)),
}
_PLAN_PATH = "benchmarks/experiments/round5-plan.json"


def _verified_bytes(path, expected, name):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Frozen round-five fixture bytes changed: " + name)
    return raw


@contextmanager
def historical_round5_inputs(evaluator):
    """Use the exact C6 snapshot (including its C3/C4/C5 inputs) in one test.

    The unchanged C7 gate supplies the original C6 binding/summary identities.
    Every input is checked against that binding before creating a temporary
    tree. Only explicitly archived tests use saved bytes; all other files come
    from the checkout and must still match their original registered hashes.
    """
    from scripts import round5_c7_performance as registered

    binding_raw = _verified_bytes(_ROOT / registered.C6_BINDING_PATH,
                                  registered.C6_BINDING_SHA256,
                                  registered.C6_BINDING_PATH)
    binding = json.loads(binding_raw)
    inventory = dict(binding["evaluator_files"])
    inventory.update({
        registered.C6_BINDING_PATH: registered.C6_BINDING_SHA256,
        registered.C6_SUMMARY_PATH: registered.C6_SUMMARY_SHA256,
        _PLAN_PATH: binding["plan_sha256"],
    })
    with tempfile.TemporaryDirectory(prefix="round5-historical-inputs-") as directory:
        root = Path(directory)
        for name, expected in inventory.items():
            source = (_ARCHIVED_ROOT / (Path(name).name + ".txt")
                      if name in _ARCHIVED_FILES else _ROOT / name)
            raw = _verified_bytes(source, expected, name)
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        with patch.object(evaluator, "ROOT", root), patch.object(
                evaluator, "PLAN", root / _PLAN_PATH):
            yield root
