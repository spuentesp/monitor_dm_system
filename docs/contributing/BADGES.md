# Badge Setup

This document covers the two badges that require one-time external setup.

---

## 1. Coverage badge (Codecov)

Codecov is free for public repos.

1. Sign up at <https://codecov.io> and connect the `spuentesp/monitor_dm_system` repository.
2. Copy the upload token from the Codecov dashboard.
3. Add it as a GitHub Actions secret named `CODECOV_TOKEN` (repo → Settings → Secrets and variables → Actions).
4. The coverage badge in `README.md` is already wired up — it will start rendering after the next `CI` run.

---

## 2. Mutation score badge (dynamic, via Gist)

The `Mutation Tests` workflow computes a kill rate from cosmic-ray and writes it
to a public GitHub Gist as a shields.io endpoint JSON. This gives a live
percentage badge without needing any third-party service.

### One-time setup

1. **Create a public Gist** at <https://gist.github.com> with a file named `mutation-score.json` containing:
   ```json
   { "schemaVersion": 1, "label": "mutation score", "message": "pending", "color": "lightgrey" }
   ```
   Note the Gist ID from the URL (the alphanumeric string after `gist.github.com/spuentesp/`).

2. **Create a fine-grained PAT** at GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens.
   - Scopes needed: **Gists** (read + write).
   - No repository access required.

3. **Add two GitHub Actions secrets** (repo → Settings → Secrets and variables → Actions):
   | Secret name | Value |
   |---|---|
   | `GIST_TOKEN` | The PAT from step 2 |
   | `MUTATION_GIST_ID` | The Gist ID from step 1 |

4. **Uncomment the badge line** in `README.md`:
   ```markdown
   [![Mutation Score](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/spuentesp/YOUR_GIST_ID/raw/mutation-score.json)](...)
   ```
   Replace `YOUR_GIST_ID` with the actual ID.

After the next `Mutation Tests` run (weekly Sunday 3 AM UTC, or trigger manually via workflow_dispatch), the badge will update automatically.

---

## Badge reference

| Badge | Source | Requires setup |
|---|---|---|
| CI | GitHub Actions `ci.yml` | No |
| Nightly Integration | GitHub Actions `nightly-integration.yml` | No |
| Contract Tests | GitHub Actions `contract-tests.yml` | No |
| Property Tests | GitHub Actions `property-tests.yml` | No |
| Behavior Tests | GitHub Actions `behavior-tests.yml` | No |
| Mutation Tests | GitHub Actions `mutation.yml` | No (run status only) |
| Coverage % | Codecov | Yes — `CODECOV_TOKEN` secret |
| Mutation score % | shields.io + GitHub Gist | Yes — `GIST_TOKEN` + `MUTATION_GIST_ID` secrets |
| Python / License / etc. | shields.io static | No |
