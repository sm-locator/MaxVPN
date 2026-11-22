"""Backend/UI recovery contract for VLESS availability.

All observations use disposable in-memory SQLite.
No router access, routing actions or deployments.
"""

import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from appliance.maxvpn import vless_control as vc

APPLIANCE = Path(__file__).resolve().parents[1]


@pytest.fixture
def recovery_states():
    now = datetime.now(timezone.utc)

    db = sqlite3.connect(":memory:")
    db.execute("""
        CREATE TABLE checks (
            profile INTEGER NOT NULL,
            at TEXT NOT NULL,
            source TEXT NOT NULL,
            delay INTEGER,
            PRIMARY KEY (profile, at)
        ) WITHOUT ROWID
        """)

    def add(seconds_ago, source, delay):
        stamp = (now - timedelta(seconds=seconds_ago)).isoformat(
            timespec="microseconds"
        )

        vc.VlessControl._add_check(db, 1, stamp, source, delay)

    def state():
        return vc.VlessControl._profile_availability(db, "1", now)

    try:
        add(180, "urltest", 64)
        add(120, "manual", None)
        failed = state()

        add(30, "urltest", 52)
        recovered = state()

        add(110, "manual", None)
        late = state()

        add(15, "manual", None)
        second_failure = state()

        add(15, "urltest", 70)
        same_time = state()

        yield {
            "failed": failed,
            "recovered": recovered,
            "late": late,
            "second_failure": second_failure,
            "same_time": same_time,
        }
    finally:
        db.close()


def test_backend_recovery_precedence(recovery_states):
    states = recovery_states

    failed = states["failed"]
    assert failed["status"] == "no_result"
    assert failed["first_failed_at"] is not None

    recovered = states["recovered"]
    assert recovered["status"] == "reachable"
    assert recovered["first_failed_at"] is None
    assert recovered["source"] == "urltest"
    assert recovered["delay_ms"] == 52
    assert recovered["last_recovered_at"] is not None
    assert recovered["last_outage_duration_seconds"] == 90

    late = states["late"]
    assert late["status"] == "reachable"
    assert late["first_failed_at"] is None
    assert late["delay_ms"] == 52

    second_failure = states["second_failure"]
    assert second_failure["status"] == "no_result"
    assert second_failure["first_failed_at"] is not None

    same_time = states["same_time"]
    assert same_time["status"] == "reachable"
    assert same_time["first_failed_at"] is None
    assert same_time["delay_ms"] == 70


JS_CONTRACT = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html = fs.readFileSync(process.argv[1], 'utf8');
const states = JSON.parse(fs.readFileSync(0, 'utf8'));

function extract(name) {
  const start = html.indexOf(`function ${name}(`);
  assert(start >= 0, `Missing function: ${name}`);

  const rest = html.slice(start);
  const next = rest.match(
    /\n(?:async\s+)?function\s+[A-Za-z_$][\w$]*\s*\(/
  );
  assert(next, `Missing boundary: ${name}`);
  return rest.slice(0, next.index);
}

const names = [
  'formatVlessDuration',
  'formatVlessTimestamp',
  'vlessIntervalSeconds',
  'vlessMeasurementAgeSeconds',
  'vlessProfileMeasurement'
];

const state = {
  vless: {
    settings: {urltest_interval: '3m'}
  },
  vlessSelectionHistory: {
    current: {urltest_interval: '3m'},
    profile_availability: {}
  }
};

const ctx = vm.createContext({state});
vm.runInContext(names.map(extract).join('\n'), ctx);

function render(item) {
  state.vlessSelectionHistory.profile_availability = {
    '1': item
  };

  return vm.runInContext(
    'vlessProfileMeasurement({id:1})',
    ctx
  );
}

let result = render(states.failed);
assert.equal(result.failed, true);
assert.match(result.display, /Нет ответа/);

result = render(states.recovered);
assert.notEqual(result.failed, true);
assert.equal(result.delay_ms, 52);
assert.match(result.display, /URLTest/);
assert.match(result.details, /Восстановлен/);

result = render(states.late);
assert.notEqual(result.failed, true);
assert.equal(result.delay_ms, 52);

result = render(states.second_failure);
assert.equal(result.failed, true);
assert.equal(result.delay_ms, null);

result = render(states.same_time);
assert.notEqual(result.failed, true);
assert.equal(result.delay_ms, 70);

console.log('BACKEND_UI_RECOVERY_CONTRACT=PASS');
"""


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="Node.js unavailable in Python-only appliance test image",
)
def test_backend_to_ui_recovery_contract(recovery_states):
    result = subprocess.run(
        [
            "node",
            "-e",
            JS_CONTRACT,
            str(APPLIANCE / "index.html"),
        ],
        input=json.dumps(recovery_states),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "BACKEND_UI_RECOVERY_CONTRACT=PASS" in (result.stdout)
