# Vendored upstream code

Copied byte for byte, unchanged, from Mutable Instruments' repositories.
Only the files the firmware compiles are here.

| Here | From | Commit |
|---|---|---|
| `marbles/` (the DSP in `random/` and `ramp/`, `cv_reader.*`, `cv_reader_channel.h`, `io_buffer.h`, `clock_self_patching_detector.h`, `note_filter.h`, `scale_recorder.h`, `resources.{cc,h}`) | [pichenettes/eurorack](https://github.com/pichenettes/eurorack) | `f4cfa76` (2026-10-12); `marbles/` last changed in `db1566f` (2023-01-08, "latest update with reset input mode and bug fixes") |
| `stmlib/` (`stmlib.h`, 5 files of `dsp/`, 4 of `utils/`, `ui/event_queue.h`, `system/system_clock.{cc,h}`, `LICENSE`) | [pichenettes/stmlib](https://github.com/pichenettes/stmlib) | `e3bd7c9` (2023-05-30), the eurorack submodule's |

Not copied, because `../src/marbles/` replaces them: `marbles/marbles.cc`
(as `src/marblesy.cc` and `src/main.cc`), `marbles/ui.*`,
`marbles/settings.*`, `marbles/drivers/*` and `marbles/random/lag_processor.cc`
(one marked fix, see the file). Not needed: the bootloader, the hardware
design files, the resource generators and the tests.

Licence: MIT, © Emilie Gillet. The notice is at the top of every source
file, and in `stmlib/LICENSE`.
