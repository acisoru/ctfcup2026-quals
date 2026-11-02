#!/usr/bin/env bash
set -euo pipefail

# Reproducible release pipeline:
# evidence -> R8 -> Obfuscapk Docker -> checks -> handout/burntnote.apk

TASK="$(cd "$(dirname "$0")/.." && pwd)"
cd "$TASK"

R8_VERSION="${R8_VERSION:-9.5.26}"
R8_CACHE="${R8_CACHE:-$TASK/.cache/r8-$R8_VERSION.jar}"
R8_URL="https://dl.google.com/dl/android/maven2/com/android/tools/r8/$R8_VERSION/r8-$R8_VERSION.jar"
OBFUSCAPK_IMAGE="${OBFUSCAPK_IMAGE:-claudiugeorgiu/obfuscapk@sha256:33e7e0d7ac8169899bdf2201a9fe10a9fff50a2312fa9a07fe2be92c266f6f2e}"
KEEP_BUILD="${KEEP_BUILD:-0}"

SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
BUILD_TOOLS="$(find "$SDK/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -n 1)"
APKSIGNER="$BUILD_TOOLS/apksigner"
AAPT="$BUILD_TOOLS/aapt"

if [[ -z "${JAVA_HOME:-}" && -d "/opt/homebrew/opt/openjdk@21" ]]; then
  export JAVA_HOME="/opt/homebrew/opt/openjdk@21"
  export PATH="$JAVA_HOME/bin:$PATH"
fi

[[ -x "$APKSIGNER" && -x "$AAPT" ]] || {
  echo "Android build-tools not found under $SDK" >&2
  exit 1
}
command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required to fetch R8" >&2; exit 1; }

if [[ ! -s "$R8_CACHE" ]]; then
  mkdir -p "$(dirname "$R8_CACHE")"
  echo "downloading R8 $R8_VERSION"
  curl -fsSL -o "$R8_CACHE.tmp" "$R8_URL"
  mv "$R8_CACHE.tmp" "$R8_CACHE"
fi

if ! docker image inspect "$OBFUSCAPK_IMAGE" >/dev/null 2>&1; then
  docker pull "$OBFUSCAPK_IMAGE"
fi

WORK="$(mktemp -d /private/tmp/burntnote-release-work.XXXXXX)"
OUT="$(mktemp -d /private/tmp/burntnote-release-out.XXXXXX)"
R8_APK="$TASK/build/burntnote-r8.apk"
FINAL_APK="$TASK/handout/burntnote.apk"

cleanup() {
  rm -rf "$WORK" "$OUT"
  if [[ "$KEEP_BUILD" != "1" ]]; then
    rm -rf "$TASK/android/build" "$TASK/build"
  fi
}
trap cleanup EXIT

echo "[1/7] build evidence"
python3 tools/build_evidence.py >/dev/null

echo "[2/7] parity"
python3 tools/check_parity.py >/dev/null

echo "[3/7] build R8 intermediate"
HARDENED=1 R8_JAR="$R8_CACHE" ./android/build_apk.sh "$R8_APK" >/dev/null

echo "[4/7] Obfuscapk Docker pass"
docker run --rm --network none -u "$(id -u):$(id -g)" \
  -v "$R8_APK:/input/burntnote.apk:ro" \
  -v "$OUT:/output" \
  -v "$WORK:/tmp/obfuscapk-work" \
  "$OBFUSCAPK_IMAGE" -i -w /tmp/obfuscapk-work \
  -d /output/burntnote-obfuscapk.apk \
  -o DebugRemoval -o ConstStringEncryption \
  -o ClassRename -o FieldRename -o MethodRename \
  -o Reorder -o CallIndirection -o ArithmeticBranch -o Goto -o Nop \
  -o RandomManifest -o Rebuild -o NewAlignment -o NewSignature \
  /input/burntnote.apk >/dev/null

OBF_APK="$OUT/burntnote-obfuscapk.apk"
[[ -s "$OBF_APK" ]] || { echo "Obfuscapk produced no APK" >&2; exit 1; }

echo "[5/7] verify APK"
"$APKSIGNER" verify "$OBF_APK"
"$AAPT" dump badging "$OBF_APK" | rg -q "launchable-activity" || {
  echo "launcher activity missing" >&2
  exit 1
}

DEX_STRINGS="$(unzip -p "$OBF_APK" classes.dex | strings)"
if printf '%s\n' "$DEX_STRINGS" | rg -qi \
  'BurntCrypto|SeedCollector|MessageStore|deriveMaster|stepKey|PBKDF2WithHmacSHA256|AES/GCM/NoPadding|burnt-note/root|burnt-note/step|burnt-note/msg|master key'; then
  echo "obvious crypto identifiers survived obfuscation" >&2
  exit 1
fi

echo "[6/7] publish canonical APK"
mv "$OBF_APK" "$FINAL_APK"

echo "[7/7] end-to-end checks"
python3 solve/solve.py handout/evidence.tar.gz >/dev/null
echo "release ready: $FINAL_APK"
shasum -a 256 "$FINAL_APK"
