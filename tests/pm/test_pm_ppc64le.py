"""Behavior contracts for pm's linux-ppc64le target.

Upstream suppliers already publish ppc64le builds of the interpreter chain
(python-build-standalone, nodejs.org, uv); the target is data. These tests pin
detection, ELF evidence and URL construction, and never depend on the host
running them.
"""

from __future__ import annotations

import sys

import pytest

TARGET = "linux-ppc64le"


def test_all_targets_includes_ppc64le():
    from pm.store import ALL_TARGETS

    assert ALL_TARGETS.count(TARGET) == 1


def test_current_target_detects_glibc_ppc64le(monkeypatch):
    import pm.store

    monkeypatch.setattr(pm.store, "_native_machine", lambda: "ppc64le")
    monkeypatch.setattr(pm.store, "_is_bionic_libc", lambda: False)
    monkeypatch.setattr(pm.store, "_is_musl_libc", lambda: False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert pm.store.current_target() == TARGET


def test_current_target_refuses_musl_ppc64le(monkeypatch):
    """No supplier publishes musl POWER builds; glibc artifacts must not be picked."""
    import pm.store

    monkeypatch.setattr(pm.store, "_native_machine", lambda: "ppc64le")
    monkeypatch.setattr(pm.store, "_is_bionic_libc", lambda: False)
    monkeypatch.setattr(pm.store, "_is_musl_libc", lambda: True)
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="unsupported architecture"):
        pm.store.current_target()


def test_machine_matches_binary_ppc64le_elf(tmp_path):
    from pm.package import machine_matches_binary

    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[18:20] = (0x15).to_bytes(2, "little")  # EM_PPC64
    binary = tmp_path / "power"
    binary.write_bytes(bytes(header))
    assert machine_matches_binary(binary, TARGET) is True
    assert machine_matches_binary(binary, "linux-x64") is False


@pytest.mark.parametrize("pkg, version, triple", [
    ("python", "3.14.7+20260901", "ppc64le-unknown-linux-gnu"),
    ("node", "26.7.0", "linux-ppc64le"),
    ("uv", "0.12.3", "powerpc64le-unknown-linux-gnu"),
])
def test_fetch_url_names_each_suppliers_ppc64le_triple(pkg, version, triple):
    """python-build-standalone says ``ppc64le-``, rustc/uv say ``powerpc64le-``."""
    from pm.registry import get_package

    url = get_package(pkg).fetch_url(version, TARGET)
    assert url.startswith("https://") and triple in url
