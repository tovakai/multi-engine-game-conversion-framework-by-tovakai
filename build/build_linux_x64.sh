#!/usr/bin/env bash
set -euo pipefail
exec bash "$(dirname "$0")/build_linux.sh" linux-x64
