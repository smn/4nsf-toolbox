#!/bin/sh
# Run a CeGCC (arm-mingw32ce) tool: natively if CEGCC points at an installed
# toolchain, otherwise inside the Docker image with the repository mounted.
#
#   Devkit/cegcc.sh arm-mingw32ce-gcc -O2 -o hello.exe hello.c
#   CEGCC=/opt/cegcc-arm Devkit/cegcc.sh arm-mingw32ce-g++ ...
#   CEGCC_IMAGE=ghcr.io/palian-tech/cegcc:v16.2.0-ce.4 Devkit/cegcc.sh ...
#
# Images: ghcr.io/enlyze/windows-ce-build-environment-arm:latest (GCC 9.3.0,
# the default) or ghcr.io/palian-tech/cegcc:v16.2.0-ce.4 (GCC 16, win32
# threads, gdb). Both target arm-mingw32ce = Windows CE 6/7 on ARMv4+.
set -e
REPO=$(cd "$(dirname "$0")/.." && pwd)
if [ -n "${CEGCC:-}" ]; then
  PATH="$CEGCC/bin:$PATH" exec "$@"
fi
IMAGE=${CEGCC_IMAGE:-ghcr.io/enlyze/windows-ce-build-environment-arm:latest}
# paths given relative to the current directory keep working: the repository
# is mounted at the same absolute path inside the container
exec docker run --rm -v "$REPO:$REPO" -w "$(pwd)" -u "$(id -u):$(id -g)" "$IMAGE" "$@"
