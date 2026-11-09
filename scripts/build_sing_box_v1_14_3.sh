#!/usr/bin/env bash
set -Eeuo pipefail

# Reproducibly build MaxVPN's patched sing-box v1.14.3 for OpenWrt ARM64/musl.
# This script does not connect to a router or install the binary anywhere.

EXPECTED_COMMIT="7054cac5124465ffdb145870d7c01885566711b1"
EXPECTED_PATCH_SHA256="96f16e8daa33df68de293835ddd069fb7bf71d206afb44c2b47b9be2ce0199ea"
EXPECTED_CRONET_COMMIT="0d28acc44093df24b2526dea3d6ffefd6b0a54f0"
EXPECTED_NAIVEPROXY_COMMIT="72a06c9fca0e2d228588c7f3074bf7efff3ff686"
UPSTREAM_URL="https://github.com/SagerNet/sing-box.git"
UPSTREAM_TAG="v1.14.3"
DOCKER_IMAGE="golang:1.26.8-bookworm"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel 2>/dev/null)" || {
  echo "ERROR: script must be stored inside the MaxVPN Git repository (scripts/)." >&2
  exit 1
}
PATCH_DIR="$REPO_ROOT/patches/sing-box/v1.14.3"
PATCH_FILE="$PATCH_DIR/0001-urltest-force-periodic-check.patch"
PATCH_SUMS="$PATCH_DIR/SHA256SUMS"

SOURCE_DIR="${SING_BOX_SOURCE_DIR:-$HOME/src/sing-box-v1.14.3-build}"
SEED_SOURCE_DIR="${SING_BOX_SEED_SOURCE_DIR:-$HOME/src/sing-box-v1.14.3}"
CRONET_DIR="${CRONET_GO_DIR:-$HOME/src/cronet-go-sing-box-v1.14.3}"
OUT_DIR="${SING_BOX_OUTPUT_DIR:-$HOME/src/sing-box-build-v1.14.3}"
GO_MOD_CACHE="${SING_BOX_GO_MOD_CACHE:-$HOME/.cache/maxvpn-sing-box-go-mod}"
GO_BUILD_CACHE="${SING_BOX_GO_BUILD_CACHE:-$HOME/.cache/maxvpn-sing-box-go-build}"
LOG_FILE="$OUT_DIR/build.log"
NEW_BIN="$OUT_DIR/sing-box.new"
FINAL_BIN="$OUT_DIR/sing-box"

fail() { echo "ERROR: $*" >&2; exit 1; }
info() { printf '\n===== %s =====\n' "$*"; }

command -v git >/dev/null 2>&1 || fail "git is required on WSL."
command -v docker >/dev/null 2>&1 || fail "Docker is required."
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required."
command -v file >/dev/null 2>&1 || fail "file (file utility) is required on WSL."

[[ -f "$PATCH_FILE" ]] || fail "Patch not found: $PATCH_FILE"
[[ -f "$PATCH_SUMS" ]] || fail "SHA256SUMS not found: $PATCH_SUMS"
ACTUAL_PATCH_SHA256="$(sha256sum "$PATCH_FILE" | awk '{print $1}')"
[[ "$ACTUAL_PATCH_SHA256" == "$EXPECTED_PATCH_SHA256" ]] || fail "Unexpected patch SHA-256: $ACTUAL_PATCH_SHA256"
(cd "$PATCH_DIR" && sha256sum -c SHA256SUMS)

info "Prepare a clean, isolated upstream checkout"
if [[ ! -e "$SOURCE_DIR" ]]; then
  mkdir -p "$(dirname "$SOURCE_DIR")"
  if [[ -d "$SEED_SOURCE_DIR/.git" ]] && [[ "$(git -C "$SEED_SOURCE_DIR" rev-parse HEAD)" == "$EXPECTED_COMMIT" ]]; then
    # Clone the upstream tag from GitHub, not the user's edited source working tree.
    git clone --depth 1 --branch "$UPSTREAM_TAG" "$UPSTREAM_URL" "$SOURCE_DIR"
  else
    git clone --depth 1 --branch "$UPSTREAM_TAG" "$UPSTREAM_URL" "$SOURCE_DIR"
  fi
elif [[ ! -d "$SOURCE_DIR/.git" ]]; then
  fail "Source path exists but is not a Git checkout: $SOURCE_DIR"
fi

SOURCE_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
[[ "$SOURCE_COMMIT" == "$EXPECTED_COMMIT" ]] || fail "Unexpected source commit: $SOURCE_COMMIT (expected $EXPECTED_COMMIT)"

# Apply once to a clean tree. On subsequent runs, allow exactly this patch and no
# other source modifications. Never reset or clean a user's checkout.
if git -C "$SOURCE_DIR" apply --reverse --check "$PATCH_FILE" >/dev/null 2>&1; then
  info "Patch already applied; validating the existing patch state"
