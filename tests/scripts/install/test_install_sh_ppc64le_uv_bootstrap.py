"""install.sh maps a glibc POWER host to the linux-ppc64le uv pin."""

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.platforms("linux")

ROOT = Path(__file__).resolve().parents[3]

_SCRIPT = r"""
source "$1" --manifest >/dev/null
uname() { case "$1" in -m) echo ppc64le ;; -s) echo Linux ;; esac; }
head() { printf '\177ELF\0\0\0/lib64/%s\0' "$LOADER"; }
target="$(uv_bootstrap_target)" || { echo refused; exit 0; }
uv_bootstrap_pin "$target"
printf '%s\n%s\n%s\n' "$target" "$UV_PIN_URL" "$UV_PIN_SHA256"
"""


def _bootstrap(loader: str) -> list[str]:
    result = subprocess.run(
        ["bash", "-c", _SCRIPT, "_", str(ROOT / "scripts" / "install.sh")],
        env={**os.environ, "LOADER": loader},
        check=True, capture_output=True, text=True,
    )
    return result.stdout.splitlines()


def test_glibc_ppc64le_selects_the_pinned_ppc64le_uv():
    row = json.loads((ROOT / "pm" / "lock.json").read_text(encoding="utf-8-sig"))["packages"]["uv"]["artifacts"]["linux-ppc64le"]
    assert _bootstrap("ld64.so.2") == ["linux-ppc64le", row["url"], row["sha256"]]


def test_musl_ppc64le_is_refused_not_given_the_glibc_uv():
    assert _bootstrap("ld-musl-powerpc64le.so.1") == ["refused"]
