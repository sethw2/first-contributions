"""The kill switch.

A single, dead-simple mechanism to stop all trading that works even if the
strategy loop is wedged: presence of a flag file (or an in-process trip) blocks
every new order. It is intentionally file-based so an operator can trip it from
a shell — ``touch KILL_SWITCH`` — without touching the running process.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


class KillSwitch:
    def __init__(self, flag_path: str = "./KILL_SWITCH") -> None:
        self.flag_path = flag_path
        self._tripped_in_process = False
        self._reason = ""

    @property
    def is_tripped(self) -> bool:
        """True if trading must halt (either the flag file exists or tripped in-process)."""
        return self._tripped_in_process or os.path.exists(self.flag_path)

    @property
    def reason(self) -> str:
        if self._reason:
            return self._reason
        if os.path.exists(self.flag_path):
            return f"kill-switch flag file present at {self.flag_path}"
        return ""

    def trip(self, reason: str = "manual", write_file: bool = True) -> None:
        """Engage the kill switch. Persists a flag file so a restart stays halted."""
        self._tripped_in_process = True
        self._reason = reason
        if write_file:
            try:
                with open(self.flag_path, "w") as fh:
                    fh.write(f"{datetime.now(timezone.utc).isoformat()} {reason}\n")
            except OSError:
                # Even if we cannot persist, the in-process trip still halts trading.
                pass

    def reset(self) -> None:
        """Clear the kill switch. Manual, deliberate action only."""
        self._tripped_in_process = False
        self._reason = ""
        if os.path.exists(self.flag_path):
            try:
                os.remove(self.flag_path)
            except OSError:
                pass
