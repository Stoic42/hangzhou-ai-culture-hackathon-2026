#!/usr/bin/env python3
"""Host test runner for device/t5/src/buddy_engine.c.

Tries to compile and run device/t5/tests/test_buddy_engine.c with an
available host C compiler. Falls back to an ARM cross-compile syntax check
using the TuyaOpen SDK toolchain when no host compiler is available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
T5_SRC = REPO_ROOT / "device" / "t5" / "src"
T5_TESTS = REPO_ROOT / "device" / "t5" / "tests"
CJSON_DIRS = [
    Path("/f/t5open/src/libcjson/cJSON"),
    Path("F:/t5open/src/libcjson/cJSON"),
]


def find_cjson_dir() -> Path | None:
    for p in CJSON_DIRS:
        if (p / "cJSON.c").exists() and (p / "cJSON.h").exists():
            return p
    return None


def find_compiler() -> tuple[str, Path] | None:
    """Return (kind, path) for an available host C compiler, or None."""
    candidates = ["gcc", "clang", "cl"]
    for name in candidates:
        exe = shutil.which(name)
        if exe:
            return name, Path(exe)
    return None


def compile_with_host_compiler(compiler: Path, cjson_dir: Path, out: Path) -> bool:
    cmd = [
        str(compiler),
        str(T5_TESTS / "test_buddy_engine.c"),
        str(T5_SRC / "buddy_engine.c"),
        str(cjson_dir / "cJSON.c"),
        f"-I{T5_SRC}",
        f"-I{cjson_dir}",
        "-o", str(out),
    ]
    if sys.platform == "win32" and compiler.name.lower() == "cl.exe":
        cmd = [
            str(compiler),
            str(T5_TESTS / "test_buddy_engine.c"),
            str(T5_SRC / "buddy_engine.c"),
            str(cjson_dir / "cJSON.c"),
            f"/I{T5_SRC}",
            f"/I{cjson_dir}",
            f"/Fe{out}",
        ]
    print("Compiling:", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("Compile failed:")
        print(proc.stdout)
        print(proc.stderr)
        return False
    return True


def cross_compile_syntax_check(cjson_dir: Path) -> bool:
    """Use the TuyaOpen ARM GCC to at least verify the C sources compile."""
    arm_gcc_candidates = [
        Path("/f/t5open/platform/tools/gcc-arm-none-eabi-10.3-2021.10/bin/arm-none-eabi-gcc.exe"),
        Path("F:/t5open/platform/tools/gcc-arm-none-eabi-10.3-2021.10/bin/arm-none-eabi-gcc.exe"),
    ]
    arm_gcc = None
    for p in arm_gcc_candidates:
        if p.exists():
            arm_gcc = p
            break
    if arm_gcc is None:
        print("No host compiler and no ARM cross compiler found; cannot verify C sources.")
        return False

    cmd = [
        str(arm_gcc),
        "-c",
        str(T5_SRC / "buddy_engine.c"),
        f"-I{cjson_dir}",
        f"-I{T5_SRC}",
        "-o", str(T5_TESTS / "buddy_engine.o"),
    ]
    print("No host compiler available; running ARM cross-compile syntax check:")
    print(" ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if T5_TESTS.joinpath("buddy_engine.o").exists():
        T5_TESTS.joinpath("buddy_engine.o").unlink()
    if proc.returncode != 0:
        print("Cross-compile failed:")
        print(proc.stdout)
        print(proc.stderr)
        return False
    print("ARM cross-compile syntax check passed (warnings are expected).")
    return True


def main() -> int:
    cjson_dir = find_cjson_dir()
    if cjson_dir is None:
        print("cJSON source not found; expected at /f/t5open/src/libcjson/cJSON")
        return 1

    compiler = find_compiler()
    if compiler is None:
        print("No host C compiler found in PATH.")
        return 0 if cross_compile_syntax_check(cjson_dir) else 1

    out = T5_TESTS / "test_buddy_engine"
    if sys.platform == "win32":
        out = out.with_suffix(".exe")
    if not compile_with_host_compiler(compiler[1], cjson_dir, out):
        return 1

    print("Running:", out)
    proc = subprocess.run([str(out)], capture_output=True, text=True)
    print(proc.stdout)
    print(proc.stderr)
    if out.exists():
        out.unlink()
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
