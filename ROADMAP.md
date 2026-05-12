# IPA Labeler — Deployment & Multi-User Roadmap

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

## Progress

- [x] **Pre-deploy app hardening** — path-sanitized uploads, extension whitelist, `threading.Lock` on annotations file, `/healthz`, shared-boundary drag fix, Enter-to-add-segment, upload error handling, ResizeObserver waveform redraw, `beforeunload` guard + toast notifications, timestamp dedupe, smoke tests in `tests/test_app.py`
- [x] **Step 1.2** — `IPA_LABELER_DATA_DIR` env var; `harvard.wav` auto-seeded into a fresh data dir on startup
- [x] **Step 1.3** — `Dockerfile` (non-root, gunicorn `-w 1`, `IPA_LABELER_DATA_DIR=/data`), `.dockerignore`, `.github/workflows/build.yml` pushing to `ghcr.io/cmiley/ipa-labeler:latest` + `:sha-<short>`. Verified end-to-end with `docker build` + `docker run` + named-volume restart-persist via Colima.
- [x] **Step 1.4** — Manifests in `homelab-k8s/kubernetes/apps/ipa-labeler/` + `pvc.yaml` (Longhorn 20Gi) + ingress (`ipa.homelab.caylermiley.com`, Authelia ForwardAuth) + ArgoCD Application at `bootstrap/apps/ipa-labeler.yaml`. Pushed to homelab-k8s; pod `1/1 Running` on `dell-optiplex`, cert issued via DNS-01.
- [x] **Step 1.5** — ArgoCD Application synced; verified `1/1 Running` end-to-end.
- [x] **Step 1.6 — REPLACED** — Cloudflare Tunnel not needed. Wildcard CNAME `*.homelab.caylermiley.com → 192.168.20.200` in public DNS already covers reachability: LAN clients route directly to MetalLB; off-LAN clients reach the cluster via the existing Headscale/Tailscale mesh. No new cluster infrastructure required.
- [x] **Authelia rule** — `ipa.homelab.caylermiley.com` added to user-level `one_factor` rules in `core/authelia/configmap.yaml`; default-deny was 403'ing the host. Verified `https://ipa.homelab.caylermiley.com/` returns 302 → Authelia portal.
- [x] **Phase 2 — backend** — CNPG `ipa-labeler-pg` Cluster provisioned (10Gi Longhorn). SQLAlchemy 2.0 + Alembic 0001 schema (users / audio_clips / annotations JSONB). New blueprints `/api/clips` (list/get/upload/audio + sha256 dedupe + mutagen probe) and `/api/clips/<id>/annotations` (per-user GET/PUT, `user=me|all`). `/api/me` + per-user export. 13 pytest tests all green.
- [x] **Phase 2 — migration script** — `scripts/migrate_from_json.py` ingests legacy `annotations.json` under a synthetic `legacy-system` user; idempotent by sha256. Tested locally against the dev DB with real harvard data.
- [x] **Phase 2 — frontend** — Clip dropdown, upload + dedupe toast, save/load/export wired to clip-id endpoints, plus "View others" mode: toggle between editing-your-own and read-only browsing of any other user's annotation (segment counts shown per user). Read-only mode hides Save/Add Segment/Create Segments and blocks mutation entry points.
- [x] **Phase 2 — deployment** — `deployment.yaml` updated with `alembic-upgrade` init container + `DATABASE_URL` from CNPG-issued `ipa-labeler-pg-app` secret. Phase 2 image built + pushed to GHCR. ArgoCD synced; pod `1/1 Running`.
- [x] **Phase 2 — backups (Step 2.7)** — `backups.yaml` adds a 5Gi Longhorn PVC + nightly CronJob (04:00 PT) that runs `pg_dump --no-owner --no-privileges`, gzips to `/backups/<UTC-date>.sql.gz`, prunes >14d. One-off run verified: `2026-05-12.sql.gz` present on the backup PVC.
- [x] **Phase 2 — archive legacy data** — `/data/annotations.json` on the production PVC renamed to `annotations.json.phase1-archived` after migration. Nothing reads it; kept as historical evidence.
- [x] **Phase 3 — ASR auto-transcribe** — `asr.py` module with lazy-loaded `faster-whisper tiny.en` (CT2 int8) + `gruut`/`gruut-lang-en`. New endpoint `POST /api/clips/<id>/transcribe` → `{semanticLabel, segments:[{startTime,endTime,text=IPA,semanticLabel=word}]}`. Frontend "✨ Auto-transcribe" button replaces current annotations with the suggestion and marks dirty so the user reviews + saves. Model baked into the image at `/app/.cache/huggingface` via Dockerfile RUN step; `HF_HUB_OFFLINE=1` set in deployment so the read-only rootfs is fine. Image size 80MB → 635MB; memory limit bumped 512Mi → 1Gi. 15 tests green (asr stubbed for speed). Verified locally on harvard.wav: 43 word-segments returned, IPA gruut-correct (`stale → stˈeɪl`, `lingers → lˈɪŋɡɚz`).

