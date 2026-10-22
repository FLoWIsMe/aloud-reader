#!/bin/sh
# Make the data folder writable by the app user, then drop root. A bind-mounted ./data on
# Linux is created root-owned by Docker, which would otherwise stop the first start.
set -e

DATA_DIR="${ALOUD_DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
    if [ -n "$PUID" ] && [ "$PUID" != "$(id -u aloud)" ]; then
        usermod -o -u "$PUID" aloud >/dev/null 2>&1 || true
    fi
    if [ -n "$PGID" ] && [ "$PGID" != "$(id -g aloud)" ]; then
        groupmod -o -g "$PGID" aloud >/dev/null 2>&1 || true
    fi
    mkdir -p "$DATA_DIR/models" "$DATA_DIR/cache"
    # Only the top level and the model files are touched; the cache can hold thousands of files.
    chown aloud:aloud "$DATA_DIR" "$DATA_DIR/models" "$DATA_DIR/cache" 2>/dev/null || true
    find "$DATA_DIR" -maxdepth 2 -type f ! -user aloud -exec chown aloud:aloud {} + 2>/dev/null || true
    exec gosu aloud "$@"
fi

exec "$@"
