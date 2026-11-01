#!/usr/bin/env bash
# Builds and runs test/voice_test.cc: Plaits 1.2's DSP (vendor/, unchanged)
# through the port's src/plaits/dsp/dsp.h and src/plaits/user_data.*, on the
# host, with g++, AddressSanitizer and UndefinedBehaviorSanitizer.
#
#   bash test/run_voice_test.sh [--quick] [--verbose] [--engine N]
#
# (about 2 minutes; --quick 20 s). From Windows, in plaits/firmware:
#   wsl.exe -e bash test/run_voice_test.sh
# Objects go to test/build/voice/ (git-ignored), or to $VOICE_TEST_BUILD.
# Exit status 0 when every check passed and the sanitizers stayed quiet.
# (The next line restarts the script without CRs if Git checked it out with
# Windows line ends, which bash cannot run.)
if [ -z "${VOICE_TEST_LF:-}" ] && grep -q $'\r' "$0" 2>/dev/null; then VOICE_TEST_LF=1 VOICE_TEST_SELF="$0" exec bash <(tr -d '\r' < "$0") "$@"; fi #
set -euo pipefail

SELF="${VOICE_TEST_SELF:-$0}"
TEST_DIR="$(cd "$(dirname "$SELF")" && pwd)"
FW="$(cd "$TEST_DIR/.." && pwd)"
BUILD="${VOICE_TEST_BUILD:-$TEST_DIR/build/voice}"
CXX="${CXX:-g++}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"

case "$FW$BUILD" in
  *" "*) echo "run_voice_test.sh: paths with spaces are not supported" >&2
         exit 2 ;;
esac

# src/ before vendor/: the port's plaits/dsp/dsp.h and plaits/user_data.h
# replace upstream's (vendor/ has neither, so a mix-up cannot build).
CXXFLAGS="-std=gnu++14 -DTEST -O2 -g -fsanitize=address,undefined \
-fno-omit-frame-pointer -I$FW/test -I$FW/src -I$FW/vendor"
# The vendored code with the firmware Makefile's warnings (it builds without
# any); the test itself with -Wextra too, less what the vendored headers it
# includes trip.
VENDOR_WARNINGS="-Wall -Wno-missing-attributes -Wno-stringop-overflow \
-Wno-unused-local-typedefs"
TEST_WARNINGS="-Wall -Wextra -Wno-unused-parameter -Wno-unused-local-typedefs"

# Everything plaits::Voice needs, and the port's user data store.
SOURCES="$(find "$FW/vendor/plaits/dsp" -name '*.cc' | LC_ALL=C sort | tr '\n' ' ')"
SOURCES="$SOURCES $FW/vendor/plaits/resources.cc"
SOURCES="$SOURCES $FW/vendor/stmlib/dsp/units.cc"
SOURCES="$SOURCES $FW/vendor/stmlib/utils/random.cc"
SOURCES="$SOURCES $FW/src/plaits/user_data.cc"
SOURCES="$SOURCES $FW/test/voice_test.cc"

mkdir -p "$BUILD"
# Rebuild everything when the compiler or the flags change: the objects
# depend on this stamp, rewritten only when its contents differ.
printf '%s\n' "$CXX $CXXFLAGS | $VENDOR_WARNINGS | $TEST_WARNINGS" \
  > "$BUILD/flags.new"
if cmp -s "$BUILD/flags.new" "$BUILD/flags"; then
  rm -f "$BUILD/flags.new"
else
  mv -f "$BUILD/flags.new" "$BUILD/flags"
fi
cat > "$BUILD/voice_test.mk" <<'EOF'
.RECIPEPREFIX := >
OBJECTS := $(patsubst $(FW)/%.cc,$(BUILD)/obj/%.o,$(SOURCES))

$(BUILD)/voice_test: $(OBJECTS)
> $(CXX) $(CXXFLAGS) $(OBJECTS) -o $@

$(BUILD)/obj/test/%.o: $(FW)/test/%.cc $(BUILD)/flags
> @mkdir -p $(@D)
> $(CXX) $(CXXFLAGS) $(TEST_WARNINGS) -MMD -MP -c $< -o $@

$(BUILD)/obj/%.o: $(FW)/%.cc $(BUILD)/flags
> @mkdir -p $(@D)
> $(CXX) $(CXXFLAGS) $(VENDOR_WARNINGS) -MMD -MP -c $< -o $@

-include $(OBJECTS:.o=.d)
EOF

echo "voice_test: building in $BUILD ($JOBS jobs)"
make -s -j"$JOBS" -f "$BUILD/voice_test.mk" \
  FW="$FW" BUILD="$BUILD" SOURCES="$SOURCES" CXX="$CXX" \
  CXXFLAGS="$CXXFLAGS" VENDOR_WARNINGS="$VENDOR_WARNINGS" \
  TEST_WARNINGS="$TEST_WARNINGS"

# One known report in upstream code is suppressed, nothing else:
# plaits/dsp/fm/dx_units.h, Pow2Fast(): "r.w += x_integral << 23" shifts a
# negative exponent left (the 6-op models, at low operator levels). That is
# undefined in C++14, but GCC defines signed << as the two's complement
# result and does not exploit it (GCC manual, "Integers implementation"), on
# the Seed as here, so it computes 2^x as intended.
cat > "$BUILD/ubsan.supp" <<'EOF'
shift-base:plaits/dsp/fm/dx_units.h
EOF

# ASan stops at its first error; UBSan reports and goes on, and is counted.
export ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=1}"
export UBSAN_OPTIONS="${UBSAN_OPTIONS:-print_stacktrace=1:suppressions=$BUILD/ubsan.supp}"
SANITIZER_LOG="$BUILD/sanitizer.log"
start=$(date +%s)
set +e
"$BUILD/voice_test" "$@" 2> "$SANITIZER_LOG"
status=$?
set -e
elapsed=$(( $(date +%s) - start ))

reports=$(grep -c -E "runtime error:|ERROR: AddressSanitizer|ERROR: LeakSanitizer" "$SANITIZER_LOG" || true)
if [ -s "$SANITIZER_LOG" ]; then
  echo "---- stderr ($SANITIZER_LOG) ----"
  head -n 200 "$SANITIZER_LOG"
  echo "----"
fi
if [ "$reports" -eq 0 ]; then
  echo "PASS sanitizers: no ASan, LSan or UBSan reports (one known upstream" \
       "shift in fm/dx_units.h suppressed)"
else
  echo "FAIL sanitizers: $reports report(s), see $SANITIZER_LOG"
fi
echo "voice_test: exit status $status, ${elapsed} s"
if [ "$status" -ne 0 ] || [ "$reports" -ne 0 ]; then
  exit 1
fi
exit 0
