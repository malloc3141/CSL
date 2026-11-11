#!/usr/bin/env bash
# Update the server checkout to a commit, rebuild, restart, health-check.
#
# Run by .github/workflows/deploy.yml on the self-hosted runner (user `csl`). To redeploy, use
# "Run workflow" in the Actions tab. By hand on the server the repo is private, so the fetch needs a token:
#   gh auth token | sudo -u csl -H bash -c 'GITHUB_TOKEN=$(cat) bash /home/csl/CSL/deploy/deploy.sh origin/main'
#
# The checkout in $DEPLOY_DIR is a plain clone of the repo. backend/.env, frontend/.env.production,
# backend/data/ (the event log), .venv, node_modules and .next are gitignored and survive the reset.
set -euo pipefail

REV="${1:?usage: deploy.sh <commit-sha|origin/main>}"
DEPLOY_DIR="${DEPLOY_DIR:-/home/csl/CSL}"
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0

cd "$DEPLOY_DIR"
echo "::group::git $(git rev-parse --short HEAD) -> $REV"
if [ -n "${GITHUB_TOKEN:-}" ]; then
  # Same mechanism as actions/checkout: the job token goes in a header, never in the URL or in .git/config.
  auth="$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w0)"
  git -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $auth" fetch --quiet origin main
else
  git fetch --quiet origin main
fi
git reset --hard --quiet "$REV"
git log -1 --oneline
echo "::endgroup::"

echo "::group::backend: uv sync"
cd "$DEPLOY_DIR/backend"
uv sync
echo "::endgroup::"

echo "::group::frontend: pnpm install + build"
cd "$DEPLOY_DIR/frontend"
corepack pnpm install --frozen-lockfile
corepack pnpm build
echo "::endgroup::"

echo "::group::restart"
sudo -n /usr/bin/systemctl restart csl-backend csl-frontend
for _ in $(seq 1 30); do
  if curl -fs -o /dev/null http://127.0.0.1:8000/api/health && curl -fs -o /dev/null http://127.0.0.1:3100/dev; then
    curl -fsS http://127.0.0.1:8000/api/health
    echo
    echo "deployed $(git -C "$DEPLOY_DIR" rev-parse --short HEAD)"
    echo "::endgroup::"
    exit 0
  fi
  sleep 1
done
echo "::endgroup::"
echo "::error::health check failed after restart; see journalctl -u csl-backend -u csl-frontend"
exit 1
