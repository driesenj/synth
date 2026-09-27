# Firmware design — v1 feature set and control map

The design of the full firmware on the v2 hardware of `pinout.md`, now
built: it uses the 28 keys, the 15 scanned buttons, the two pots, the CV
select switch, the clock jack, both DIN sockets and the USB-UART, and drives
the toy, MIDI out, CV/gate A and B, AUX and the record-button LED. Where the
build departed from the sketch the text below was updated; §7 lists the
decisions taken along the way.

Words: *tap* = one closure into the toy through the injector; *long* = a
button held ≥ 1 s (`LONG_PRESS_MS`, one constant for every long press);
*performance event* = a note on/off or a toy-button press, whoever produced
it.

---

## 1. Signal flow

```
 keys ──────────────────┐                        ┌──→ toy      (a tap per note or button; mono, one-shot)
 MIDI in ch 1 (DIN/USB) ┼──→ performance events ─┼──→ MIDI out (DIN + USB) ch 1, CC 20-34
 loop playback ─────────┤          │              └──→ CV/gate A or B  (the switch), base pitch + tune
 arpeggiator ───────────┘          └──→ looper record (keys, MIDI in and the arp; never its own playback)

 MIDI in ch 2 ──────────────────────────────────────→ CV/gate on the other pair, pots not applied
 buttons ───→ toy taps (voices, catface, rhythm, STOP), CC out, looper transport, settings
 clock: tap tempo | MIDI clock | jack ───→ loop transport, arp, AUX shapes, LED beat, MIDI clock out
```

One router. A note behaves the same whether a key, a DAW, the arp or the
loop played it: a tap into the toy, a note on MIDI out, CV/gate on the
selected channel. The looper records what comes in from the keys, MIDI and
the arp, never what it plays back, so overdubs stack instead of doubling.

---

## 2. Control map

The toy's buttons: what they did, what they do. Buttons with a long-press
function act on release (a short press costs the release, ~100 ms — fine
for transport and settings); the voice buttons and catface act on the press,
as now, so the toy's latency is unchanged.

| Button | Toy's function | Short press | Long press (≥ 1 s) |
|---|---|---|---|
| piano · bells · meow · organ · banjo | voice | **unchanged** — tapped into the toy, CC 20–24 out, and recorded into the loop | — |
| ♪ (treble clef) | demo songs | **tap tempo** — 3+ taps set the internal clock | the toy's demo song (its old function) |
| catface | cat sound | **unchanged**, and recorded into the loop | **toy notes** on / off — the toy stops playing notes (keys, MIDI, arp, loops) and only its buttons still reach it; the jacks and MIDI carry on. Hold the cat's face to hush the cat |
| STOP | stops rhythm / song | **stop the loop**, and STOP tapped into the toy | **panic** — notes off everywhere, tap queue flushed, gates low |
| record | the toy's recorder | empty → **record** · recording → play · playing → **overdub** · overdubbing → play | **undo** the newest overdub |
| play | the toy's playback | **play / stop** the loop | **clear** the loop (only while stopped) |
| rock | rhythm | **next rhythm**: rock → blues → samba → techno → disco → rock … tapped into the toy | stop the rhythm (STOP into the toy; the loop keeps going) |
| blues | rhythm | **quantise loop** on / off | **gate mode**: retrigger / legato |
| samba | rhythm | **quantise pitch** on / off | **glide**: off / short / long |
| techno | rhythm | **AUX waveform**: next | **AUX rate**: per loop / per bar / per beat |
| disco | rhythm | **arpeggiator** on / off | **arp order**: up / down / up-down / as played |
| volume ± · tempo ± | on the toy's PCB | **unchanged** — native, not scanned; reachable from MIDI CC 35–38 | — |

Every one of the toy's own functions stays reachable: the voices, catface
and rhythms directly, the demo song on a long press, volume and tempo on
the toy's own buttons. Only its recorder is gone, replaced by the looper.

| Control | Function |
|---|---|
| base pitch pot | transposes the keys' path — keys, MIDI ch 1, the arp, both loops — on CV and MIDI out, ±12 semitones, on both pairs. The toy plays its own pitch regardless, and MIDI ch 2's CV is untouched: the DAW's C4 is always the C4 voltage. Quantise pitch **on**: semitone steps. **Off**: continuous — detune the CV voice against the toy, or sweep |
| tune pot | ±50 cents on the keys' CV, always continuous |
| CV select switch | which CV/gate pair the keys drive **and which loop they record into**: open = A, closed = B. There is a loop per pair; the transport buttons and the LED belong to the selected one, the other keeps playing on its own pair. MIDI ch 2 gets the other pair |
| clock in | external clock, `CLOCK_PPQN` pulses per beat (default 4: one per 16th). Overrides tap tempo while pulses arrive |
| MIDI in | DIN and USB, merged — §3.4 |
| LED | looper state and the beat — §3.7 |