**Phase 2 done-when criteria — all met:**
- [x] Multi-user labeling works (View Others mode + per-user backend)
- [x] sha256 dedupe (test_upload_dedupes_by_sha256)
- [x] annotations.json fully migrated + archived
- [x] pg_dump CronJob runs successfully (verified one-off)
- [x] Rollout (`kubectl rollout restart`) preserves data (Postgres pod independent; verified during View Others rollout)

Target end-state for Phases 1–2: Flask app at `ipa.homelab.caylermiley.com`, backed by Postgres, with Authelia SSO + admin-managed Authelia/LLDAP users. LAN-direct and Tailscale-via-Headscale for off-LAN. Annotations are per-user, per-clip; harvard.wav is the seed sample and any logged-in user can label any clip in the database.

---

## Decisions you need to make before starting

| # | Decision | Options | Recommendation |
|---|----------|---------|----------------|
| D1 | ~~Public reachability~~ | **Resolved.** Wildcard public CNAME already routes `*.homelab.caylermiley.com` to the MetalLB IP; Headscale handles off-LAN. No cloudflared needed. | |
| D2 | ~~Public hostname~~ | **Resolved.** `ipa.homelab.caylermiley.com`. | |
| D3 | Image registry | (a) GHCR via existing `github-runner`. (b) Local registry on cluster. | **(a)** — already wired up. |
| D4 | Postgres flavor | (a) Bare Postgres StatefulSet + Longhorn PVC. (b) CloudNativePG `Cluster` resource. | **(b)** — CloudNativePG is already deployed in your cluster (`bootstrap/apps/cloudnative-pg.yaml`); a single `Cluster` resource is simpler than a hand-rolled StatefulSet and gives you scheduled backups, scale-up, and metrics out of the box. |
| D5 | Audio storage backend | (a) Longhorn PVC mounted at `/data/clips/`. (b) MinIO with S3 API. | **(a)** to start; migrate to MinIO if/when you want signed URLs or cross-app access. |
| D6 | User identity source | Authelia headers (`Remote-User`, `Remote-Email`, `Remote-Groups`) injected by ForwardAuth. | Use these; no separate user table login flow. App creates a `users` row on first request from a new `Remote-User`. |

Fill these in (or accept the recommendations) before running Phase 1.

---

## Phase 1 — Containerize and deploy the current app

**Goal:** existing single-file Flask app reachable at the chosen hostname, behind Authelia, with persistent storage. No code changes.

**Prereqs:** D1, D2, D3, D6 settled. Cloudflare Tunnel set up if D1 = (a) — see Phase 1 Step 6.

### Step 1.1 — Dockerfile

Path: `ipa_labeler/Dockerfile`

```dockerfile
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
ENV FLASK_APP=app.py
EXPOSE 8080
CMD ["uv", "run", "gunicorn", "-w", "2", "-b", "0.0.0.0:8080", "app:app"]
```

Add `gunicorn` to `pyproject.toml` dependencies.

`.dockerignore` should exclude: `uploads/`, `annotations.json`, `.venv/`, `__pycache__/`, `.git/`.

**Verify:** `docker build -t ipa-labeler:dev . && docker run -p 8080:8080 ipa-labeler:dev` → can hit `localhost:8080`.

