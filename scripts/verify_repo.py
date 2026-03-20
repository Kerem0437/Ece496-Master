#!/usr/bin/env python3
"""
ECE496 Repo Verifier / Doctor

Purpose:
- Quick checks to prevent demo-day surprises.
- Validates structure, Python syntax, optional training smoke test, and prints exact next steps.

Usage:
  python scripts/verify_repo.py
  python scripts/verify_repo.py --full   # heavier checks (optional)
  python scripts/verify_repo.py --full --run-build  # runs `npm run build` (requires Node + npm)

This script does NOT need internet access.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


REPO = Path(__file__).resolve().parents[1]
DASH = REPO / "dashboard"
MLS = REPO / "ml_service"
DEMO = REPO / "demo"


def run(cmd: List[str], cwd: Path | None = None, timeout: int = 120) -> Tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            shell=False,
        )
        return p.returncode, p.stdout
    except Exception as e:
        return 999, f"ERROR running {cmd}: {e}"


def header(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def ok(msg: str):
    print(f"[OK] {msg}")


def warn(msg: str):
    print(f"[WARN] {msg}")


def fail(msg: str):
    print(f"[FAIL] {msg}")


def check_exists(path: Path, why: str) -> bool:
    if path.exists():
        ok(f"Found {path.relative_to(REPO)} ({why})")
        return True
    fail(f"Missing {path.relative_to(REPO)} ({why})")
    return False


def list_large_files(root: Path, mb: int = 50):
    big = []
    for p in root.rglob("*"):
        if p.is_file():
            sz = p.stat().st_size
            if sz >= mb * 1024 * 1024:
                big.append((p, sz))
    big.sort(key=lambda x: -x[1])
    if big:
        warn(f"Large files (>{mb}MB) detected (may break uploads):")
        for p, sz in big[:20]:
            print(f"  - {p.relative_to(REPO)} : {sz/1024/1024:.1f} MB")
    else:
        ok(f"No files > {mb}MB")


def python_compileall() -> bool:
    header("Python syntax check (compileall)")
    code, out = run([sys.executable, "-m", "compileall", "-q", str(REPO)], timeout=180)
    if code == 0:
        ok("All Python files compiled successfully")
        return True
    fail("Python compileall failed")
    print(out)
    return False


def python_smoke_train() -> bool:
    header("ML training smoke test (fast)")
    cmd = [
        sys.executable,
        "train.py",
        "--data-dir",
        "../demo/data",
        "--epochs",
        "1",
        "--seq-len",
        "30",
        "--stride",
        "30",
        "--max-windows",
        "120",
    ]
    code, out = run(cmd, cwd=MLS, timeout=240)
    if code == 0:
        ok("Train smoke test succeeded (artifacts written)")
        return True
    fail("Train smoke test failed")
    print(out)
    return False


def python_smoke_service() -> bool:
    header("ML service import check")
    code, out = run([sys.executable, "-c", "import server; print('import ok')"], cwd=MLS, timeout=30)
    if code == 0:
        ok("ml_service/server.py imports successfully")
        return True
    fail("ml_service/server.py import failed")
    print(out)
    return False


def node_info():
    header("Node / npm info (informational)")
    for cmd in (["node", "--version"], ["npm", "--version"]):
        if shutil.which(cmd[0]) is None:
            warn(f"{cmd[0]} not found in PATH")
            continue
        code, out = run(cmd, timeout=30)
        print(out.strip())


def next_build(run_build: bool) -> bool:
    header("Dashboard build check (optional)")
    if not run_build:
        warn("Skipped `npm run build` (pass --run-build to execute).")
        print("If you want to run it yourself:")
        print("  cd dashboard")
        print("  npm install")
        print("  npm run build")
        return True

    if shutil.which("npm") is None:
        fail("npm not found. Install Node.js first.")
        return False

    if not (DASH / "node_modules").exists():
        warn("dashboard/node_modules not found -> running `npm install` first")
        code, out = run(["npm", "install"], cwd=DASH, timeout=600)
        if code != 0:
            fail("npm install failed")
            print(out)
            return False
        ok("npm install ok")

    code, out = run(["npm", "run", "build"], cwd=DASH, timeout=600)
    if code == 0:
        ok("Next.js build succeeded")
        return True

    fail("Next.js build failed")
    print(out)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="Run heavier checks (smoke training).")
    ap.add_argument("--run-build", action="store_true", help="Run `npm run build` in dashboard (requires Node).")
    args = ap.parse_args()

    header("System info")
    print(f"Platform: {platform.platform()}")
    print(f"Python: {sys.version.split()[0]}  ({sys.executable})")

    header("Repo structure checks")
    ok("Repo root: " + str(REPO))

    good = True
    good &= check_exists(REPO / "MASTER_RUNBOOK.md", "master documentation")
    good &= check_exists(DASH / "package.json", "Next.js dashboard")
    good &= check_exists(MLS / "train.py", "ML training script")
    good &= check_exists(MLS / "server.py", "ML service")
    good &= check_exists(DEMO / "data", "training data folder")
    good &= check_exists(DASH / "demo-json" / "experiments.json", "demo experiments index")
    good &= check_exists(DASH / ".env.example", "dashboard env template")

    list_large_files(REPO, mb=50)

    good &= python_compileall()

    if args.full:
        good &= python_smoke_service()
        good &= python_smoke_train()

    node_info()
    good &= next_build(args.run_build)

    header("Result")
    if good:
        ok("All requested checks passed ✅")
        print("Next steps: follow MASTER_RUNBOOK.md for demo/live execution.")
        sys.exit(0)
    else:
        fail("One or more checks failed ❌")
        print("Fix the errors above, then re-run: python scripts/verify_repo.py --full")
        sys.exit(1)


if __name__ == "__main__":
    main()