else
  STATUS_BEFORE="$(git -C "$SOURCE_DIR" status --porcelain --untracked-files=all)"
  [[ -z "$STATUS_BEFORE" ]] || fail "Source checkout has unexpected modifications before patch application:\n$STATUS_BEFORE"
  git -C "$SOURCE_DIR" apply --check "$PATCH_FILE"
  git -C "$SOURCE_DIR" apply "$PATCH_FILE"
fi

git -C "$SOURCE_DIR" diff --check
STATUS="$(git -C "$SOURCE_DIR" status --porcelain --untracked-files=all)"
[[ "$STATUS" == " M protocol/group/urltest.go" ]] || fail "Source tree must contain only the expected modified file. Status:\n${STATUS:-<clean>}"
NUMSTAT="$(git -C "$SOURCE_DIR" diff --numstat)"
[[ "$NUMSTAT" == $'1\t1\tprotocol/group/urltest.go' ]] || fail "Unexpected patch diff:\n$NUMSTAT"

python3 - "$SOURCE_DIR/protocol/group/urltest.go" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
start = text.find("func (g *URLTestGroup) loopCheck(")
end = text.find("\nfunc (g *URLTestGroup) CheckOutbounds(", start)
if start < 0 or end < 0:
    raise SystemExit("ERROR: URLTestGroup.loopCheck structure not found")
block = text[start:end]
if block.count("g.CheckOutbounds(g.ctx, false)") != 1:
    raise SystemExit("ERROR: expected exactly one unchanged initial/non-periodic force=false call")
if block.count("g.CheckOutbounds(g.ctx, true)") != 1:
    raise SystemExit("ERROR: expected exactly one force=true call in loopCheck")
tick = block.find("case <-ticker.C:")
forced = block.find("g.CheckOutbounds(g.ctx, true)")
if tick < 0 or forced < tick:
    raise SystemExit("ERROR: force=true is not in the periodic ticker branch")
print("URLTest patch structural check: OK (initial call unchanged; periodic tick force=true)")
PY

info "Validate the pinned Chromium/NaiveProxy toolchain"
[[ -d "$CRONET_DIR/.git" ]] || fail "cronet-go checkout missing: $CRONET_DIR"
ACTUAL_CRONET_COMMIT="$(git -C "$CRONET_DIR" rev-parse HEAD)"
[[ "$ACTUAL_CRONET_COMMIT" == "$EXPECTED_CRONET_COMMIT" ]] || fail "Unexpected cronet-go commit: $ACTUAL_CRONET_COMMIT"
ACTUAL_NAIVEPROXY_COMMIT="$(git -C "$CRONET_DIR/naiveproxy" rev-parse HEAD 2>/dev/null)" || fail "NaiveProxy submodule is not initialized."
[[ "$ACTUAL_NAIVEPROXY_COMMIT" == "$EXPECTED_NAIVEPROXY_COMMIT" ]] || fail "Unexpected NaiveProxy submodule commit: $ACTUAL_NAIVEPROXY_COMMIT"
CLANG="$CRONET_DIR/naiveproxy/src/third_party/llvm-build/Release+Asserts/bin/clang"
SYSROOT="$CRONET_DIR/naiveproxy/src/out/sysroot-build/openwrt/23.05.5/aarch64"
[[ -x "$CLANG" ]] || fail "Prepared Chromium clang not found: $CLANG. Prepare the pinned cronet-go Linux ARM64/musl toolchain first."
[[ -d "$SYSROOT" ]] || fail "Prepared OpenWrt ARM64/musl sysroot not found: $SYSROOT"
echo "sing-box commit: $SOURCE_COMMIT"
echo "cronet-go commit: $ACTUAL_CRONET_COMMIT"
echo "NaiveProxy submodule: $ACTUAL_NAIVEPROXY_COMMIT"

mkdir -p "$OUT_DIR" "$GO_MOD_CACHE" "$GO_BUILD_CACHE"
rm -f "$NEW_BIN"

info "Run tests and build Linux ARM64/musl binary in Docker"
set +e
docker run --rm --platform linux/amd64 \
  -v "$SOURCE_DIR:/sing-box" \
  -v "$CRONET_DIR:/cronet-go" \
  -v "$OUT_DIR:/out" \
  -v "$GO_MOD_CACHE:/go/pkg/mod" \
  -v "$GO_BUILD_CACHE:/root/.cache/go-build" \
  -w /cronet-go \
  "$DOCKER_IMAGE" \
  bash -c '
set -euo pipefail

cd /sing-box
git config --global --add safe.directory /sing-box

echo "===== Go version ====="
go version

