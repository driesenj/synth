// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: runs the registered tests (see check.h).
//   test [-v] [group | group.name]...

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "check.h"

namespace test {

namespace {

TestCase* first = 0;
TestCase* last = 0;
int checks = 0;
int failures = 0;
bool verbose = false;
const TestCase* current = 0;

bool Matches(const TestCase* t, int argc, char** argv) {
  bool any = false;
  for (int i = 1; i < argc; ++i) {
    if (argv[i][0] == '-') {
      continue;
    }
    any = true;
    char full[256];
    snprintf(full, sizeof(full), "%s.%s", t->group, t->name);
    if (!strcmp(argv[i], t->group) || !strcmp(argv[i], full)) {
      return true;
    }
  }
  return !any;
}

}  // namespace

void Register(TestCase* test_case) {
  test_case->next = 0;
  if (last) {
    last->next = test_case;
  } else {
    first = test_case;
  }
  last = test_case;
}

bool Check(bool ok, const char* expression, const char* file, int line) {
  ++checks;
  if (!ok) {
    ++failures;
    printf("FAIL %s.%s: %s (%s:%d)\n", current ? current->group : "?",
           current ? current->name : "?", expression, file, line);
  }
  return ok;
}

bool CheckNear(double a, double b, double tolerance, const char* ea,
               const char* eb, const char* file, int line) {
  ++checks;
  const double d = a > b ? a - b : b - a;
  if (!(d <= tolerance)) {
    ++failures;
    printf("FAIL %s.%s: %s = %.9g, %s = %.9g, |difference| %.3g > %.3g "
           "(%s:%d)\n", current ? current->group : "?",
           current ? current->name : "?", ea, a, eb, b, d, tolerance, file,
           line);
    return false;
  }
  return true;
}

void Note(const char* format, ...) {
  if (!verbose) {
    return;
  }
  va_list args;
  va_start(args, format);
  printf("     ");
  vprintf(format, args);
  printf("\n");
  va_end(args);
}

}  // namespace test

int main(int argc, char** argv) {
  for (int i = 1; i < argc; ++i) {
    if (!strcmp(argv[i], "-v")) {
      test::verbose = true;
    }
  }
  int run = 0;
  for (test::TestCase* t = test::first; t; t = t->next) {
    if (!test::Matches(t, argc, argv)) {
      continue;
    }
    test::current = t;
    const int before = test::failures;
    if (test::verbose) {
      printf("---- %s.%s\n", t->group, t->name);
    }
    t->function();
    ++run;
    if (test::verbose && test::failures == before) {
      printf("ok   %s.%s\n", t->group, t->name);
    }
  }
  printf("%d tests, %d checks, %d failed\n", run, test::checks,
         test::failures);
  return test::failures || !run ? 1 : 0;
}
