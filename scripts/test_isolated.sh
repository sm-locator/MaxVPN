#!/usr/bin/env bash
set -euo pipefail

root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
scratch="$(mktemp -d /tmp/maxvpn-test.XXXXXXXX)"
project="maxvpn-test-$(printf '%s' "${scratch##*.}" | tr '[:upper:]' '[:lower:]')"
image_override="${MAXVPN_TEST_IMAGE:-}"
export MAXVPN_TEST_IMAGE="${image_override:-$project-backend}"
export MAXVPN_TEST_SOURCE="$scratch/source"
export MAXVPN_TEST_UID="$(id -u)"
export MAXVPN_TEST_GID="$(id -g)"
export MAXVPN_TEST_PASSWORD
MAXVPN_TEST_PASSWORD="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"

compose=(
    docker compose --env-file /dev/null
    --project-name "$project" --file "$root/compose.test.yml"
)

cleanup() {
    local status=$?
    trap - EXIT
    "${compose[@]}" down --volumes || status=1
    if [[ -z "$image_override" ]] && docker image inspect "$MAXVPN_TEST_IMAGE" >/dev/null 2>&1; then
        docker image rm "$MAXVPN_TEST_IMAGE" >/dev/null || status=1
    fi
    rm -rf -- "$scratch"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

mkdir "$MAXVPN_TEST_SOURCE"
# Include current edits to tracked files, but keep local .env, backups and keys
# outside the Docker build context and the read-only test source mount.
(
    cd "$root"
    git ls-files --cached --deduplicate -z |
        while IFS= read -r -d '' path; do
            if [[ -e "$path" || -L "$path" ]]; then
                printf '%s\0' "$path"
            fi
        done |
        tar --null --exclude=.env --no-recursion -T - -cf -
) | tar -xf - -C "$MAXVPN_TEST_SOURCE"

if [[ -n "$image_override" ]]; then
    docker image inspect "$image_override" >/dev/null
else
    "${compose[@]}" build backend-tests
fi

"${compose[@]}" up -d --wait --wait-timeout 60 database
source "$root/scripts/verify_upgrade.sh"
verify_upgrade
status=0
"${compose[@]}" run --rm -T --no-deps backend-tests bash -euc '
    (cd backend && python -m alembic upgrade head)
    exec python -m pytest -q -p no:cacheprovider "$@"
' bash "$@" </dev/null || status=$?
"${compose[@]}" run --rm -T --no-deps appliance-tests </dev/null || status=$?
exit "$status"
