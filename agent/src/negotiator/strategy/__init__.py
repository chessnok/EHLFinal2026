"""Strategies by name. Add yours here: any class with prepare/decide/conclude/keepalive (see base.py)."""

from collections.abc import Callable

from negotiator.data import WorldData
from negotiator.strategy.base import Decision, Strategy
from negotiator.strategy.baseline import BaselineStrategy
from negotiator.strategy.tactical import TacticalStrategy

STRATEGIES: dict[str, Callable[[WorldData | None], Strategy]] = {
    "tactical": TacticalStrategy,
    "baseline": BaselineStrategy,
}

__all__ = ["STRATEGIES", "BaselineStrategy", "Decision", "Strategy", "TacticalStrategy"]
