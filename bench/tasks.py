"""Benchmark tiers: load them, set up a clone, and grade it with the hidden tests.

A tier is a folder with tier.json (repo, base commit, setup, suite) and one
JSON file per task (issue, fix commit, hidden tests). Every task in a tier
starts from the same base commit, because one session works them all.
"""

import glob
import json
import os
import re
import shutil
import subprocess

TIER_FIELDS = ("repo", "base_commit", "setup", "suite_cmd", "failure_regex")
TASK_FIELDS = ("name", "issue", "fix_ref", "hidden_tests", "hidden_test_cmd")
EXCLUDE = ".venv/\nnode_modules/\n.claude/\n"


def _load(path, fields):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    missing = [k for k in fields if k not in d]
    if missing:
        raise ValueError(f"{path}: missing {', '.join(missing)}")
    return d


def load_tier(folder):
    tier = _load(os.path.join(folder, "tier.json"), TIER_FIELDS)
    re.compile(tier["failure_regex"])
    tier["name"] = os.path.basename(os.path.normpath(folder))
    tier.setdefault("notes", "")
    paths = sorted(p for p in glob.glob(os.path.join(folder, "*.json")) if os.path.basename(p) != "tier.json")
    tier["tasks"] = [_load(p, TASK_FIELDS) for p in paths]
    if not tier["tasks"]:
        raise ValueError(f"{folder}: no task files")
    return tier


def tasks_md(tier):
    parts = [f"# Tasks: {len(tier['tasks'])} for this repository", ""]
    for t in tier["tasks"]:
        parts += [f"## {t['name']}", "", t["issue"].strip(), ""]
    if tier["notes"].strip():
        parts += ["## Notes for every task", "", tier["notes"].strip(), ""]
    return "\n".join(parts)


def sh(cmd, cwd, timeout):
    """Run a shell command; return (exit code, output). A timeout gives exit code None."""
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"


def failing(tier, clone, timeout=1800):
    """The ids of failing tests in the full suite, or None if the suite could not run."""
    code, out = sh(tier["suite_cmd"], clone, timeout)
    ids = set(re.findall(tier["failure_regex"], out, re.M))
    if code is None or (code != 0 and not ids):
        return None
    return ids


def prepare(tier, clone, timeout=1800):
    """Clone at the base commit, set up, and return the tests already failing there."""
    if os.path.exists(clone):
        raise RuntimeError(f"{clone} already exists; remove it or choose another --work folder")
    os.makedirs(os.path.dirname(clone), exist_ok=True)
    steps = [f'git clone -q -c core.longpaths=true "{tier["repo"]}" "{clone}"', f"git -C \"{clone}\" checkout -q {tier['base_commit']}"]
    for step in steps:
        code, out = sh(step, os.path.dirname(clone), 900)
        if code != 0:
            raise RuntimeError(f"{step}: {out[-400:]}")
    _forget_the_future(clone)
    with open(os.path.join(clone, ".git", "info", "exclude"), "a", encoding="utf-8", newline="\n") as f:
        f.write(EXCLUDE)
    for step in tier["setup"]:
        code, out = sh(step, clone, timeout)
        if code != 0:
            raise RuntimeError(f"setup step {step!r} failed: {out[-400:]}")
    before = failing(tier, clone, timeout)
    if before is None:
        raise RuntimeError(f"the suite could not run at the base commit: {tier['suite_cmd']}")
    return before