---

## 3. Features

### 3.1 Playing

- A key: tap into the toy (as now), note on/off on MIDI ch 1 (velocity
  fixed), CV/gate on the selected channel.
- CV is 1 V/oct with 0 V = A2 (MIDI 45): the lowest key A3 sits at 1 V with
  the pot centred, C6 at 3.25 V, and ±1 octave from the pot stays inside the
  DAC's 0–4.95 V. Outside that it clamps.
- Last-note priority with a note stack: release a key while another is
  held and CV returns to the held one, gate stays high. Gate is 0 / 4.5 V.
- Quantise pitch: on = base pitch in semitone steps, with hysteresis so the
  ADC's noise cannot flicker a step; off = continuous, smoothed.
- MIDI out as now — notes on ch 1, buttons as CC 20–34 (127 press / 0
  release) — plus everything the loop and the arp play.

### 3.2 Looper

- **Two loops, one per CV/gate pair.** The switch selects the active one:
  the keys record into it, record / play / STOP / undo / clear act on it,
  the LED shows it. The other loop keeps playing on its own pair. Build a
  loop on A, flip to B, play over it and build a second there. Panic and a
  DAW's start / stop act on both. The first loop to record sets the beat
  grid; while any loop runs, a new recording's first note snaps to that
  grid instead of moving it.
- **Records** key, MIDI ch 1 and arp notes (on and off), the voice buttons
  and catface. Does **not** record rhythm, STOP, the transport or settings
  buttons, or the loops' own playback. With the arp on, the held keys are the
  arp's input and the arp's notes are what gets recorded — not both.
- Positions are stored in **clock ticks** (96 per beat), not milliseconds,
  so a loop follows a tempo change or an external clock instead of drifting
  against it.
- **First pass**: record arms (LED blinks red); the first note starts the
  loop and *is* beat 1 — with the internal clock, the clock's phase is reset
  to it; with an external clock the note snaps to the clock's grid. Record,
  play or STOP closes the loop: length as played (quantise off) or rounded to
  the nearest **beat** (on). Record and play go straight into playback; STOP
  keeps the loop and stops.
- The beat, not the bar: no clock source knows the bar. MIDI clock is 24
  pulses per quarter with no time signature, the jack is bare pulses, tap
  tempo is beats. A 3-beat loop is a 3-beat loop. `BEATS_PER_BAR` (4) exists
  only for the AUX *per bar* rate and the LED's beat-1 flash, counted from
  beat 1 of the loop, where a wrong assumption is harmless.
- **Overdub**: record while playing. Each pass is a layer; long record undoes
  the newest layer, and can be repeated down to the first pass. A note held
  across the end of a pass is closed on its last tick and reopened on the
  first tick of the next, in the next layer; a key still down when the
  recording closes keeps recording until it comes up. So every note-on has
  its note-off in its own layer and undo never leaves a note hanging.
- **Quantise loop** is a live toggle: on = every event plays at its nearest
  16th; off = as recorded. Events keep their raw ticks, so it can be flipped
  while the loop runs and flipped back; the flip takes effect from the next
  pass.
- **Toy playback**: each note is a tap, and a tap costs 100 ms on a mono
  switch, so a loop denser than ~10 notes/s arpeggiates — the same thing a
  chord does today. A tap that would leave the queue more than
  `LOOP_TAP_LATE_MS` (40) late is dropped *for the toy only*; MIDI and CV play
  it on time. Live keys are never dropped in favour of the loop.
- Limits: 1024 events (6 KB), 64 beats — `LOOP_MAX_EVENTS`, `LOOP_MAX_BEATS`.

### 3.3 Clock

- **Internal**: tap tempo on ♪, 40–300 BPM, default 120, remembered across
  power cycles. Always running, so the arp, AUX shapes and the beat LED work
  with no loop and no cable.
- **MIDI clock** (24 PPQN) from DIN or USB: takes over while it runs;
  start / stop / continue drive the loop transport (start = loop from
  beat 1).
- **Jack**: `CLOCK_PPQN` pulses per beat, on an edge interrupt so the edge
  time is exact; takes over while pulses arrive. No transport — the loop's
  beat 1 is the first recorded note.
