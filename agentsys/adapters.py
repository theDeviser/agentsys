"""Provider adapters. Each wraps an officially supported headless CLI; none share credentials or quota."""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .store import literal_prefix

# Stripped from child envs so a run never silently switches from a subscription login to API billing.
API_KEY_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY",
                "OPENROUTER_API_KEY", "CURSOR_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN", "GH_TOKEN")


@dataclass
class RunResult:
    text: str
    exit_code: int
    tokens_in: int | None = None       # uncached input (+ cache writes)
    tokens_out: int | None = None
    tokens_cached: int | None = None   # cache reads
    cost_usd: float | None = None
    model: str | None = None
    usage_source: str = "unknown"      # provider-reported | mock | unknown
    note: str = ""
    raw_usage: dict = field(default_factory=dict)

    @property
    def total_tokens(self):
        parts = [self.tokens_in, self.tokens_out, self.tokens_cached]
        return None if all(p is None for p in parts) else sum(p or 0 for p in parts)


def _child_env():
    env = {k: v for k, v in os.environ.items() if k not in API_KEY_VARS}
    env["AGENT_BRIDGE_HEADLESS"] = "1"
    env["AGENTSYS_HEADLESS"] = "1"
    return env


def _version_key(path):
    return [int(x) for x in re.findall(r"\d+", path)]


def _find(name, ext_globs):
    p = shutil.which(name)
    if p:
        return p
    hits = []
    for g in ext_globs:
        hits += [h for h in glob.glob(os.path.expanduser(g)) if os.access(h, os.X_OK)]
    return max(hits, key=_version_key) if hits else None


class Adapter:
    name = "base"
    provider = "none"
    default_estimate = 100_000

    def binary(self):
        return None

    def detect(self) -> dict:
        b = self.binary()
        return {"adapter": self.name, "provider": self.provider, "available": bool(b), "binary": b}

    def _exec(self, cmd, workdir, timeout, stdin=None):
        start = time.time()
        try:
            p = subprocess.run(cmd, cwd=str(workdir), input=stdin, capture_output=True, text=True,
                               timeout=timeout, env=_child_env())
            return p.returncode, p.stdout, p.stderr, time.time() - start
        except subprocess.TimeoutExpired as e:
            return 124, (e.stdout or "") if isinstance(e.stdout, str) else "", f"timed out after {timeout}s", timeout

    def run(self, prompt, workdir, *, write: bool, timeout: int, model=None, max_usd=None) -> RunResult:
        raise NotImplementedError


