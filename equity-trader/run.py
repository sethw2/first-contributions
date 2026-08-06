#!/usr/bin/env python3
"""Command-line entrypoint for the equity trading system.

Subcommands:
  backtest   Run the event-driven backtester over CSV data.
  paper      Run the live loop against Alpaca PAPER trading.
  live       Run against LIVE trading (guarded; requires explicit confirmation).
  kill       Trip the kill switch (halts any running instance).

Safety: ``live`` is the ONLY path that touches real money, and it refuses to
start without ``--i-understand-live`` plus an interactive confirmation.
Everything defaults to paper.
"""

from __future__ import annotations

import argparse
import os
import sys

from equity_trader.backtest.engine import Backtester
from equity_trader.config.settings import Environment, load_settings
from equity_trader.data.market_data import CsvDataProvider
from equity_trader.engine.core import TradingEngine
from equity_trader.engine.loop import LiveLoop
from equity_trader.monitoring.logging_setup import setup_logging
from equity_trader.risk.kill_switch import KillSwitch
from equity_trader.risk.manager import RiskManager
from equity_trader.strategy.momentum_reversion import MomentumReversionStrategy


def _build_strategy(settings):
    return MomentumReversionStrategy(settings.strategy, settings.universe)


def cmd_backtest(args) -> int:
    settings = load_settings(args.config)
    setup_logging(settings.log_dir)
    provider = CsvDataProvider(args.data_dir)
    market = {}
    for sym in settings.universe.symbols:
        try:
            bars = provider.load(sym)
            if bars:
                market[sym] = bars
        except FileNotFoundError:
            print(f"note: no data file for {sym}, skipping")
    if args.benchmark not in market:
        print(f"error: benchmark {args.benchmark} has no data in {args.data_dir}")
        return 2
    report = Backtester(settings, _build_strategy(settings)).run(
        market, benchmark=args.benchmark)
    print(report.summary())
    return 0


def _live_or_paper(args, environment: str) -> int:
    settings = load_settings(args.config)
    settings.environment = environment
    settings.validate()
    setup_logging(settings.log_dir)

    from equity_trader.execution.alpaca_broker import AlpacaBroker
    from equity_trader.data.market_data import AlpacaDataProvider

    broker = AlpacaBroker(
        settings,
        i_understand_live=getattr(args, "i_understand_live", False),
        require_confirmation=True,
    )
    data = AlpacaDataProvider(settings.api_key, settings.api_secret,
                              feed=settings.data_feed, timeframe=args.timeframe)
    risk = RiskManager(settings.risk, KillSwitch(settings.kill_switch_file))
    engine = TradingEngine(settings, broker, _build_strategy(settings), risk)
    loop = LiveLoop(settings, engine, data, poll_seconds=args.poll)
    loop.run()
    return 0


def cmd_paper(args) -> int:
    return _live_or_paper(args, Environment.PAPER)


def cmd_live(args) -> int:
    if not args.i_understand_live:
        print("Refusing to run live without --i-understand-live. Default is paper.")
        return 2
    return _live_or_paper(args, Environment.LIVE)


def cmd_kill(args) -> int:
    settings = load_settings(args.config)
    KillSwitch(settings.kill_switch_file).trip(reason=args.reason or "cli")
    print(f"kill switch tripped: {settings.kill_switch_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Short-term equity trading system")
    p.add_argument("--config", default=os.path.join(
        os.path.dirname(__file__), "equity_trader", "config", "default.yaml"))
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("backtest", help="run the backtester over CSV data")
    b.add_argument("--data-dir", required=True, help="dir with {SYMBOL}.csv files")
    b.add_argument("--benchmark", default="SPY")
    b.set_defaults(func=cmd_backtest)

    pa = sub.add_parser("paper", help="run against Alpaca paper trading")
    pa.add_argument("--poll", type=int, default=60)
    pa.add_argument("--timeframe", default="30Min")
    pa.set_defaults(func=cmd_paper)

    lv = sub.add_parser("live", help="run against LIVE trading (guarded)")
    lv.add_argument("--poll", type=int, default=60)
    lv.add_argument("--timeframe", default="30Min")
    lv.add_argument("--i-understand-live", action="store_true",
                    help="required acknowledgement that this trades REAL money")
    lv.set_defaults(func=cmd_live)

    k = sub.add_parser("kill", help="trip the kill switch")
    k.add_argument("--reason", default="")
    k.set_defaults(func=cmd_kill)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
