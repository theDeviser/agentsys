# GitHub Pages

The landing page in `site/` deploys from the `pages` workflow to
**https://thedeviser.github.io/agentsys/** on every push to `main`.

One-time setup: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

Preview locally with the same `/agentsys/` URL prefix as production:

```sh
./scripts/preview_site.sh        # http://127.0.0.1:8766/agentsys/
```

The changelog page is generated from `CHANGELOG.md` by `scripts/build_changelog_site.py`;
CI fails if you forget to regenerate it. README banners come from `site/banner.html` via
`scripts/render_banner.sh`.
