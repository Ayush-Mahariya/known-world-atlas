# Deployment

The atlas is a static site. There is no server, no database and no API, so
deploying it is "upload a folder" — but two things are worth knowing before you
do it.

## Before you publish

**This must stay non-commercial.** The map geometry is CC BY-NC-SA 3.0 and it is
load-bearing. Hosting it publicly is fine; putting ads on it, gating it behind
payment, or folding it into anything commercial is not. Share-alike also means
if you publish modifications, they carry the same licence. See
[`02-data-sources.md`](02-data-sources.md).

**Keep the attribution visible.** It is in the MapLibre attribution control at
the bottom right and is a licence obligation, not decoration. Don't hide it with
CSS.

The world is George R. R. Martin's. This is a fan project, published as such.

## What gets built

`data/processed/` is committed, so a fresh clone already has the gazetteer,
lore, terrain grid and vector layers. What is *not* committed is the derived
output the browser actually fetches:

- `web/public/data/` — a copy of the processed data
- `web/public/tiles/` — 336 DEM and satellite PNGs

`scripts/build-site.sh` regenerates both and then builds the app:

```bash
bash scripts/build-site.sh    # ~25 seconds
# -> web/dist, about 8.9 MB across 362 files
```

It needs **python3 and node, and nothing else**. The tile builders import only
the Python standard library — no pip install, no network access. That is
deliberate: it means any CI image with Python can build this.

It does *not* run pipeline stages 01–07. Those need the source shapefiles and
the wiki dump, and their output is committed. Only re-run them
(`scripts/run-pipeline.sh`) when the underlying data or the cost model changes.

## Recommended: Cloudflare Pages

Matches what you already run, and static assets are free at this scale.

Connect the repo, then set:

| Setting | Value |
|---|---|
| Build command | `bash scripts/build-site.sh` |
| Build output directory | `web/dist` |
| Root directory | *(leave blank — the script handles paths)* |

If the build image picks the wrong interpreter, add an environment variable
`PYTHON_VERSION=3.12`. The script honours a `PY` override too, so `PY=python3.12`
works as a fallback.

For a custom domain on `ayush-mahariya.in`, add the subdomain in the Pages
project (e.g. `atlas.ayush-mahariya.in`), then add the CNAME it gives you at
your DNS provider.

To deploy without wiring up Git at all:

```bash
bash scripts/build-site.sh
npx wrangler pages deploy web/dist --project-name known-world-atlas
```

## GitHub Pages, step by step

`.github/workflows/deploy-pages.yml` builds the site, runs the router parity
test, and publishes. It triggers on pushes to `main` or `master`, and can be run
by hand from the Actions tab. Because the parity test runs before the publish
step, a change that breaks the travel model never reaches production.

### 1. Push the repository

The repo publishes about **6.5 MB** — the raw wiki dump and the reference
basemaps are gitignored and regenerated or refetched, not stored.

```bash
cd known-world-atlas
git add .
git commit -m "The Known World Atlas"
git remote add origin git@github.com:<username>/known-world-atlas.git
git push -u origin master        # or: git branch -M main && git push -u origin main
```

**The repository must be public** unless you have GitHub Pro — Pages on private
repos is a paid feature. Publishing the source is consistent with the licence
anyway: ShareAlike means modifications have to be distributable under the same
terms. See [LICENSE](../LICENSE).

### 2. Turn on Pages *before* the first run

**Settings → Pages → Build and deployment → Source: `GitHub Actions`.**

Do this first. If the source is still set to "Deploy from a branch", the deploy
job fails with a permissions error even though the build succeeded.

### 3. Watch the first build

The Actions tab shows two jobs, `build` then `deploy`, taking two or three
minutes together. The site lands at:

```
https://<username>.github.io/known-world-atlas/
```

That subpath works without any config change because `vite.config.ts` sets
`base: './'` and the app fetches `./data` and `./tiles` relative to the
document. This is the usual thing that breaks a Vite app on project Pages, and
it is already handled.

