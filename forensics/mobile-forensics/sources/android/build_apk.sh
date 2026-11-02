#!/usr/bin/env bash
# Builds the R8 intermediate APK. Obfuscapk produces the release artifact.
set -euo pipefail

SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
BUILD_TOOLS="$(find "$SDK/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -n 1)"
PLATFORM="$SDK/platforms/android-35/android.jar"
if [[ ! -f "$PLATFORM" ]]; then
  PLATFORM="$(find "$SDK/platforms" -name android.jar | sort -V | tail -n 1)"
fi
[[ -f "$PLATFORM" ]] || { echo "android.jar not found under $SDK/platforms" >&2; exit 1; }

if [[ -z "${JAVA_HOME:-}" && -d "/opt/homebrew/opt/openjdk@21" ]]; then
  export JAVA_HOME="/opt/homebrew/opt/openjdk@21"
  export PATH="$JAVA_HOME/bin:$PATH"
fi

MIN_SDK=24
TARGET_SDK=34
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/../build/burntnote-r8.apk}"

rm -rf "$HERE/build"
mkdir -p "$HERE/build/classes" "$HERE/build/dex" "$HERE/build/generated" "$HERE/build/unsigned"

"$BUILD_TOOLS/aapt2" compile --dir "$HERE/app/src/main/res" -o "$HERE/build/resources.zip"
"$BUILD_TOOLS/aapt2" link \
  -I "$PLATFORM" \
  --manifest "$HERE/app/src/main/AndroidManifest.xml" \
  --java "$HERE/build/generated" \
  --min-sdk-version "$MIN_SDK" \
  --target-sdk-version "$TARGET_SDK" \
  -o "$HERE/build/unsigned/base.apk" \
  "$HERE/build/resources.zip"

javac \
  -encoding UTF-8 \
  -g:none \
  -source 8 -target 8 \
  -bootclasspath "$PLATFORM" \
  -d "$HERE/build/classes" \
  $(find "$HERE/app/src/main/java" "$HERE/build/generated" -name '*.java')

CLASS_JAR="$HERE/build/classes.jar"
(cd "$HERE/build/classes" && jar cf "$CLASS_JAR" .)

R8_JAR="${R8_JAR:-}"
if [[ -z "$R8_JAR" ]]; then
  for candidate in \
      "$HERE/r8.jar" \
      "$SDK/cmdline-tools/latest/lib/r8.jar" \
      "$SDK/tools/lib/r8.jar"; do
    if [[ -f "$candidate" ]]; then
      R8_JAR="$candidate"
      break
    fi
  done
fi

if [[ -n "$R8_JAR" ]]; then
  echo "using R8: $R8_JAR"
  java -cp "$R8_JAR" com.android.tools.r8.R8 \
    --release \
    --lib "$PLATFORM" \
    --min-api "$MIN_SDK" \
    --output "$HERE/build/dex" \
    --pg-conf "$HERE/proguard-rules.pro" \
    "$CLASS_JAR"
else
  if [[ "${HARDENED:-0}" == "1" ]]; then
    echo "error: HARDENED=1 requires R8_JAR or an SDK-provided r8.jar" >&2
    exit 1
  fi
  echo "warning: R8 not found; using D8 fallback (no shrinking/obfuscation)" >&2
  "$BUILD_TOOLS/d8" \
    --release \
    --lib "$PLATFORM" \
    --min-api "$MIN_SDK" \
    --output "$HERE/build/dex" \
    "$CLASS_JAR"
fi

cp "$HERE/build/unsigned/base.apk" "$HERE/build/unsigned/with-dex.apk"
(cd "$HERE/build/dex" && zip -qr "$HERE/build/unsigned/with-dex.apk" classes.dex)

KEYSTORE="$HERE/build/debug.keystore"
keytool -genkeypair \
  -keystore "$KEYSTORE" \
  -storepass android \
  -keypass android \
  -alias androiddebugkey \
  -dname "CN=Android Debug,O=CTF,C=RU" \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 >/dev/null

"$BUILD_TOOLS/zipalign" -p -f 4 "$HERE/build/unsigned/with-dex.apk" "$HERE/build/unsigned/aligned.apk"
mkdir -p "$(dirname "$OUT")"
"$BUILD_TOOLS/apksigner" sign \
  --ks "$KEYSTORE" \
  --ks-pass pass:android \
  --key-pass pass:android \
  --out "$OUT" \
  "$HERE/build/unsigned/aligned.apk"

"$BUILD_TOOLS/apksigner" verify "$OUT"
echo "built: $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
