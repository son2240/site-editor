"""Review and deploy a static site that lives in a git repository (GitHub Pages).

    python deploy.py --site ../my-site          # show the diff, ask y/N, deploy

Flow: diff -> secret scan -> explicit confirmation -> commit -> push -> wait for the
Pages build of exactly that commit -> fetch the changed files from the live site and
compare them byte for byte with the commit.

The confirmation is bound to the reviewed change: `review()` returns a `change_id`
(a hash of the diff and of every changed file), and `deploy()` refuses to run if the
working tree no longer matches it. What you approved is what gets published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SECRET_PATTERNS = [
    ("slack token", re.compile(rb"xox[abposr]-[A-Za-z0-9-]{10,}")),
    ("github token", re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}")),
    ("openai/anthropic key", re.compile(rb"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("aws key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("google key", re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("private key", re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
BLOCKED_NAMES = re.compile(r"(^|/)(\.env(\..*)?|.*\.(pem|key|p12|pfx)|id_rsa.*|credentials.*\.json)$", re.I)
MAX_DIFF_CHARS = 200_000


class DeployError(RuntimeError):
    pass


def git(site: Path, *args: str, check: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(site), *args], capture_output=True, text=True, encoding="utf-8")
    if check and p.returncode != 0:
        raise DeployError(f"git {' '.join(args)}: {p.stderr.strip() or p.stdout.strip()}")
    return p.stdout


def repo_info(site: Path) -> dict:
    url = git(site, "remote", "get-url", "origin").strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    branch = git(site, "rev-parse", "--abbrev-ref", "HEAD").strip()
    info = {"remote": re.sub(r"//[^@/]+@", "//", url), "branch": branch, "owner": None, "repo": None, "site_url": None}
    if m:
        owner, repo = m.group(1), m.group(2)
        info.update(owner=owner, repo=repo)
        info["site_url"] = f"https://{repo}/" if repo.lower() == f"{owner.lower()}.github.io" \
            else f"https://{owner.lower()}.github.io/{repo}/"
    return info


def upstream(site: Path) -> str | None:
    """The remote-tracking branch (what is published), or None if there is none yet."""
    p = subprocess.run(["git", "-C", str(site), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                       capture_output=True, text=True)
    if p.returncode == 0 and p.stdout.strip():
        return p.stdout.strip()
    branch = git(site, "rev-parse", "--abbrev-ref", "HEAD").strip()
    ref = f"origin/{branch}"  # pushed without -u: fall back to the remote-tracking ref
    q = subprocess.run(["git", "-C", str(site), "rev-parse", "--verify", "--quiet", f"refs/remotes/{ref}"], capture_output=True)
    return ref if q.returncode == 0 else None


def changed_files(site: Path, base: str | None = None) -> list[dict]:
    """[{path, status}]: everything that differs from `base` (the published branch), i.e.
    unpushed commits plus working-tree changes, plus untracked files (respecting .gitignore)."""
    out: dict[str, str] = {}
    if base:
        for line in git(site, "diff", "--name-status", "--no-renames", base, "--", ".").splitlines():
            code, _, path = line.partition("\t")
            out[path] = {"A": "added", "D": "deleted"}.get(code[:1], "modified")
    for line in git(site, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames").split("\0"):
        if not line:
            continue
        code, path = line[:2], line[3:]
        if base and path not in out and code != "??":
            continue  # same as published (e.g. reverted after an unpushed commit)
        out[path] = "added" if code == "??" or "A" in code else "deleted" if "D" in code else out.get(path, "modified")
    return [{"path": k, "status": v} for k, v in sorted(out.items())]


def review(site: Path) -> dict:
    """Everything a human needs to approve a deploy, plus the id that binds the approval."""
    site = Path(site).resolve()
    base = upstream(site)
    files = changed_files(site, base)
    diff = git(site, "diff", base or "HEAD", "--no-color", "--", ".")
    ahead = git(site, "log", "--oneline", f"{base}..HEAD").splitlines() if base else []
    h = hashlib.sha256(diff.encode("utf-8"))
    for f in files:
        p = site / f["path"]
        h.update(f["path"].encode("utf-8") + b"\0" + f["status"].encode())
        if p.is_file():
            h.update(hashlib.sha256(p.read_bytes()).digest())
            if f["status"] == "added":
                diff += f"\n+++ new file: {f['path']} ({p.stat().st_size} bytes)\n"
                if p.stat().st_size < 20_000 and _is_text(p):
                    diff += "".join("+" + ln for ln in p.read_text(encoding="utf-8", errors="replace").splitlines(True))
    findings = scan(site, files)
    return {"files": files, "diff": diff[:MAX_DIFF_CHARS], "diff_truncated": len(diff) > MAX_DIFF_CHARS,
            "change_id": h.hexdigest()[:16], "secrets": findings, "repo": repo_info(site),
            "head": git(site, "rev-parse", "--short", base or "HEAD").strip(), "unpushed_commits": ahead}


def _is_text(p: Path) -> bool:
    return b"\0" not in p.read_bytes()[:4096]


def scan(site: Path, files: list[dict]) -> list[dict]:
    """Secret-looking content or file names in the change. Values are never returned."""
    out = []
    for f in files:
        if f["status"] == "deleted":
            continue
        if BLOCKED_NAMES.search(f["path"]):
            out.append({"path": f["path"], "kind": "blocked file name"})
            continue
        p = site / f["path"]
        if not p.is_file():
            continue
        data = p.read_bytes()
        for kind, rx in SECRET_PATTERNS:
            n = len(rx.findall(data))
            if n:
                out.append({"path": f["path"], "kind": kind, "count": n})
    return out


def deploy(site: Path, message: str, change_id: str, log=print, wait_sec: int = 300) -> dict:
    site = Path(site).resolve()
    r = review(site)
    if not r["files"]:
        raise DeployError("nothing to deploy")
    if r["change_id"] != change_id:
        raise DeployError("the files changed after you reviewed them; review the diff again")
    if r["secrets"]:
        raise DeployError("secret-looking content found: " + ", ".join(f"{s['path']} ({s['kind']})" for s in r["secrets"]))
    message = (message or "").strip() or "Update site"
    git(site, "add", "-A", "--", ".")
    if git(site, "diff", "--cached", "--name-only").strip():
        log(f"commit: {message}")
        git(site, "commit", "-q", "-m", message)
    else:
        log("no new edits: pushing the commits that were not published yet")
    sha = git(site, "rev-parse", "HEAD").strip()
    log(f"push {sha[:7]} to {r['repo']['remote']} ({r['repo']['branch']})")
    try:
        git(site, "push", "origin", r["repo"]["branch"])
    except DeployError:
        log("push failed: the commit is kept locally. Fix the problem and deploy again (it will push it).")
        raise
    result = {"ok": True, "commit": sha, "site_url": r["repo"]["site_url"], "pages_build": None, "verified": []}
    info = r["repo"]
    if info["owner"] and shutil.which("gh"):
        result["pages_build"] = wait_for_pages(info["owner"], info["repo"], sha, log, wait_sec)
    if info["site_url"]:
        servable = [f["path"] for f in r["files"] if f["status"] != "deleted"][:8]
        result["verified"] = verify_live(site, info["site_url"], sha, servable, log, wait_sec)
        result["ok"] = all(v["match"] for v in result["verified"]) and result["pages_build"] in (None, "built")
    log("done" if result["ok"] else "pushed, but the live site does not match yet (see details)")
    return result


def wait_for_pages(owner: str, repo: str, sha: str, log, wait_sec: int) -> str:
    deadline, last = time.time() + wait_sec, None
    while time.time() < deadline:
        p = subprocess.run(["gh", "api", f"repos/{owner}/{repo}/pages/builds/latest"],
                           capture_output=True, text=True, encoding="utf-8")
        if p.returncode == 0:
            b = json.loads(p.stdout)
            status = b.get("status")
            if b.get("commit") == sha and status in ("built", "errored"):
                log(f"pages build: {status}")
                return status
            if status != last:
                log(f"pages build: {status or 'waiting'}")
                last = status
        time.sleep(5)
    log("pages build: timed out")
    return "timeout"


def verify_live(site: Path, site_url: str, sha: str, paths: list[str], log, wait_sec: int) -> list[dict]:
    """Fetch each changed file from the live site until it matches the committed bytes."""
    results = []
    deadline = time.time() + wait_sec
    for path in paths:
        want = subprocess.run(["git", "-C", str(site), "show", f"{sha}:{path}"], capture_output=True).stdout
        url = site_url + path.lstrip("/")
        match = False
        while time.time() < deadline:
            try:
                req = urllib.request.Request(f"{url}?v={sha[:7]}{int(time.time())}", headers={"Cache-Control": "no-cache"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    match = resp.read() == want
            except OSError:
                match = False
            if match:
                break
            time.sleep(5)
        log(f"live {'OK ' if match else 'DIFF'} {path}")
        results.append({"path": path, "url": url, "match": match})
    return results


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Review and deploy a git-hosted static site")
    ap.add_argument("--site", required=True, help="path to the site repository")
    ap.add_argument("-m", "--message", default="")
    a = ap.parse_args(argv)
    site = Path(a.site).resolve()
    r = review(site)
    if not r["files"]:
        print("No changes to deploy.")
        return 0
    print(f"Site: {r['repo']['site_url'] or r['repo']['remote']}   branch: {r['repo']['branch']}   published: {r['head']}")
    for c in r["unpushed_commits"]:
        print(f"  not yet published: {c}")
    print("Changed files:")
    for f in r["files"]:
        print(f"  {f['status']:<9} {f['path']}")
    print("\n" + r["diff"])
    if r["secrets"]:
        print("\nBLOCKED: secret-looking content:")
        for s in r["secrets"]:
            print(f"  {s['path']}: {s['kind']}")
        return 2
    msg = a.message or input("\nCommit message [Update site]: ").strip()
    if input(f"Publish these {len(r['files'])} file(s) to {r['repo']['site_url']}? [y/N] ").strip().lower() != "y":
        print("Cancelled. Nothing was committed or pushed.")
        return 1
    res = deploy(site, msg, r["change_id"])
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["ok"] else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DeployError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
