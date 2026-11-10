"""codex_wrap.py - run the coder CLI for NightCoder and make sure its work is committed.

NightCoder fails a spec with NO_COMMIT when the coder edited files but did not commit (new Codex
sandboxes can block writes to .git, or the coder simply forgets). This wrapper:
  1. records HEAD, runs the real command unchanged (stdin/stdout/stderr pass straight through,
     so NightCoder still sees everything, including any purchase text it must react to),
  2. if HEAD did not move but the tree changed, commits those changes itself,
  3. appends one line per run to a log, and exits with the coder's own exit code.
NightCoder's gates (scope, diff guard, test re-run, rollback) still judge the commit.

    python codex_wrap.py --repo C:/work/rra-codex --log C:/Users/x/nc2/wrap.log -- codex exec --sandbox workspace-write -
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import subprocess
import sys


def git(repo: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def head(repo: str) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv:
        print("usage: codex_wrap.py --repo DIR --log FILE -- <coder command ...>", file=sys.stderr)
        return 2
    cut = argv.index("--")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--log", required=True)
    a = ap.parse_args(argv[:cut])
    cmd = argv[cut + 1:]
    if not cmd:
        print("codex_wrap: no coder command given", file=sys.stderr)
        return 2
    exe = shutil.which(cmd[0]) or cmd[0]          # resolves codex.cmd / codex.ps1 shims on Windows
    before = head(a.repo)
    try:
        rc = subprocess.run([exe, *cmd[1:]], cwd=a.repo).returncode
    except FileNotFoundError:
        print(f"codex_wrap: coder not found: {cmd[0]}", file=sys.stderr)
        rc = 127
    after = head(a.repo)
    dirty = git(a.repo, "status", "--porcelain").stdout.strip()
    action = "coder-committed" if after != before else ("nothing-changed" if not dirty else "")
    if not action:
        git(a.repo, "add", "-A")
        c = git(a.repo, "-c", "user.name=NightCoder wrap", "-c", "user.email=nightcoder-wrap@localhost",
                "commit", "-m", "chore: commit coder changes (coder left them uncommitted)")
        action = "wrapper-committed" if c.returncode == 0 else f"wrapper-commit-failed: {c.stderr.strip()[:200]}"
        print(f"codex_wrap: {action}", file=sys.stderr)
    stamp = _dt.datetime.now().isoformat(timespec="seconds")
    with open(a.log, "a", encoding="utf-8") as f:
        f.write(f"{stamp}\trc={rc}\t{action}\t{before[:8]}->{head(a.repo)[:8]}\t{' '.join(cmd)}\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
