# Shipyard CI ⚓

<p align="center">
  <strong>Enterprise CI/CD Pipelines, GitHub Actions, Argo Workflows, and Jenkins Integrations for Shipyard Agent Evaluations.</strong>
</p>

<p align="center">
  <a href="https://github.com/dock-at-the-yards/shipyard-ci/actions"><img src="https://img.shields.io/badge/CI-Argo%20%7C%20GHA%20%7C%20Jenkins-blueviolet.svg" alt="CI Engines"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Shipyard%20(source--available)-blue.svg" alt="License: Shipyard source-available"></a>
</p>

---

## What is Shipyard CI?

`shipyard-ci` turns AI agent evaluation from exploratory local "vibe checks" into an automated, deterministic **blocking gate in your pull requests and delivery pipelines**.

As of v0.0.2 the gate answers the question that matters on every PR: **"did it get worse?"** Pipelines run each eval k times (`--repeat`), compare the candidate against a committed baseline (`shipyard compare`), and block on regressions, flakes, infra errors, and suite-definition changes. Reports render as Markdown, JSON, and JUnit XML, and the GitHub Action upserts a single sticky delta comment instead of spamming the PR.

When an autonomous coding or workflow agent regresses on prompt instructions, leaks sensitive variables, or fails deterministic Python scoring rubrics, `shipyard-ci` fails the pipeline and blocks merge. Errored repeats are labeled **infra** (never agent failures), and a k≥3 noise floor keeps a stochastic suite from flipping the gate on noise.

---

## Supported CI / CD Platforms

| Platform | Location | Description |
| :--- | :--- | :--- |
| **GitHub Actions** | [`action.yml`](action.yml) | Composite action: repeat-aware run, delta gate against a committed baseline (or a baseline artifact), sticky PR comment, annotations, JUnit + rollout uploads, job summary. |
| **Argo Workflows (WFT)** | [`argo/workflow-template.yaml`](argo/workflow-template.yaml) | Kubernetes-native `WorkflowTemplate` & `CronWorkflow` with repeats and S3 report/rollout archiving. |
| **Jenkins** | [`jenkins/Jenkinsfile`](jenkins/Jenkinsfile) | Declarative multi-stage pipeline + Groovy Shared Library with the repeat loop, JUnit, baseline compare. |
| **GitLab CI** | [`gitlab/.gitlab-ci-shipyard.yml`](gitlab/.gitlab-ci-shipyard.yml) | Docker-in-Docker GitLab runner template with repeat/report flags, baseline compare, JUnit report artifact. |

---

## How the CLI Is Installed

`shipyard-core`, the evaluation engine, is a **private** repository. The CLI depends on it through a filesystem `replace` directive, and the Go toolchain explicitly refuses to `go install` any module whose `go.mod` contains one:

```
The go.mod file for the module providing named packages contains one or
more replace directives. It must not contain directives that would cause
it to be interpreted differently than if it were the main module.
```

