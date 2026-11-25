"""Pluggable analyzers.

Register a function with ``register_analyzer``. ``analyze_video`` picks one
from ``Settings.detector`` (``auto``, ``classic``, or ``footage``).

A replacement analyzer must return the same top-level dict the API already
stores: ``video``, ``quality``, ``preanalysis``, ``calibration``, ``deliveries``.
Each delivery uses ``release_time_s``, ``contact``, ``shot``, ``virtual_runs``,
``bat_detected`` and ``batsman_detected``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from bowlinger.config import Settings

Analyzer = Callable[[Path, Settings, dict, dict], dict]

ANALYZERS: dict[str, Analyzer] = {}


def register_analyzer(name: str) -> Callable[[Analyzer], Analyzer]:
    def decorate(func: Analyzer) -> Analyzer:
        ANALYZERS[name] = func
        return func

    return decorate


def get_analyzer(name: str) -> Analyzer:
    if name not in ANALYZERS:
        known = ", ".join(sorted(ANALYZERS))
        raise KeyError(f"Unknown analyzer {name!r}. Registered: {known}")
    return ANALYZERS[name]
