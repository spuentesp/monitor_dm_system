# Badge Setup

This document covers the badge that requires one-time external setup.

---

## 1. Coverage badge (Codecov)

Codecov is free for public repos.

1. Sign up at <https://codecov.io> and connect the `spuentesp/monitor_dm_system` repository.
2. Copy the upload token from the Codecov dashboard.
3. Add it as a GitHub Actions secret named `CODECOV_TOKEN` (repo → Settings → Secrets and variables → Actions).
4. The coverage badge in `README.md` is already wired up — it will start rendering after the next `CI` run.

---

## Badge reference

| Badge | Source | Requires setup |
|---|---|---|
| CI | GitHub Actions `ci.yml` | No |
| Weekly Integration | GitHub Actions `nightly-integration.yml` | No |
| Coverage % | Codecov | Yes — `CODECOV_TOKEN` secret |
| Python / License / etc. | shields.io static | No |
