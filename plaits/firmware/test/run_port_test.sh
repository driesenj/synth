#!/usr/bin/env bash
# Host tests of the Plaitsy port: the UI, drivers and storage on a model of
# the board (hal_fake.cc), with Plaits' voice for the checks that need it.
#
# Run from WSL (or any Linux with g++ and python3), from anywhere:
#   plaits/firmware/test/run_port_test.sh            all groups
#   plaits/firmware/test/run_port_test.sh nav        one group: cv, norm,
#                                                    nav, tables, cal,
#                                                    storage, userdata,
#                                                    transfer
# Exit status: 0 when every check passed and the sanitizers stayed quiet.
# FSK_DEBUG=1 makes the transfer group print, for each block it sends
# through TIMBRE, the first symbol the decoder got wrong (run lengths and
# sample ages around it).
#
# Builds into test/build/port (ignored by git). The vendored DSP objects are
# kept between runs (that code never changes); the port and the tests are
# rebuilt every time.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FW="$(dirname "$HERE")"
OUT="$HERE/build/port"
CXX="${CXX:-g++}"
CXXFLAGS="-std=gnu++14 -DTEST -O1 -g -fsanitize=address,undefined \
-fno-omit-frame-pointer -Wall -Wno-unused-local-typedefs"
INCLUDES="-I$HERE -I$FW/src -I$FW/vendor"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"

mkdir -p "$OUT"
cd "$FW"

# Board tables from the netlist (no bytecode left in the hardware folder).
python3 -B -E -P "$HERE/gen_board_tables.py" "$HERE/board_tables.h"

PORT_SOURCES=(src/plaits/ui.cc src/plaits/settings.cc src/plaits/user_data.cc
              src/storage.cc src/plaits/drivers/*.cc)
TEST_SOURCES=(test/port_test.cc test/test_cv.cc test/test_ui.cc
              test/test_storage.cc test/test_transfer.cc test/hal_fake.cc)
mapfile -t VENDOR_SOURCES < <(find vendor/plaits/dsp -name '*.cc' | sort)
VENDOR_SOURCES+=(vendor/plaits/resources.cc vendor/plaits/user_data_receiver.cc
                 vendor/stm_audio_bootloader/fsk/packet_decoder.cc
                 vendor/stmlib/dsp/units.cc vendor/stmlib/utils/random.cc)

# Start over when the compiler or the flags change.
STAMP="$OUT/flags"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$CXX $CXXFLAGS" ]; then
  rm -f "$OUT"/*.o
  echo "$CXX $CXXFLAGS" > "$STAMP"
fi

object_of() {
  echo "$OUT/$(echo "$1" | tr '/' '_' | sed 's/\.cc$/.o/')"
}

compile() {
  local src="$1" obj
  obj="$(object_of "$src")"
  # shellcheck disable=SC2086
  $CXX $CXXFLAGS $INCLUDES -c "$src" -o "$obj"
}
export -f compile object_of
export CXX CXXFLAGS INCLUDES OUT

STALE_VENDOR=()
for src in "${VENDOR_SOURCES[@]}"; do
  obj="$(object_of "$src")"
  if [ ! -f "$obj" ] || [ "$src" -nt "$obj" ]; then
    STALE_VENDOR+=("$src")
  fi
done

echo "building: ${#PORT_SOURCES[@]} port + ${#TEST_SOURCES[@]} test sources," \
     "${#STALE_VENDOR[@]} of ${#VENDOR_SOURCES[@]} vendor sources ($JOBS jobs)"
printf '%s\n' "${PORT_SOURCES[@]}" "${TEST_SOURCES[@]}" "${STALE_VENDOR[@]}" |
  xargs -P "$JOBS" -I{} bash -c 'compile "$@"' _ {}

OBJECTS=()
for src in "${PORT_SOURCES[@]}" "${TEST_SOURCES[@]}" "${VENDOR_SOURCES[@]}"; do
  OBJECTS+=("$(object_of "$src")")
done
# shellcheck disable=SC2086
$CXX $CXXFLAGS "${OBJECTS[@]}" -o "$OUT/port_test"

LOG="$OUT/port_test.log"
set +e
ASAN_OPTIONS="detect_leaks=1:abort_on_error=0" \
UBSAN_OPTIONS="print_stacktrace=1:halt_on_error=0" \
  "$OUT/port_test" "$@" 2>&1 | tee "$LOG"
STATUS=${PIPESTATUS[0]}
set -e

SANITIZER=$(grep -c -E "runtime error|ERROR: AddressSanitizer|ERROR: LeakSanitizer" "$LOG" || true)
if [ "$SANITIZER" != "0" ]; then
  echo "sanitizer reports: $SANITIZER (see $LOG)"
  grep -E "runtime error|ERROR: AddressSanitizer|ERROR: LeakSanitizer" "$LOG" | sort | uniq -c | head -20
  [ "$STATUS" = "0" ] && STATUS=101
fi
echo "run_port_test: exit status $STATUS"
exit "$STATUS"