### 4. Point a subdomain at it

`ayush-mahariya.in` itself already serves the portfolio site, so the atlas needs
its own subdomain — `atlas.ayush-mahariya.in` or similar. One custom domain per
Pages site.

**At GoDaddy** (DNS → Manage Zones → your domain → Add record):

| Type | Name | Value | TTL |
|------|------|-------|-----|
| CNAME | `atlas` | `<username>.github.io` | default (1 hour) |

Enter just `atlas` as the name, not the full hostname — GoDaddy appends the
domain. The value must end in `.github.io` with no path and no `https://`.

**Then in GitHub**: Settings → Pages → Custom domain → `atlas.ayush-mahariya.in`
→ Save. GitHub runs a DNS check; if it fails, the record has not propagated yet.
Give it fifteen minutes and re-check rather than changing anything.

Once the check passes, GitHub provisions a Let's Encrypt certificate. When
**Enforce HTTPS** stops being greyed out, tick it. Certificate issuance is
usually minutes but is documented as taking up to 24 hours.

If you would rather use the apex domain, that means moving the portfolio to a
subdomain and using A records (`185.199.108.153`, `.109.153`, `.110.153`,
`.111.153`) plus the AAAA equivalents, instead of a CNAME. A CNAME on a subdomain
is much less trouble.

### 5. If the custom domain keeps resetting

With Actions-based publishing the domain lives in repository settings, not in
the repo. That is normally fine. If you find it clearing on deploys, pin it by
committing the hostname into the build output:

```bash
echo 'atlas.ayush-mahariya.in' > web/public/CNAME
```

Vite copies `web/public/` into `dist/` verbatim, so it ships with every build.
Keep it identical to the Settings value — a mismatch will fight itself.

## Anywhere else

`web/dist` is plain static files with relative URLs (`base: './'` in
`vite.config.ts`), so it works at a domain root *or* in a subdirectory without
reconfiguration. Netlify, S3 + CloudFront, Vercel, or a USB stick all work.

One constraint: keep the app at a single path. The data URLs resolve relative to
the document, so `/atlas/` is fine but `/atlas/some/route` would break them. The
app has no path routing today, so this only matters if you add some — at which
point switch `DATA`/`TILES` in `main.ts` to absolute paths.

## Caching

`web/public/_headers` is copied into `dist/` and read by Cloudflare Pages and
Netlify:

- `/tiles/*` and `/assets/*` — immutable, cached for a year. Tile URLs never
  change content, and Vite hashes the bundle filenames.
- `/data/*` — one hour, revalidated. These change on redeploy under stable names.

On a host that ignores `_headers` you lose caching efficiency, not correctness.

Worth checking after your first deploy: `data/terrain.bin` is 542 KB raw and
compresses about 45×, but some CDNs skip compression for
`application/octet-stream`. Confirm with:

```bash
curl -sI -H 'Accept-Encoding: br, gzip' https://your-domain/data/terrain.bin \
  | grep -i 'content-encoding\|content-length'
```

If nothing comes back compressed, the pipeline also writes `terrain.bin.gz` —
serve that and decompress client-side, or enable compression for that MIME type.

## Size and limits

| | |
|---|---|
| Total | 8.9 MB, 362 files |
| Largest file | ~1.1 MB (the JS bundle; 296 KB over the wire gzipped) |
| Tiles | 336 PNGs, 4.5 MB |

Comfortably inside Cloudflare Pages' limits (25 MB/file, 20,000 files) and
GitHub Pages' (1 GB total, 100 MB/file).

## Verifying a build locally

```bash
bash scripts/build-site.sh
cd web/dist && python3 -m http.server 8899
```

Then open <http://localhost:8899>. This is worth doing before a first deploy —
it catches path problems that `npm run dev` hides, because the dev server
falls back to `index.html` for missing files while a static host returns 404.
