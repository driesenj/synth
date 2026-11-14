#!/bin/sh
# Build and run the host test (Linux or WSL: wsl.exe -e sh run.sh from this folder)
set -e
cd "$(dirname "$0")"
g++ -std=c++17 -g -O1 -Wall -Wno-unused-parameter -fsanitize=address,undefined -I. -o /tmp/eight_host_test host_test.cpp
/tmp/eight_host_test
