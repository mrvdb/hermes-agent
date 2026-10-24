"""Behavior contracts for pm's linux-ppc64le target.

Upstream suppliers already publish ppc64le builds of the interpreter chain
(python-build-standalone, nodejs.org, uv); the target is data. These tests pin
detection, ELF evidence and URL construction, and never depend on the host
running them.
"""

from __future__ import annotations

import json
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


@pytest.mark.parametrize("pkg", ["ripgrep", "ffmpeg", "cua-driver", "chromium"])
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


# What python-build-standalone 3.14.9 records on ppc64le (sysconfig.get_config_var): it
# cross-compiles POWER, so every tool carries the triple's prefix.
_CROSS = "/usr/bin/powerpc64le-linux-gnu-"
_LDFLAGS = " -shared -Wl,-z,noexecstack -Wl,-z,relro -Wl,--exclude-libs,ALL -Wl,--no-tls-get-addr-optimize"
_PBS_PPC64LE = {
    "CC": _CROSS + "gcc -pthread", "CXX": _CROSS + "g++",
    "LDSHARED": _CROSS + "gcc -pthread" + _LDFLAGS, "LDCXXSHARED": _CROSS + "g++" + _LDFLAGS,
    "AR": "ar",
}


def _pinned_recording(tmp_path, monkeypatch, recorded, name="pinned-python"):
    # One file per recording: pm.build_compilers caches the toolchain per interpreter path.
    pinned = tmp_path / name
    pinned.write_text(f"#!/bin/sh\necho '{json.dumps(recorded)}'\n", encoding="utf-8")
    pinned.chmod(0o755)
    monkeypatch.setattr("pm._uv._toolchain", lambda **kwargs: (tmp_path / "uv", pinned))


def _bin_dir(directory, *names):
    directory.mkdir()
    for name in names:
        (directory / name).write_text("#!/bin/sh\n", encoding="utf-8")
        (directory / name).chmod(0o755)
    return str(directory)


@pytest.mark.platforms("linux")
def test_cross_built_pbs_builds_sdists_with_the_native_gcc(tmp_path, monkeypatch):
    """A native POWER host has gcc, not the cross triple's gcc PBS recorded."""
    from pm.environment import managed_environment

    _pinned_recording(tmp_path, monkeypatch, _PBS_PPC64LE)
    native = _bin_dir(tmp_path / "native", "gcc", "g++", "ar")
    built = managed_environment(tmp_path / "venv", env={"PATH": native}, cache=tmp_path).env
    assert {key: built.get(key) for key in _PBS_PPC64LE if key != "AR"} == {
        "CC": "gcc -pthread", "CXX": "g++",
        "LDSHARED": "gcc -pthread" + _LDFLAGS, "LDCXXSHARED": "g++" + _LDFLAGS,
    }
    # A host that has the recorded cross toolchain keeps it.
    cross = _bin_dir(tmp_path / "cross", "powerpc64le-linux-gnu-gcc", "powerpc64le-linux-gnu-g++")
    installed = {key: value.replace("/usr/bin/", cross + "/") for key, value in _PBS_PPC64LE.items()}
    _pinned_recording(tmp_path, monkeypatch, installed, "cross-python")
    kept = managed_environment(tmp_path / "kept", env={"PATH": native}, cache=tmp_path).env
    assert not {"CC", "CXX", "LDSHARED", "LDCXXSHARED"} & kept.keys()
