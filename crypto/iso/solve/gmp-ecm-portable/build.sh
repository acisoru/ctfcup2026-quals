#!/usr/bin/env bash
set -euo pipefail

PORTABLE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

GMP_ECM_REPO="${GMP_ECM_REPO:-https://github.com/sethtroisi/gmp-ecm.git}"
GMP_ECM_COMMIT="${GMP_ECM_COMMIT:-8ea5e214fdf2f0ddf9415141b8dc039ed6f5874e}"
CGBN_REPO="${CGBN_REPO:-https://github.com/NVlabs/CGBN.git}"
CGBN_COMMIT="${CGBN_COMMIT:-114601b07ae8c3e4d46b250208ea8d9def7a12f0}"
PATCH_FILE="$PORTABLE_DIR/patches/0001-custom-cgbn-kernel.patch"

BITS=2300
SM=""
CUDA_HOME_ARG=""
PREFIX="$PORTABLE_DIR"
JOBS="$( (nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4) )"
GENERIC=0

die() { echo "error: $*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: $0 [options]

Builds a GPU-enabled GMP-ECM with a custom CGBN kernel for the target N size.

Options:
  --bits N        target number size in bits (default: 2300).
                  Kernel size is rounded up to a multiple of 128 and must be
                  <= 32768.
  --sm N          CUDA compute capability without dot, e.g. 89 for RTX 4090,
                  90 for H100/H200. Auto-detected via nvidia-smi if omitted.
  --cuda DIR      CUDA toolkit root (default: auto-detect from nvcc).
  --prefix DIR    install prefix (default: $PORTABLE_DIR).
  --jobs N        parallel build jobs (default: $JOBS).
  --generic       do not use -march=native.
  --clean         remove build/src before cloning (full rebuild).
  -h, --help      show this help.

Environment:
  CC, CXX, CFLAGS                 passed through to configure.
  CUDA_HOST_COMPILER_DIR          passed as --with-cuda-compiler (directory
                                  containing the host compiler).
  GMP_ECM_COMMIT, CGBN_COMMIT     override pinned commits (not recommended).

Dependencies (Debian/Ubuntu):
  sudo apt-get install build-essential automake autoconf libtool m4 libgmp-dev
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --bits) BITS="${2:?}"; shift 2 ;;
    --sm) SM="${2:?}"; shift 2 ;;
    --cuda) CUDA_HOME_ARG="${2:?}"; shift 2 ;;
    --prefix) PREFIX="${2:?}"; shift 2 ;;
    --jobs) JOBS="${2:?}"; shift 2 ;;
    --generic) GENERIC=1; shift ;;
    --clean) rm -rf "$PORTABLE_DIR/build/src"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done

[[ "$BITS" =~ ^[0-9]+$ ]] || die "--bits must be an integer"
[ "$BITS" -ge 256 ] || die "--bits must be >= 256"
[ "$BITS" -le 32768 ] || die "--bits must be <= 32768 (gmp-ecm GPU limit)"
[[ "$JOBS" =~ ^[0-9]+$ ]] && [ "$JOBS" -ge 1 ] || die "--jobs must be >= 1"

for cmd in git make gcc g++ autoreconf libtoolize m4; do
  command -v "$cmd" >/dev/null 2>&1 || die "missing '$cmd' (install build-essential automake autoconf libtool m4)"
done

if ! printf '#include <gmp.h>\nint main(void){return 0;}\n' | "${CC:-gcc}" -x c - -o /tmp/.gmp_check.$$ >/dev/null 2>&1; then
  rm -f /tmp/.gmp_check.$$
  die "GMP headers/lib not found (install libgmp-dev or set CFLAGS/CPPFLAGS/LDFLAGS)"
fi
rm -f /tmp/.gmp_check.$$

# --- CUDA detection ---------------------------------------------------------
if [ -n "$CUDA_HOME_ARG" ]; then
  CUDA_HOME="$CUDA_HOME_ARG"
elif [ -n "${CUDA_HOME:-}" ]; then
  CUDA_HOME="$CUDA_HOME"
elif command -v nvcc >/dev/null 2>&1; then
  CUDA_HOME="$(cd -- "$(dirname -- "$(command -v nvcc)")/.." && pwd)"
else
  for d in /usr/local/cuda /usr/local/cuda-*; do
    if [ -x "$d/bin/nvcc" ]; then CUDA_HOME="$d"; break; fi
  done
fi
[ -n "${CUDA_HOME:-}" ] || die "CUDA toolkit not found (use --cuda DIR)"
[ -x "$CUDA_HOME/bin/nvcc" ] || die "nvcc not found under $CUDA_HOME"
[ -f "$CUDA_HOME/include/cuda.h" ] || die "cuda.h not found under $CUDA_HOME"

