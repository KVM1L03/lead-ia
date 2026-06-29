# Branch Protection Settings

Agent workflow: feature branch → PR → CI → human review → merge. See `CLAUDE.md` §5.

These settings must be applied manually in **GitHub → Settings → Branches →
Branch protection rules** for the `main` branch. They cannot be committed to
the repo.

## Required rules for `main`

| Setting | Value |
|---|---|
| Require a pull request before merging | ✅ enabled |
| Required approving reviews | 1 |
| Require status checks to pass before merging | ✅ enabled |
| Required status checks | `python`, `frontend` |
| Require branches to be up to date before merging | ✅ enabled |
| Allow force pushes | ❌ disabled |
| Allow deletions | ❌ disabled |
| Do not allow bypassing the above settings | ✅ enabled |

## How to apply

1. Go to `https://github.com/KVM1L03/lead-forge/settings/branches`
2. Click **Add rule** (or edit existing rule for `main`)
3. Set **Branch name pattern** to `main`
4. Enable each setting from the table above
5. Click **Save changes**

## Why this file exists

GitHub branch protection rules are not stored in the repository. This document
ensures the intended settings are reproducible and visible in code review,
even though they must be applied through the GitHub UI.

## Status check names

The check names `python` and `frontend` correspond to the `name:` fields of
the jobs defined in `.github/workflows/ci.yml`. If those job names change,
update the required status checks here and in GitHub settings.