### Step 1.2 — Make the app honor a data directory env var ✅

Today `app.py` hardcodes `Path("uploads")` and `Path("annotations.json")`. Change to read `IPA_LABELER_DATA_DIR` (default `.`) and place both under it. Required for the PVC mount in Step 1.5.

Single change in `app.py`:

```python
DATA_DIR = Path(os.environ.get("IPA_LABELER_DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)
app.config["UPLOAD_FOLDER"] = DATA_DIR / "uploads"
annotations_file = DATA_DIR / "annotations.json"
```

Also bind-seed `harvard.wav` into the image at build time, then copy it to `UPLOAD_FOLDER` on startup if missing (so a fresh PVC has the seed).

**Verify:** `IPA_LABELER_DATA_DIR=/tmp/ipa-test uv run python app.py` → uploads land in `/tmp/ipa-test/uploads/`.

### Step 1.3 — Build & push image via existing github-runner ✅

Add a GitHub Actions workflow (`.github/workflows/build.yml`) that builds and pushes `ghcr.io/<your-gh-user>/ipa-labeler:<sha>` and `:latest`. Self-hosted runner is already deployed in `homelab-k8s/kubernetes/apps/github-runner/`.

**Verify:** Tag is visible in GHCR after a push to main.

### Step 1.4 — k8s manifests via `./scripts/new-app.sh ipa-labeler` ✅

From `homelab-k8s/`:

```bash
./scripts/new-app.sh ipa-labeler
```

Then edit `kubernetes/apps/ipa-labeler/`:

- `deployment.yaml`: image `ghcr.io/<user>/ipa-labeler:latest`, port 8080, mount `ipa-labeler-data` PVC at `/data`, env `IPA_LABELER_DATA_DIR=/data`. Drop `readOnlyRootFilesystem: true` (Flask + uploads need write) or scope it with an `emptyDir` for `/tmp`. Probes hit `/` (or add `/healthz` to the Flask app — recommended).
- `service.yaml`: ClusterIP, port 80 → targetPort 8080.
- `ingress.yaml`: hostname from D2, `cert-manager.io/cluster-issuer: letsencrypt-prod`, Authelia ForwardAuth middleware (already in repo).
- `pvc.yaml`: `ipa-labeler-data`, Longhorn, 20Gi to start.
- `kustomization.yaml`: include `pvc.yaml`.

### Step 1.5 — ArgoCD Application

Add to `kubernetes/sets/app-set.yaml` (or create a single `Application` manifest). ArgoCD picks it up automatically.

**Verify:** `kubectl get pods -n ipa-labeler` shows the pod Running. `kubectl logs` shows gunicorn workers booting.

### Step 1.6 — Reachability ✅

No cloudflared / tunnel needed. `*.homelab.caylermiley.com` is a public-DNS wildcard CNAME → MetalLB IP `192.168.20.200`:
- LAN clients route directly
- Off-LAN clients reach the cluster via the existing Headscale/Tailscale mesh
- For each new tester, issue a Headscale pre-auth key: `kubectl -n headscale exec -it deploy/headscale -- headscale preauthkeys create -u <user>`

### Step 1.7 — Add yourself + initial users in Authelia / LLDAP

Authelia uses **LLDAP** as the user backend (`core/authelia/configmap.yaml` line ~57: `base_dn: dc=homelab,dc=caylermiley,dc=com`), so new users go in LLDAP, not into a hand-edited users.yaml. LLDAP has a web UI at `https://lldap.homelab.caylermiley.com` (admin-only via Authelia).

Steps:
1. Log in to LLDAP UI as admin.
2. Create the user, assign to the `users` group (or `admins` for cluster operators).
3. New user can immediately log in at `https://auth.homelab.caylermiley.com` and reach `ipa.homelab.caylermiley.com`.

**Verify:** New user can log in and the IPA Labeler UI loads with harvard.wav.

### Phase 1 done when

- [ ] `https://ipa.homelab.caylermiley.com` returns the IPA Labeler UI after Authelia login (LAN-direct and via Headscale)
- [ ] Harvard sample audio plays, annotations persist across pod restarts (PVC working)
- [ ] At least 2 LLDAP users can log in (you + one tester)

