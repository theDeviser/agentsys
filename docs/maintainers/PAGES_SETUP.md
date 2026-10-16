# GitHub Pages (one-time)

The landing page deploys from the **`pages`** workflow to:

**https://thedeviser.github.io/agentsys/**

If you see 404:

1. Repo **Settings → Pages → Build and deployment → Source:** **GitHub Actions** (not “Deploy from a branch”).
2. Run **Actions → pages → Run workflow** on `main`.
3. After a green deploy, open the **github-pages** environment URL on the workflow run.

Local preview (same paths as production):

```sh
cd site && python3 -m http.server 8766
# open http://127.0.0.1:8766/  (use a reverse proxy or browse files under /agentsys/ paths via GitHub Pages URL shape)
```

For path-accurate preview from repo root:

```sh
python3 -m http.server 8766 --directory site
# Production uses /agentsys/ prefix; index.html links assume that base.
```
