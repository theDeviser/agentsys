"""agentsys command-line interface."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from . import __version__, budget, gitops, verify
from .adapters import ADAPTERS
from .store import Store, TransitionError

STATE_ORDER = ("in_progress", "submitted", "verified", "changes_requested", "ready", "blocked", "escalated",
               "accepted", "merged", "cancelled")


def die(msg, code=1):
    print(f"agentsys: {msg}", file=sys.stderr)
    sys.exit(code)


def actor_of(args):
    a = args.actor or os.environ.get("AGENTSYS_ACTOR")
    if not a:
        die("set an identity with --as <harness>:<account>:<role> or AGENTSYS_ACTOR")
    return a


def open_store(args) -> Store:
    db = args.db or os.environ.get("AGENTSYS_DB")
    if not db:
        try:
            db = gitops.project_root() / ".agent-system" / "state.db"
        except gitops.GitError:
            die("not inside a git repository; pass --db PATH")
    lease = float(os.environ.get("AGENTSYS_LEASE_SECONDS", "1800"))
    st = Store(db, lease_seconds=lease)
    for tid, to in st.reap():
        print(f"(lease expired: {tid} -> {to})", file=sys.stderr)
    return st


def root_of(st: Store) -> Path:
    return st.path.parent.parent


def ago(ts):
    s = int(time.time() - ts)
    return f"{s}s" if s < 120 else f"{s // 60}m" if s < 7200 else f"{s // 3600}h"


# ---------------------------------------------------------------- commands
def cmd_init(args):
    st = open_store(args)
    root = root_of(st)
    gi = root / ".gitignore"
    ignored = gi.exists() and any(l.strip().rstrip("/") == ".agent-system" for l in gi.read_text().splitlines())
    print(f"store: {st.path}")
    if not ignored:
        print("warning: add '.agent-system/' to .gitignore so the store is never committed", file=sys.stderr)


def cmd_task_add(args):
    st = open_store(args)
    base = args.base or gitops.head_sha(root_of(st))
    t = st.add_task(actor_of(args), args.title, kind=args.kind, goal=args.goal or "", acceptance=args.accept or "",
                    allowed_paths=args.path, checks=args.check, deps=args.dep, max_attempts=args.max_attempts,
                    base=base)
    print(t["id"])


def cmd_task_list(args):
    st = open_store(args)
    tasks = st.list(args.state)
    if args.json:
        print(json.dumps(tasks, indent=2))
        return
    for t in sorted(tasks, key=lambda t: (STATE_ORDER.index(t["state"]), t["created_at"])):
        lease = ""
        if t["lease_expires"]:
            lease = f" lease {max(0, int(t['lease_expires'] - time.time()))}s"
        print(f"{t['id']}  {t['state']:<17} {t['kind']:<9} {t['title']}"
              + (f"  [{t['owner']}{lease}]" if t["owner"] else ""))


def cmd_show(args):
    st = open_store(args)
    print(json.dumps({"task": st.get(args.id), "findings": st.findings(args.id),
                      "checkpoints": st.checkpoints(args.id)}, indent=2, default=str))


def cmd_claim(args):
    st = open_store(args)
    actor = actor_of(args)
    t = st.claim(args.id, actor)
    if t["kind"] == "implement" and not args.no_worktree:
        path, branch = gitops.ensure_worktree(root_of(st), t["id"], t["base"])
        st.set_fields(t["id"], actor, "task.worktree", worktree=str(path), branch=branch)
        print(f"claimed {t['id']} (attempt {t['attempts']}); work in: {path}")
    else:
        print(f"claimed {t['id']} (attempt {t['attempts']}); read-only task, work in: {root_of(st)}")


def cmd_simple(action, owner_only=False, extra_key=None):
    def run(args):
        st = open_store(args)
        extra = {extra_key: getattr(args, extra_key)} if extra_key and getattr(args, extra_key, None) else None
        fields = {"owner": None, "lease_expires": None} if action in ("release", "block", "requeue", "unblock") else {}
        t = st.transition(args.id, action, actor_of(args), extra=extra, owner_only=owner_only, **fields)
        print(f"{t['id']} -> {t['state']}")
    return run


def cmd_heartbeat(args):
    st = open_store(args)
    t = st.heartbeat(args.id, actor_of(args))
    print(f"{t['id']} lease until {time.strftime('%H:%M:%S', time.localtime(t['lease_expires']))}")


def cmd_cancel(args):
    st = open_store(args)
    st.cancel(args.id, actor_of(args), args.reason or "")
    print(f"{args.id} -> cancelled")


def cmd_finding(args):
    st = open_store(args)
    fid = st.add_finding(args.id, actor_of(args), args.body, kind=args.kind, evidence=args.evidence,
                         confidence=args.confidence)
    print(f"finding {fid} on {args.id}")


def _checkpoint(st, t, actor, summary, commit):
    sha = None
    if t["worktree"] and Path(t["worktree"]).exists():
        if commit:
            gitops.commit_all(t["worktree"], f"[{t['id']}] {summary}", actor)
        sha = gitops.head_sha(t["worktree"])
    return st.add_checkpoint(t["id"], actor, summary, sha), sha


def cmd_checkpoint(args):
    st = open_store(args)
    t = st.get(args.id)
    cid, sha = _checkpoint(st, t, actor_of(args), args.summary, args.commit)
    print(f"checkpoint {cid} on {t['id']}" + (f" @ {sha[:10]}" if sha else ""))


def cmd_submit(args):
    st = open_store(args)
    actor = actor_of(args)
    t = st.get(args.id)
    if t["owner"] != actor:
        die(f"only the owner ({t['owner']}) can submit {t['id']}")
    _checkpoint(st, t, actor, args.summary, commit=True)
    t = st.transition(t["id"], "submit", actor, {"summary": args.summary}, owner_only=True,
                      lease_expires=None)
    print(f"{t['id']} -> {t['state']}; next: agentsys verify {t['id']}")


def cmd_verify(args):
    st = open_store(args)
    actor = actor_of(args)
    t = st.get(args.id)
    if t["state"] != "submitted":
        die(f"{t['id']} is '{t['state']}'; only submitted tasks are verified")
    results = verify.run_pipeline(t, st.findings(t["id"]))
    ok = verify.passed(results)
    sha = gitops.head_sha(t["worktree"]) if t["worktree"] and Path(t["worktree"]).exists() else None
    for r in results:
        print(f"  [{r['status']:>7}] {r['check']}: {r['detail']}")
    st.event(actor, t["id"], "verify.results", {"ok": ok, "sha": sha, "results": results})
    if ok:
        st.mark_verified(t["id"], sha)
    t = st.transition(t["id"], "verify_pass" if ok else "verify_fail", actor, {"sha": sha})
    print(f"{t['id']} -> {t['state']}" + ("; next: an independent reviewer runs `agentsys review`" if ok else ""))
    if not ok:
        sys.exit(2)


def cmd_review(args):
    st = open_store(args)
    actor = actor_of(args)
    t = st.get(args.id)
    if actor in st.authors(t["id"]):
        die(f"{actor} worked on {t['id']} and cannot review it; use a different agent or a human")
    action = "approve" if args.verdict == "approve" else "reject"
    st.add_finding(t["id"], actor, f"Review {args.verdict}: {args.reason}", kind="decision",
                   evidence=args.evidence)
    t = st.transition(t["id"], action, actor, {"reason": args.reason})
    print(f"{t['id']} -> {t['state']}")


def _target_branch(st, args):
    return args.into or gitops.current_branch(root_of(st))


def cmd_merge_check(args):
    st = open_store(args)
    t = st.get(args.id)
    if not t["branch"]:
        die(f"{t['id']} has no branch")
    target = _target_branch(st, args)
    clean, conflicts = gitops.merge_check(root_of(st), target, t["branch"])
    st.event(actor_of(args), t["id"], "merge.check", {"target": target, "clean": clean, "conflicts": conflicts})
    if clean:
        print(f"{t['branch']} merges cleanly into {target}")
    else:
        st.add_finding(t["id"], actor_of(args), f"Merge conflict with {target}", kind="blocker",
                       evidence=conflicts)
        print(f"CONFLICT merging {t['branch']} into {target}: {conflicts}")
        sys.exit(3)


def cmd_merge(args):
    st = open_store(args)
    actor = actor_of(args)
    t = st.get(args.id)
    root = root_of(st)
    target = _target_branch(st, args)
    if t["state"] != "accepted":
        die(f"{t['id']} is '{t['state']}'; only accepted tasks merge")
    if not st.approval_granted(t["id"], "merge"):
        aid = st.request_approval(t["id"], "merge", actor, f"merge {t['branch']} into {target}")
        print(f"approval {aid} requested. A human must run: agentsys approve {aid} --as human:<name>")
        sys.exit(4)
    if gitops.current_branch(root) != target or not gitops.is_clean(root):
        die(f"main tree must be on '{target}' with no uncommitted changes; agentsys won't touch your work")
    clean, conflicts = gitops.merge_check(root, target, t["branch"])
    if not clean:
        die(f"conflicts: {conflicts}")
    sha = gitops.merge(root, t["branch"], f"Merge {t['branch']}: {t['title']}")
    st.transition(t["id"], "merge", actor, {"target": target, "sha": sha})
    if args.cleanup and t["worktree"]:
        gitops.remove_worktree(root, t["worktree"])
    print(f"{t['id']} merged into {target} @ {sha[:10]}")


def cmd_approvals(args):
    st = open_store(args)
    for a in st.approvals(None if args.all else "pending"):
        print(f"#{a['id']} {a['status']:<8} {a['action']:<8} task={a['task_id']} by={a['requested_by']} {a['reason']}")


def cmd_decide(grant):
    def run(args):
        st = open_store(args)
        st.decide_approval(args.approval_id, actor_of(args), grant)
        print(f"approval {args.approval_id} {'granted' if grant else 'denied'}")
    return run


def cmd_status(args):
    st = open_store(args)
    tasks = st.list()
    counts = {}
    for t in tasks:
        counts[t["state"]] = counts.get(t["state"], 0) + 1
    print("tasks: " + (", ".join(f"{s}={counts[s]}" for s in STATE_ORDER if s in counts) or "none"))
    for t in tasks:
        if t["state"] in ("in_progress", "blocked", "escalated", "changes_requested"):
            print(f"  {t['id']} {t['state']} {t['title']}" + (f" [{t['owner']}]" if t["owner"] else ""))
    pending = st.approvals("pending")
    if pending:
        print(f"pending approvals: {', '.join('#' + str(a['id']) for a in pending)}")
    for b in st.budgets():
        s = budget.summary(st, b["provider"], b["account"])
        print(f"budget {s['provider']}/{s['account']}: {s['used']:,}/{s['limit']:,} tokens ({s['pct']}%), "
              f"reserve {s['reserve_pct']:g}% [{s['source']}]")


def cmd_log(args):
    st = open_store(args)
    for e in st.events(args.id, limit=args.limit):
        ts = time.strftime("%m-%d %H:%M:%S", time.localtime(e["ts"]))
        p = {k: v for k, v in e["payload"].items() if k != "results"}
        print(f"{ts}  {e['actor']:<34} {e['kind']:<22} {json.dumps(p) if p else ''}")


def brief(st, tid) -> str:
    t = st.get(tid)
    cps = st.checkpoints(tid)
    verified = [c for c in cps if c["verified"]]
    last_v = verified[-1] if verified else None
    since = last_v["ts"] if last_v else 0
    fs = st.findings(tid)
    lines = [f"# Task {t['id']}: {t['title']}", "",
             f"- state: {t['state']} · kind: {t['kind']} · attempt {t['attempts']}/{t['max_attempts']}"
             + (f" · owner: {t['owner']}" if t["owner"] else ""),
             f"- goal: {t['goal'] or '(none)'}", f"- acceptance: {t['acceptance'] or '(none)'}"]
    if t["kind"] == "implement":
        lines.append(f"- allowed paths (enforced at verify): {', '.join(t['allowed_paths'])}")
        lines.append(f"- worktree: {t['worktree'] or '(created on claim)'} · branch: {t['branch'] or '-'} · "
                     f"base: {(t['base'] or '')[:10]}")
        if t["worktree"] and Path(t["worktree"]).exists():
            dirty = gitops.git(["status", "--porcelain"], t["worktree"]).stdout.strip()
            if dirty:
                lines.append("- UNCOMMITTED changes in worktree (left by a previous attempt; inspect before continuing):")
                lines += [f"    {l}" for l in dirty.splitlines()[:20]]
    if t["checks"]:
        lines.append(f"- checks run at verify: {t['checks']}")
    if t["deps"]:
        lines.append(f"- depends on: {', '.join(t['deps'])}")
    lines += ["", "## Last verified checkpoint",
              f"{last_v['summary']} @ {(last_v['commit_sha'] or '')[:10]} by {last_v['author']}" if last_v
              else "(none yet)"]
    if cps and (not last_v or cps[-1]["id"] != last_v["id"]):
        c = cps[-1]
        lines.append(f"Latest unverified checkpoint: {c['summary']} @ {(c['commit_sha'] or '')[:10]} by {c['author']}")
    lines += ["", "## Findings (latest 15; NEW = after the last verified checkpoint)"]
    for f in fs[-15:]:
        ev = f" (evidence: {', '.join(f['evidence'])})" if f["evidence"] else ""
        new = "NEW " if last_v and f["ts"] > since else ""
        lines.append(f"- {new}[{f['kind']}] {f['author']}: {f['body'][:600]}{ev}")
    if not fs:
        lines.append("(none)")
    for d in t["deps"]:
        dt = st.get(d)
        lines += ["", f"## Handoff from dependency {d}: {dt['title']} ({dt['state']})"]
        for f in st.findings(d)[-8:]:
            ev = f" (evidence: {', '.join(f['evidence'])})" if f["evidence"] else ""
            lines.append(f"- [{f['kind']}] {f['author']}: {f['body'][:600]}{ev}")
    return "\n".join(lines)


def cmd_resume(args):
    print(brief(open_store(args), args.id))


AGENT_RULES = """
## Rules for this run
- You are running headless under agentsys. Do NOT run git commit, push, merge, or reset; agentsys commits for you.
- Only change files matching the allowed paths above. Changes elsewhere fail verification.
- Never print, read, or copy credentials, tokens, or .env files.
- If you are unsure or blocked, say so plainly in your final message instead of guessing.
- End with a short summary: what you changed (file paths) or found (with file:line evidence), and anything unverified.
"""


def cmd_dispatch(args):
    st = open_store(args)
    adapter = ADAPTERS.get(args.adapter) or die(f"unknown adapter {args.adapter}")
    if not adapter.binary():
        die(f"{adapter.name} CLI not found; see `agentsys adapters`")
    account = args.account or ("local" if adapter.name == "mock" else die("--account is required"))
    actor = f"{adapter.name}:{account}:{args.role}"
    t = st.get(args.id)
    try:
        est, alerts = budget.check_dispatch(st, adapter, account, role=args.role, est=args.estimate)
    except budget.BudgetError as e:
        st.event(actor, t["id"], "dispatch.refused", {"reason": str(e)})
        die(f"refused: {e}")
    for a in alerts:
        print(f"ALERT: {a}", file=sys.stderr)
    if t["state"] in ("ready", "changes_requested"):
        t = st.claim(t["id"], actor, lease_seconds=args.lease or args.timeout + 300)
    elif not (t["state"] == "in_progress" and t["owner"] == actor):
        die(f"{t['id']} is '{t['state']}' owned by {t['owner']}; cannot dispatch")
    write = t["kind"] == "implement"
    if write:
        path, branch = gitops.ensure_worktree(root_of(st), t["id"], t["base"])
        st.set_fields(t["id"], actor, "task.worktree", worktree=str(path), branch=branch)
        t = st.get(t["id"])
        workdir = path
    else:
        workdir = root_of(st)
    prompt = brief(st, t["id"]) + "\n" + AGENT_RULES
    before = budget.used_tokens(st, adapter.provider, account)
    started = time.time()
    st.event(actor, t["id"], "dispatch.start", {"adapter": adapter.name, "estimate": est, "workdir": str(workdir)})
    res = adapter.run(prompt, workdir, write=write, timeout=args.timeout, model=args.model,
                      max_usd=args.max_usd, task=t)
    run_id = st.record_run(task_id=t["id"], ts_start=started, ts_end=time.time(), adapter=adapter.name,
                           provider=adapter.provider, account=account, model=res.model or args.model,
                           exit_code=res.exit_code, tokens_in=res.tokens_in, tokens_out=res.tokens_out,
                           tokens_cached=res.tokens_cached, tokens_estimate=est, cost_usd=res.cost_usd,
                           usage_source=res.usage_source, note=res.note or None)
    evidence = [f"run:{run_id}"] + ([res.raw_usage["evidence"]] if res.raw_usage.get("evidence") else [])
    st.add_finding(t["id"], actor, res.text[:4000] or "(empty output)", kind="output", evidence=evidence)
    usage = f"{res.total_tokens:,} tokens" if res.total_tokens is not None else "usage not reported"
    print(f"run {run_id}: exit {res.exit_code}, {usage} [{res.usage_source}]")
    for a in budget.post_run_alerts(st, adapter.provider, account, before):
        print(f"ALERT: {a}", file=sys.stderr)
    if res.exit_code != 0:
        st.add_finding(t["id"], actor, f"Run {run_id} failed (exit {res.exit_code}); task released", kind="blocker",
                       evidence=[f"run:{run_id}"])
        st.transition(t["id"], "release", actor, owner_only=True, owner=None, lease_expires=None)
        die(f"{t['id']} released back to ready after failed run", 5)
    _checkpoint(st, t, actor, f"{adapter.name} run {run_id}", commit=write)
    t = st.transition(t["id"], "submit", actor, {"run_id": run_id}, owner_only=True, lease_expires=None)
    print(f"{t['id']} -> {t['state']}; next: agentsys verify {t['id']}")


def cmd_budget_set(args):
    st = open_store(args)
    st.set_budget(args.provider, args.account, args.limit, actor_of(args), reserve_pct=args.reserve,
                  source=args.source, note=args.note)
    print(f"budget {args.provider}/{args.account} = {args.limit:,} tokens (reserve {args.reserve:g}%)")


def cmd_budget_show(args):
    st = open_store(args)
    rows = st.budgets()
    seen = {(b["provider"], b["account"]) for b in rows}
    for r in st.runs():
        if (r["provider"], r["account"]) not in seen and r["provider"] != "mock":
            seen.add((r["provider"], r["account"]))
            rows.append({"provider": r["provider"], "account": r["account"]})
    total_limit = 0
    for b in rows:
        s = budget.summary(st, b["provider"], b["account"])
        if s["limit"] is None:
            print(f"{s['provider']}/{s['account']}: used {s['used']:,} tokens, NO LIMIT SET")
            continue
        total_limit += s["limit"]
        print(f"{s['provider']}/{s['account']}: {s['used']:,} / {s['limit']:,} tokens ({s['pct']}%), "
              f"remaining {s['remaining']:,}, reserve {s['reserve_pct']:g}% [{s['source']}]")
    if total_limit:
        print(f"sum of separate per-account limits: {total_limit:,} (not a shared pool)")


def cmd_usage_add(args):
    st = open_store(args)
    st.record_run(task_id=args.task, ts_start=time.time(), ts_end=time.time(), adapter="interactive",
                  provider=args.provider, account=args.account, model=args.model, exit_code=0,
                  tokens_in=args.tokens, tokens_out=0, tokens_cached=0, tokens_estimate=None, cost_usd=None,
                  usage_source="self-reported", note=args.note)
    print(f"recorded {args.tokens:,} self-reported tokens for {args.provider}/{args.account}")


def cmd_ui(args):
    from .ui import serve
    st = open_store(args)
    path = st.path
    st.close()
    serve(path, port=args.port)


def cmd_adapters(args):
    for a in ADAPTERS.values():
        d = a.detect()
        print(f"{d['adapter']:<7} provider={d['provider']:<10} {'available' if d['available'] else 'MISSING':<10} "
              f"{d['binary'] or ''}")


# ---------------------------------------------------------------- parser
def build_parser():
    p = argparse.ArgumentParser(prog="agentsys", description="Durable task coordination for multiple coding agents.")
    p.add_argument("--version", action="version", version=f"agentsys {__version__}")
    p.add_argument("--as", dest="actor", help="identity, e.g. cursor:alice:implementer (or AGENTSYS_ACTOR)")
    p.add_argument("--db", help="store path (default: <git root>/.agent-system/state.db, or AGENTSYS_DB)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def sp(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        s.set_defaults(fn=fn)
        return s

    sp("init", cmd_init, "create the store for this repository")
    task = sub.add_parser("task", help="create and list tasks").add_subparsers(dest="sub", required=True)
    a = task.add_parser("add", help="create a task")
    a.set_defaults(fn=cmd_task_add)
    a.add_argument("title")
    a.add_argument("--kind", choices=("implement", "research"), default="implement")
    a.add_argument("--goal")
    a.add_argument("--accept", help="acceptance criteria")
    a.add_argument("--path", action="append", help="allowed path glob (repeatable; required for implement)")
    a.add_argument("--check", action="append", help="shell command that must pass at verify (repeatable)")
    a.add_argument("--dep", action="append", help="task id this depends on (repeatable)")
    a.add_argument("--base", help="git ref to branch from (default: HEAD)")
    a.add_argument("--max-attempts", type=int, default=2)
    ls = task.add_parser("list", help="list tasks")
    ls.set_defaults(fn=cmd_task_list)
    ls.add_argument("--state")
    ls.add_argument("--json", action="store_true")

    sp("show", cmd_show, "full task record as JSON").add_argument("id")
    c = sp("claim", cmd_claim, "claim a task (creates a worktree for implement tasks)")
    c.add_argument("id")
    c.add_argument("--no-worktree", action="store_true")
    sp("heartbeat", cmd_heartbeat, "extend your lease").add_argument("id")
    sp("release", cmd_simple("release", owner_only=True), "give a claimed task back").add_argument("id")
    b = sp("block", cmd_simple("block", extra_key="reason"), "mark blocked (needs human/dependency)")
    b.add_argument("id")
    b.add_argument("--reason")
    sp("unblock", cmd_simple("unblock"), "return a blocked task to ready").add_argument("id")
    sp("requeue", cmd_simple("requeue"), "return an escalated task to ready").add_argument("id")
    x = sp("cancel", cmd_cancel, "cancel a task")
    x.add_argument("id")
    x.add_argument("--reason")

    f = sp("finding", cmd_finding, "record a finding, artifact, decision, blocker or question")
    f.add_argument("id")
    f.add_argument("body")
    f.add_argument("--kind", default="finding", choices=("finding", "artifact", "decision", "blocker", "question"))
    f.add_argument("--evidence", action="append", help="file:line, command, URL (repeatable)")
    f.add_argument("--confidence", choices=("low", "medium", "high"))
    k = sp("checkpoint", cmd_checkpoint, "record progress (optionally commit the worktree)")
    k.add_argument("id")
    k.add_argument("summary")
    k.add_argument("--commit", action="store_true")
    s = sp("submit", cmd_submit, "commit and hand the task to verification")
    s.add_argument("id")
    s.add_argument("summary")
    sp("verify", cmd_verify, "run the verification pipeline").add_argument("id")
    r = sp("review", cmd_review, "independent review (reviewer must not have worked on the task)")
    r.add_argument("id")
    r.add_argument("verdict", choices=("approve", "reject"))
    r.add_argument("--reason", required=True)
    r.add_argument("--evidence", action="append")
    m = sp("merge-check", cmd_merge_check, "dry-run merge; detects conflicts without touching any tree")
    m.add_argument("id")
    m.add_argument("--into")
    m = sp("merge", cmd_merge, "merge an accepted task (requires human approval)")
    m.add_argument("id")
    m.add_argument("--into")
    m.add_argument("--cleanup", action="store_true", help="remove the worktree after merging")
    ap = sp("approvals", cmd_approvals, "list approval requests")
    ap.add_argument("--all", action="store_true")
    sp("approve", cmd_decide(True), "grant an approval (human: actors only)").add_argument("approval_id", type=int)
    sp("deny", cmd_decide(False), "deny an approval (human: actors only)").add_argument("approval_id", type=int)

    sp("status", cmd_status, "overview of tasks, approvals and budgets")
    lg = sp("log", cmd_log, "audit trail")
    lg.add_argument("id", nargs="?")
    lg.add_argument("--limit", type=int)
    sp("resume", cmd_resume, "self-contained brief to continue a task from its last verified checkpoint").add_argument("id")

    d = sp("dispatch", cmd_dispatch, "run a headless agent on a task, within budget")
    d.add_argument("id")
    d.add_argument("--adapter", required=True, choices=sorted(ADAPTERS))
    d.add_argument("--account", help="account label, e.g. alice (required for real adapters)")
    d.add_argument("--model")
    d.add_argument("--role", choices=("work", "review"), default="work")
    d.add_argument("--estimate", type=int, help="override the token estimate")
    d.add_argument("--timeout", type=int, default=900)
    d.add_argument("--lease", type=float, help="lease seconds (default: timeout + 300)")
    d.add_argument("--max-usd", type=float, help="provider-side spend cap (Claude Code only)")

    bud = sub.add_parser("budget", help="per-account token limits").add_subparsers(dest="sub", required=True)
    bs = bud.add_parser("set")
    bs.set_defaults(fn=cmd_budget_set)
    bs.add_argument("provider")
    bs.add_argument("account")
    bs.add_argument("--limit", type=int, required=True, help="token limit for this provider/account")
    bs.add_argument("--reserve", type=float, default=20.0, help="%% held back for verification/review")
    bs.add_argument("--source", default="manual")
    bs.add_argument("--note")
    bud.add_parser("show").set_defaults(fn=cmd_budget_show)
    u = sub.add_parser("usage", help="self-report interactive usage").add_subparsers(dest="sub", required=True)
    ua = u.add_parser("add")
    ua.set_defaults(fn=cmd_usage_add)
    ua.add_argument("provider")
    ua.add_argument("account")
    ua.add_argument("tokens", type=int)
    ua.add_argument("--task")
    ua.add_argument("--model")
    ua.add_argument("--note")
    sp("adapters", cmd_adapters, "detect available agent CLIs")
    sp("ui", cmd_ui, "read-only live dashboard on 127.0.0.1").add_argument("--port", type=int, default=8791)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.fn(args)
    except (TransitionError, KeyError, ValueError, gitops.GitError) as e:
        die(str(e).strip("'\""))


if __name__ == "__main__":
    main()