- Priority MIDI > jack > internal; two seconds without external ticks and
  the internal clock resumes at the last tempo, phase-continuous.
- Bars are `BEATS_PER_BAR` (4) from beat 1 — the loop's start, a MIDI start,
  or the first tap.
- **MIDI clock out**: 0xF8 at 24 PPQN plus start / stop with the loop,
  whenever the master is *not* MIDI clock in — internal or the jack. So a
  DAW can follow the keyboard, and a modular clock at the jack comes out of
  the DIN socket as MIDI clock. Never re-sent from MIDI clock in: that is a
  loop.

### 3.4 MIDI in

Two parsers — DIN on UART2, USB on UART0 when `USB_MIDI` is 1 — each with
its own running status, feeding one handler. Real-time bytes interleave,
active sensing and SysEx are ignored.

| Message | Effect |
|---|---|
| notes, ch 1 | performance events: the toy, the selected CV/gate pair, recorded into the loop like keys. Not echoed to MIDI out (no thru — the DAW's local echo must be off). For the toy, notes outside A3–C6 are folded by octaves into range (`MIDI_IN_FOLD`, or dropped); CV gets the real note |
| notes, ch 2 | the *other* CV/gate pair, direct, pots not applied. The DAW drives one CV voice while the keys play the toy and the other |
| CC 20–34 | taps the matching toy button — the same numbers the buttons send *out*, so a DAW that recorded a voice change plays it back onto the toy |
| CC 35–38 | tempo +, tempo −, volume +, volume − — the toy's own buttons, injectable though never scanned |
| program change 0–4 | piano, bells, meow, organ, banjo |
| CC 1 (mod wheel) | AUX, when the AUX waveform is *mod wheel* |
| pitch bend | ±2 semitones on the CV of the channel it arrives on (ch 1 = the keys' pair, ch 2 = the other) |
| CC 64 (sustain) | holds that channel's gate, and its last note, until released |
| CC 102–111 | settings — the table below |
| CC 120 / 123 | all notes off on MIDI, CV and the toy's queue — panic without the reset |
| clock, start, stop, continue | §3.3 |

Settings over CC, so a DAW can automate them; the same state the buttons
change, with the same LED blink:

| CC | Setting | Value |
|---|---|---|
| 102 | quantise loop | < 64 off, ≥ 64 on |
| 103 | quantise pitch | < 64 off, ≥ 64 on |
| 104 | AUX waveform | 0–10, the table in §3.6 |
| 105 | AUX rate | 0 per loop, 1 per bar, 2 per beat |
| 106 | gate mode | < 64 legato, ≥ 64 retrigger |
| 107 | glide | 0 off, 1 short, 2 long |
| 108 | arpeggiator | < 64 off, ≥ 64 on |
| 109 | arp order | 0 up, 1 down, 2 up-down, 3 as played |
| 110 | arp rate | 0 16ths, 1 8ths, 2 quarters — no button for this one, `ARP_DIV` is the default |
| 111 | toy notes | < 64 off, ≥ 64 on |

**USB**: the bridge grows a return path — the DAW's output on a MIDI port →
serial. It needs **two loopMIDI ports** on Windows, `Meowsic out` (keyboard →
DAW) and `Meowsic in` (DAW → keyboard): every writer on a loopMIDI port
reaches every reader, so one port would echo the keyboard's own notes
straight back into it and the toy would double every note. `--create` on
macOS/Linux makes a separate input and output already.

### 3.5 CV / gate

- Two identical channels, each: 12-bit DAC → ×1.5, `CV_CODES_PER_SEMITONE`
  per channel as calibrated; gate on a GPIO, 0 / 4.5 V.
- Per channel: a note stack (last-note priority), pitch bend, sustain.
  The keys' channel also gets base pitch, tune, quantise pitch, gate mode
  and glide; the other channel is what the DAW sent, 1 V/oct.
- **Gate mode**. *Retrigger*: the gate dips low for `GATE_RETRIG_MS` (3) on
  every new note while others are held, so an envelope restarts per note.
  *Legato*: it stays high across overlapping notes.
- **Glide**: the DAC code slews toward the target — off, ~50 ms, ~250 ms
  (`GLIDE_MS`). The DAC is written every loop iteration anyway.
- The switch is read as a level, at boot and on change; flipping it moves
  the keys' channel and sends the old channel's gate low.

### 3.6 AUX out

8-bit DAC, 0–4.5 V, written when it changes. Shapes are phase-locked to
the clock; the **rate** (techno long) is per loop, per bar or per beat —
*per loop* is the active loop's pass, the other loop's if the active one is
stopped, and a bar when no loop runs.

| # | Waveform | What it is for |
|---|---|---|
| 0 | saw up — the loop phase, today's plan | a ramp over the loop for a filter or a sequencer's CV in |
| 1 | saw down | |
| 2 | triangle | |
| 3 | sine | a synced LFO |
| 4 | square | half the period high |
| 5 | random | a new level each period — sample & hold |
| 6 | clock | 10 ms pulse per beat (or per 16th at rate = beat) — a clock out for the modular |
| 7 | reset | one pulse at loop start |
| 8 | envelope | 4.5 V on every note of the keys' channel, decaying over ~300 ms — an AD for modules without one |
| 9 | mod wheel | MIDI CC 1 in, straight through |
| 10 | off | 0 V |

### 3.7 LED

| State | LED |
|---|---|
| empty, stopped | off; a dim tick on each beat once tap tempo has been set |
| armed (record, waiting for the first note) | red, blinking |
| recording the first pass | red |
| playing | green, brighter on each beat, brightest on beat 1 |
| overdubbing | orange (red + green) |
| stopped, loop in memory | dim green |
| panic | white, 300 ms |
| a setting toggled | blue: two blinks = on, one = off; *n* + 1 blinks = AUX waveform *n* |
| tap tempo | a blue flash per tap |

PWM on all three legs, so the colours can be balanced against the 330 Ω red
leg (`pinout.md` §7).

### 3.8 Arpeggiator

The mono one-shot toy suits it. On: the held keys (and held MIDI ch 1
notes) are played one at a time at `ARP_DIV` of the clock — 16ths by
default — in the chosen order: up, down, up-down, as played. Each arp note
is a performance event like any other: a tap into the toy, MIDI out, CV/gate
on the keys' channel, and recorded by the looper when overdubbing. Over a
running loop it is a second voice with no extra gear. Off: the held keys
sound as they did.

### 3.9 Settings

Quantise loop, quantise pitch, AUX waveform and rate, gate mode, glide, arp
on/off, order and rate, toy notes, and the tempo — kept in NVS, written two
seconds after the last change, read at boot. Nothing else persists; the loop is
gone at power-off.

---

## 4. Later, not now

Loop multiply (double the length to vary over two passes), transposing the
loop from the keys, a scale mode for MIDI-in and the arp, a second level of
undo. None of them needs hardware either; they wait for the above to be
played.

---

## 5. What shapes it

- **The toy is mono and one-shot, and a tap is 100 ms on one switch.** Keys,
  MIDI in, the arp and the loop all queue for it. Dense material
  arpeggiates; the loop's taps get dropped when late, live keys never do.
  MIDI and CV are not subject to any of this.
- **One loop, ~2.6 ms per iteration.** Every time-based thing has ≤ 3 ms of
  jitter: fine for the looper (a 16th at 120 BPM is 125 ms), acceptable for
  MIDI clock out, exact for the clock jack because that is an interrupt.
  Where it matters, the DAW should be the master.
- **The ESP32 ADC is noisy and does not reach its rails.** Hysteresis on the
  quantised pot, smoothing on the continuous one, dead zones at both ends.
- **Long-press buttons act on release**, so record, play, STOP and the
  setting buttons respond ~100 ms after the finger comes off. The voice
  buttons and catface keep press-time response.
- **The toy's rhythms never sync to the loop.** Its tempo is its own and the
  firmware cannot read it. The rhythm cycle button is a convenience, not a
  drum machine in the loop.
- **Ghosting.** The button board shares matrix lines with the keys; the
  ghost filter is unchanged and rejects only true rectangles, so holding a
  transport button while playing is safe.

---

## 6. Modules and build order

New files, each with the header it needs; the existing drivers are untouched.

| File | Owns |
|---|---|
| `controls.cpp` | button semantics — press / release / long, tap tempo, rhythm cycling, setting toggles; the pots with smoothing and hysteresis; the switch; the LED |
| `router.cpp` | the performance-event router: sources in, toy tap + MIDI out + CV per event; the note stacks; base pitch, tune, quantise pitch |
| `cv.cpp` | note → DAC code per channel, glide, gates and gate mode, pitch bend |
| `auxout.cpp` | the AUX output: period from the clock or the active loop, the eleven shapes. Not `aux.cpp` — a reserved DOS device name |
| `clock.cpp` | the transport (namespace `clk` — `clock` is libc's): tick source selection, tap tempo, BPM, tick counter, beat and bar phase, MIDI clock in and out |
| `midi_in.cpp` | the two parsers and message dispatch; settings over CC go through `controls`' setters, so buttons and CCs are one code path |
| `looper.cpp` | event store, record / overdub / play / stop / undo / clear, quantise, the playback cursor |
| `arp.cpp` | the held-note set, order, the step on each clock division |
| `settings.cpp` | NVS |
| `main.cpp` | glue: scan → events → controls / router → arp → looper → outputs, in the existing loop |

Plus `led.cpp` — the three PWM legs, a base colour and a blink overlay —
on its own because the looper and the controls both drive it.

### Work list

Four stages, each testable on its own and shipping the previous ones.

**Stage 1 — controls, CV/gate, router.** The keys reach the jacks; pots,
switch and LED work; long presses and settings toggle (the ones without a
consumer yet just blink). `systest` `g` and `v` already prove the jacks, so
this is the routing and the pots.

- [x] `config.h`: long press, CV zero note and pot ranges, glide and
      retrigger times, ADC dead zones, LED balance, the settings enums.
      `PIN_PANIC` and `TRANSPOSE` go — the STOP button and the pot replace them
- [x] `settings.h`: the settings struct and its defaults (RAM only until stage 4)
- [x] `led`: PWM on the three legs, base colour, blink codes
- [x] `cv`: note stack per channel, DAC code from note + offset + bend, glide,
      gate with retrigger / legato, sustain, AUX parked at 0 V
- [x] `router`: performance events → toy tap, MIDI out (transposed by the
      pot), CV on the keys' channel; note → position table; panic
- [x] `controls`: press / release / long, rhythm cycle, setting toggles and
      their blinks, pots with smoothing, hysteresis and dead zones, the
      switch, commands out to `main`
- [x] `main.cpp`: wire it up; panic from STOP long; `pollPanic` goes
- [x] build, then README: scope table, config table, the panic section
- [x] acceptance run written — `tests.md`, stage 1
- [ ] acceptance run passes on the instrument

**Stage 2 — MIDI in.** DIN first (`systest` `n` is the reference), then USB.

- [x] `midi_in`: two parsers with running status and interleaved real-time
- [x] dispatch: ch 1 → router, ch 2 → the other CV pair, CC 20–38 taps,
      program change, bend, sustain, CC 102–110 settings, CC 120 / 123
- [x] bridge return path with two ports; `test_bridge.py` for the new direction;
      `midi_send.py` to drive it without a DAW
- [x] README: the DAW section, two loopMIDI ports
- [x] acceptance run written — `tests.md`, stage 2 (over USB; the DIN part
      waits for working sockets)
- [ ] acceptance run passes on the instrument

**Stage 3 — clock, looper, arp.**

- [x] `clock`: internal tick engine, tap tempo, beat / bar phase, the LED beat
- [x] MIDI clock in, start / stop / continue; MIDI clock out when not following it
- [x] jack clock on an interrupt, `CLOCK_PPQN`, takeover and fallback
- [x] `looper`: event store, record / overdub / play / stop / undo / clear,
      length rounding, quantise on playback, toy taps dropped when late
- [x] looper LED states; record / play / STOP wired through
- [x] `arp`: held-note set, order, step on the clock division
- [x] README: the looper and clock sections
- [x] acceptance run written — `tests.md`, stage 3 (`midi_send.py` gained
      `clock` / `start` / `stop` / `continue`; the jack part waits for a clock source)
- [ ] acceptance run passes on the instrument

**Stage 4 — AUX shapes, settings.**

- [x] AUX waveform table and rate — `auxout.cpp`
- [x] NVS: load at boot, save two seconds after the last change
- [x] README and `pinout.md` brought in line; this document updated to
      what is built
- [x] acceptance run written — `tests.md`, stage 4
- [ ] acceptance run passes on the instrument

---

## 7. Decisions taken

- The pots act on the keys' path only — on both pairs, now that each has a
  loop; MIDI ch 2's CV is what the DAW sent.
- One loop per CV pair, the switch selecting the active one (added on the
  bench: a loop should stay on the jack it was built on).
- Toy notes on / off on a long catface, so the keys can play the jacks
  without the cat (added on the bench).
- MIDI ch 1 notes are recorded by the loop like keys.
- The loop rounds to the beat; a bar is an assumption (`BEATS_PER_BAR` = 4)
  used only where being wrong is harmless.
- Every extra is in: arp, glide, gate mode, MIDI clock out, bend / mod /
  sustain, settings over CC.
- One long-press threshold, 1 s, for everything.
