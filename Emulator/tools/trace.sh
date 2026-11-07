#!/bin/sh
# Attach the CE API tracer to the running VM (QEMU started with -gdb tcp:127.0.0.1:1234).
# Usage: tools/trace.sh OUT.log   (Ctrl-C to stop)
HERE=$(cd "$(dirname "$0")" && pwd)
LOG=${1:-trace.log}
: > "$LOG"
COREDLL_EXPORTS="$HERE/coredll_exports.txt" exec gdb-multiarch -batch -ex "set pagination off" \
  -ex "set architecture arm" -ex "set arm fallback-mode arm" -ex "set logging file $LOG" \
  -ex "target remote 127.0.0.1:1234" -ex "source $HERE/trace.gdb.py"
