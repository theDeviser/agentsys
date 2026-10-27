#!/usr/bin/env python3
"""Generate site/docs/*.html from markdown sources (stdlib only)."""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "site" / "docs"
BASE = "/agentsys/"
REPO = "https://github.com/theDeviser/agentsys/blob/main/"
SVG_DEFS = """<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="i-mark" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="4" cy="4" r="2"/><circle cx="12" cy="4" r="2"/><circle cx="8" cy="12" r="2"/><path d="M5.5 5.4 7 10.4M10.5 5.4 9 10.4M6 4h4"/></symbol>
</svg>"""
NAV_BRAND = f'<a class="nav-brand" href="{BASE}"><svg width="18" height="18"><use href="#i-mark"/></svg>agentsys</a>'

# slug, source path relative to ROOT, nav title, nav group
PAGES: list[tuple[str, str, str, str]] = [
    ("index", "docs/index.md", "Overview", "Getting started"),
    ("architecture", "docs/ARCHITECTURE.md", "Architecture", "Guides"),
    ("integrations", "docs/integrations.md", "Integrations", "Guides"),
    ("cli-reference", "docs/cli-reference.md", "CLI reference", "Reference"),
    ("roadmap", "docs/ROADMAP.md", "Roadmap", "Reference"),
    ("security", "SECURITY.md", "Security", "Project"),
    ("threat-model", "THREAT_MODEL.md", "Threat model", "Project"),
    ("contributing", "CONTRIBUTING.md", "Contributing", "Project"),
]

DOC_LINKS = {
    "docs/index.md": "index.html",
    "index.md": "index.html",
    "docs/ARCHITECTURE.md": "architecture.html",
    "ARCHITECTURE.md": "architecture.html",
    "docs/integrations.md": "integrations.html",
    "integrations.md": "integrations.html",
    "docs/cli-reference.md": "cli-reference.html",
    "cli-reference.md": "cli-reference.html",
    "docs/ROADMAP.md": "roadmap.html",
    "ROADMAP.md": "roadmap.html",
    "SECURITY.md": "security.html",
    "../SECURITY.md": "security.html",
    "THREAT_MODEL.md": "threat-model.html",
    "../THREAT_MODEL.md": "threat-model.html",
    "CONTRIBUTING.md": "contributing.html",
    "../CONTRIBUTING.md": "contributing.html",
    "CHANGELOG.md": f"{BASE}changelog.html",
    "../CHANGELOG.md": f"{BASE}changelog.html",
}


def slug_heading(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", s)


def resolve_href(target: str, source: Path) -> str:
    t = target.split("#", 1)
    path_part, frag = t[0], (f"#{t[1]}" if len(t) > 1 else "")
    if path_part.startswith("http://") or path_part.startswith("https://"):
        return target
    if path_part.startswith("/agentsys/"):
        return path_part + frag
    if path_part in DOC_LINKS:
        href = DOC_LINKS[path_part]
        if href.endswith(".html") and not href.startswith("/"):
            href = href + frag
        elif frag:
            href = href + frag
        return href
    if path_part.startswith("docs/") and path_part.endswith(".md"):
        name = path_part[5:-3].lower().replace("_", "-")
        if name == "index":
            return f"index.html{frag}"
        return f"{name}.html{frag}"
    if path_part.endswith(".md"):
        base = path_part.rsplit("/", 1)[-1][:-3].lower().replace("_", "-")
        if base == "architecture":
            return f"architecture.html{frag}"
        return f"{base}.html{frag}"
    rel = (source.parent / path_part).resolve()
    try:
        rel = rel.relative_to(ROOT)
    except ValueError:
        return REPO + path_part + frag
    return REPO + str(rel).replace("\\", "/") + frag


def inline_md(text: str, source: Path) -> str:
    s = html.escape(text)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)

    def link(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2)
        href = resolve_href(url, source)
        return f'<a href="{html.escape(href, quote=True)}">{label}</a>'

    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, s)
    return s


