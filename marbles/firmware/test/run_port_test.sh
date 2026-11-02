#!/bin/bash
# Marblesy host tests: builds the port and Marbles' own code with g++ under
# AddressSanitizer and UBSan, on a model of the board (hal_fake.cc), and
# runs them. Needs g++ and python3 (WSL or Linux). From marbles/firmware:
#
#   bash test/run_port_test.sh          all groups
#   bash test/run_port_test.sh outcal   one group (cv, dac, outcal, leds,
#                                       buttons, io, storage, settings, dsp)
set -e
cd "$(dirname "$0")/.."

mkdir -p test/build
python3 test/gen_board_tables.py test/build/board_tables.h

SOURCES="$(ls src/*.cc | grep -v -e main.cc -e hal_daisy.cc) \
  src/marbles/*.cc src/marbles/drivers/*.cc src/marbles/random/*.cc \
  $(find vendor -name '*.cc' | sort) \
  test/hal_fake.cc test/port_test.cc"

g++ -std=gnu++14 -g -O1 -DTEST \
  -Wall -Wno-unused-variable -Wno-unused-function \
  -fsanitize=address,undefined -fno-sanitize-recover=undefined \
  -Itest/build -Isrc -Ivendor -Itest \
  $SOURCES -o test/build/port_test

ASAN_OPTIONS=detect_leaks=0 test/build/port_test "$@"
