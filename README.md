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

When an autonomous coding or workflow agent regresses on prompt instructions, leaks sensitive variables, or fails deterministic Python scoring rubrics, `shipyard-ci` fails the pipeline and blocks merge.

---

## Supported CI / CD Platforms

| Platform | Location | Description |
| :--- | :--- | :--- |
| **GitHub Actions** | [`action.yml`](action.yml) | Composite action with automated PR markdown comment summaries. |
| **Argo Workflows (WFT)** | [`argo/workflow-template.yaml`](argo/workflow-template.yaml) | Kubernetes-native `WorkflowTemplate` & `CronWorkflow` with S3 rollout archiving. |
| **Jenkins** | [`jenkins/Jenkinsfile`](jenkins/Jenkinsfile) | Declarative multi-stage pipeline + Groovy Shared Library. |
| **GitLab CI** | [`gitlab/.gitlab-ci-shipyard.yml`](gitlab/.gitlab-ci-shipyard.yml) | Docker-in-Docker GitLab runner template with rollout caching. |

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
| `test` | latest `-alpha` / `-beta` / `-rc` | validating a new CLI against your evals before it ships |
| `dev` | latest `-dev` build | debugging the CLI itself |

**Pin an exact version in production.** Track the channel while you integrate, then pin once you are satisfied:

```yaml
uses: dock-at-the-yards/shipyard-ci@v1
with:
  path: 'evalset/'
  channel: 'stable'
  version: 'v0.0.1'   # exact, immutable
```

| Platform | Channel | Version pin |
| :--- | :--- | :--- |
| GitHub Actions | `channel:` input | `version:` input |
| GitLab CI | `SHIPYARD_CHANNEL` variable | `SHIPYARD_VERSION` variable |
| Jenkins | `CHANNEL` parameter | `VERSION` parameter |
| Groovy library | `channel:` config | `version:` config |
| Argo | `ghcr.io/dock-at-the-yards/shipyard-cli:<tag>` | pin the digest |

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

    steps:
      - uses: actions/checkout@v4

      - name: Run Shipyard Gate
        uses: dock-at-the-yards/shipyard-ci@v1
        with:
          path: 'evalset/'
          post-comment: 'true'
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Archive Rollout Trajectories
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: atif-trajectories
          path: evalset/rollouts/
```

---

## 2. Argo Workflows (Kubernetes WFT)

Deploy the `WorkflowTemplate` to your Kubernetes cluster:

```bash
kubectl apply -f argo/workflow-template.yaml
kubectl apply -f argo/cron-workflow.yaml
```

Trigger an ad-hoc run using the Argo CLI:

```bash
argo submit --from wft/shipyard-eval-runner \
  -p eval-path="evalset/order-bot" \
  -p agent-name="claude-code" \
  -p git-repo="https://github.com/my-org/agents.git"
```

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
                shipyardEval(evalPath: 'evalset/', agent: 'claude-code', ci: true)
            }
        }
    }
}
```

---

## Trajectory Rollout Artifacts

Every CI run captures complete **Agent Trajectory Interchange Format (ATIF)** JSON logs, tracking:
- Step-by-step tool invocations (bash, edits, web search).
- Model latency and token usage.
- Itemized Python rubric criteria scores.

---

## License

**Proprietary — all rights reserved.** This repository is not open source and is not licensed under any open source license.

You may **not** copy, reproduce, redistribute, sublicense, publish, fork, mirror, or create derivative works of this software without prior written authorization. See [LICENSE](LICENSE) for the full terms.
