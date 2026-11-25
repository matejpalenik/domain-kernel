#!/usr/bin/env bash
set -euo pipefail

if (( $# > 1 )); then
    echo "Usage: bash check.sh [/path/to/tla2tools.jar]" >&2
    exit 2
fi

scratch="$(mktemp -d "${TMPDIR:-/tmp}/discovery-lease.XXXXXX")"
trap 'rm -rf -- "$scratch"' EXIT

if (( $# == 1 )); then
    jar="$(cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")"
else
    jar="$scratch/tla2tools.jar"
    curl --fail --silent --show-error --location --proto '=https' --retry 2 \
        https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar -o "$jar"
fi

digest="$(shasum -a 256 "$jar")"
if [[ ${digest%% *} != 936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88 ]]; then
    echo "Expected the official TLA+ Tools v1.7.4 jar." >&2
    exit 1
fi

java="${JAVA_HOME:+$JAVA_HOME/bin/}java"
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

run_tlc() {
    local metadir="$1"
    shift
    "$java" -cp "$jar" tlc2.TLC -workers 1 -metadir "$scratch/$metadir" \
        "$@" DiscoveryLeaseTakeover
}

run_tlc intact -config intact.cfg

cp intact.cfg "$scratch/reachable.cfg"
printf '\nINVARIANTS NoOriginalProgress NoTakeoverAtMatchingVersion NoResumedProgress\n' \
    >> "$scratch/reachable.cfg"
if ! run_tlc reachable -continue -config "$scratch/reachable.cfg" > "$scratch/reachable.log" 2>&1; then
    cat "$scratch/reachable.log" >&2
    exit 1
fi
for invariant in NoOriginalProgress NoTakeoverAtMatchingVersion NoResumedProgress; do
    if ! grep -Fq "Invariant $invariant is violated." "$scratch/reachable.log"; then
        cat "$scratch/reachable.log" >&2
        exit 1
    fi
done
echo "Reached original progress, takeover at a matching version, and resumed progress."

if run_tlc guard-disabled -config guard-disabled.cfg > "$scratch/guard-disabled.log" 2>&1; then
    echo "TLC accepted the model with the lease guard disabled." >&2
    exit 1
fi
cat "$scratch/guard-disabled.log"
grep -Fq 'Invariant NoOriginalSaveAfterTakeover is violated.' "$scratch/guard-disabled.log"
grep -Eq '^State 2: <ExpireOriginal ' "$scratch/guard-disabled.log"
grep -Eq '^State 3: <Takeover ' "$scratch/guard-disabled.log"
grep -Eq '^State 4: <CommitCheckpoint ' "$scratch/guard-disabled.log"
grep -Fq 'saved = {"original"}' "$scratch/guard-disabled.log"
