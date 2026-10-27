"""Task templates and multi-step pipelines from profile or built-ins."""
from __future__ import annotations

from .profile import load

BUILTIN = {
    "research-implement": [
        {"key": "research", "kind": "research", "title": "Research: {title}", "goal": "{goal}"},
        {"key": "impl", "kind": "implement", "title": "{title}", "goal": "{goal}",
         "deps": ["research"]},
    ],
}


class PipelineError(ValueError):
    pass


def list_templates(root) -> dict[str, list]:
    prof = load(root) or {}
    custom = prof.get("templates") or {}
    out = dict(BUILTIN)
    for name, steps in custom.items():
        if isinstance(steps, list):
            out[name] = steps
    return out


def expand(name: str, root, *, title: str, goal: str = "", paths: list[str] | None = None,
           checks: list[str] | None = None) -> list[dict]:
    templates = list_templates(root)
    if name not in templates:
        raise PipelineError(f"unknown template {name}")
    paths = list(paths or [])
    checks = list(checks or [])
    ctx = {"title": title, "goal": goal or title}
    specs: list[dict] = []
    for step in templates[name]:
        spec = {k: v for k, v in step.items() if k != "key"}
        spec["title"] = (step.get("title") or title).format(**ctx)
        if step.get("goal") or step.get("kind") == "research":
            spec["goal"] = (step.get("goal") or ctx["goal"]).format(**ctx)
        spec["kind"] = step.get("kind", "implement")
        if spec["kind"] == "implement":
            spec["allowed_paths"] = paths
            spec["checks"] = checks
        else:
            spec["allowed_paths"] = []
            spec["checks"] = []
        spec["deps"] = list(step.get("deps") or [])
        spec["_key"] = step.get("key")
        specs.append(spec)
    keys = {s["_key"] for s in specs if s.get("_key")}
    for s in specs:
        for d in s["deps"]:
            if d not in keys:
                raise PipelineError(f"unknown dependency key {d} in template {name}")
        if s["kind"] == "implement" and not s["allowed_paths"]:
            raise PipelineError("implement step needs at least one --path")
    return specs


def create(st, actor: str, specs: list[dict]) -> list[str]:
    ids: dict[str, str] = {}
    created: list[str] = []
    for spec in specs:
        deps = [ids[d] for d in spec["deps"]]
        t = st.add_task(
            actor,
            spec["title"],
            kind=spec["kind"],
            goal=spec.get("goal", ""),
            acceptance=spec.get("acceptance", ""),
            allowed_paths=spec.get("allowed_paths"),
            checks=spec.get("checks"),
            deps=deps,
            max_attempts=spec.get("max_attempts", 2),
            base=spec.get("base"),
        )
        key = spec.get("_key")
        if key:
            ids[key] = t["id"]
        created.append(t["id"])
    return created
