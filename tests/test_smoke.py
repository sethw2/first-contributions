"""Smoke tests for the scaffold.

These assert only that the package and its submodules import and that the
paper-first default holds. No feature behavior is tested yet.
"""

import importlib

import equities
from equities.config import DEFAULT_MODE, TradingMode


def test_package_imports():
    assert equities.__version__ == "0.0.0"


def test_submodules_import():
    for name in ("data", "signals", "risk", "execution", "portfolio", "backtest"):
        importlib.import_module(f"equities.{name}")


def test_paper_is_the_default():
    assert DEFAULT_MODE is TradingMode.PAPER
