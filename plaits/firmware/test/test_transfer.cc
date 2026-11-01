// Plaitsy host tests, group 8: receiving a user data block (DX7 bank, wave
// terrain, wavetables) through the TIMBRE input, as main.cc does it, with
// the ADC timings Plaitsy may have.
//
// Plaits decodes the block at the 4 kHz poll rate: the sign of the
// derivative of the TIMBRE CV changes at every symbol boundary, and a
// symbol's length in polls (2, 5 or 9) says what it is (UserDataReceiver,
// Demodulator<9, 5, 2>). Plaits' SDADC samples at a fixed point of every
// poll. Plaitsy's ADC scans freely, so the reading Poll() takes is up to
// one scan old, by an amount that changes from poll to poll. These runs
// send a whole 4 kB block (16 packets: preamble, 256 bytes, CRC) and see
// whether it arrives.

#include "port_test.h"

#include "plaits/user_data_receiver.h"

namespace test {

using namespace plaits;
using stm_audio_bootloader::PacketDecoderState;

namespace {

// The editor's signal: one half-cosine per symbol, rising and falling in
// turn, so the derivative's sign flips at every symbol boundary.
struct FskSignal {
  std::vector<double> start;  // start of each symbol (us), then the end
  std::vector<int> symbols;   // what was sent
  double amplitude;
  double offset;

  double operator()(double t) const {
    if (t < start.front()) {
      return offset - amplitude;
    }
    if (t >= start.back()) {
      const size_t n = start.size() - 1;
      return offset + (n % 2 ? amplitude : -amplitude);
    }
    const size_t k = static_cast<size_t>(
        std::upper_bound(start.begin(), start.end(), t) - start.begin()) - 1;
    const double x = (t - start[k]) / (start[k + 1] - start[k]);
    const double rising = k % 2 == 0 ? 1.0 : -1.0;
    return offset - rising * amplitude * cos(M_PI * x);
  }
};

std::shared_ptr<FskSignal> Encode(const uint8_t* block, double t0,
                                  double amplitude, double clock_error) {
  std::vector<int> symbols;
  auto blanks = [&symbols](int n) {
    for (int i = 0; i < n; ++i) symbols.push_back(2);
  };
  blanks(64);
  for (int p = 0; p < UserData::SIZE / 256; ++p) {
    blanks(16);
    for (int i = 0; i < 32; ++i) {
      symbols.push_back(i % 2 == 0 ? 1 : 0);  // preamble
    }
    uint8_t packet[260];
    memcpy(packet, block + 256 * p, 256);
    const uint32_t crc = plaitsy::Crc32(0, packet, 256);  // standard CRC-32
    packet[256] = static_cast<uint8_t>(crc >> 24);
    packet[257] = static_cast<uint8_t>(crc >> 16);
    packet[258] = static_cast<uint8_t>(crc >> 8);
    packet[259] = static_cast<uint8_t>(crc);
    for (int b = 0; b < 260; ++b) {
      for (int bit = 7; bit >= 0; --bit) {
        symbols.push_back((packet[b] >> bit) & 1);
      }
    }
  }
  blanks(600);  // end of transmission: 500 blanks or more
  const double kPoll = 250.0 * (1.0 + clock_error);
  const double kDuration[3] = { 2.0 * kPoll, 5.0 * kPoll, 9.0 * kPoll };
  auto signal = std::make_shared<FskSignal>();
  signal->amplitude = amplitude;
  signal->offset = 0.0;
  double t = t0;
  for (int s : symbols) {
    signal->start.push_back(t);
    t += kDuration[s];
  }
  signal->start.push_back(t);
  signal->symbols = symbols;
  return signal;
}

// FSK_DEBUG=1: a second threshold + demodulator on the same samples, never
// resynchronized, so its symbols line up one to one with the sent ones;
// prints the first that differs, with the run lengths and sample ages.
struct ShadowDemodulator {
  AdaptiveThreshold threshold;
  bool previous_sign;
  int run;  // samples in the current run
  struct Run {
    int symbol;
    int length;
    double t;
    double age;
  };
  std::vector<Run> runs;

