# Ephemeral self-hosted runner

Runs a GitHub Actions runner that handles **one job then exits** and re-registers.
No always-on heavy daemon; only the lightweight loop stays resident.

## Usage

```bash
export REPO="owner/repo"
export TOKEN="ghp_..."   # PAT with repo scope
export RUNNER_DIR="$HOME/actions-runner"
./ephemeral/runner-loop.sh
```

## As a service

- macOS: wrap in a `launchd` plist that runs at login.
- Linux/RPi: wrap in a `systemd` unit with `Restart=always`.

## Notes

- `--ephemeral` makes the runner auto-unregister after one job.
- For truly event-triggered (no polling), front this with a webhook listener
  that starts the loop only on `workflow_job` queued events.
