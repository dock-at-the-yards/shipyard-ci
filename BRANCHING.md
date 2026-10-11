# Branching strategy

Three long-lived branches, one per environment. Code moves up exactly one tier
at a time, and never down.

```
  feature/*  ──PR──▶  develop  ──PR──▶  staging  ──PR──▶  main
             dev         dev              test          prod
```

| Branch | Environment | Purpose |
|---|---|---|
| `develop` | integration | day-to-day work lands here |
| `staging` | pre-production | templates exercised against a real pipeline |
| `main` | production | what consumers copy |

## What "production" means here

`shipyard-ci` publishes no versioned artifacts and runs no long-lived service.
Nothing is deployed, so the tiers are not about environments in the usual sense.

The production surface is the **templates themselves**: `action.yml`, the Argo
workflows, the GitLab CI config, the Jenkinsfile and its shared library. People
copy these into their own pipelines, so a consumer reading `main` is copying
code that will run in their CI and gate their releases.

That makes `staging` worth having for one specific reason: it is where a template
gets pointed at a real pipeline and observed to work before `main` recommends it
to everyone. A `main` that skipped that step is asking consumers to be the first
to find out.

## Working on a change

```bash
git checkout develop && git pull
git checkout -b feat/short-description
# ... work ...
git push -u origin feat/short-description
gh pr create --base develop
```

Feature branches are throwaway. Nothing long-lived forks from `main`.

## Promoting

```bash
# develop -> staging
gh workflow run promote.yml --repo dock-at-the-yards/shipyard-ci -f target=staging

# staging -> main
gh workflow run promote.yml --repo dock-at-the-yards/shipyard-ci -f target=production
```

The workflow refuses to skip a tier, so `develop` cannot reach `main` directly.

## Fixing something in production

```bash
git checkout main && git pull
git checkout -b fix/the-thing
# ... fix ...
git push -u origin fix/the-thing
gh pr create --base main --title "fix: the thing"

git checkout develop && git merge main && git push
git checkout staging && git merge develop && git push
```

A broken template on `main` is worth fixing this way rather than by pushing to
`develop` and promoting, because consumers may already have copied it.

## CI, and where it runs

CI runs on a GitHub-hosted runner. The whole job is a few seconds of YAML
parsing and shell syntax checking, so there is nothing here that a self-hosted
runner would make faster, and keeping the Pi out of it leaves that machine free
for the repositories whose builds actually take minutes.

| Check | What it catches |
|---|---|
| Parse every YAML file | a syntax error in a template, which otherwise surfaces only when someone adopts it |
| Validate the composite action | a missing `runs` key, an input with no description, or a composite action with no steps |
| Byte-compile `report_generator.py` | syntax errors and bad imports, without needing a real `rollouts/` directory |
| Check nothing generated is committed | a stale `__pycache__`; requires `.gitignore` to cover it |
| Shell scripts parse | `bash -n` over tracked `*.sh` |

There is no build and no test suite in the usual sense — this repository is
templates and one script. Validating that each template is well-formed and
internally consistent is the useful equivalent, and it is what CI does.

Groovy and the Jenkins shared library are not type-checked here; there is no
Jenkinsfile linter in the workflow, so changes to `jenkins/` are reviewed by eye.

## Branch protection

`main` and `staging` require a pull request and a passing
`CI / Validate templates`, with no force-push and no deletion. `develop` allows
direct pushes, since that is where work lands, but still blocks force-push and
deletion.