def parse_table(lines: list[str], source: Path) -> str:
    rows = [line.strip() for line in lines if line.strip()]
    if len(rows) < 2:
        return ""
    def cells(row: str) -> list[str]:
        return [c.strip() for c in row.strip("|").split("|")]

    head = cells(rows[0])
    body_rows = rows[2:] if re.match(r"^[\s|:-]+$", rows[1]) else rows[1:]
    out = ["<table><thead><tr>"]
    for c in head:
        out.append(f"<th>{inline_md(c, source)}</th>")
    out.append("</tr></thead><tbody>")
    for row in body_rows:
        if not row.startswith("|"):
            continue
        out.append("<tr>")
        for c in cells(row):
            out.append(f"<td>{inline_md(c, source)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def md_to_html(text: str, source: Path) -> tuple[str, list[tuple[str, str]]]:
    """Return HTML body and TOC entries (id, title)."""
    lines = text.splitlines()
    out: list[str] = []
    toc: list[tuple[str, str]] = []
    i = 0
    list_stack: list[tuple[int, str]] = []  # indent, tag ul/ol

    def close_lists(until: int = -1) -> None:
        nonlocal list_stack
        while list_stack and list_stack[-1][0] > until:
            tag = list_stack.pop()[1]
            out.append(f"</{tag}>")

    while i < len(lines):
        line = lines[i]
        if re.match(r"^\[[^\]]+\]: ", line):
            i += 1
            continue

        if line.startswith("```"):
            close_lists()
            lang = line[3:].strip()
            i += 1
            code_lines: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            code = html.escape("\n".join(code_lines))
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(
                f'<div class="code-block"><button type="button" class="code-copy" '
                f'aria-label="Copy code">Copy</button><pre><code{cls}>{code}</code></pre></div>'
            )
            continue

        if line.startswith("|") and "|" in line[1:]:
            close_lists()
            table_lines = [line]
            i += 1
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            out.append(parse_table(table_lines, source))
            continue

        if line.startswith("# "):
            close_lists()
            title = line[2:].strip()
            out.append(f"<h1>{inline_md(title, source)}</h1>")
            i += 1
            continue

        m = re.match(r"^(#{2,6})\s+(.+)$", line)
        if m:
            close_lists()
            level = len(m.group(1))
            title = m.group(2).strip()
            hid = slug_heading(title)
            if level <= 3:
                toc.append((hid, title))
            out.append(
                f'<h{level} id="{hid}">{inline_md(title, source)}</h{level}>'
            )
            i += 1
            continue

        if line.startswith("> "):
            close_lists()
            quote_lines = [line[2:]]
            i += 1
            while i < len(lines) and lines[i].startswith("> "):
                quote_lines.append(lines[i][2:])
                i += 1
            inner = " ".join(quote_lines)
            out.append(f"<blockquote><p>{inline_md(inner, source)}</p></blockquote>")
            continue

        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.+)$", line)
        if m:
            indent = len(m.group(1))
            marker = m.group(2)
            tag = "ol" if marker[0].isdigit() else "ul"
            if not list_stack or indent > list_stack[-1][0]:
                out.append(f"<{tag}>")
                list_stack.append((indent, tag))
            elif indent < list_stack[-1][0]:
                close_lists(indent - 1)
                if not list_stack or list_stack[-1][0] != indent:
                    out.append(f"<{tag}>")
                    list_stack.append((indent, tag))
            out.append(f"<li>{inline_md(m.group(3), source)}</li>")
            i += 1
            continue

        if not line.strip():
            close_lists()
            i += 1
            continue

        close_lists()
        out.append(f"<p>{inline_md(line.strip(), source)}</p>")
        i += 1

    close_lists()
    return "\n".join(out), toc


def nav_html(current: str) -> str:
    groups: dict[str, list[tuple[str, str]]] = {}
    for slug, _src, title, group in PAGES:
        groups.setdefault(group, []).append((slug, title))
    parts = [
        '<nav class="docs-sidebar" aria-label="Documentation">',
        '<div class="docs-search-box">',
        '<input type="search" id="docs-search" class="docs-search" placeholder="Search docs…" '
        'autocomplete="off" aria-label="Search documentation">',
        '<kbd class="docs-search-kbd" aria-hidden="true">/</kbd>',
        '<div id="docs-search-results" class="docs-search-results" hidden></div>',
        '</div>',
    ]
    for group, items in groups.items():
        parts.append(f'<div class="docs-nav-group"><div class="docs-nav-label">{html.escape(group)}</div><ul>')
        for slug, title in items:
            href = "index.html" if slug == "index" else f"{slug}.html"
            cur = ' aria-current="page"' if slug == current else ""
            parts.append(
                f'<li><a href="{href}"{cur}>{html.escape(title)}</a></li>'
            )
        parts.append("</ul></div>")
    parts.append("</nav>")
    return "\n".join(parts)


