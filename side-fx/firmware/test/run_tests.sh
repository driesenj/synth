#!/usr/bin/env bash
# Host tests of the Side FXy firmware, under AddressSanitizer and
# UndefinedBehaviorSanitizer.
#
# Run from WSL (or any Linux with g++ and python3), from anywhere:
#   side-fx/firmware/test/run_tests.sh               every group
#   side-fx/firmware/test/run_tests.sh fx_plate ui   only these groups
#   TEST_ARGS=-v side-fx/firmware/test/run_tests.sh engine   with notes
#
# A group is test/groups/<group>.txt: the sources its test binary links (one
# path per line, relative to side-fx/firmware, # for comments), on top of
# the core every group gets (CORE below). Each group links its own binary,
# so a group can use the fake registry (test/fake_registry.cc) while
# another uses the real blocks.
#
# Builds into test/build/<groups> (ignored by git), or $OUT: separate
# invocations never share objects. Vendored objects are kept between runs;
# the firmware's and the tests' own sources are rebuilt every time.
# Exit status: 0 when every group built and passed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FW="$(dirname "$HERE")"
CXX="${CXX:-g++}"
CXXFLAGS="-std=gnu++14 -DSIDEFX_HOST_TEST -O1 -g -fsanitize=address,undefined \
-fno-omit-frame-pointer -Wall -Wno-unused-local-typedefs"
INCLUDES="-I$HERE -I$FW/src -I$FW/vendor"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"
export UBSAN_OPTIONS="${UBSAN_OPTIONS:-halt_on_error=1:print_stacktrace=1}"
export ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}"

CORE=(test/test_main.cc src/engine/params.cc src/engine/memory.cc
      src/engine/modulation.cc vendor/stmlib/dsp/units.cc
      vendor/stmlib/utils/random.cc)

cd "$FW"

if [ "$#" -gt 0 ]; then
  GROUPS_TO_RUN=("$@")
else
  GROUPS_TO_RUN=()
  for f in test/groups/*.txt; do
    GROUPS_TO_RUN+=("$(basename "$f" .txt)")
  done
fi
if [ "$#" -gt 0 ]; then
  OUT="${OUT:-$HERE/build/$(IFS=-; echo "$*")}"
else
  OUT="${OUT:-$HERE/build/all}"
fi
mkdir -p "$OUT/obj"

# Start over when the compiler or the flags change.
STAMP="$OUT/flags"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$CXX $CXXFLAGS" ]; then
  rm -f "$OUT"/obj/*.o
  echo "$CXX $CXXFLAGS" > "$STAMP"
fi

group_sources() {
  local group="$1" file="test/groups/$1.txt"
  if [ ! -f "$file" ]; then
    echo "no such group: $group ($file)" >&2
    return 1
  fi
  printf '%s\n' "${CORE[@]}"
  sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^$/d' "$file"
}

object_of() {
  echo "$OUT/obj/$(echo "$1" | tr '/' '_' | sed 's/\.\(cc\|c\)$/.o/')"
}

compile() {
  local src="$1" obj
  obj="$(object_of "$src")"
  # shellcheck disable=SC2086
  if ! $CXX $CXXFLAGS $INCLUDES -c "$src" -o "$obj" 2> "$obj.log"; then
    cat "$obj.log"
    echo "compile failed: $src"
    rm -f "$obj"
    return 1
  fi
  if [ -s "$obj.log" ]; then
    cat "$obj.log"
  fi
}
export -f compile object_of
export CXX CXXFLAGS INCLUDES OUT

# Every source any requested group needs, once.
declare -A WANTED=()
for g in "${GROUPS_TO_RUN[@]}"; do
  while IFS= read -r src; do
    WANTED["$src"]=1
  done < <(group_sources "$g")
done

TO_BUILD=()
for src in "${!WANTED[@]}"; do
  if [ ! -f "$src" ]; then
    echo "missing source: $src" >&2
    exit 1
  fi
  obj="$(object_of "$src")"
  case "$src" in
    vendor/*)
      if [ ! -f "$obj" ] || [ "$src" -nt "$obj" ]; then
        TO_BUILD+=("$src")
      fi
      ;;
    *)
      TO_BUILD+=("$src")
      ;;
  esac
done

echo "building ${#TO_BUILD[@]} of ${#WANTED[@]} sources for" \
     "${#GROUPS_TO_RUN[@]} group(s) ($JOBS jobs)"
BUILD_OK=1
if [ "${#TO_BUILD[@]}" -gt 0 ]; then
  printf '%s\n' "${TO_BUILD[@]}" |
    xargs -P "$JOBS" -I{} bash -c 'compile "$@"' _ {} || BUILD_OK=0
fi
if [ "$BUILD_OK" != 1 ]; then
  echo "BUILD FAILED"
  exit 1
fi

STATUS=0
SUMMARY=()
for g in "${GROUPS_TO_RUN[@]}"; do
  OBJECTS=()
  while IFS= read -r src; do
    OBJECTS+=("$(object_of "$src")")
  done < <(group_sources "$g")
  BIN="$OUT/$g"
  # shellcheck disable=SC2086
  if ! $CXX $CXXFLAGS "${OBJECTS[@]}" -o "$BIN" -lm; then
    echo "LINK FAILED: $g"
    SUMMARY+=("$g: link failed")
    STATUS=1
    continue
  fi
  echo "== $g"
  # shellcheck disable=SC2086
  if "$BIN" ${TEST_ARGS:-} > "$OUT/$g.log" 2>&1; then
    if [ -n "${TEST_ARGS:-}" ]; then
      cat "$OUT/$g.log"
    else
      tail -n 1 "$OUT/$g.log"
    fi
    SUMMARY+=("$g: $(tail -n 1 "$OUT/$g.log")")
  else
    cat "$OUT/$g.log"
    SUMMARY+=("$g: FAILED ($(tail -n 1 "$OUT/$g.log"))")
    STATUS=1
  fi
done

echo
echo "summary:"
printf '  %s\n' "${SUMMARY[@]}"
exit $STATUS
