from datetime import datetime, timezone

import pytest

from equity_trader.config.settings import RiskLimits
from equity_trader.risk.kill_switch import KillSwitch
from equity_trader.risk.manager import RejectReason, RiskManager
from equity_trader.risk.models import Account, Order, OrderType, Position, Side


NOW = datetime(2026, 8, 3, 15, tzinfo=timezone.utc)


def make_rm(tmp_path, **limit_overrides):
    limits = RiskLimits(**limit_overrides) if limit_overrides else RiskLimits()
    ks = KillSwitch(flag_path=str(tmp_path / "KILL"))
    return RiskManager(limits, ks)


def account(equity=100_000.0, bp=100_000.0):
    return Account(equity=equity, cash=equity, buying_power=bp)


def entry_order(symbol="AAPL", qty=100, price=100.0):
    return Order(symbol=symbol, side=Side.BUY, qty=qty, order_type=OrderType.MARKET,
                 limit_price=price, client_order_id=f"{symbol}-test")


# ---------------------------------------------------------------- sizing
def test_sizing_notional_cap_binds(tmp_path):
    rm = make_rm(tmp_path)
    # risk budget = 100k * 0.75% = 750; stop dist 2 -> 375 shares by risk,
    # but 20% notional cap = 20k / 100 = 200 shares. Cap binds.
    qty = rm.size_position(equity=100_000, entry_price=100, stop_price=98)
    assert qty == 200


def test_sizing_risk_budget_binds(tmp_path):
    rm = make_rm(tmp_path)
    # stop dist 10 -> 75 shares by risk; notional cap 200. Risk binds.
    qty = rm.size_position(equity=100_000, entry_price=100, stop_price=90)
    assert qty == 75


def test_sizing_rejects_zero_stop_distance(tmp_path):
    rm = make_rm(tmp_path)
    assert rm.size_position(equity=100_000, entry_price=100, stop_price=100) == 0


def test_sizing_adv_participation_cap_binds(tmp_path):
    rm = make_rm(tmp_path)  # max_adv_participation default 1%
    # Risk allows 375 shares and notional allows 200, but a thin name with
    # 10,000 ADV caps us at 1% = 100 shares.
    qty = rm.size_position(equity=100_000, entry_price=100, stop_price=98,
                           avg_daily_volume=10_000)
    assert qty == 100


def test_sizing_adv_cap_absent_when_no_volume(tmp_path):
    rm = make_rm(tmp_path)
    # No ADV supplied -> cap does not apply; notional cap (200) still binds.
    qty = rm.size_position(equity=100_000, entry_price=100, stop_price=98)
    assert qty == 200


# ---------------------------------------------------------------- gating
def test_kill_switch_blocks_entry(tmp_path):
    rm = make_rm(tmp_path)
    rm.start_session(account())
    rm.kill_switch.trip("test", write_file=False)
    d = rm.validate_entry(entry_order(), account(), [], NOW)
    assert not d.approved and d.reason == RejectReason.KILL_SWITCH


def test_circuit_breaker_blocks_entry(tmp_path):
    rm = make_rm(tmp_path)
    rm.start_session(account(equity=100_000))
    d = rm.validate_entry(entry_order(), account(equity=96_000), [], NOW)  # -4%
    assert not d.approved and d.reason == RejectReason.CIRCUIT_BREAKER


def test_shorting_disabled_by_default(tmp_path):
    rm = make_rm(tmp_path)
    rm.start_session(account())
    o = entry_order()
    o.side = Side.SELL
    d = rm.validate_entry(o, account(), [], NOW)
    assert not d.approved and d.reason == RejectReason.SHORTING_DISABLED


def test_max_positions_enforced(tmp_path):
    rm = make_rm(tmp_path, max_concurrent_positions=2)
    rm.start_session(account())
    held = [
        Position("X", 10, 100, NOW, 95, NOW, kind="momentum"),
        Position("Y", 10, 100, NOW, 95, NOW, kind="momentum"),
    ]
    d = rm.validate_entry(entry_order(), account(), held, NOW)
    assert not d.approved and d.reason == RejectReason.MAX_POSITIONS


def test_per_symbol_notional_cap(tmp_path):
    rm = make_rm(tmp_path)
    rm.start_session(account())
    # 300 * 100 = 30k > 20% of 100k = 20k
    d = rm.validate_entry(entry_order(qty=300, price=100), account(), [], NOW)
    assert not d.approved and d.reason == RejectReason.POSITION_NOTIONAL


def test_gross_exposure_cap(tmp_path):
    rm = make_rm(tmp_path, max_gross_exposure=1.0, max_position_notional_pct=1.0)
    rm.start_session(account())
    held = [Position("X", 950, 100, NOW, 95, NOW)]  # 95k gross
    d = rm.validate_entry(entry_order(qty=100, price=100), account(), held, NOW)  # +10k -> 105k
    assert not d.approved and d.reason == RejectReason.GROSS_EXPOSURE


def test_buying_power_cap(tmp_path):
    rm = make_rm(tmp_path)
    rm.start_session(account())
    d = rm.validate_entry(entry_order(qty=100, price=100), account(bp=5_000), [], NOW)
    assert not d.approved and d.reason == RejectReason.BUYING_POWER


def test_pdt_limit_blocks_entry_below_threshold(tmp_path):
    rm = make_rm(tmp_path)
    acct = account(equity=20_000, bp=20_000)
    rm.start_session(acct)
    for _ in range(3):
        rm.register_open("SPY", NOW)
        rm.register_close("SPY", NOW)
    d = rm.validate_entry(entry_order(qty=10, price=100), acct, [], NOW)
    assert not d.approved and d.reason == RejectReason.PDT_LIMIT


def test_clean_entry_approved(tmp_path):
    rm = make_rm(tmp_path)
    rm.start_session(account())
    d = rm.validate_entry(entry_order(qty=100, price=100), account(), [], NOW)
    assert d.approved and d.reason == RejectReason.OK


def test_exit_never_blocked_by_pdt(tmp_path):
    rm = make_rm(tmp_path)
    acct = account(equity=20_000, bp=20_000)
    rm.start_session(acct)
    for _ in range(3):
        rm.register_open("SPY", NOW)
        rm.register_close("SPY", NOW)
    o = Order(symbol="SPY", side=Side.SELL, qty=10, order_type=OrderType.MARKET)
    d = rm.validate_exit(o, acct, NOW)
    assert d.approved


def test_compute_stops_long(tmp_path):
    rm = make_rm(tmp_path, atr_stop_multiple=2.0, max_holding_days=14)
    stop, tp, tstop = rm.compute_stops(Side.BUY, entry_price=100, atr=1.0, entry_time=NOW)
    assert stop == pytest.approx(98.0)      # 100 - 2*1
    assert tp == pytest.approx(103.0)       # 100 + 3*1
    assert (tstop - NOW).days == 14
