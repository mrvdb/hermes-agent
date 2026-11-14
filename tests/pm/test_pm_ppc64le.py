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


def test_pnpm_fetches_the_executable_npm_publishes_for_power():
    """npm names POWER after Node's process.arch: @pnpm/exe.linux-ppc64 is the
    little-endian build; there is no exe.linux-ppc64le."""
    from pm.registry import get_package

    executable, launcher = get_package("pnpm").fetch_urls("12.15.0", TARGET)
    assert executable == "https://registry.npmjs.org/@pnpm/exe.linux-ppc64/-/exe.linux-ppc64-12.15.0.tgz"
    assert launcher == "https://registry.npmjs.org/pnpm/-/pnpm-12.15.0.tgz"


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


def _solve_for(machine: str) -> dict:
    """The [tool.uv] policy a generated workspace gets for an interpreter on linux/*machine*."""
    from pm import workspace

    policy = {"environments": ["python_version >= '3.14'"], "override-dependencies": ["Pillow==13.0.0"]}
    workspace._solve_only_for(policy, {"sys_platform": "linux", "platform_machine": machine})
    return policy


def _dropped(policy: dict, machine: str) -> set[str]:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement

    host = {**default_environment(), "sys_platform": "linux", "platform_machine": machine}
    return {req.name for req in map(Requirement, policy["override-dependencies"])
            if req.marker is not None and not req.marker.evaluate(host)}


def test_ppc64le_workspace_solve_drops_wheel_only_packages_with_no_build_here():
    """uv fails the whole narrowed lock when any extra reaches a wheel-only package with no
    ppc64le build (playwright via google-meet stopped an update), installed or not."""
    policy = _solve_for("ppc64le")
    assert "playwright" in _dropped(policy, "ppc64le")
    assert "Pillow==13.0.0" in policy["override-dependencies"]


def test_other_hosts_keep_every_package_in_the_solve():
    assert _dropped(_solve_for("x86_64"), "x86_64") == set()


def _ppc64le_unbuildable_in_core_lock() -> set[str]:
    """Wheel-only packages core's uv.lock reaches on linux/ppc64le that have no build for it.

    Walks from hermes-agent with every extra, following only edges whose marker can hold on
    that host, and stops at the packages the ppc64le solve already drops.
    """
    import re
    import tomllib
    from pathlib import Path

    from packaging.markers import Marker, default_environment

    from pm import workspace

    text = (Path(__file__).resolve().parents[2] / "uv.lock").read_text(encoding="utf-8")
    lock = tomllib.loads(text)
    host = {**default_environment(), "sys_platform": "linux", "platform_machine": "ppc64le",
            "platform_system": "Linux", "os_name": "posix", "implementation_name": "cpython",
            "platform_python_implementation": "CPython", "python_version": "3.14",
            "python_full_version": "3.14.0"}
    extras = {""} | set(re.findall(r"extra == '([^']*)'", text))

    def holds(marker: str | None) -> bool:
        return marker is None or any(Marker(marker).evaluate({**host, "extra": extra}) for extra in extras)

    entries: dict[str, list[dict]] = {}
    for package in lock["package"]:
        if holds(" or ".join(f"({m})" for m in package.get("resolution-markers", [])) or None):
            entries.setdefault(package["name"], []).append(package)
    dropped = set(workspace._NO_BUILD_FOR_HOST[("linux", "ppc64le")])
    seen, todo, unbuildable = set(), [("hermes-agent", None, tuple(entries["hermes-agent"][0].get(
        "optional-dependencies", {})))], set()
    while todo:
        name, version, wanted = todo.pop()
        if name in dropped:
            continue
        for package in entries.get(name, []):
            if version is not None and package["version"] != version:
                continue
            key = (name, package["version"], wanted)
            if key in seen:
                continue
            seen.add(key)
            tags = [wheel["url"].rsplit("-", 1)[1] for wheel in package.get("wheels", [])]
            if ("registry" in package["source"] and "sdist" not in package
                    and not any(tag == "any.whl" or "ppc64le" in tag for tag in tags)):
                unbuildable.add(name)
            edges = [*package.get("dependencies", [])]
            for extra in wanted:
                edges += package.get("optional-dependencies", {}).get(extra, [])
            todo += [(edge["name"], edge.get("version"), tuple(edge.get("extra", ())))
                     for edge in edges if holds(edge.get("marker"))]
    return unbuildable


def test_ppc64le_solve_drops_every_wheel_only_package_core_pins_without_a_build_here():
    """A plugin generation is moved onto core's pins (`uv lock -P`), so a core pin that is
    wheel-only with no ppc64le build fails the narrowed lock even where the previous
    generation held an older, buildable version (espeakng-loader 0.2.4 via [kittentts])."""
    assert _ppc64le_unbuildable_in_core_lock() == set()
