import os

from equity_trader.risk.kill_switch import KillSwitch


def test_starts_untripped(tmp_path):
    ks = KillSwitch(flag_path=str(tmp_path / "KILL"))
    assert ks.is_tripped is False


def test_trip_in_process_and_file(tmp_path):
    flag = tmp_path / "KILL"
    ks = KillSwitch(flag_path=str(flag))
    ks.trip("manual test")
    assert ks.is_tripped is True
    assert "manual test" in ks.reason
    assert os.path.exists(flag)  # persists across restart


def test_flag_file_alone_trips(tmp_path):
    flag = tmp_path / "KILL"
    flag.write_text("halt")
    ks = KillSwitch(flag_path=str(flag))
    assert ks.is_tripped is True  # even without an in-process trip


def test_reset_clears_everything(tmp_path):
    flag = tmp_path / "KILL"
    ks = KillSwitch(flag_path=str(flag))
    ks.trip("x")
    ks.reset()
    assert ks.is_tripped is False
    assert not os.path.exists(flag)
