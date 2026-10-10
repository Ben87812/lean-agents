"""Run the benchmark: each arm works the same tier in its own clone, then is graded and measured.

    python bench/run.py --tier bench/tasks/long --work D:/bench-work --validate
    python bench/run.py --tier bench/tasks/long --work D:/bench-work --cap 40000000 \\
        --arm baseline --arm lean=v1 --arm lean+notes=cut/module-notes

An arm is a name, optionally with a git ref of this repository: the ref is
checked out as a worktree under <work>/plugins and loaded with --plugin-dir.
An arm without a ref runs without the plugin. Every arm is stopped once its
session passes --cap tokens, and graded on what it left.
"""

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import tasks  # noqa: E402
from diagnose import report  # noqa: E402
from transcripts import load_session, project_dir, tokens  # noqa: E402

BLOCKED = ("git push*", "gh *", "curl *", "pip *", "uv *", "npm install*", "go get*")
CLAUDE_FLAGS = ["--model", "opus", "--output-format", "json", "--permission-mode", "acceptEdits",
                "--allowedTools", "Bash", "PowerShell", "Read", "Edit", "Write", "Grep", "Glob", "Agent",
                "--disallowedTools"] + [f"{shell}({cmd})" for shell in ("Bash", "PowerShell") for cmd in BLOCKED] + [
                "WebFetch", "WebSearch"]


def parse_arm(spec):
    name, _, ref = spec.partition("=")
    return dict(name=name, ref=ref or None)


def plugin_checkout(arm, work):
    """The plugin folder for an arm: a detached worktree of its ref, or None for no plugin."""
    if arm.get("plugin") or not arm["ref"]:
        return arm.get("plugin")
    path = os.path.join(work, "plugins", arm["name"].replace("+", "-"))
    if os.path.isdir(path):
        subprocess.run(["git", "-C", path, "checkout", "-q", "--detach", arm["ref"]], check=True, capture_output=True)
    else:
        subprocess.run(["git", "-C", ROOT, "worktree", "add", "-q", "--detach", path, arm["ref"]],
                       check=True, capture_output=True)
    return path


def installed_lean():
    """lean-agents installs enabled in the user's settings. Every arm switches them off, so the baseline
    runs without the plugin and the lean arms run only the version under test."""
    home = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    try:
        with open(os.path.join(home, "settings.json"), encoding="utf-8") as f:
            enabled = json.load(f).get("enabledPlugins") or {}
    except (OSError, ValueError):
        return []
    return [k for k in enabled if k.split("@")[0] == "lean-agents"]


