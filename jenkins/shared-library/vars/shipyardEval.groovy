// Shipyard evaluation step for Jenkins shared libraries.
//
// shipyard-core is private, so `go install` cannot provision the CLI; the Go
// toolchain rejects a module whose go.mod carries a filesystem replace. The
// CLI is installed from its published release artifacts instead.
//
//   shipyardEval(
//       evalPath: 'evalset/',
//       agent:    'claude-code',
//       model:    'gpt-4o',
//       channel:  'stable',   // stable | test | dev
//       version:  '',         // pin e.g. 'v0.1.0'; empty tracks the channel
//       install:  true        // set false when shipyard is already on PATH
//   )

def call(Map config = [:]) {
    def evalPath = config.get('evalPath', 'evalset/')
    def agent    = config.get('agent', 'claude-code')
    def model    = config.get('model', '')
    def channel  = config.get('channel', 'stable')
    def version  = config.get('version', '')
    def doInstall = config.get('install', true)

    stage("Shipyard Eval (${agent})") {
        echo "Running Shipyard on ${evalPath} with ${agent} (channel ${channel})..."

        if (doInstall) {
            sh '''
                set -eu
                apk add --no-cache bash curl ca-certificates >/dev/null 2>&1 || \
                    (apt-get update && apt-get install -y curl ca-certificates)
                set -- --channel "$CHANNEL" --yes
                if [ -n "$VERSION" ]; then set -- "$@" --version "$VERSION"; fi
                curl -fsSL https://raw.githubusercontent.com/dock-at-the-yards/shipyard-cli/main/install.sh | sh -s -- "$@"
                shipyard version
            '''
        }

        def flags = ""
        if (agent) flags += " --agent ${agent}"
        if (model) flags += " --model ${model}"
        flags += " --run-id \"jenkins-build-${env.BUILD_NUMBER ?: 'local'}\""

        sh """
            set -eu
            shipyard run '${evalPath}'${flags}
        """
    }
}