  void Init() {
    threshold.Init(0.001f, 0.005f);
    previous_sign = false;
    run = 0;
  }
  void Process(float sample, double t, double age) {
    const bool sign = threshold.ProcessCosine(sample);
    if (sign == previous_sign) {
      ++run;
      return;
    }
    previous_sign = sign;
    const int d = run;  // Demodulator's duration_: samples in the run - 1
    runs.push_back({ d >= 7 ? 2 : (d >= 3 ? 1 : 0), run + 1, t, age });
    run = 0;
  }
  void Report(const std::vector<int>& sent, const char* label) const {
    // runs[0] is the rest before the first symbol.
    size_t first = 0;
    for (size_t j = 1; j < runs.size() && j - 1 < sent.size(); ++j) {
      if (runs[j].symbol != sent[j - 1]) {
        first = j;
        break;
      }
    }
    if (!first) {
      printf("     fsk debug (%s): all %zu symbols right\n", label,
             runs.size() - 1);
      return;
    }
    printf("     fsk debug (%s): first wrong symbol #%zu at %.1f ms\n", label,
           first - 1, runs[first].t * 1e-3);
    for (size_t j = first > 8 ? first - 8 : 1;
         j < std::min(runs.size(), first + 6); ++j) {
      printf("       #%zu sent %d got %d run %d samples, age %.0f us%s\n",
             j - 1, sent[j - 1], runs[j].symbol, runs[j].length, runs[j].age,
             j == first ? "   <--" : "");
    }
  }
};

struct TransferResult {
  bool end_of_transmission;
  float progress;
  int packets_ok;
  int crc_errors;
  int sync_errors;
  bool saved;
  bool data_ok;
  double seconds;
};

// stop_at_first_error: end the run at the first CRC error or the first sync
// error after a packet arrived (either makes the whole transfer fail: the
// receiver starts again from 0).
TransferResult Transfer(std::function<double(double)> age, double amplitude,
                        double clock_error, uint64_t seed,
                        bool stop_at_first_error = false) {
  TransferResult r;
  memset(&r, 0, sizeof(r));
  fake::ResetBoard();
  FreshFlash();
  Rig rig;
  rig.Boot();
  rig.RunMs(300.0);
  // Bring the target model: the block is for model 13 (wavetables).
  rig.patch.engine = 13;
  std::vector<uint8_t> block(UserData::SIZE);
  uint64_t state = seed;
  for (int i = 0; i < UserData::SIZE; ++i) {
    state ^= state << 13;
    state ^= state >> 7;
    state ^= state << 17;
    block[i] = static_cast<uint8_t>(state >> 24);
  }
  block[UserData::SIZE - 2] = 13;
  block[UserData::SIZE - 1] = 13;
  const std::vector<uint8_t> sent = block;

  std::vector<uint8_t> rx_buffer(UserData::SIZE);
  UserDataReceiver receiver;
  receiver.Init(rx_buffer.data(), UserData::SIZE);
  UserData user_data;

  const double t0 = fake::TimeUs() + 1000.0 + 37.3;  // off the poll grid
  std::shared_ptr<FskSignal> signal = Encode(block.data(), t0, amplitude,
                                             clock_error);
  fake::PatchFunction(plaitsy::hal::ADC_TIMBRE,
                      [signal](double t) { return (*signal)(t); });
  fake::SetAdcLatencyFunction(age);
  const double end = signal->start.back() + 200000.0;
  PacketDecoderState previous = stm_audio_bootloader::PACKET_DECODER_STATE_SYNCING;
  const double started = fake::TimeUs();
  const bool debug = getenv("FSK_DEBUG") != nullptr;
  ShadowDemodulator shadow;
  shadow.Init();
  while (fake::TimeUs() < end) {
    const double now = fake::TimeUs();
    rig.Poll();
    if (rig.polls % 4 == 0) {
      rig.MainLoop();
    }
    if (debug) {
      shadow.Process(rig.modulations.timbre, now, age(now));
    }
    // main.cc's AudioCallback(), after ui.Poll().
    if (!rig.modulations.timbre_patched) {
      continue;
    }
    const PacketDecoderState s = receiver.Process(rig.modulations.timbre);
    bool fatal = false;
    if (s != previous) {
      if (s == stm_audio_bootloader::PACKET_DECODER_STATE_OK) ++r.packets_ok;
      if (s == stm_audio_bootloader::PACKET_DECODER_STATE_ERROR_CRC) {
        ++r.crc_errors;
        fatal = true;
      }
      if (s == stm_audio_bootloader::PACKET_DECODER_STATE_ERROR_SYNC) {
        ++r.sync_errors;
        fatal = r.packets_ok > 0;
      }
    }
    previous = s;
    if (stop_at_first_error && fatal) {
      break;
    }
    if (s == stm_audio_bootloader::PACKET_DECODER_STATE_END_OF_TRANSMISSION) {
      r.end_of_transmission = true;
      r.progress = receiver.progress();
      if (receiver.progress() == 1.0f) {
        r.saved = user_data.Save(receiver.rx_buffer(), rig.patch.engine);
      }
      receiver.Reset();
      break;
    }
  }
  r.seconds = (fake::TimeUs() - started) * 1e-6;
  if (debug) {
    char label[64];
    snprintf(label, sizeof(label), "+-%.1f V", amplitude);
    shadow.Report(signal->symbols, label);
  }
  const uint8_t* p = user_data.ptr(13);
  r.data_ok = r.saved && p &&
      memcmp(p, sent.data(), UserData::SIZE - 2) == 0;
  fake::SetAdcLatencyFunction(nullptr);
  return r;
}

std::string Describe(const TransferResult& r) {
  char text[200];
  snprintf(text, sizeof(text), "%s, progress %.2f, %d packets OK, %d CRC "
           "errors, %d sync errors, saved %d, data %s (%.1f s)",
           r.end_of_transmission ? "end of transmission" : "NO END",
           r.progress, r.packets_ok, r.crc_errors, r.sync_errors, r.saved,
           r.data_ok ? "intact" : "WRONG", r.seconds);
  return text;
}

// How old the TIMBRE reading is at each Poll() on the Seed, from a model of
// libDaisy's scheduling (v9.0.0, src/per/adc.cpp, src/sys/dma.c):
// - with a mux configured, the 9-channel sequence runs in one-shot DMA mode;
//   its end raises DMA1_Stream2's interrupt, whose handler moves the mux and
//   restarts the sequence (taking `restart` us);
// - every DMA interrupt has priority 0/0, so that handler cannot preempt the
//   audio callback (DMA1_Stream0/1, which also wins ties), nor the reverse;
// - the DMA writes each channel's result as soon as it is converted; TIMBRE
//   (A1) is the second of the nine, sampled around 1.5/9 into the sequence;
// - the callback takes `callback` us plus a little more on some UI tasks
//   and a random `jitter`.
// Returns, per Poll() n (at n * 250 us), how long before n * 250 us the
// reading it gets was sampled.
std::vector<double> SeedLatencySchedule(double conversion, double restart,
                                        double callback, double jitter,
                                        int polls, uint64_t seed) {
  std::vector<double> latency(polls);
  uint64_t state = seed ? seed : 1;
  auto uniform = [&state]() {
    state ^= state << 13;
    state ^= state >> 7;
    state ^= state << 17;
    return static_cast<double>(state >> 11) / 9007199254740992.0;
  };
  const double kTaskExtra[4] = { 4.0, 1.0, 2.0, 1.5 };  // LEDs, buttons, ...
  double cpu_free = 0.0;
  double sequence = 0.0;  // start of the running sequence
  double previous_sequence = -1e9;
  double isr_request = sequence + conversion;
  int n = 0;
  while (n < polls) {
    const double audio_request = n * 250.0;
    const double audio_start = std::max(audio_request, cpu_free);
    const double isr_start = std::max(isr_request, cpu_free);
    if (isr_start < audio_start) {
      cpu_free = isr_start + restart;
      previous_sequence = sequence;
      sequence = cpu_free;
      isr_request = sequence + conversion;
    } else {
      // Convert() at the start of the callback: TIMBRE's slot holds the
      // running sequence's value once it has been converted, else the
      // previous sequence's.
      const double written = sequence + 2.0 * conversion / 9.0;
      const double sampled = (written <= audio_start ? sequence
                                                      : previous_sequence) +
          1.5 * conversion / 9.0;
      latency[n] = audio_request - sampled;
      cpu_free = audio_start + callback + kTaskExtra[n % 4] + jitter * uniform();
      ++n;
    }
  }
  return latency;
}

}  // namespace

void TestDataTransfer() {
  Section("8. User data through TIMBRE, with the ADC's timing");
  struct Model {
    const char* name;
    std::function<double(double)> age;
    bool plaits_like;
  };
  auto scan = [](double period, double phase) {
    return [period, phase](double t) { return fmod(t + phase, period); };
  };
  auto random_age = [](double max_age, uint64_t seed) {
    auto state = std::make_shared<uint64_t>(seed);
    return [state, max_age](double) {
      uint64_t& x = *state;
      x ^= x << 13;
      x ^= x >> 7;
      x ^= x << 17;
      return static_cast<double>(x >> 11) / 9007199254740992.0 * max_age;
    };
  };
  const Model models[] = {
    { "fixed sample point (Plaits' SDADC)", [](double) { return 0.0; }, true },
    { "fixed 200 us old", [](double) { return 200.0; }, true },
    { "free-running scan, 200 us", scan(200.0, 44.0), false },
    { "free-running scan, 170 us", scan(170.0, 10.0), false },
    { "free-running scan, 230 us", scan(230.0, 51.0), false },
    { "free-running scan, 245 us (slow beat)", scan(245.0, 3.0), false },
    { "random age 0..200 us", random_age(200.0, 99), false },
  };
  const double amplitudes[] = { 2.5, 1.0 };
  for (double amplitude : amplitudes) {
    for (const Model& m : models) {
      if (!m.plaits_like) {
        continue;
      }
      // The encoder, the decoder and the rig must work where Plaits does.
      const TransferResult r = Transfer(m.age, amplitude, 150e-6, 1234);
      const bool ok = r.end_of_transmission && r.progress == 1.0f &&
          r.saved && r.data_ok;
      char name[160];
      snprintf(name, sizeof(name), "transfer (+-%.1f V, %s): the 4 kB block "
               "arrives", amplitude, m.name);
      Check(name, ok, "%s", Describe(r).c_str());
    }
  }

  // How much the reading's age may vary before the decoder fails.
  std::string stress;
  for (const Model& m : models) {
    if (m.plaits_like) {
      continue;
    }
    const TransferResult r = Transfer(m.age, 1.0, 150e-6, 1234, true);
    const bool ok = r.end_of_transmission && r.progress == 1.0f && r.data_ok;
    stress += std::string(stress.empty() ? "" : "; ") + m.name +
        (ok ? " ok" : " FAILS");
  }
  double tolerated = 0.0;
  bool still_ok = true;
  const double spans[] = { 25.0, 50.0, 75.0, 100.0, 150.0 };
  for (double span : spans) {
    bool all_ok = true;
    for (uint64_t seed = 1; seed <= 3 && all_ok; ++seed) {
      const TransferResult r = Transfer(random_age(span, seed * 7 + 1), 1.0,
                                        150e-6, 1234 + seed, true);
      all_ok = r.end_of_transmission && r.progress == 1.0f && r.data_ok;
    }
    char text[64];
    snprintf(text, sizeof(text), "; random age 0..%.0f us %s", span,
             all_ok ? "ok (3 of 3)" : "FAILS");
    stress += text;
    still_ok = still_ok && all_ok;
    if (still_ok) {
      tolerated = span;
    }
  }
  Observe("FSK decoder (Plaits' own) against the age of the reading Poll() "
          "gets, ADC timing models not taken from the Seed: %s. Random ages "
          "spanning up to %.0f us were tolerated. A failure is a skipped "
          "sample: the derivative then spans ~0.5 ms, a symbol boundary is "
          "seen a poll late and a 5-poll 'one' shrinks to 3 polls, read as a "
          "'zero'", stress.c_str(), tolerated);

  // The Seed's timing, from libDaisy's scheduling. The conversion time of
  // the 9-channel OVS_8 sequence and the audio callback's length are not
  // known before the hardware runs (the callback's depends on the model), so
  // sweep them. A poll reads TIMBRE from the latest sequence or the one
  // before, depending on whether TIMBRE's conversion finished just before
  // or just after the poll: that is what makes the age jump.
  // Expected on the Seed: the sequence about 100 us (ADC clock 12.3 MHz) or
  // 200 us (6.1 MHz, rev V's extra /2) for 9 x 8 x 17 cycles, the callback
  // a fraction of the 250 us (Plaits fits the slowest model in it on a
  // 72 MHz Cortex-M4). The check covers 60..230 us x 30..150 us; the rest
  // of the sweep is reported.
  const double callbacks[] = { 30, 60, 100, 150, 190 };
  int runs = 0, failed = 0, steady = 0, expected_failed = 0;
  std::string failures_text, expected_failures_text;
  for (double callback : callbacks) {
    for (double conversion = 40.0; conversion <= 250.0; conversion += 5.0) {
      const std::vector<double> schedule = SeedLatencySchedule(
          conversion, 10.0, callback, 10.0, 140000,
          static_cast<uint64_t>(conversion * 1000 + callback));
      double lo = 1e9, hi = -1e9;
      for (size_t i = 1000; i < schedule.size(); ++i) {
        lo = std::min(lo, schedule[i]);
        hi = std::max(hi, schedule[i]);
      }
      if (hi - lo <= 25.0) {
        ++steady;  // the age barely moves: as the fixed-age references
        continue;
      }
      auto table = std::make_shared<std::vector<double>>(schedule);
      auto origin = std::make_shared<double>(NAN);
      auto age = [table, origin](double now) {
        if (std::isnan(*origin)) {
          *origin = now;
        }
        long n = lround((now - *origin) / 250.0);
        n = std::max(0L, std::min(n, static_cast<long>(table->size()) - 1));
        return (*table)[n];
      };
      const TransferResult r = Transfer(age, 1.0, 150e-6, 4321, true);
      const bool ok = r.end_of_transmission && r.progress == 1.0f &&
          r.data_ok;
      ++runs;
      if (!ok) {
        ++failed;
        char text[96];
        snprintf(text, sizeof(text), "%s%.0f/%.0f (age %.0f..%.0f)",
                 failures_text.empty() ? "" : ", ", conversion, callback, lo,
                 hi);
        failures_text += text;
        if (conversion >= 60.0 && conversion <= 230.0 && callback <= 150.0) {
          ++expected_failed;
          expected_failures_text += text;
        }
      }
    }
  }
  const int total = runs + steady;
  Check("transfer: the 4 kB block arrives at the expected Seed ADC timings "
        "(sequence 60..230 us x callback 30..150 us, 5 us steps; the scan's "
        "restart waits for the audio callback, as in libDaisy)",
        expected_failed == 0, "%d fail%s%s; %d of the %d timings swept keep "
        "the age within 25 us, %d were run", expected_failed,
        expected_failed ? ": " : "", expected_failures_text.c_str(), steady,
        total, runs);
  Observe("TIMBRE data transfer risk: over the whole sweep (sequence "
          "40..250 us x callback 30..190 us) %d of %d timings lose the block "
          "(sequence/callback us): %s. Two bands: a sequence (+ restart) "
          "about as long as the 250 us poll, and a callback near 190 us "
          "(76 %% CPU). Plaits' SDADC has a fixed sample point; the Seed's "
          "free-running scan gives Poll() a reading from the latest or the "
          "previous sequence, and the age jumps by a sequence when TIMBRE's "
          "conversion ends within a few us of a poll",
          failed, total, failed ? failures_text.c_str() : "none");
}

}  // namespace test