---

## Phase 2 — Multi-user with Postgres

**Goal:** annotations are stored per-user in Postgres. All authenticated users see all clips and can add/edit their own annotations. Existing `annotations.json` is migrated. Clip upload endpoint is added.

### Step 2.1 — Decide the data model

Tables (Postgres 16):

```sql
CREATE TABLE users (
  id          BIGSERIAL PRIMARY KEY,
  authelia_sub TEXT UNIQUE NOT NULL,  -- from Remote-User header
  email       TEXT,
  display_name TEXT,
  is_admin    BOOLEAN NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audio_clips (
  id                BIGSERIAL PRIMARY KEY,
  storage_filename  TEXT UNIQUE NOT NULL,    -- on-disk name in /data/clips/
  original_filename TEXT NOT NULL,
  content_sha256    TEXT UNIQUE NOT NULL,    -- dedupe key
  duration_seconds  REAL,
  sample_rate_hz    INTEGER,
  uploaded_by       BIGINT REFERENCES users(id),
  uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  status            TEXT NOT NULL DEFAULT 'approved'  -- 'pending'|'approved'|'rejected'
);

CREATE TABLE annotations (
  id          BIGSERIAL PRIMARY KEY,
  clip_id     BIGINT NOT NULL REFERENCES audio_clips(id) ON DELETE CASCADE,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  segments    JSONB NOT NULL,   -- [{startTime, endTime, text, semanticLabel}, ...]
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (clip_id, user_id)
);

CREATE INDEX annotations_clip_idx ON annotations(clip_id);
CREATE INDEX annotations_user_idx ON annotations(user_id);
```

Notes:
- Keep segments as `JSONB` (matches existing in-memory shape; cheap to update wholesale on save). If you later need queries like "find all annotations containing [θ]", add a generated column or a separate `annotation_segments` table — that's a Phase 3 concern.
- `status` lets you queue uploads for review without blocking labeling.
- `UNIQUE (clip_id, user_id)` enforces one annotation document per user per clip; the existing UI already represents annotations as a single list per file.

### Step 2.2 — Postgres in-cluster

Path: `homelab-k8s/kubernetes/apps/ipa-labeler/postgres-*.yaml`

- `postgres-statefulset.yaml`: image `postgres:16-alpine`, 1 replica, mount `ipa-labeler-pg-data` PVC at `/var/lib/postgresql/data`, prefer amd64 node.
- `postgres-service.yaml`: headless `ipa-labeler-pg`, port 5432.
- `postgres-pvc.yaml`: Longhorn, 10Gi.
- `postgres-secret.yaml` (SOPS): `POSTGRES_PASSWORD`, `POSTGRES_USER=ipa`, `POSTGRES_DB=ipa_labeler`.

App reads `DATABASE_URL=postgresql://ipa:$(POSTGRES_PASSWORD)@ipa-labeler-pg:5432/ipa_labeler` from the same secret.

**Verify:** `kubectl exec -it ipa-labeler-pg-0 -- psql -U ipa -d ipa_labeler -c '\dt'` (empty until migrations run).

### Step 2.3 — App rewrite

Add dependencies: `sqlalchemy>=2.0`, `psycopg[binary]>=3.2`, `alembic>=1.13`, `python-magic`, `mutagen` (or `pydub`) for audio metadata.

New module layout:

```
ipa_labeler/
├── app.py                # Flask app factory + routes
├── db.py                 # SQLAlchemy engine, session, models
├── auth.py               # extract user from Authelia headers, get-or-create user row
├── clips.py              # upload, list, fetch by id; ffprobe for duration/sr
├── annotations.py        # CRUD by (clip_id, user_id)
├── migrations/           # alembic
└── ...
```

Authelia header extraction (no token validation needed — Traefik already enforces it):

```python
def current_user(req) -> User:
    sub = req.headers.get("Remote-User")
    if not sub:
        abort(401)
    return get_or_create_user(sub, email=req.headers.get("Remote-Email"),
                              display_name=req.headers.get("Remote-Name"))
```

Endpoint changes from the existing API:

