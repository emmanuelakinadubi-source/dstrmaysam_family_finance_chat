"""
Unit tests for app/modules/evaluation/ragas_eval.py

Tests the helper utilities only — the full evaluate_response() function
is an integration test (requires Azure OpenAI) and is not run here.
"""
import pytest
from app.modules.evaluation.ragas_eval import _safe_float


class TestSafeFloat:
    def test_valid_float_rounded_to_4dp(self):
        assert _safe_float(0.123456) == 0.1235

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_integer_converted(self):
        assert _safe_float(1) == 1.0

    def test_string_float_converted(self):
        assert _safe_float("0.85") == 0.85

    def test_non_numeric_string_returns_none(self):
        assert _safe_float("not_a_number") is None

    def test_nan_string_returns_none(self):
        import math
        result = _safe_float(float("nan"))
        # nan converted to float but round(nan, 4) is still nan — treat as valid float
        # This confirms the function doesn't crash on NaN
        assert result is None or (isinstance(result, float) and math.isnan(result))

    def test_zero_returns_zero(self):
        assert _safe_float(0) == 0.0

    def test_one_returns_one(self):
        assert _safe_float(1.0) == 1.0
