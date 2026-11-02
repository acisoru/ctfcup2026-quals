#!/usr/bin/env bash
set -euo pipefail

SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
BUILD_TOOLS="$(find "$SDK/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -n 1)"
R8_JAR="$BUILD_TOOLS/lib/d8.jar"
PLATFORM="$SDK/platforms/android-35/android.jar"
MOBILE_AAR="${MOBILE_AAR:-../GoMobileNativeLib/mobilelib.aar}"
API_BASE_URL="${API_BASE_URL:-https://10.0.2.2:8443}"
MIN_SDK="${MIN_SDK:-23}"
TARGET_SDK="${TARGET_SDK:-35}"
if [[ -z "${JAVA_HOME:-}" && -d "/opt/homebrew/opt/openjdk@21" ]]; then
  export JAVA_HOME="/opt/homebrew/opt/openjdk@21"
  export PATH="$JAVA_HOME/bin:$PATH"
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-base-url)
      API_BASE_URL="${2:?missing value for --api-base-url}"
      shift 2
      ;;
    --min-sdk)
      MIN_SDK="${2:?missing value for --min-sdk}"
      shift 2
      ;;
    --target-sdk)
      TARGET_SDK="${2:?missing value for --target-sdk}"
      shift 2
      ;;
    -h|--help)
      echo "usage: $0 [--api-base-url URL] [--min-sdk API] [--target-sdk API]"
      echo "default URL: $API_BASE_URL"
      echo "default min SDK: $MIN_SDK"
      echo "default target SDK: $TARGET_SDK"
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$PLATFORM" ]]; then
  PLATFORM="$(find "$SDK/platforms" -name android.jar | sort -V | tail -n 1)"
fi

if [[ ! -f "$PLATFORM" ]]; then
  echo "android.jar not found under $SDK/platforms" >&2
  exit 1
fi

if [[ ! -f "$R8_JAR" ]]; then
  echo "R8 jar not found at $R8_JAR" >&2
  exit 1
fi

NDK="${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}}"
if [[ -z "$NDK" && -d "$SDK/ndk" ]]; then
  NDK="$(find "$SDK/ndk" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -n 1)"
fi
STRIP=""
if [[ -n "$NDK" ]]; then
  STRIP="$(find "$NDK/toolchains/llvm/prebuilt" -path '*/bin/llvm-strip' | head -n 1 || true)"
fi

rm -rf build
mkdir -p build/classes build/dex build/generated/java/com/ctf/sealedprefs build/unsigned build/signed

MOBILE_CLASSES=()
if [[ ! -f "$MOBILE_AAR" ]]; then
  echo "mobilelib.aar not found at $MOBILE_AAR" >&2
  echo "build it first: cd ../GoMobileNativeLib && gomobile bind -target=android -androidapi=23 -trimpath -ldflags='-s -w' -o mobilelib.aar ." >&2
  exit 1
fi

mkdir -p build/mobilelib build/native-lib/lib
unzip -q "$MOBILE_AAR" -d build/mobilelib
if [[ -f build/mobilelib/classes.jar ]]; then
  if ! javap -classpath build/mobilelib/classes.jar mobilelib.Mobilelib \
      | grep -q 'isRootedEnvironment(java.lang.String, java.lang.String, java.lang.String, java.lang.String)'; then
    echo "mobilelib.aar is stale: rebuild GoMobileNativeLib/mobilelib.aar after native API changes" >&2
    exit 1
  fi
  if ! javap -classpath build/mobilelib/classes.jar mobilelib.Mobilelib \
      | grep -q 'verifySealedParcel(java.lang.String, java.lang.String, java.lang.String)'; then
    echo "mobilelib.aar is stale: rebuild GoMobileNativeLib/mobilelib.aar after native API changes" >&2
    exit 1
  fi
  MOBILE_CLASSES+=(build/mobilelib/classes.jar)
fi
if [[ -d build/mobilelib/jni ]]; then
  for so in build/mobilelib/jni/*/*.so; do
    [[ -f "$so" ]] || continue
    abi="$(basename "$(dirname "$so")")"
    mkdir -p "build/native-lib/lib/$abi"
    cp "$so" "build/native-lib/lib/$abi/"
    if [[ -n "$STRIP" ]]; then
      "$STRIP" --strip-unneeded "build/native-lib/lib/$abi/$(basename "$so")"
    fi
  done
fi

API_BASE_URL="$API_BASE_URL" python3 -c 'import os
value = os.environ["API_BASE_URL"]
escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
path = "build/generated/java/com/ctf/sealedprefs/BuildConfig.java"
with open(path, "w", encoding="utf-8") as f:
    f.write("package com.ctf.sealedprefs;\n\n")
    f.write("public final class BuildConfig {\n")
    f.write("    public static final String API_BASE_URL = \"" + escaped.rstrip("/") + "\";\n")
    f.write("}\n")
'

"$BUILD_TOOLS/aapt2" compile --dir app/src/main/res -o build/resources.zip
"$BUILD_TOOLS/aapt2" link \
  -I "$PLATFORM" \
  --manifest app/src/main/AndroidManifest.xml \
  --java build/generated/java \
  --min-sdk-version "$MIN_SDK" \
  --target-sdk-version "$TARGET_SDK" \
  -o build/unsigned/base.apk \
  build/resources.zip

javac \
  -g:none \
  -source 8 -target 8 \
  -bootclasspath "$PLATFORM" \
  -d build/classes \
  $(find app/src/main/java build/generated/java -name '*.java')

java -cp "$R8_JAR" com.android.tools.r8.R8 \
  --release \
  --dex \
  --lib "$PLATFORM" \
  --min-api "$MIN_SDK" \
  --pg-conf proguard-rules.pro \
  --pg-map-output build/mapping.txt \
  --output build/dex \
  "${MOBILE_CLASSES[@]}" \
  $(find build/classes -name '*.class')

cp build/unsigned/base.apk build/unsigned/with-dex.apk
cd build/dex
zip -qr ../unsigned/with-dex.apk classes.dex
cd ../..
if [[ -d build/native-lib/lib ]]; then
  cd build/native-lib
  zip -qr ../unsigned/with-dex.apk lib
  cd ../..
fi

KEYSTORE="build/debug.keystore"
keytool -genkeypair \
  -keystore "$KEYSTORE" \
  -storepass android \
  -keypass android \
  -alias androiddebugkey \
  -dname "CN=Android Debug,O=CTF,C=RU" \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 >/dev/null

"$BUILD_TOOLS/zipalign" -p -f 4 build/unsigned/with-dex.apk build/signed/aligned.apk
"$BUILD_TOOLS/apksigner" sign \
  --ks "$KEYSTORE" \
  --ks-pass pass:android \
  --key-pass pass:android \
  --out build/sealed-prefs.apk \
  build/signed/aligned.apk

"$BUILD_TOOLS/apksigner" verify build/sealed-prefs.apk
echo "built: $(pwd)/build/sealed-prefs.apk"
echo "api base url: $API_BASE_URL"
echo "min sdk: $MIN_SDK"
echo "target sdk: $TARGET_SDK"
echo "minified: R8"
if [[ -n "$STRIP" ]]; then
  echo "native strip: $STRIP"
fi
echo "mapping: $(pwd)/build/mapping.txt"
