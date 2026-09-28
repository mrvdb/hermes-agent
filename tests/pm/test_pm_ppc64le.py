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


@pytest.mark.parametrize("pkg", ["ripgrep", "ffmpeg", "cua-driver"])
def test_tools_without_upstream_ppc64le_build_are_gapped(pkg):
    from pm.registry import get_package

    assert get_package(pkg).missing_reason(TARGET)


def test_ffmpeg_ppc64le_gap_keeps_the_musl_gaps():
    from pm.registry import get_package
    from pm.store import MUSL_TARGETS

    gaps = get_package("ffmpeg").gaps
    assert TARGET in gaps and MUSL_TARGETS <= set(gaps)


def test_tool_roots_skip_packages_gapped_on_this_target(monkeypatch):
    """A gapped required tool has no artifact to publish; without the filter it
    reaches _install() and raises 'unavailable on <target>'."""
    from pm import registry
    import pm.store

    monkeypatch.setattr(pm.store, "current_target", lambda: TARGET)
    roots = registry.tool_roots(["ffmpeg", "node", "npm", "python", "ripgrep"])
    assert "ripgrep" not in roots and "ffmpeg" not in roots
    assert {"node", "npm", "python"} <= set(roots)


def test_tool_roots_unchanged_where_nothing_is_gapped(monkeypatch):
    from pm import registry
    import pm.store

    monkeypatch.setattr(pm.store, "current_target", lambda: "linux-x64")
    assert registry.tool_roots(["ffmpeg", "node", "npm", "python", "ripgrep"]) == [
        "ffmpeg", "node", "npm", "python", "ripgrep"]
