"""Alerting.

A tiny pluggable notifier for breaches and errors (circuit breaker, kill
switch, unhandled errors, large divergence from expectation). The default just
logs; wire a real channel (email/Slack/webhook) by subclassing ``Alerter``.
Keep alerts loud and rare — noise trains operators to ignore them.
"""

from __future__ import annotations

import logging

log = logging.getLogger("equity_trader.alerts")


class Alerter:
    def send(self, subject: str, body: str = "", urgent: bool = False) -> None:
        level = logging.ERROR if urgent else logging.WARNING
        log.log(level, "ALERT %s | %s", subject, body)


class NullAlerter(Alerter):
    def send(self, subject: str, body: str = "", urgent: bool = False) -> None:
        pass
