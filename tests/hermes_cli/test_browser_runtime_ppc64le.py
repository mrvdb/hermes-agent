"""browser_exec on linux-ppc64le runs the distribution's Chromium.

Chrome-for-Testing and Playwright's mirror publish no ppc64le Chromium, so pm
has none to install there; the system ``chromium`` must stand in, as it does
on Termux.
"""

from __future__ import annotations

import pm
from hermes_cli import browser_runtime


def test_chromium_executable_falls_back_to_system_chromium_on_ppc64le(monkeypatch):
    monkeypatch.setattr(pm, "current_target", lambda: "linux-ppc64le")
    monkeypatch.setattr(browser_runtime, "_configured_executable", lambda: None)
    monkeypatch.setattr(browser_runtime, "_pm_executable", lambda: None)
    monkeypatch.setattr(browser_runtime, "_baked_executable", lambda: None)
    monkeypatch.setattr(browser_runtime, "_system_executable", lambda: "/usr/bin/chromium")

    assert browser_runtime.chromium_executable() == "/usr/bin/chromium"


def test_chromium_executable_ignores_system_chromium_where_pm_builds_one(monkeypatch):
    monkeypatch.setattr(pm, "current_target", lambda: "linux-x64")
    monkeypatch.setattr(browser_runtime, "_configured_executable", lambda: None)
    monkeypatch.setattr(browser_runtime, "_pm_executable", lambda: None)
    monkeypatch.setattr(browser_runtime, "_baked_executable", lambda: None)
    monkeypatch.setattr(browser_runtime, "_system_executable", lambda: "/usr/bin/chromium")

    assert browser_runtime.chromium_executable() is None
