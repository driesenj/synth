#pragma once


#define DEBUG_LOG 0

#define STATIC_ASSERT(expr) typedef char _sa_[(expr) ? 1 : -1]

#define CLAMP(x, lo, hi)  ((x) < (lo) ? (lo) : ((x) > (hi) ? (hi) : (x)))
