// Copyright 2026 the Marblesy authors. MIT licence, see marbles/firmware/LICENSE.
//
// Marblesy: the firmware's entry points, driven by main.cc on the Seed and
// by the host tests. marblesy.cc holds Marbles' marbles.cc minus its
// hardware set-up.

#ifndef MARBLESY_MARBLESY_H_
#define MARBLESY_MARBLESY_H_

#include "marbles/cv_reader.h"
#include "marbles/io_buffer.h"
#include "marbles/settings.h"
#include "marbles/ui.h"

namespace marblesy {

// t deja vu held at power-up, and no other button: the firmware update
// gesture. Three readings 10 ms apart; before Init().
bool BootloaderGesture();

// Everything but the interrupts. After hal::Init().
void Init();

// The I/O interrupt, at 32 kHz.
void IoTick();

// The DSP interrupt, pended by IoTick() at every block of 5 samples.
void DspTick();

// The main loop's work: settings saves.
void Persist();

// The brightness an output LED shows for an output voltage.
uint8_t OutputLedLevel(float volts);

}  // namespace marblesy

// Marbles' globals, as in marbles.cc.
extern marbles::CvReader cv_reader;
extern marbles::IOBuffer io_buffer;
extern marbles::Settings settings;
extern marbles::Ui ui;

#endif  // MARBLESY_MARBLESY_H_
