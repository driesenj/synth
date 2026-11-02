// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: a tiny test framework.
//
//   TEST(group, name) { CHECK(x == 1); CHECK_NEAR(y, 0.5, 1e-6); }
//
// A failed check prints its file and line and the test goes on. The test
// binary runs every test, or those whose "group" or "group.name" matches an
// argument, and exits 1 when any check failed.

#ifndef SIDEFX_TEST_CHECK_H_
#define SIDEFX_TEST_CHECK_H_

#include <math.h>
#include <stdio.h>

namespace test {

typedef void (*TestFunction)();

struct TestCase {
  const char* group;
  const char* name;
  TestFunction function;
  TestCase* next;
};

void Register(TestCase* test_case);

struct Registrar {
  explicit Registrar(TestCase* test_case) { Register(test_case); }
};

bool Check(bool ok, const char* expression, const char* file, int line);
bool CheckNear(double a, double b, double tolerance, const char* ea,
               const char* eb, const char* file, int line);

// Writes a note under the current test (shown with -v or on failure).
void Note(const char* format, ...) __attribute__((format(printf, 1, 2)));

}  // namespace test

#define TEST(group, name)                                              \
  static void test_##group##_##name();                                 \
  static test::TestCase test_case_##group##_##name = {                 \
    #group, #name, test_##group##_##name, 0 };                         \
  static test::Registrar test_registrar_##group##_##name(              \
      &test_case_##group##_##name);                                    \
  static void test_##group##_##name()

#define CHECK(c) test::Check((c), #c, __FILE__, __LINE__)
#define CHECK_NEAR(a, b, tolerance) \
  test::CheckNear((a), (b), (tolerance), #a, #b, __FILE__, __LINE__)

#endif  // SIDEFX_TEST_CHECK_H_