def toc_html(toc: list[tuple[str, str]]) -> str:
    if not toc:
        return ""
    items = "".join(
        f'<li><a href="#{html.escape(i)}">{html.escape(t)}</a></li>' for i, t in toc
    )
    return f'<nav class="docs-toc" aria-label="On this page"><div class="docs-toc-label">On this page</div><ul>{items}</ul></nav>'


def prev_next(current: str) -> tuple[str | None, str | None]:
    slugs = [p[0] for p in PAGES]
    idx = slugs.index(current)
    prev_p = PAGES[idx - 1] if idx > 0 else None
    nxt = PAGES[idx + 1] if idx < len(PAGES) - 1 else None
    return prev_p, nxt


def wrap_page(
    slug: str,
    title: str,
    body: str,
    toc: list[tuple[str, str]],
    source_rel: str,
) -> str:
    prev_p, nxt = prev_next(slug)
    pager_parts = ['<div class="docs-pager">']
    if prev_p:
        ps, _, pt, _ = prev_p
        ph = "index.html" if ps == "index" else f"{ps}.html"
        pager_parts.append(f'<a class="docs-pager-prev" href="{ph}">← {html.escape(pt)}</a>')
    else:
        pager_parts.append("<span></span>")
    if nxt:
        ns, _, nt, _ = nxt
        nh = "index.html" if ns == "index" else f"{ns}.html"
        pager_parts.append(f'<a class="docs-pager-next" href="{nh}">{html.escape(nt)} →</a>')
    pager_parts.append("</div>")
    pager_html = "".join(pager_parts)
    edit = REPO + source_rel.replace("\\", "/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} — agentsys docs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{BASE}css/site.css">
<link rel="stylesheet" href="{BASE}css/docs.css">
</head>
<body class="docs-layout">
{SVG_DEFS}
<nav class="nav is-scrolled">
  <div class="nav-inner">
    {NAV_BRAND}
    <div class="nav-right">
      <a class="nav-link" href="{BASE}">Home</a>
      <a class="nav-link" href="index.html" aria-current="page">Docs</a>
      <a class="nav-link" href="{BASE}changelog.html">Changelog</a>
      <a class="nav-stars" href="https://github.com/theDeviser/agentsys">GitHub</a>
    </div>
  </div>
</nav>
<div class="docs-shell">
{nav_html(slug)}
<main class="docs-main prose docs-prose">
<article>
{body}
{pager_html}
<p class="docs-edit"><a href="{html.escape(edit)}">Edit this page on GitHub</a></p>
</article>
</main>
{toc_html(toc)}
</div>
<footer class="footer">
  <div class="footer-inner">
    <div class="footer-brand">MIT licensed</div>
    <div class="footer-links"><a href="https://github.com/theDeviser/agentsys">GitHub</a><a href="{BASE}">Home</a></div>
  </div>
</footer>
<script src="{BASE}js/docs.js"></script>
</body>
</html>
"""


def build_search_index(entries: list[dict[str, str]]) -> None:
    path = OUT_DIR / "search-index.json"
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    search: list[dict[str, str]] = []
    for slug, rel, title, _group in PAGES:
        src = ROOT / rel
        if not src.is_file():
            print(f"missing {rel}", file=sys.stderr)
            return 1
        raw = src.read_text(encoding="utf-8")
        body, toc = md_to_html(raw, src)
        page_title = title
        if slug == "index":
            m = re.match(r"^#\s+(.+)", raw)
            if m:
                page_title = m.group(1).strip()
        html_page = wrap_page(slug, page_title, body, toc, rel)
        out_name = "index.html" if slug == "index" else f"{slug}.html"
        out_path = OUT_DIR / out_name
        out_path.write_text(html_page, encoding="utf-8")
        plain = re.sub(r"<[^>]+>", " ", body)
        plain = re.sub(r"\s+", " ", plain).strip()[:8000]
        search.append({
            "title": page_title,
            "slug": out_name,
            "url": f"{BASE}docs/{out_name}",
            "text": plain,
        })
        print(f"wrote site/docs/{out_name}")
    build_search_index(search)
    print("wrote site/docs/search-index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