def _git(clone, *args):
    return subprocess.run(["git", *args], cwd=clone, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _forget_the_future(clone):
    """Leave only the base commit's history: no remote, no other branches or tags, no reflog.
    A full clone holds the real fix, and an agent working in a fresh worktree of main would see it."""
    steps = [["checkout", "-q", "-B", "main", "HEAD"], ["remote", "remove", "origin"]]
    for step in steps:
        out = _git(clone, *step)
        if out.returncode != 0:
            raise RuntimeError(f"git {' '.join(step)}: {out.stderr[-300:]}")
    refs = _git(clone, "for-each-ref", "--format=%(refname)").stdout.split()
    for ref in refs:
        if ref != "refs/heads/main":
            _git(clone, "update-ref", "-d", ref)
    for step in (["reflog", "expire", "--expire=now", "--all"], ["gc", "-q", "--prune=now"]):
        out = _git(clone, *step)
        if out.returncode != 0:
            raise RuntimeError(f"git {' '.join(step)}: {out.stderr[-300:]}")


def _agent_test_files(tier, clone, hidden):
    """Test files the agents added since the base commit, other than the hidden ones."""
    added = _git(clone, "diff", "--name-only", "--diff-filter=A", tier["base_commit"], "HEAD").stdout.split()
    added += _git(clone, "ls-files", "--others", "--exclude-standard").stdout.split()
    return sorted({p for p in added if "test" in os.path.basename(p).lower() and p not in hidden})


def _run_hidden(t, clone, timeout):
    code, msg = sh(t["hidden_test_cmd"], clone, timeout)
    return ("pass" if code == 0 else ("error" if code is None else "fail")), ("" if code == 0 else msg[-500:])


def grade(tier, clone, before, timeout=1800):
    """Compare the suite with the base, then run each task's hidden tests and put the files back.

    "hidden" is the grade. When it is not a pass, "hidden_alone" repeats the run with the agents' own new
    test files set aside, to tell a broken build caused by a clash between test files from broken code."""
    after = failing(tier, clone, timeout)
    out = dict(new_failures=None if after is None else sorted(after - before), tasks=[])
    for t in tier["tasks"]:
        r = dict(task=t["name"])
        hidden = t["hidden_tests"]
        existed = [p for p in hidden if _git(clone, "cat-file", "-e", f"HEAD:{p}").returncode == 0]
        fetched = _git(clone, "fetch", "-q", tier["repo"], t["fix_ref"])
        paths = " ".join(f'"{p}"' for p in hidden)
        code, msg = sh(f"git checkout {t['fix_ref']} -- {paths}", clone, 120)
        if fetched.returncode != 0 or code != 0:
            r.update(hidden="error", detail=(fetched.stderr + msg)[-500:])
        else:
            r["hidden"], r["detail"] = _run_hidden(t, clone, timeout)
            if r["hidden"] != "pass":
                aside = _agent_test_files(tier, clone, hidden)
                if aside:
                    store = clone + ".aside"
                    for p in aside:
                        os.makedirs(os.path.dirname(os.path.join(store, p)), exist_ok=True)
                        os.replace(os.path.join(clone, p), os.path.join(store, p))
                    try:
                        r["hidden_alone"], _ = _run_hidden(t, clone, timeout)
                    finally:
                        for p in aside:
                            os.replace(os.path.join(store, p), os.path.join(clone, p))
                        shutil.rmtree(store, ignore_errors=True)
                    r["set_aside"] = aside
        _git(clone, "reset", "-q", "--", *hidden)
        for p in hidden:
            if p in existed:
                _git(clone, "checkout", "HEAD", "--", p)
            elif os.path.exists(os.path.join(clone, p)):
                os.remove(os.path.join(clone, p))
        out["tasks"].append(r)
    return out


def validate(tier, workdir, timeout=1800):
    """Every task's hidden tests must fail at the base and pass once the real fixes are applied."""
    problems = []
    clone = os.path.join(workdir, "validate-" + tier["name"])
    before = prepare(tier, clone, timeout)
    for t, r in zip(tier["tasks"], grade(tier, clone, before, timeout)["tasks"]):
        if r["hidden"] != "fail":
            problems.append(f"{t['name']}: hidden tests {r['hidden']} at the base commit; expected fail")
    sh("git reset -q --hard && git clean -qfd", clone, 120)
    for t in tier["tasks"]:
        patch = os.path.join(workdir, f"gold-{t['name']}.patch")
        excludes = " ".join(f'":(exclude){p}"' for p in t["hidden_tests"])
        code, msg = sh(f'git diff {t["fix_ref"]}~1 {t["fix_ref"]} -- . {excludes} > "{patch}"', clone, 120)
        if code == 0:
            code, msg = sh(f'git apply "{patch}"', clone, 120)
        if code != 0:
            problems.append(f"{t['name']}: the real fix does not apply at the base: {msg[-300:]}")
    g = grade(tier, clone, before, timeout)
    for t, r in zip(tier["tasks"], g["tasks"]):
        if r["hidden"] != "pass":
            problems.append(f"{t['name']}: hidden tests {r['hidden']} with the real fix applied: {r['detail'][-300:]}")
    if g["new_failures"]:
        problems.append(f"the real fixes break other tests: {', '.join(g['new_failures'][:10])}")
    return problems
