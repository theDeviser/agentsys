#!/usr/bin/env python3
"""Generate site/changelog.html from CHANGELOG.md (stdlib only)."""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "CHANGELOG.md"
OUT = ROOT / "site" / "changelog.html"
BASE = "/agentsys/"


def md_to_fragment(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_list = False
    for line in lines:
        if line.startswith("# "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2 id=\"{slug(line[2:])}\">{html.escape(line[2:].strip())}</h2>")
        elif line.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline_md(html.escape(line[2:].strip()))}</li>")
        elif not line.strip():
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append("")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{inline_md(html.escape(line.strip()))}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def slug(h: str) -> str:
    s = re.sub(r"[^\w\s-]", "", h.lower()).strip()
    return re.sub(r"[-\s]+", "-", s)


def inline_md(s: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)


def wrap(body: str) -> str:
    return f"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Changelog — agentsys</title>
<link rel="stylesheet" href="{BASE}css/tokens.css">
<link rel="stylesheet" href="{BASE}css/site.css">
</head>
<body class="page">
<header class="top">
  <a class="brand" href="{BASE}">agentsys</a>
  <nav><a href="{BASE}">Home</a> · <a href="{BASE}changelog.html">Changelog</a></nav>
</header>
<main class="prose">
{body}
</main>
<footer class="foot"><a href="https://github.com/theDeviser/agentsys">GitHub</a></footer>
</body>
</html>
"""


def main() -> int:
    if not MD.is_file():
        print("CHANGELOG.md missing", file=sys.stderr)
        return 1
    body = md_to_fragment(MD.read_text(encoding="utf-8"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(wrap(body), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
