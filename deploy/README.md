# Mentor AI — Deployment & Workflow Manifests

This directory contains deployment scripts and GitHub Actions workflows for production operations.

## GitHub Actions Workflows

Located in `deploy/github-workflows/`:
1. `notification-dispatch.yml`: Persistent Notification Engine cron runner (triggers `POST /api/v1/notifications/dispatch` every 15 minutes).
2. `ci.yml`: Continuous Integration pipeline for running backend pytest and frontend build/tests.

### Enabling Workflows in GitHub Actions

GitHub requires OAuth tokens to have the `workflow` scope to modify `.github/workflows/`. If your local GitHub CLI token does not have this scope:

```bash
# 1. Grant workflow scope to GitHub CLI
gh auth refresh -s workflow

# 2. Copy workflows to .github/
mkdir -p .github/workflows
cp deploy/github-workflows/*.yml .github/workflows/

# 3. Commit and push
git add .github/
git commit -m "ci: activate github actions workflows"
git push origin main
```

### GitHub Secrets Required

Configure the following secret in your GitHub repository (`Settings > Secrets and variables > Actions`):
- `NOTIFICATION_DISPATCH_SECRET`: The matching secret configured in the Render backend environment for securing the dispatch endpoint.
