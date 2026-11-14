#!/usr/bin/env bash
# Sourced by test_isolated.sh after the disposable database becomes healthy.
# Never takes a production connection URL. Dumps/evidence stay in private /tmp.
verify_upgrade() {
    mkdir "$scratch/evidence"
    local restore_url="postgresql+psycopg://maxvpn_test:$MAXVPN_TEST_PASSWORD@database:5432/maxvpn_restore_test"
    local revision
    for revision in c5c9faf426ba 2a6f19c4b8d1; do
        "${compose[@]}" run --rm -T --no-deps -e MAXVPN_DISPOSABLE_DATABASE=1 \
            backend-tests python scripts/verify_upgrade.py seed "$revision"
        verify_upgrade_case "$revision" "$restore_url"
    done
    # An optional existing local dump is copied only into this disposable DB.
    if [[ -n "${MAXVPN_UPGRADE_DUMP:-}" ]]; then
        "${compose[@]}" run --rm -T --no-deps -e MAXVPN_DISPOSABLE_DATABASE=1 \
            backend-tests python scripts/verify_upgrade.py reset
        "${compose[@]}" exec -T database pg_restore -U maxvpn_test -d maxvpn_test \
            --no-owner --no-privileges --exit-on-error < "$MAXVPN_UPGRADE_DUMP"
        verify_upgrade_case local-dump "$restore_url"
    fi
    "${compose[@]}" run --rm -T --no-deps -e MAXVPN_DISPOSABLE_DATABASE=1 \
        backend-tests python scripts/verify_upgrade.py reset
}

verify_upgrade_case() {
    local label="$1" restore_url="$2"
    local evidence="$scratch/evidence"
    local runner=("${compose[@]}" run --rm -T --no-deps -e MAXVPN_DISPOSABLE_DATABASE=1
        --volume "$evidence:/evidence")
    "${runner[@]}" backend-tests python scripts/verify_upgrade.py snapshot "/evidence/$label.json"
    "${compose[@]}" exec -T database pg_dump -U maxvpn_test -d maxvpn_test \
        --format=custom --no-owner --no-privileges > "$evidence/$label.dump"
    chmod 600 "$evidence/$label.dump"
    "${runner[@]}" backend-tests python scripts/verify_upgrade.py upgrade-verify "/evidence/$label.json"
    "${compose[@]}" exec -T database createdb -U maxvpn_test maxvpn_restore_test
    "${compose[@]}" exec -T database pg_restore -U maxvpn_test -d maxvpn_restore_test \
        --no-owner --no-privileges --exit-on-error < "$evidence/$label.dump"
    "${runner[@]}" -e ALEMBIC_DATABASE_URL="$restore_url" -e DATABASE_URL="$restore_url" \
        backend-tests python scripts/verify_upgrade.py verify "/evidence/$label.json"
    "${runner[@]}" -e ALEMBIC_DATABASE_URL="$restore_url" -e DATABASE_URL="$restore_url" \
        backend-tests python scripts/verify_upgrade.py upgrade-verify "/evidence/$label.json"
    "${compose[@]}" exec -T database dropdb -U maxvpn_test maxvpn_restore_test
    printf 'Upgrade and backup/restore verified: %s\n' "$label"
}