# --- SM detection -----------------------------------------------------------
if [ -z "$SM" ]; then
  if command -v nvidia-smi >/dev/null 2>&1; then
    SM="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null \
          | tr -d ' .' | grep -E '^[0-9]+$' | sort -n | head -n1 || true)"
  fi
fi
[ -n "$SM" ] || die "cannot detect GPU compute capability; pass --sm (e.g. --sm 89)"
[[ "$SM" =~ ^[0-9]+$ ]] || die "--sm must be digits without dot (e.g. 89)"

# --- kernel geometry --------------------------------------------------------
KBITS=$(( ((BITS + 6 + 127) / 128) * 128 ))
[ "$KBITS" -lt 2432 ] && KBITS=2432
[ "$KBITS" -le 32768 ] || die "kernel size $KBITS exceeds 32768"
if [ "$KBITS" -le 4096 ]; then TPI=16; else TPI=32; fi

echo "== portable gmp-ecm build =="
echo "  target N bits : $BITS"
echo "  CGBN kernel   : $KBITS bits, TPI=$TPI"
echo "  compute cap   : sm_$SM"
echo "  CUDA          : $CUDA_HOME"
echo "  prefix        : $PREFIX"

SRC_DIR="$PORTABLE_DIR/build/src"
GMP_ECM_SRC="$SRC_DIR/gmp-ecm"
CGBN_SRC="$SRC_DIR/CGBN"
mkdir -p "$SRC_DIR"

sync_repo() {
  local repo="$1" dir="$2" commit="$3"
  if [ ! -d "$dir/.git" ]; then
    echo "-- cloning $repo"
    git clone --quiet "$repo" "$dir"
  fi
  echo "-- checkout $commit in $dir"
  git -C "$dir" fetch --quiet --tags origin
  git -C "$dir" checkout --quiet --force "$commit"
  git -C "$dir" reset --hard --quiet "$commit"
  git -C "$dir" clean -fdxq
}

sync_repo "$GMP_ECM_REPO" "$GMP_ECM_SRC" "$GMP_ECM_COMMIT"
sync_repo "$CGBN_REPO" "$CGBN_SRC" "$CGBN_COMMIT"

echo "-- applying patch"
git -C "$GMP_ECM_SRC" apply --check "$PATCH_FILE"
git -C "$GMP_ECM_SRC" apply "$PATCH_FILE"

echo "-- autoreconf"
(cd "$GMP_ECM_SRC" && autoreconf -i >/dev/null)

CFLAGS_BASE="-O3 -funroll-loops"
[ "$GENERIC" -eq 0 ] && CFLAGS_BASE="$CFLAGS_BASE -march=native"
CFLAGS_FULL="${CFLAGS:-} $CFLAGS_BASE -DECM_CUSTOM_BITS=$KBITS -DECM_CUSTOM_TPI=$TPI"

CONFIGURE_ARGS=(
  "--enable-gpu=$SM"
  "--with-cuda=$CUDA_HOME"
  "--with-cuda-bin=$CUDA_HOME/bin"
  "--with-cgbn-include=$CGBN_SRC/include/cgbn"
)
if [ -n "${CUDA_HOST_COMPILER_DIR:-}" ]; then
  CONFIGURE_ARGS+=("--with-cuda-compiler=$CUDA_HOST_COMPILER_DIR")
fi

echo "-- configure"
(cd "$GMP_ECM_SRC" && ./configure "${CONFIGURE_ARGS[@]}" CFLAGS="$CFLAGS_FULL" >/dev/null)

echo "-- make -j$JOBS"
(cd "$GMP_ECM_SRC" && make -j"$JOBS" >/dev/null)

[ -x "$GMP_ECM_SRC/ecm" ] || die "build produced no ecm binary"
mkdir -p "$PREFIX/bin"
install -m 0755 "$GMP_ECM_SRC/ecm" "$PREFIX/bin/ecm"

cat > "$PREFIX/build-info.txt" <<EOF
built_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(uname -srm)
target_n_bits=$BITS
custom_kernel_bits=$KBITS
custom_kernel_tpi=$TPI
compute_cap=$SM
cuda_home=$CUDA_HOME
gmp_ecm_repo=$GMP_ECM_REPO
gmp_ecm_commit=$GMP_ECM_COMMIT
cgbn_repo=$CGBN_REPO
cgbn_commit=$CGBN_COMMIT
cflags=$CFLAGS_FULL
EOF

echo
echo "built: $PREFIX/bin/ecm"
echo "info : $PREFIX/build-info.txt"
echo
echo "Example:"
echo "  $PREFIX/factor.py --n N.txt --b1 3000000 --b2 10000000 \\"
echo "      --devices 0,1,2 --threads $( (nproc 2>/dev/null || echo 32) ) --waves 2"
