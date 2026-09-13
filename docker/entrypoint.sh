#!/usr/bin/env bash
# markdown-gost container entrypoint.
#
# Starts unoserver in the background on ${UNOSERVER_HOST}:${UNOSERVER_PORT},
# waits for it to accept connections, then exec's the command passed in.
#
# unoserver is required by the PDF pipeline (DOCX -> PDF) and by the
# screenshot test harness. Even for CLI-only invocations we start it so that
# `markdown-gost convert ... -f pdf` works without extra wiring.
set -euo pipefail

UNOSERVER_HOST="${UNOSERVER_HOST:-127.0.0.1}"
UNOSERVER_PORT="${UNOSERVER_PORT:-2003}"
UNOSERVER_UNO_PORT="${UNOSERVER_UNO_PORT:-2002}"
LO_USER_PROFILE="${LO_USER_PROFILE:-/tmp/lo-profile}"
RUNTIME_DIR="${MARKDOWN_GOST_RUNTIME_DIR:-/tmp/markdown-gost-runtime}"
UNOSERVER_LOG="${RUNTIME_DIR}/unoserver.log"
UNOSERVER_PID_FILE="${RUNTIME_DIR}/unoserver.pid"

mkdir -p "${RUNTIME_DIR}" "${LO_USER_PROFILE}" "${HOME:-/tmp/md2gost-home}"

log() { echo "[entrypoint] $*" >&2; }

start_unoserver() {
    log "starting unoserver on ${UNOSERVER_HOST}:${UNOSERVER_PORT} (uno ${UNOSERVER_UNO_PORT})"
    # unoserver 3.x expects a plain absolute path here and converts it to a
    # file:// URI internally. Passing a file:// URI directly raises
    # "relative path can't be expressed as a file URI" inside Path.as_uri().
    /usr/bin/python3 -m unoserver.server \
        --interface "${UNOSERVER_HOST}" \
        --port "${UNOSERVER_PORT}" \
        --uno-interface "${UNOSERVER_HOST}" \
        --uno-port "${UNOSERVER_UNO_PORT}" \
        --user-installation "${LO_USER_PROFILE}" \
        >"${UNOSERVER_LOG}" 2>&1 &
    UNOSERVER_PID=$!
    echo "${UNOSERVER_PID}" >"${UNOSERVER_PID_FILE}"
}

wait_for_unoserver() {
    local i
    for i in $(seq 1 60); do
        if nc -z "${UNOSERVER_HOST}" "${UNOSERVER_PORT}" 2>/dev/null; then
            log "unoserver is ready (after ${i}s)"
            return 0
        fi
        sleep 1
    done
    log "ERROR: unoserver did not come up within 60s"
    if [[ -f "${UNOSERVER_LOG}" ]]; then
        log "--- last 50 lines of ${UNOSERVER_LOG} ---"
        tail -n 50 "${UNOSERVER_LOG}" >&2 || true
    fi
    return 1
}

cleanup() {
    if [[ -f "${UNOSERVER_PID_FILE}" ]]; then
        local pid
        pid="$(cat "${UNOSERVER_PID_FILE}")"
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            log "stopping unoserver (pid ${pid})"
            kill -TERM "${pid}" 2>/dev/null || true
        fi
    fi
}
trap cleanup EXIT INT TERM

start_unoserver
wait_for_unoserver

if [[ $# -eq 0 ]]; then
    log "no command supplied — sleeping forever"
    exec tail -f /dev/null
fi

log "exec: $*"
exec "$@"
