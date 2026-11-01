# Vendored upstream code

Copied byte for byte, unchanged, from Mutable Instruments' repositories.
Only the files the firmware compiles are here.

| Here | From | Commit |
|---|---|---|
| `plaits/dsp/**`, `plaits/resources.{cc,h}`, `plaits/user_data_receiver.{cc,h}`, `plaits/pot_controller.h` | [pichenettes/eurorack](https://github.com/pichenettes/eurorack) | `f4cfa76` (2026-10-12); `plaits/` last changed in `08460a6` (2023-08-16), the Plaits 1.2 code arrived in `0232b40` (2023-05-29) |
| `stmlib/` (`stmlib.h`, 10 files of `dsp/`, 6 of `utils/`, `LICENSE`) | [pichenettes/stmlib](https://github.com/pichenettes/stmlib) | `e3bd7c9` (2023-05-30), the eurorack submodule's |
| `stm_audio_bootloader/fsk/packet_decoder.{cc,h}`, `LICENSE` | [pichenettes/stm-audio-bootloader](https://github.com/pichenettes/stm-audio-bootloader) | `1ec7d63` (2019-04-02), the eurorack submodule's |

Not copied, because `../src/plaits/` replaces them: `plaits/plaits.cc`
(as `src/main.cc`), `plaits/ui.*`, `plaits/settings.*`, `plaits/user_data.h`,
`plaits/dsp/dsp.h` and `plaits/drivers/*`. Not needed: the bootloader, the
hardware design files, the resource generators and the tests.

Licence: MIT, © Emilie Gillet. The notice is at the top of every source
file, and in `stmlib/LICENSE` and `stm_audio_bootloader/LICENSE`.
