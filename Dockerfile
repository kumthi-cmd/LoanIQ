# syntax=docker/dockerfile:1
# =============================================================================
# Dockerfile: the LoanIQ container. One image holds the whole app.
#
# Where it sits: git push -> GitHub Actions builds and tests this image
#   (.github/workflows/ci.yml) -> the host (Render today, via render.yaml) builds
#   it again from main and runs it.
#
# BUSINESS: a visitor gets exactly what passed the tests: the Loan Tape screen and
#   the loan API, served by one server on one web address, over the same seeded
#   synthetic tape on every deploy. No real borrower data ever goes in the image.
#
# TECH: a multi-stage build. Each FROM line starts a fresh image; only what a later
#   stage copies with `COPY --from` survives. So Node and node_modules (hundreds of
#   MB) build the SPA in stage 1 and are then thrown away; the image that runs holds
#   only Python, the back end and the built static files.
#   - Build context is the repo root (`docker build .`), because Vite reads
#     ../content and ../brand while it builds the SPA (frontend/vite.config.ts).
#   - Paths inside /app copy the repo layout (backend/, content/, frontend/dist,
#     data/), so REPO_ROOT in loan_tape_gen.py and SPA_DIR / LABELS_PATH in main.py
#     resolve with no container-only settings.
#   - Portable: nothing here is Render-specific. Any host that runs a container and
#     sets $PORT (Render, DigitalOcean App Platform, Cloud Run, Lightsail) can run it.
#   - Versions must match local development: Node from .nvmrc, Python from
#     backend/.venv. backend/tests/test_deploy_config.py checks both.
# =============================================================================


# -----------------------------------------------------------------------------
# Stage 1 "spa": build the single-page app with Node.
# -----------------------------------------------------------------------------
# TECH: node:26-slim is Debian with Node 26, the major version in .nvmrc.
#   "AS spa" names the stage so stage 2 can copy from it.
FROM node:26-slim AS spa
WORKDIR /app

# TECH: copy only the two package files first, then install. Docker caches each
#   step as a layer and reuses it while its inputs are unchanged, so a code-only
#   change skips the slow `npm ci`. npm ci installs the exact versions in the lock
#   file and fails if package.json and the lock file disagree.
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-audit --no-fund

# BUSINESS: content/ holds the visitor-facing words (screen explanations, glossary)
#   and brand/ the LoanIQ Labs logo kit; the build bundles both into the SPA.
# TECH: .dockerignore keeps frontend/node_modules and frontend/dist out of this COPY,
#   so the fresh Linux install above is not overwritten by a Windows one.
COPY content/ content/
COPY brand/ brand/
COPY frontend/ frontend/

# TECH: the same `npm run build` test.ps1 runs: type check, then Vite writes
#   /app/frontend/dist (index.html, hashed JS/CSS, fonts, /icon/).
RUN cd frontend && npm run build


# -----------------------------------------------------------------------------
# Stage 2 "runtime": the image that runs. Python, the API and the built SPA.
# -----------------------------------------------------------------------------
# TECH: python:3.12-slim matches backend/.venv (Python 3.12). "slim" drops compilers
#   and docs; every dependency here ships a ready-built Linux wheel.
FROM python:3.12-slim AS runtime

# TECH: PYTHONDONTWRITEBYTECODE stops .pyc files being written into the image;
#   PYTHONUNBUFFERED sends log lines straight to the host's log viewer;
#   PIP_NO_CACHE_DIR keeps pip's download cache out of the image.
#   PORT is the default port. Hosts set their own $PORT when they start the
#   container (Render's default is 10000).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000

WORKDIR /app

# TECH: a plain user with no rights beyond reading the app. If the web server were
#   ever compromised, the attacker would not be root inside the container.
#   A fixed uid (10001) makes file ownership predictable on every host.
RUN useradd --create-home --uid 10001 loaniq

# TECH: dependencies first, for the same layer caching as npm ci above. The pins in
#   requirements.txt make every image install identical versions. The file also
#   holds the test tools (pytest, pytest-cov, httpx2), a few MB that the running
#   app never imports. One requirements file keeps local setup simple.
COPY backend/requirements.txt backend/
RUN pip install -r backend/requirements.txt

# TECH: the back end (code and config TOML files), the content main.py reads
#   (content/loan-columns.json and the rest), and the built SPA from stage 1.
#   Copied as root and left owned by root, so the loaniq user can read them but
#   not change them.
COPY backend/ backend/
COPY content/ content/
COPY --from=spa /app/frontend/dist frontend/dist

# BUSINESS: the seeded synthetic tape is made once, when the image is built, with
#   the generator's defaults (size and seed in backend/app/config/loan_tape_gen.toml).
#   Every deploy of the same commit serves the same loans, and the server starts fast
#   because it only loads the Parquet file into DuckDB.
# TECH: data/ is not in Git (.gitignore), so the image makes it. The generator writes
#   to <repo>/data, which is /app/data here. -m runs the module the same way you do
#   locally; it must run from backend/ so `app` is importable.
WORKDIR /app/backend
RUN python -m app.loan_tape_gen

# TECH: from here on, everything runs as the non-root user.
USER loaniq
EXPOSE 10000

# TECH: uvicorn serves the FastAPI app on every network interface (0.0.0.0), which a
#   container needs: 127.0.0.1 would only accept connections from inside it.
#   The shell form ("sh -c") is there so ${PORT:-10000} is read when the container
#   starts, not when the image is built: the host's $PORT, or 10000 if it is unset.
#   `exec` replaces the shell with uvicorn, so the host's stop signal (SIGTERM)
#   reaches uvicorn directly and it shuts down cleanly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
