#!/usr/bin/env bash
set -Eeuo pipefail
if [[ ${1:-} == --help ]]; then
    echo 'Usage: sudo ./update.sh'
    echo 'Upgrade an existing appliance and enable the password-protected web UI.'
    echo 'Retains Paperless credentials, jobs, SSH and network settings. Run while scanner is idle.'
    exit 0
fi
[[ $# -eq 0 ]] || { echo 'Unknown option.' >&2; exit 2; }
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec bash "$project_dir/install.sh" --update