class MockAdapter(Adapter):
    """Deterministic stand-in for a real agent. Output is always labelled MOCK. Spends nothing."""
    name = "mock"
    provider = "mock"
    default_estimate = 0

    def binary(self):
        return "builtin"

    def run(self, prompt, workdir, *, write, timeout, model=None, max_usd=None, task=None) -> RunResult:
        mode = os.environ.get("AGENTSYS_MOCK_MODE", "ok")
        target = None
        if write and task and task.get("allowed_paths"):
            target = self._target(Path(workdir), task, out_of_scope=(mode == "out_of_scope"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write(f"MOCK change for {task['id']} (attempt {task.get('attempts')})\n")
        if mode == "crash":
            os._exit(137)  # simulate the agent process dying mid-task, after a partial write
        rel = str(target.relative_to(workdir)) if target else None
        text = f"[MOCK] Completed '{task['title'] if task else 'task'}'." + (f" Wrote {rel}." if rel else "")
        return RunResult(text=text, exit_code=0, tokens_in=0, tokens_out=0, tokens_cached=0, cost_usd=0.0,
                         model="mock", usage_source="mock", raw_usage={"evidence": rel})

    @staticmethod
    def _target(workdir: Path, task, out_of_scope=False) -> Path:
        if out_of_scope:
            return workdir / "OUT_OF_SCOPE_BY_MOCK.md"
        prefix = literal_prefix(task["allowed_paths"][0])
        if prefix and not prefix.endswith("/") and Path(prefix).suffix:
            return workdir / prefix
        return workdir / (prefix or "") / f"mock-{task['id']}.md"


class CursorAdapter(Adapter):
    name = "cursor"
    provider = "cursor"
    default_estimate = 120_000

    def binary(self):
        return _find("cursor-agent", ["~/.local/bin/cursor-agent"])

    def run(self, prompt, workdir, *, write, timeout, model=None, max_usd=None, task=None) -> RunResult:
        # cursor-agent only accepts the prompt as an argument (visible in `ps` to the same user).
        cmd = [self.binary(), "-p", "--output-format", "json", "--trust", "--sandbox", "enabled",
               "--workspace", str(workdir)]
        cmd += ["--force"] if write else ["--mode", "ask"]
        if model:
            cmd += ["--model", model]
        code, out, err, _ = self._exec(cmd + [prompt], workdir, timeout)
        try:
            res = json.loads(out.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return RunResult(text=(err or out).strip()[-800:], exit_code=code or 1, note="unparseable output")
        u = res.get("usage") or {}
        return RunResult(
            text=(res.get("result") or "").strip(), exit_code=1 if res.get("is_error") else code,
            tokens_in=_n(u.get("inputTokens")) + _n(u.get("cacheWriteTokens")) if u else None,
            tokens_out=u.get("outputTokens"), tokens_cached=u.get("cacheReadTokens"), model=model,
            usage_source="provider-reported" if u else "unknown", raw_usage=u)


class ClaudeAdapter(Adapter):
    name = "claude"
    provider = "anthropic"
    default_estimate = 80_000

    def binary(self):
        return _find("claude", ["~/.cursor/extensions/anthropic.claude-code-*/resources/native-binary/claude",
                                "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"])

    def run(self, prompt, workdir, *, write, timeout, model=None, max_usd=None, task=None) -> RunResult:
        tools = "Read,Glob,Grep,Edit,Write" if write else "Read,Glob,Grep"
        cmd = [self.binary(), "-p", "--output-format", "json", "--allowedTools", tools,
               "--permission-mode", "acceptEdits" if write else "default"]
        if model:
            cmd += ["--model", model]
        if max_usd:
            cmd += ["--max-budget-usd", str(max_usd)]
        code, out, err, _ = self._exec(cmd, workdir, timeout, stdin=prompt)
        try:
            res = json.loads(out.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            return RunResult(text=(err or out).strip()[-800:], exit_code=code or 1, note="unparseable output")
        u = res.get("usage") or {}
        models = list((res.get("modelUsage") or {}).keys())
        return RunResult(
            text=(res.get("result") or "").strip(), exit_code=1 if res.get("is_error") else code,
            tokens_in=_n(u.get("input_tokens")) + _n(u.get("cache_creation_input_tokens")) if u else None,
            tokens_out=u.get("output_tokens"), tokens_cached=u.get("cache_read_input_tokens"),
            cost_usd=res.get("total_cost_usd"), model=",".join(models) or model,
            usage_source="provider-reported" if u else "unknown", raw_usage=u)


class CodexAdapter(Adapter):
    name = "codex"
    provider = "openai"
    default_estimate = 60_000

    def binary(self):
        return _find("codex", ["~/.cursor/extensions/openai.chatgpt-*/bin/*/codex",
                               "~/.vscode/extensions/openai.chatgpt-*/bin/*/codex"])

    def run(self, prompt, workdir, *, write, timeout, model=None, max_usd=None, task=None) -> RunResult:
        cmd = [self.binary(), "exec", "--json", "--sandbox", "workspace-write" if write else "read-only",
               "-C", str(workdir)]
        if model:
            cmd += ["--model", model]
        code, out, err, _ = self._exec(cmd + ["-"], workdir, timeout, stdin=prompt)
        text, usage, errors = "", {}, []
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "turn.failed":
                errors.append(_error_message((ev.get("error") or {}).get("message")))
            if ev.get("type") == "turn.completed" and isinstance(ev.get("usage"), dict):
                for k, v in ev["usage"].items():
                    if isinstance(v, int):
                        usage[k] = usage.get(k, 0) + v
            item = ev.get("item") or {}
            if ev.get("type") == "item.completed" and item.get("type") == "agent_message":
                text = item.get("text") or text
        if not text and code != 0:
            text = "; ".join(errors) or _quiet(err)[-800:] or "codex exited with no output"
        cached = usage.get("cached_input_tokens")
        return RunResult(
            text=text.strip(), exit_code=code,
            tokens_in=(usage["input_tokens"] - (cached or 0)) if "input_tokens" in usage else None,
            tokens_out=usage.get("output_tokens"), tokens_cached=cached, model=model,
            usage_source="provider-reported" if usage else "unknown", raw_usage=usage)


def _n(v):
    return v if isinstance(v, int) else 0


def _error_message(raw):
    """Codex nests the API error as a JSON string; pull out the human-readable part."""
    try:
        return json.loads(raw)["error"]["message"]
    except (TypeError, ValueError, KeyError):
        return str(raw or "unknown error")


def _quiet(stderr):
    """Drop MCP transport chatter (unauthenticated servers) so the real error is visible."""
    return "\n".join(l for l in (stderr or "").splitlines() if "rmcp::" not in l).strip()


ADAPTERS = {a.name: a for a in (MockAdapter(), CursorAdapter(), ClaudeAdapter(), CodexAdapter())}