def write_settings(clone, plugin):
    """The clone's project settings: the plugin's snippet for a lean arm, and installed lean-agents off."""
    settings = {}
    if plugin:
        with open(os.path.join(plugin, "skills", "lean-agent-runs", "settings-snippet.json"), encoding="utf-8") as f:
            settings = json.load(f)
    off = installed_lean()
    if off:
        settings.setdefault("enabledPlugins", {}).update({k: False for k in off})
    if settings:
        os.makedirs(os.path.join(clone, ".claude"), exist_ok=True)
        with open(os.path.join(clone, ".claude", "settings.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(settings, f, indent=2)


def kill_tree(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        os.killpg(proc.pid, signal.SIGKILL)


def transcript(clone, sid):
    """The session's main transcript, or None. The folder is named after the clone's path, which may
    be spelled through a symlink (macOS /var is /private/var), so both spellings are tried."""
    for root in (clone, os.path.realpath(clone)):
        path = os.path.join(project_dir(root), sid + ".jsonl")
        if os.path.exists(path):
            return path
    return None


def session_tokens(clone, sid):
    main = transcript(clone, sid)
    if not main:
        return 0
    return sum(tokens(a["calls"]) for a in load_session(os.path.dirname(main), main)[2])


def run_arm(tier, arm, work, cap, claude, prompt, max_hours=6, poll=60):
    # Each arm gets its own folder: agents that write next to the clone (../) never share files.
    folder = os.path.join(work, tier["name"], arm["name"])
    clone = os.path.join(folder, "repo")
    res = dict(arm=arm["name"], ref=arm["ref"], cap=cap)
    try:
        plugin = plugin_checkout(arm, work)
        before = tasks.prepare(tier, clone)
        with open(os.path.join(folder, "tasks.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(tasks.tasks_md(tier))
    except Exception as e:  # a failed setup stops this arm only
        res["error"] = f"setup failed: {e}"
        return res
    write_settings(clone, plugin)
    sid = str(uuid.uuid4())
    cmd = claude + ["-p", prompt, "--session-id", sid] + CLAUDE_FLAGS + (["--plugin-dir", plugin] if plugin else [])
    start, stopped, out = time.time(), None, []
    with open(os.path.join(folder, "stderr.txt"), "w", encoding="utf-8") as err:
        proc = subprocess.Popen(cmd, cwd=clone, stdout=subprocess.PIPE, stderr=err, text=True, encoding="utf-8",
                                errors="replace", start_new_session=os.name != "nt")
        reader = threading.Thread(target=lambda: out.append(proc.stdout.read()), daemon=True)
        reader.start()
        while proc.poll() is None:
            time.sleep(poll)
            if session_tokens(clone, sid) > cap:
                stopped = "cap"
            elif time.time() - start > max_hours * 3600:
                stopped = "time limit"
            if stopped:
                kill_tree(proc)
                break
        proc.wait()
        reader.join(10)
        proc.stdout.close()
    res.update(session=sid, wall_s=round(time.time() - start), stopped=stopped, exit=proc.returncode)
    try:
        res["usd"] = json.loads("".join(out) or "{}").get("total_cost_usd")
    except ValueError:
        res["usd"] = None
    try:  # anything after the run fails for this arm only, and the other arms' results are still written
        res["grade"] = tasks.grade(tier, clone, before)
        main = transcript(clone, sid)
        if main:
            res["measure"] = report(os.path.dirname(main), main)
        else:
            res["measure"] = None
            res["error"] = f"no transcript for session {sid} in {project_dir(clone)}; compare with the folders under it"
    except BaseException as e:  # stats() ends with SystemExit when a session made no model calls
        res.setdefault("measure", None)
        res["error"] = f"after the run: {e}"
    return res


def summarize(res, n_tasks):
    m, g = res.get("measure"), res.get("grade") or {}
    passed = sum(1 for t in g.get("tasks", []) if t["hidden"] == "pass")
    if m:
        res["figures"] = dict(
            tokens=m["tokens"], cost=m["cost"], usd=res.get("usd"), passed=passed, of=n_tasks,
            tokens_per_pass=m["tokens"] / passed if passed else None, wall_min=res["wall_s"] / 60,
            min_per_task=res["wall_s"] / 60 / n_tasks, above_100k=m["above"], peak=m["peak"],
            lead_peak=m["lead_peak"], startup=m["startup"], rebuys=m["rewrites"],
            new_failures=g.get("new_failures"), stopped=res.get("stopped"))
    return res


def run(tier, arms, work, cap, claude, max_hours=6, poll=60):
    with open(os.path.join(HERE, "prompt.txt"), encoding="utf-8") as f:
        prompt = f.read().strip()
    tdir = os.path.join(work, tier["name"])
    os.makedirs(tdir, exist_ok=True)
    with cf.ThreadPoolExecutor(len(arms)) as ex:
        futures = [ex.submit(run_arm, tier, a, work, cap, claude, prompt, max_hours, poll) for a in arms]
        done = [summarize(f.result(), len(tier["tasks"])) for f in futures]
    results = dict(tier=tier["name"], date=time.strftime("%Y-%m-%d"), cap=cap, runs_per_arm=1,
                   tasks=[t["name"] for t in tier["tasks"]], arms=done)
    with open(os.path.join(tdir, "results.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(results, f, indent=1)
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", required=True, help="tier folder, for example bench/tasks/long")
    ap.add_argument("--work", required=True, help="folder for clones and results (outside this repository)")
    ap.add_argument("--arm", action="append", default=[], help="name or name=git-ref; repeat for each arm")
    ap.add_argument("--cap", type=float, help="token ceiling per arm")
    ap.add_argument("--max-hours", type=float, default=6, help="time limit per arm (default 6)")
    ap.add_argument("--poll", type=float, default=60, help="seconds between spend checks (default 60)")
    ap.add_argument("--validate", action="store_true", help="check the tier is gradeable, then stop")
    args = ap.parse_args()
    tier = tasks.load_tier(args.tier)
    work = os.path.abspath(args.work)
    os.makedirs(work, exist_ok=True)
    if args.validate:
        problems = tasks.validate(tier, work)
        print("\n".join(problems) or f"{tier['name']}: every task is gradeable")
        sys.exit(1 if problems else 0)
    if not args.arm or not args.cap:
        ap.error("a run needs --arm (one or more) and --cap")
    res = run(tier, [parse_arm(a) for a in args.arm], work, args.cap, [shutil.which("claude") or "claude"],
              args.max_hours, args.poll)
    for a in res["arms"]:
        f = a.get("figures") or {}
        print(f"{a['arm']:12} {a.get('error') or ''}{f.get('tokens', 0) / 1e6:8.1f}M tokens  "
              f"{f.get('passed', 0)}/{f.get('of', 0)} passed  stopped: {a.get('stopped')}")
    print(os.path.join(work, tier["name"], "results.json"))


if __name__ == "__main__":
    main()