| Old | New |
|---|---|
| `GET /annotations/<filename>` | `GET /api/clips/<clip_id>/annotations?user=me\|all` |
| `POST /annotations/<filename>` | `PUT /api/clips/<clip_id>/annotations` (uses current_user) |
| `GET /audio/<filename>` | `GET /api/clips/<clip_id>/audio` |
| (none) | `GET /api/clips` — list with pagination, filter by `labeled_by_me`, `unlabeled`, `mine` |
| `POST /upload` | `POST /api/clips` — multipart, validates magic bytes + duration, dedupes by sha256 |
| (none) | `GET /api/me` — returns current_user info for the frontend |
| `GET /export/...` | unchanged contract; reads from DB |

### Step 2.4 — Frontend changes

Minimum-viable changes to `static/app.js` + `templates/index.html`:

1. On load, `GET /api/me` then `GET /api/clips` and render a clip list panel (left rail).
2. Selecting a clip loads `GET /api/clips/<id>/audio` and `GET /api/clips/<id>/annotations?user=me`.
3. Add a toggle: "Show: my annotations / all annotations (read-only)". When viewing all, each segment block displays the labeling user's name and is non-editable unless it's yours.
4. Upload UI: change the existing upload to call `POST /api/clips` and refresh the list. Show validation errors (duration > N minutes, unsupported format).
5. Save annotation now `PUT`s to the new endpoint; the response is the canonical server state — reconcile.

Keep all existing IPA palette / waveform / slider logic untouched. The data layer is what changes.

### Step 2.5 — Migration script

One-shot script `scripts/migrate_from_json.py`:

1. Read `annotations.json` from the existing PVC.
2. For each `filename`, compute SHA-256 of the file in `uploads/`, insert into `audio_clips` (uploader = bootstrap user "system").
3. Insert one `annotations` row per (clip, system user) with the existing segments JSON.

Run once via `kubectl exec` after Phase 2 deploys, before flipping DNS / re-enabling user logins.

### Step 2.6 — Cutover

1. Scale Phase 1 deployment to 0.
2. Deploy Postgres + new app image.
3. Run alembic upgrade head, then `migrate_from_json.py`.
4. Smoke test from your laptop and one other Authelia user.
5. Scale to 1; verify all clips & annotations visible.
6. Snapshot the old `annotations.json` and `uploads/` to a backup directory on the PVC before deleting them.

### Step 2.7 — Backups

Minimum: a daily CronJob that runs `pg_dump` and writes to a separate Longhorn PVC. Retention: 14 days, prune older. Same CronJob can `tar` the clips directory.

Skipped for now: off-cluster backup target (S3, Backblaze). Add when the dataset is worth more than the cluster is.

### Phase 2 done when

- [ ] Two users logged in simultaneously see each other's annotations in read-only mode and can independently edit their own
- [ ] Uploading a duplicate file (same sha256) returns the existing clip rather than creating a second copy
- [ ] `annotations.json` data is fully migrated, old file archived
- [ ] `pg_dump` CronJob has run at least once successfully
- [ ] `kubectl rollout restart deployment/ipa-labeler -n ipa-labeler` causes no data loss

---

## Roadmap teasers (Phase 3+ — not in scope here)

- Per-segment annotation table for IPA-symbol queries ("show me every clip with /ʒ/")
- Annotation versioning (keep history; allow "revert to my v3")
- Inter-annotator agreement metrics (Cohen's κ on segment overlap)
- Audio waveform pre-computation server-side, cached in Postgres or a sidecar Redis
- Dataset export endpoint: build a HuggingFace-style parquet of (clip, ipa, semantic, user, timestamps)
- Forced alignment integration (Montreal Forced Aligner) as a one-click "pre-fill" for new clips
- Public read-only viewer (no login) for completed/curated subset

---

## Quick session-resume cheatsheet

When you come back to this:

1. Open this file, find the first unchecked box.
2. The step is self-contained — paths and commands are inline.
3. If a decision (D1–D6) hasn't been made, do that first.
4. Commit per `homelab-k8s/CLAUDE.md` conventions: `deploy: …`, `infra: …`, `fix: …`.
