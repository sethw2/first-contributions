"""Configuration: risk limits, universe, strategy params, and environment.

Settings load from a YAML file (see ``default.yaml``) with environment-variable
overrides for anything sensitive. Secrets (API keys) come from the environment
ONLY and are never read from or written to YAML.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class Environment(str):
    PAPER = "paper"
    LIVE = "live"


@dataclass
class RiskLimits:
    """Every hard limit the RiskManager enforces. Conservative by default."""

    risk_per_trade: float = 0.0075          # fraction of equity risked to the stop (0.75%)
    max_concurrent_positions: int = 8
    max_gross_exposure: float = 1.0         # 1.0 = no leverage
    max_position_notional_pct: float = 0.20  # any one symbol <= 20% of equity
    max_adv_participation: float = 0.01     # any one position <= 1% of the name's avg daily volume
    daily_loss_limit: float = 0.03          # -3% session P&L -> flatten & halt
    max_holding_days: float = 14.0          # 2-week ceiling (time stop)
    min_holding_minutes: float = 30.0       # 30-minute floor
    atr_stop_multiple: float = 2.0          # hard stop = entry -/+ k * ATR
    allow_shorting: bool = False            # long-only in v1
    pdt_equity_threshold: float = 25_000.0  # accounts below this are PDT-limited
    pdt_max_day_trades: int = 3             # per rolling 5 business days

    def validate(self) -> None:
        assert 0 < self.risk_per_trade <= 0.05, "risk_per_trade must be in (0, 5%]"
        assert self.max_concurrent_positions >= 1
        assert 0 < self.max_gross_exposure <= 4.0
        assert 0 < self.max_position_notional_pct <= 1.0
        assert 0 < self.max_adv_participation <= 0.25
        assert 0 < self.daily_loss_limit < 1.0
        assert self.min_holding_minutes >= 0
        assert self.max_holding_days * 24 * 60 > self.min_holding_minutes


@dataclass
class UniverseConfig:
    symbols: List[str] = field(default_factory=lambda: [
        "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
        "META", "XLF", "XLE", "XLK", "IWM",
    ])
    # Liquidity floor. Lowered per operator guidance: with a sub-$100M book we
    # won't move lower-liquidity names, so $5M ADV is acceptable. Names below
    # this are screened out because stops become unreliable when you can't exit.
    min_avg_dollar_volume: float = 5_000_000.0
    min_price: float = 5.0                       # no sub-$5 names (wide spreads / manipulation)


@dataclass
class StrategyParams:
    # NOTE: signal strength (breakout distance, RVOL, z-score depth) is used only
    # to RANK and SELECT candidates — never to size positions. Per operator
    # direction, the profit edge must come from predicting direction, not sizing.
    breakout_lookback: int = 20
    trend_lookback: int = 200
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    zscore_lookback: int = 20
    zscore_entry: float = -2.0
    atr_period: int = 14
    # Volume is an OPTIONAL input, not a requirement. RVOL only nudges ranking.
    # Set require_volume_confirmation=True to re-enable a hard volume gate; the
    # multiple below is used ONLY when that flag is on.
    require_volume_confirmation: bool = False
    volume_confirm_multiple: float = 1.2
    take_profit_atr_multiple: float = 3.0
    max_new_positions_per_cycle: int = 3


@dataclass
class Settings:
    environment: str = Environment.PAPER
    risk: RiskLimits = field(default_factory=RiskLimits)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    strategy: StrategyParams = field(default_factory=StrategyParams)
    starting_equity: float = 100_000.0
    data_feed: str = "iex"                       # Alpaca free feed
    regular_hours_only: bool = True              # trade ONLY during 9:30-16:00 ET regular session
    kill_switch_file: str = "./KILL_SWITCH"
    log_dir: str = "./logs"

    # --- secrets: environment only ---
    @property
    def api_key(self) -> Optional[str]:
        return os.getenv("ALPACA_API_KEY")

    @property
    def api_secret(self) -> Optional[str]:
        return os.getenv("ALPACA_API_SECRET")

    @property
    def is_live(self) -> bool:
        return self.environment == Environment.LIVE

    def validate(self) -> None:
        assert self.environment in (Environment.PAPER, Environment.LIVE)
        self.risk.validate()


def load_settings(path: Optional[str] = None) -> Settings:
    """Load settings from YAML if available, else return safe defaults.

    Any missing keys fall back to the conservative dataclass defaults, so a
    partial or absent config file still produces a valid, safe configuration.
    """

    data: Dict[str, Any] = {}
    if path and os.path.exists(path):
        try:
            import yaml  # optional dependency; defaults used if unavailable
            with open(path, "r") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            data = {}

    settings = Settings()
    if "environment" in data:
        settings.environment = str(data["environment"]).lower()
    if "starting_equity" in data:
        settings.starting_equity = float(data["starting_equity"])
    if "data_feed" in data:
        settings.data_feed = str(data["data_feed"])
    if "regular_hours_only" in data:
        settings.regular_hours_only = bool(data["regular_hours_only"])
    if "kill_switch_file" in data:
        settings.kill_switch_file = str(data["kill_switch_file"])

    settings.risk = _merge(RiskLimits(), data.get("risk", {}))
    settings.universe = _merge(UniverseConfig(), data.get("universe", {}))
    settings.strategy = _merge(StrategyParams(), data.get("strategy", {}))

    # An env var can force paper mode but must never silently enable live.
    if os.getenv("FORCE_PAPER", "").lower() in ("1", "true", "yes"):
        settings.environment = Environment.PAPER

    settings.validate()
    return settings


def _merge(obj: Any, overrides: Dict[str, Any]) -> Any:
    for key, value in (overrides or {}).items():
        if hasattr(obj, key):
            setattr(obj, key, value)
    return obj
