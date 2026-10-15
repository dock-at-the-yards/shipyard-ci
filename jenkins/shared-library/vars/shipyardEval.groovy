// Shipyard evaluation step for Jenkins shared libraries.
//
// shipyard-core is private, so `go install` cannot provision the CLI; the Go
// toolchain rejects a module whose go.mod carries a filesystem replace. The
// CLI is installed from its published release artifacts instead.
//
//   shipyardEval(
//       evalPath:  'evalset/',
//       agent:     'claude-code',
//       model:     'gpt-4o',
//       channel:   'stable',   // stable | test | dev
//       version:   '',         // pin e.g. 'v0.0.2'; empty tracks the channel
//       repeat:    3,          // repeats per eval; k>=3 enables the noise floor
//       baseline:  'baselines/main.json',  // relative to evalPath; delta gate when present
//       junitFile: 'shipyard-junit.xml',   // relative to evalPath for the junit step
//       install:   true        // set false when shipyard is already on PATH
//   )

def call(Map config = [:]) {
    def evalPath  = config.get('evalPath', 'evalset/')
    def agent     = config.get('agent', 'claude-code')
    def model     = config.get('model', '')
    def channel   = config.get('channel', 'stable')
    def version   = config.get('version', '')
    def repeat    = config.get('repeat', 1)
    def baseline  = config.get('baseline', 'baselines/main.json')
    def junitFile = config.get('junitFile', 'shipyard-junit.xml')
    def doInstall = config.get('install', true)

    stage("Shipyard Eval (${agent})") {
        echo "Running Shipyard on ${evalPath} with ${agent} (channel ${channel}, k=${repeat})..."

        if (doInstall) {
            // The installer must receive the configured channel/version: the
            // previous single-quoted script read $CHANNEL/$VERSION, which were
            // never exported, so a pinned version was silently ignored.
            def installArgs = "--channel '${channel}' --yes"
            if (version) {
                installArgs = "--channel '${channel}' --version '${version}' --yes"
            }
            sh """
                set -eu
                if ! apk add --no-cache bash curl ca-certificates >/dev/null 2>&1; then
                    apt-get update && apt-get install -y curl ca-certificates
                fi
                curl -fsSL https://raw.githubusercontent.com/dock-at-the-yards/shipyard-cli/main/install.sh | sh -s -- ${installArgs}
                shipyard version
            """
        }

        def runId = "jenkins-build-${env.BUILD_NUMBER ?: 'local'}"
        def flags = ''
        if (agent) {
            flags += " --agent '${agent}'"
        }
        if (model) {
            flags += " --model '${model}'"
        }
        flags += " --run-id '${runId}' --repeat '${repeat}' --report markdown,json,junit"

        try {
            sh """
                set -u
                run_code=0
                shipyard run '${evalPath}'${flags} || run_code=\$?
                compare_code=0
                if [ -f '${evalPath}${baseline}' ]; then
                    shipyard compare '${evalPath}' \
                        --baseline '${evalPath}${baseline}' \
                        --run-id '${runId}' || compare_code=\$?
                else
                    echo "No baseline at ${evalPath}${baseline}; skipping the delta gate."
                fi
                if [ "\${run_code}" -ne 0 ]; then
                    echo "shipyard run exited \${run_code}"
                    exit "\${run_code}"
                fi
                if [ "\${compare_code}" -ne 0 ]; then
                    echo "shipyard compare exited \${compare_code} (1 = blocked, 2 = usage error)"
                    exit "\${compare_code}"
                fi
            """
        } finally {
            // Publish the JUnit report even when the gate blocked the build.
            junit testResults: "${evalPath}${junitFile}", allowEmptyResults: true
        }
    }
}