echo
echo "===== Compile/test URLTest package ====="
go test ./protocol/group

echo
echo "===== Load pinned Chromium toolchain environment ====="
ENV_FILE=/tmp/cronet-env.txt
(cd /cronet-go && go run ./cmd/build-naive --target=linux/arm64 --libc=musl env) > "$ENV_FILE"
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && continue
  [[ "$line" == *=* ]] || { echo "Unexpected env line: $line" >&2; exit 1; }
  name="${line%%=*}"
  value="${line#*=}"
  [[ "$name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "Invalid env name: $name" >&2; exit 1; }
  export "$name=$value"
done < "$ENV_FILE"
rm -f "$ENV_FILE"

echo
echo "===== Build tags ====="
TAGS="$(tr -d "\r\n" < release/DEFAULT_BUILD_TAGS)"
case ",$TAGS," in *,with_naive_outbound,*) ;; *) TAGS="${TAGS},with_naive_outbound" ;; esac
case ",$TAGS," in *,with_musl,*) ;; *) TAGS="${TAGS},with_musl" ;; esac
echo "$TAGS"
LDFLAGS_SHARED="$(cat release/LDFLAGS)"

export CGO_ENABLED=1 GOOS=linux GOARCH=arm64
echo
echo "===== Build binary ====="
go build -v -trimpath \
  -o /out/sing-box.new \
  -tags "$TAGS" \
  -ldflags "-X github.com/sagernet/sing-box/constant.Version=1.14.3 ${LDFLAGS_SHARED} -s -w -buildid=" \
  ./cmd/sing-box

echo
echo "===== Embedded Go build metadata ====="
BUILD_INFO="$(go version -m /out/sing-box.new)"
printf "%s\n" "$BUILD_INFO"
printf "%s\n" "$BUILD_INFO" | grep -Fq "GOOS=linux" || { echo "Missing GOOS=linux in build metadata" >&2; exit 1; }
printf "%s\n" "$BUILD_INFO" | grep -Fq "GOARCH=arm64" || { echo "Missing GOARCH=arm64 in build metadata" >&2; exit 1; }
printf "%s\n" "$BUILD_INFO" | grep -Fq "CGO_ENABLED=1" || { echo "Missing CGO_ENABLED=1 in build metadata" >&2; exit 1; }
printf "%s\n" "$BUILD_INFO" | grep -Fq "with_naive_outbound" || { echo "Missing with_naive_outbound build tag" >&2; exit 1; }
printf "%s\n" "$BUILD_INFO" | grep -Fq "with_musl" || { echo "Missing with_musl build tag" >&2; exit 1; }

echo
echo "BUILD_COMPLETE"
' 2>&1 | tee "$LOG_FILE"
BUILD_RC=${PIPESTATUS[0]}
set -e
[[ "$BUILD_RC" -eq 0 ]] || fail "Docker build failed (exit $BUILD_RC). See $LOG_FILE"

[[ -s "$NEW_BIN" ]] || fail "Build reported success but output file is missing/empty: $NEW_BIN"
FILE_DESC="$(file "$NEW_BIN")"
echo "$FILE_DESC"
[[ "$FILE_DESC" == *"ELF 64-bit LSB executable, ARM aarch64"* ]] || fail "Output is not an ARM64 ELF executable: $FILE_DESC"
[[ "$FILE_DESC" == *"statically linked"* ]] || fail "Output is not statically linked as expected: $FILE_DESC"
NEW_SHA256="$(sha256sum "$NEW_BIN" | awk '{print $1}')"

# Preserve the previous output artifact instead of silently overwriting it.
if [[ -f "$FINAL_BIN" ]]; then
  OLD_OUTPUT_SHA256="$(sha256sum "$FINAL_BIN" | awk '{print $1}')"
  if [[ "$OLD_OUTPUT_SHA256" == "$NEW_SHA256" ]]; then
    rm -f "$NEW_BIN"
    echo "Rebuilt binary has the same SHA-256 as existing output; kept existing artifact."
  else
    PREVIOUS_BIN="$OUT_DIR/sing-box.previous-$(date +%Y%m%d-%H%M%S)"
    mv "$FINAL_BIN" "$PREVIOUS_BIN"
    echo "Previous build preserved at: $PREVIOUS_BIN"
    mv "$NEW_BIN" "$FINAL_BIN"
  fi
else
  mv "$NEW_BIN" "$FINAL_BIN"
fi

info "Build complete (no router deployment performed)"
ls -lh "$FINAL_BIN"
file "$FINAL_BIN"
sha256sum "$FINAL_BIN"
echo "Build log: $LOG_FILE"
echo "Artifact: $FINAL_BIN"
echo "This script does not scp, install, restart services, or change router/configuration state."