So every integration here installs the CLI from its **published release artifacts** via [`shipyard-cli`](https://github.com/dock-at-the-yards/shipyard-cli)'s `install.sh`, which verifies SHA256 checksums. There is no `go install` path, by design.

### Release channels

Every integration accepts a channel so a pipeline can track a moving target or a fixed version:

| Channel | Tracks | Use for |
| :--- | :--- | :--- |
| `stable` (default) | latest non-prerelease | production pipelines |
| `dev` | latest `-dev` build | debugging the CLI itself |

**Pin an exact version in production.** Track the channel while you integrate, then pin once you are satisfied:

```yaml
uses: dock-at-the-yards/shipyard-ci@v1
with:
  path: 'evalset/'
  channel: 'stable'
  version: 'v0.0.2'   # exact, immutable
```

| Platform | Channel | Version pin |
| :--- | :--- | :--- |
| GitHub Actions | `channel:` input | `version:` input |
| GitLab CI | `SHIPYARD_CHANNEL` variable | `SHIPYARD_VERSION` variable |
| Jenkins | `CHANNEL` parameter | `VERSION` parameter |
| Groovy library | `channel:` config | `version:` config |
| Argo | `install.sh --channel` at pod start | `install.sh --version` |

To see exactly what a pipeline ran, `shipyard version` reports the version, the CLI commit, the engine commit it was built against, and the channel.

---

## 1. GitHub Actions Quickstart

Add `.github/workflows/agent-gate.yml` to your repository:

```yaml
name: Agent Regression Gate

on:
  pull_request:
    branches: [main]

jobs:
  shipyard:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      checks: write   # renders the JUnit report in the test pane (report-checks)

    steps:
      - uses: actions/checkout@v4

      - name: Run Shipyard Gate
        uses: dock-at-the-yards/shipyard-ci@v1
        with:
          path: 'evalset/'
          channel: 'stable'
          version: 'v0.0.2'   # pin the CLI; v0.0.2 is the first compare/junit release
          repeat: '3'          # k>=3 enables the 95% t-interval noise floor
          baseline: 'baselines/main.json'
          post-comment: 'true'
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

`repeat: '3'` is the recommended setting: the delta gate only applies the noise margin when either side of the comparison has k≥3 repeats.

### Action inputs

| Input | Default | Description |
| :--- | :--- | :--- |
| `channel` | `stable` | Shipyard release channel to install: `stable`, `test`, or `dev`. |
| `version` | *(empty)* | Pin an exact version, e.g. `v0.0.2`. Empty tracks the channel. |
| `path` | `evalset/` | Path to the eval or evalset directory. |
| `agent` | *(empty)* | Agent override (e.g. `claude-code`, `codex`, `langgraph`). |
| `provider` | *(empty)* | LLM provider override (e.g. `openai`, `anthropic`, `gemini`). |
| `model` | *(empty)* | Model override (e.g. `gpt-4o`, `claude-3-5-sonnet-20241022`). |
| `repeat` | `1` | Repeats per eval (k). k≥3 enables the 95% t-interval noise floor; **3 is recommended**. |
| `baseline` | `baselines/main.json` | Baseline JSON for the delta gate, relative to `path` (so the default resolves to `<path>/baselines/main.json`, the `shipyard baseline save` convention). An explicit workspace-root file is honored when no target-relative one exists. |
| `baseline-artifact` | *(empty)* | Name of an uploaded artifact containing a baseline JSON. Used only when no committed baseline file exists — the baseline-from-artifact fallback. |
| `policy` | *(empty)* | Path to a gate policy TOML passed to `shipyard compare --policy`. Without it, the `[gate]` table in the target manifest (or the defaults) applies. |
| `junit-file` | `shipyard-junit.xml` | Workspace-root path the JUnit XML is copied to for upload. |
| `report-checks` | `true` | Publish the JUnit XML as a check run (`Shipyard evals`) so results render in the GitHub test pane. Needs `checks: write` on the caller; without it the step degrades gracefully. |
| `post-comment` | `true` | Post/upsert the evaluation report as a PR comment. |
| `github-token` | `${{ github.token }}` | Token for posting PR comments. |

### Outputs

| Output | Description |
| :--- | :--- |
| `exit-code` | `shipyard run` exit code (0 = every eval passed). |
| `compare-exit-code` | `shipyard compare` exit code: `0` gate passed, `1` blocked, `2` usage error (empty when compare was skipped). |
| `rollout-dir` | Path to the generated `<path>/rollouts/<run-id>/` directory. |
| `compare-file` | Path to the JSON delta report (`shipyard-compare.json`), empty when compare was skipped. |
| `junit-file` | Workspace-root path of the JUnit XML (empty when the run produced none). |
| `summary-markdown` | The Markdown summary written to the job summary. |

### What the action does on every PR

1. **Run** — `shipyard run <path> --run-id pr-<number> --repeat <k> --report markdown,json,junit`. The run id is stable per PR, so artifacts and the comment update in place on reruns.
2. **Compare (delta gate)** — when a baseline exists, `shipyard compare <path> --baseline <baseline> --run-id pr-<number> --json` (plus `--policy` when set). Exit `1` (blocked) is captured, not thrown: the action still produces reports and annotations, then fails the job at the end with a clear message. Exit `2` (usage error) fails immediately. With no baseline file, compare is skipped with a notice.
3. **Annotate** — every blocking eval gets a GitHub annotation on its eval directory (`::error file=<path>/<eval-name>,line=1`); flakes get `::warning::`; improved/same evals are not annotated. Suite-definition refusals surface as a suite-mismatch annotation naming the changed evals and files.
4. **Reports** — the run's `shipyard-report.md`, plus the delta table rendered from the compare output, are written to `$GITHUB_STEP_SUMMARY` and returned as `summary-markdown`.
5. **Artifacts** — the JUnit XML (`shipyard-junit-<run_id>`) and `<path>/rollouts/` (`shipyard-rollouts-<run_id>`) are uploaded with `if: always()`.
6. **Sticky comment** — a single comment marked `<!-- shipyard-report -->` is created and then **updated in place** on reruns (never a new comment). It contains the run report, the delta table, and a link to the workflow run and artifacts. Over-long reports are truncated gracefully below GitHub's 64 KiB comment limit.
7. **Gate** — the action fails when `shipyard run` failed or `shipyard compare` returned `1` (blocked). Posting a comment never changes the gate outcome.

### Baselines

A baseline is a committed, schema-stable snapshot of a green `main` run:

```bash
shipyard run evalset/ --repeat 3
shipyard baseline save evalset/ --name main   # writes evalset/baselines/main.json
git add evalset/baselines/main.json
```

Baselines carry the suite digest they were taken from. If an instruction, rubric, or environment file changes, `shipyard compare` **refuses** to compare different suites (exit `1` with a message naming the changed eval and files) unless `--allow-suite-mismatch` is passed — a baseline is only meaningful against the suite it measured.

**Regenerating a baseline is a `main`-only operation.** [`examples/baseline-regeneration.yml`](examples/baseline-regeneration.yml) runs the suite with `--repeat 3`, saves `baselines/main.json`, and opens a pull request with the refreshed baseline (the run's own delta against the previous baseline becomes the PR body). The workflow is guarded on `github.ref == 'refs/heads/main'`, so no other branch can rewrite the reference results.

**No committed baseline? Use an artifact.** If a repository cannot commit a baseline (for example, because the eval suite lives in a separate private repo), the action can restore one from a previous run's upload:

```yaml
- name: Fetch the current baseline artifact
  uses: actions/download-artifact@v4      # upload it from a main-only job
  with:
    name: shipyard-baseline
    path: evalset/baselines/
```

or, entirely inside the action:

```yaml
- uses: dock-at-the-yards/shipyard-ci@v1
  with:
    baseline-artifact: 'shipyard-baseline'   # downloaded only when no committed file exists
```

The artifact is copied into place at the resolved baseline path before the delta gate runs. When neither a committed baseline nor an artifact exists, the action proceeds and skips compare with a notice.

---

## 2. Argo Workflows (Kubernetes WFT)

Deploy the `WorkflowTemplate` to your Kubernetes cluster:

```bash
kubectl apply -f argo/workflow-template.yaml
kubectl apply -f argo/cron-workflow.yaml
```

Trigger an ad-hoc run using the Argo CLI (`repeat` defaults to `3`):

```bash
argo submit --from wft/shipyard-eval-runner \
  -p eval-path="evalset/order-bot" \
  -p agent-name="claude-code" \
  -p repeat="3" \
  -p git-repo="https://github.com/my-org/agents.git"
```

The pod runs `shipyard run ... --repeat <k> --report markdown,json,junit` and archives both the ATIF rollouts and the reports to S3. Argo has no PR-comment surface, so the gate is the exit code, and the compare step is wired in as a follow-up (see the comment in the template) that reads `baselines/main.json` when the repo commits one.

---

## 3. Jenkins Pipeline

In your Jenkins Pipeline job or multibranch pipeline, point to [`jenkins/Jenkinsfile`](jenkins/Jenkinsfile), or import the shared library step:

```groovy
@Library('shipyard-shared-library') _

pipeline {
    agent any
    stages {
        stage('Eval') {
            steps {
                shipyardEval(
                    evalPath: 'evalset/',
                    agent: 'claude-code',
                    repeat: 3,                                // k>=3 enables the noise floor
                    baseline: 'baselines/main.json',          // delta gate when the file exists
                    junitFile: 'shipyard-junit.xml',          // published via the junit step
                    version: 'v0.0.2'
                )
            }
        }
    }
}
```

The bundled `Jenkinsfile` takes the same settings as build parameters (`EVAL_PATH`, `AGENT`, `MODEL`, `CHANNEL`, `VERSION`, `REPEAT`, `BASELINE`, `JUNIT_FILE`), publishes the JUnit report to the test pane, archives the Markdown/JSON reports plus rollouts, and fails the build when either the run or the delta gate fails.

---

## 4. GitLab CI

Include the template in `.gitlab-ci.yml`:

```yaml
include:
  - remote: 'https://raw.githubusercontent.com/dock-at-the-yards/shipyard-ci/main/gitlab/.gitlab-ci-shipyard.yml'
```

Tune per project with variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `SHIPYARD_CHANNEL` | `stable` | Release channel to install. |
| `SHIPYARD_VERSION` | *(empty)* | Pin an exact version, e.g. `v0.0.2`. |
| `SHIPYARD_REPEAT` | `1` | Repeats per eval; `3` enables the noise floor. |
| `SHIPYARD_BASELINE` | `baselines/main.json` | Baseline relative to `EVAL_PATH`; the delta gate runs when the file exists. |
| `EVAL_PATH` | `evalset/` | Eval or evalset directory. |
| `AGENT` | `claude-code` | Agent override. |

The job runs with `--run-id gitlab-$CI_PIPELINE_ID --report markdown,json,junit`, gates on the baseline when present, publishes the JUnit report through GitLab's `artifacts:reports:junit`, and keeps the reports and rollouts as job artifacts for 14 days.

---

## Trajectory Rollout Artifacts

Every CI run captures complete **Agent Trajectory Interchange Format (ATIF)** JSON logs, tracking:
- Step-by-step tool invocations (bash, edits, web search).
- Model latency and token usage.
- Itemized Python rubric criteria scores.

Rollouts live at `<path>/rollouts/<run-id>/` (one directory per repeat), and each run also writes `results.json` (suite results), `shipyard-report.md` / `shipyard-report.json` / `shipyard-junit.xml` (reports), and `shipyard-compare.json` (delta gate output) at the eval root.

---

## License

**Proprietary — all rights reserved.** This repository is not open source and is not licensed under any open source license.

You may **not** copy, reproduce, redistribute, sublicense, publish, fork, mirror, or create derivative works of this software without prior written authorization. See [LICENSE](LICENSE) for the full terms.
