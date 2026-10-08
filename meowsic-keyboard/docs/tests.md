# Acceptance runs

One run per stage of `firmware.md`. A stage is done when its run passes on
the instrument, not when it builds. Each run assumes the ones before it
still pass, and `systest` has already proved the hardware — these test the
firmware's behaviour, not the wiring.

Two builds are used throughout:

- **text** — `pio run -e text -t upload`, then `pio device monitor -b 115200`.
  The same firmware with `USB_MIDI 0`: UART0 logs every key, command and
  state change; `s` dumps the state, `x` is panic. DIN MIDI still works.
- **midi** — `pio run -e esp32dev -t upload` (the default, `USB_MIDI 1`),
  then `python tools/serial_midi_bridge.py --midi <port> --monitor`. UART0 is
  MIDI; the bridge's `--monitor` decodes what the keyboard sends.

Stop the bridge before flashing — it holds the serial port.

Expected voltages assume the 1 V/oct calibration was done (`systest` `v`)
and are at the jack tips: CV 1 V/oct from A2 = 0 V, gates 0 / 4.5 V. A meter
on a patch cable is enough; a VCO and an envelope make the glide and
retrigger checks audible instead of inferred.

---

## Stage 1 — panel, CV/gate, router

Everything cabled, rails and toy on, USB for the monitor. Meter on the CV1
jack, a second lead (or the same meter, later) on gate 1. CV select switch
**open** (channel A), base pitch and tune **centred**.

### A. Text build

Boot first. The monitor must show, in this order:

```
Meowsic MIDI - the full firmware (docs/firmware.md)
MCP23017 up. Frame period 2 ms.
state:
  quantise loop  on
  quantise pitch on
  gate mode      retrigger
  glide          off
  aux waveform   0 saw up
  aux rate       per loop
  arp            off
  arp order      up
  arp rate       16ths
  toy notes      on
  tempo          120
  keys -> CV A   base +0.00   tune +0.00
  CV A  gate low           code    0  0.000 V
  CV B  gate low           code    0  0.000 V
  clock internal 120.0 bpm
  loop A* empty     0.00 beats  0 events  layer 0
  loop B  empty     0.00 beats  0 events  layer 0
  aux     0  0.00 V
monitor: s = state, x = panic
```

(`*` marks the loop the switch selects. The settings shown are the defaults
on a fresh board; after stage 4 they are whatever was last set.)

`base` may read ±1 with the knob only roughly centred; `tune` within ±0.05.
The LED is off. The toy is silent (no meow on boot).

| # | Do | Expect |
|---|---|---|
| 1 | Press and release a few keys | Each logs `DOWN` / `UP`; the toy plays them |
| 2 | Press **A3**, the lowest key, hold it | Log `CV A gate high note 57 code 828 1.001 V` (the code is 12 × `CV_CODES_PER_SEMITONE`, the volts nominal). Meter: CV1 **1.000 V**, gate 1 **4.5 V** |
| 3 | Release it | `CV A gate low`; gate 0 V; CV1 **stays** at 1.000 V |
| 4 | Press **A4**, then **A5**, then **C6** | 2.000 V, 3.000 V, 3.250 V |
| 5 | Hold A3, press A4 | CV1 2.000 V, gate high |
| 6 | Still holding A3, release A4 | CV1 back to **1.000 V**, gate **still high** — the note stack |
| 7 | Release A3 | gate low |
| 8 | Hold A3, press A4 (with a scope on gate 1, or an envelope patched: gate mode is *retrigger*) | The gate dips low for ~3 ms as A4 lands: the envelope restarts |
| 9 | Long-press **blues** (≥ 1 s) | LED: **1 blue blink**. Log `gate mode legato`. Repeat step 8: no dip, the envelope does not restart |
| 10 | Long-press blues again | **2 blue blinks**, `gate mode retrigger` |
| 11 | Turn **base pitch** fully clockwise, slowly | Log `pots: base +1.00 … +12.00` in whole steps, no fractions, no step going back and forth. If the numbers *fall* clockwise, set `POT_BASE_REVERSED 1` |
| 12 | Hold A3 at base +12 | CV1 **2.000 V** |
| 13 | Turn base fully anticlockwise, hold A3 | `base -12.00`; CV1 **0.000 V** |
| 14 | Park the knob just at a step boundary, wait 10 s | No `pots:` lines — the hysteresis holds |
| 15 | Centre the knob. Short-press **samba** | **1 blue blink**, `quantise pitch off`. `pots:` now shows fractions |
| 16 | Hold A3 and turn base slowly | The meter and the `CV A … code` lines sweep continuously with the knob |
| 17 | Short-press samba | **2 blinks**, `quantise pitch on`; back to whole steps |
| 18 | Centre base. Hold A3, turn **tune** end to end | `tune -0.50 … +0.50`; CV1 moves **1.000 ± 0.042 V**. Clockwise must raise it; otherwise flip `POT_TUNE_REVERSED` |
| 19 | Centre tune. Long-press **samba** | **2 blinks**, `glide short`. Play A3 then C6: the CV ramps over ~150 ms — a VCO slides, the log shows an intermediate `code` or two. Play C6 again after a gap: it still slides in from the last pitch |
| 20 | Long-press samba | **3 blinks**, `glide long` — the ramp takes ~0.75 s, half a dozen intermediate codes in the log |
| 21 | Long-press samba | **1 blink**, `glide off` — steps are instant again |
| 22 | Close the **CV select switch** | Log `keys -> CV B`. Meter on CV2 / gate 2: repeat steps 2–4 there. CV1 must not move and gate 1 must stay low |
| 23 | Hold a key on B, flip the switch open | `keys -> CV A`; gate 2 drops although the key is still held, and gate 1 stays low; releasing the key changes nothing on either jack |
| 24 | Press each **voice button** — piano, bells, meow, organ, banjo | The toy changes voice, as before; each logs its `DOWN` |
| 25 | Press **catface** | The toy's cat sound, as before |
| 25a | Hold **catface** ≥ 1 s | The cat sound on the press, then **1 blue blink**, `toy notes off`. Play keys: CV and gate move, MIDI goes out (part B), the toy is **silent**; the voice buttons and a rhythm still work on it. Hold catface again: 2 blinks, `toy notes on`, the keys sound |
| 26 | Short-press **rock** six times, a second apart | The toy starts rock, then blues, samba, techno, disco, rock — the cycle |
| 27 | Long-press rock | The rhythm stops (toy STOP). No `cmd:` line |
| 28 | Short rock, then short-press **STOP** | Rhythm stops (STOP is tapped into the toy); with no loop, nothing else |
| 29 | Long-press **♪** | The toy's demo song plays. Short STOP stops it |
| 30 | Short-press ♪ | LED: one blue flash; a single tap sets nothing (stage 3 tests tap tempo) |
| 31 | **Record** short, then short again; **play** short; hold play; hold record | `loop A* armed` and the LED blinks red, then `loop A* empty`; play with no loop: nothing; the long presses on an empty loop: nothing — and a long press must **not** also fire the short one on release (record held ≥ 1 s then released does not arm) |
| 32 | Short **blues**, twice | `quantise loop off` (1 blink), then `on` (2 blinks) |
| 33 | Short **techno**, repeatedly | `aux waveform 1 saw down` … `10 off` … back to `0 saw up`; the blink count is the number + 1 (11 for *off*) |
| 34 | Long techno, three times | `aux rate per bar` (2 blinks), `per beat` (3), `per loop` (1) |
| 35 | Short **disco**, twice; long disco, four times | `arp on` (2) / `off` (1); `arp order down` (2), `up-down` (3), `as played` (4), `up` (1) |
| 36 | Hold **record** and, while holding, play keys | The keys sound and reach CV as usual; nothing arms on the release (the hold was a long press: undo, which on an empty loop does nothing) |
| 37 | **Panic**: hold A3 (gate high), then hold **STOP** for a second | LED **white** 300 ms; log `PANIC - all notes off`; gate 1 drops **while A3 is still held**. CV1 **keeps** 1.000 V — pitch always holds its last value (as in step 3), so a release tail never dives; the gate is what stops the sound. Releasing STOP logs nothing more. Release A3, press it again: it plays |
| 38 | Type `s` in the monitor | The state dump, reflecting every setting changed above |
| 39 | Type `x` | Same as step 37 |
| 40 | *Optional.* Short SDA to GND for a second | Log `PANIC`, `I2C recovery`; afterwards the keys play and CV1 returns to the level it held |
| 41 | Wait 3 s, power-cycle | Every setting changed above is **still in force** — they live in NVS (stage 4). Put them back by hand: there is no reset |

### B. MIDI build

Flash the default build, run the bridge with `--monitor`. Switch open, pots
centred.

| # | Do | Expect |
|---|---|---|
| 1 | Press and release A3 | `ch1 note on A3 (57) vel 100` then `note off A3 (57)`. The **number** is the test: octave names differ by convention — the bridge and most DAWs call 60 C4, FL Studio calls it C5, so FL shows this note as A4 |
| 2 | Base pitch to +12; press and release A3 | `note on A4 (69)` / `note off A4 (69)` — MIDI follows the pot |
| 3 | Base centred. Hold A3, turn base to +12, release A3 | `note on A3 (57)` … `note off A3 (57)`: the note-off matches the note that went out, not the pot's new value |
| 4 | Turn tune end to end while holding a key | Nothing on MIDI — tune is CV only |
| 5 | Hold A3, press A4, release both | Two note-ons, two note-offs; nothing hangs |
| 6 | Press each voice button, catface | `cc 20 = 127` / `= 0` for piano … `cc 24` banjo, `cc 27` catface |
| 7 | Press ♪, STOP, record, play, the five rhythm buttons | Each sends its own CC on press (127) and release (0): 25, 26, 28, 29, 30–34 — the panel reports itself whatever it does |
| 8 | Hold A3, hold STOP for a second | `note off A3`, then `cc 120 = 0`, `cc 123 = 0` |
| 9 | A DAW on the port | Plays the keys as a MIDI keyboard, transposed by the pot |

Pass: every row as expected, no meow on boot, no hung notes anywhere.

---

## Stage 2 — MIDI in

The keyboard as a receiver: notes on channel 1 play the toy and the keys'
CV pair like keys, channel 2 drives the other pair, CCs press the toy's
buttons and change the settings. The DIN sockets are not proven on this
build, so the run goes over **USB** — the bridge's return path — with known
messages from `tools/midi_send.py`, no DAW needed. The DIN part at the end
is for when the sockets work.

**Setup.** In loopMIDI, two ports named `Meowsic out` and `Meowsic in`
(rename the existing one; add the other). Flash the **midi** build. Then, in
one terminal:

```bash
python tools/serial_midi_bridge.py --midi "Meowsic out" --midi-in "Meowsic in" --monitor
```

which must print `midi out: Meowsic out …  (keyboard -> DAW)` and
`midi in : Meowsic in …  (DAW -> keyboard)`. A second terminal runs
`python tools/midi_send.py …`; its defaults are the `Meowsic in` port and
channel 1. Toy and rails on, meter on CV1 / gate 1, switch **open**, pots
**centred**, quantise pitch on (the default). Each `midi_send` line is
echoed in the bridge's monitor prefixed `<-`; lines without the prefix are
what the keyboard sent back, and there should be none unless a row says so.

### A. USB

| # | Do | Expect |
|---|---|---|
| 1 | `midi_send.py note 57` | The toy plays A3, its lowest key; CV1 **1.000 V** and gate 1 high for 0.5 s. The monitor shows `<- ch1 note on A3 (57)` then `<- … note off` and **no outgoing** note — MIDI in is not echoed |
| 2 | `note 69` | Toy A4; CV1 **2.000 V** |
| 3 | `note 45` — A2, below the keybed | The toy plays **A3** (folded up an octave); CV1 **0.000 V** — CV gets the real note |
| 4 | `note 96` — C7, above it | The toy plays **C6** (folded down); CV1 **4.250 V** |
| 5 | `scale 57 84 --hold 0.15` | The toy plays every key A3 → C6 chromatically; CV1 climbs 1.000 → 3.250 V in 83 mV steps, gate pulsing |
| 6 | `chord 57 61 64 --hold 1` | The toy arpeggiates the three (one switch, press order); CV1 ends at E4 = **1.583 V**; gate high for 1 s, then low. Nothing hangs |
| 7 | Base pitch pot to +12, then `note 57` | CV1 **2.000 V** — channel 1 gets the pot, like a key. Centre the pot after |
| 8 | `note 57 --ch 2 --hold 2` | **CV2** 1.000 V and **gate 2** high for 2 s; the toy is **silent**; CV1 and gate 1 untouched |
| 9 | Base pitch to +12, then `note 57 --ch 2` | CV2 still **1.000 V** — the other pair gets the note as sent, no pot. Centre it |
| 10 | Hold **A3 on the keybed** while `note 62 --ch 2 --hold 2` runs | Two voices: CV1 1.000 V / gate 1 high with the key, CV2 1.417 V / gate 2 high with the message, each unaffected by the other |
| 11 | Close the **switch**, repeat rows 1 and 8 | Channel 1 now lands on **CV2 / gate 2** (and the toy), channel 2 on **CV1 / gate 1**. Open it again |
| 12 | `cc 20 127`, `cc 21 127`, `cc 22 127`, `cc 23 127`, `cc 24 127` | The toy's voice changes: piano, bells, meow, organ, banjo. `cc 27 127`: the cat sound. `cc 20 0`: nothing — a release taps nothing |
| 13 | `cc 30 127`, then `cc 26 127` | The rock rhythm starts, then the toy's STOP stops it |
| 14 | `cc 37 127` ×3, then `cc 38 127` ×3 | The toy's volume steps up three times, then down — the buttons that never scan, by injection |
| 15 | `cc 30 127`, then `cc 35 127` ×3 and `cc 36 127` ×3, then `cc 26 127` | The rhythm speeds up, slows down, stops |
| 16 | `pc 2`, then `pc 0`; then `pc 2 --ch 2` | Meow, then piano. On channel 2: nothing — program change is the keys channel only |
| 17 | Hold A3 on the keybed, then `bend 8191 --hold 2` | CV1 rises to **1.167 V** (+2 semitones) for 2 s, then back to 1.000 V. `bend -8192 --hold 2`: **0.833 V** |
| 18 | Hold A3 on the keybed, then `bend 8191 --ch 2` | CV1 does **not** move — bend follows its channel. (With a note held on channel 2 it would move CV2) |
| 19 | `sustain 57 60 --hold 2` | A3 then C4 play on the toy; after both note-offs the gate **stays high** and CV1 holds C4 = **1.250 V** for 2 s; at the pedal-up the gate drops |
| 20 | `sustain 57 60 --ch 2 --hold 2` | The same on CV2 / gate 2, the toy silent |
| 21 | `cc 102 0`, `cc 102 127` | LED: **1** blue blink, then **2** — quantise loop off, on |
| 22 | `cc 103 0`, then turn base pitch while holding a key; `cc 103 127` | 1 blink; the CV sweeps continuously; 2 blinks and it steps again |
| 23 | `cc 104 3`, `cc 104 10`, `cc 104 11`, `cc 104 0` | **4** blinks (sine), **11** (off), **none** — out of range is ignored — then **1** (saw up) |
| 24 | `cc 105 2`, `cc 105 0` | 3 blinks, 1 blink |
| 25 | `cc 106 0`, `cc 106 127` | 1 blink (legato), 2 (retrigger) |
| 26 | `cc 107 2`, then play two keys; `cc 107 0` | 3 blinks and the pitch slides between the keys over ~0.75 s; 1 blink and it steps |
| 27 | `cc 108 127`, `cc 108 0`; `cc 109 3`, `cc 109 0`; `cc 110 1`, `cc 110 0` | 2, 1; 4, 1; 2, 1 blinks. (With no keys held nothing is audible; stage 3 covers the arp itself) |
| 27a | `cc 111 0`, then `note 57`; `cc 111 127`, then `note 57` | 1 blink; the toy stays **silent** for the note while CV1 / gate 1 play it; 2 blinks; the toy plays it again |
| 28 | `cc 104 9`, then `cc 1 127`, `cc 1 64`, `cc 1 0`; then `cc 104 0` | 10 blinks (mod wheel); meter on the **AUX** jack: **4.5 V**, **~2.26 V**, **0 V**; then 1 blink and AUX stays 0 V whatever CC 1 says |
| 29 | Hold A3 on the keybed, then `midi_send.py panic` | Gate 1 drops while the key is held; the monitor shows the keyboard's outgoing `note off A3` for the key and **no** `cc 120` / `cc 123` — the request is not echoed back. Release and press the key: it plays |
| 30 | `note 57 --ch 2 --hold 10`, and **Ctrl-C the bridge** while it holds | Gate 2 drops the moment the bridge exits — it sends all-notes-off to the keyboard on the way out |
| 31 | `python tools/serial_midi_bridge.py --midi "Meowsic in" --midi-in "Meowsic in"` | Refuses: the same port both ways would echo the keyboard to itself. (Also with `loopMIDI Port` for both, which rtmidi lists as `… 1` and `… 0`) |
| 32 | *Optional.* FL Studio: Options → MIDI settings, **Meowsic out** enabled as input, **Meowsic in** enabled as output with a port number; a channel's MIDI Out plugin on that port, channel 1, notes in the piano roll | The toy and CV1 follow the piano roll; the same on channel 2 → CV2 only. Playing the keybed records into FL as before |

### B. DIN — when the sockets work

`systest` `n` first, to prove the socket itself. Then a MIDI keyboard or an
interface into the DIN in socket, and the same expectations as rows 1, 8,
12 and 21 above, sent from there. With both the bridge and a DIN source
connected, notes from either arrive; the two never disturb each other's
running status.

Pass: every row as expected, nothing echoed back to the DAW, no hung notes
or gates on either pair.

---

## Stage 3 — clock, looper, arpeggiator

The **text** build for most of it — the log names every loop state and
tempo change — and the **midi** build with the bridge for MIDI clock and
transport. Toy and rails on, meter on CV1 / gate 1, switch open, pots
centred, defaults (quantise loop on, arp off). The beat is on the LED
throughout: a tick per beat, brighter on beat 1.

### A. Text build — tap tempo and the looper

| # | Do | Expect |
|---|---|---|
| 1 | Boot | The dump ends with `clock internal 120.0 bpm` and `loop empty 0.00 beats 0 events layer 0`; LED off — no beat tick yet |
| 2 | Tap **♪** four times at a steady ~120 (half-second gaps) | A blue flash per tap; from the third tap `tap: 1xx bpm` within ±5 of what you tapped, `clock internal 1xx.x bpm`; the LED now ticks dim white on every beat, brighter every fourth, in time with your taps |
| 3 | Tap four times at ~90 | `tap: 9x bpm`; the tick slows. A single tap after a pause of more than 2 s changes nothing |
| 4 | Press **record** | LED **blinks red**; log `loop armed` |
| 5 | Press record again | LED back to the beat tick; `loop empty` — disarmed |
| 6 | Record, then play **A3 C4 E4 G4**, one per beat on the LED ticks, then press record right after the fourth note's beat | LED **red** from the first note (beat 1 moves to it); on the second record press `loop playing 4.00 beats 8 events layer 0` — the length rounded to whole beats — and LED **green**, pulsing with the beat, strongest at the loop's beat 1 |
| 7 | Listen and meter for a few passes | The toy plays the four notes every pass; CV1 steps 1.000 / 1.250 / 1.583 / 1.833 V with gate 1 pulsing; nothing drifts against the LED |
| 8 | Short **blues** (quantise loop off), then play a deliberately sloppy phrase and record it as a 2-ish-beat loop | `loop playing 2.xx beats` — the length as played, not rounded. Short blues again: `quantise loop on`; from the **next pass** the notes sit on 16ths (the length stays as recorded). Long play while stopped later clears it — for now STOP, long play, and re-record row 6 |
| 9 | While playing, press **record** | LED **orange**; `loop overdub … layer 1`. Play two more notes; press record | LED green; `loop playing 4.00 beats 12 events layer 1`; both parts loop |
| 10 | Hold **record** ≥ 1 s | `loop playing … 8 events layer 0` — the overdub is gone, the first pass plays alone |
| 11 | Overdub once more (record, notes, record); then press **STOP** | `loop stopped`; LED **dim green**; gate 1 low; the toy silent |
| 12 | Press **play** | Playback resumes from the top on the **next beat** (quantise on); green |
| 13 | Press play | `loop stopped` — play toggles |
| 14 | From stopped, press **record** | On the next beat: `loop overdub … layer 2` — record from stopped plays and overdubs at once. Press record: `playing` |
| 15 | Hold **record** ≥ 1 s twice | `layer 1`, then `layer 0`; a third hold changes nothing — the first pass stays until it is cleared |
| 16 | STOP, then hold **play** ≥ 1 s | `loop A* empty`; a **red flash**; LED back to the beat tick |
| 16a | Record a pass, let it play, then hold **play** ≥ 1 s **while it plays** | It stops and clears in one go — red flash, `loop A* stopped` then `empty`. (It used to refuse while playing, which left the next record press overdubbing the loop you meant to be rid of) |
| 17 | **A bass note that lasts the loop.** Clear; record; hold A3 for four of the LED's beats and press record while it is still down; release it | `loop A* playing 4.00 beats **2 events**` — one note-on, one note-off at the end. Every pass: one tap on the toy at the start (the blob is one-shot, so it decays — CV1 holds 1.000 V with gate 1 high for the whole pass). Let it run a dozen passes and press `s`: **still 2 events**, and the keys still play the toy. (It used to add two events a pass until the toy went deaf) |
| 17a | Overdub, and hold a key **across** the loop point — press record, hold C4 from the third beat until past the start of the next pass, then release and press record | The overdub spans the point: on playback C4 retriggers at the loop start and runs on, and a long record once removes the whole overdub with nothing left hanging |
| 18 | Record a pass; overdub and, during it, press **bells**, then **piano** two beats later | Each pass the toy switches to bells then back to piano at those points; the log shows the events count rising by 2 |
| 19 | Record a pass of **fast chord mashing** (lots of keys, quickly) | The toy plays what it can — an arpeggiated subset, never lagging behind the beat — while CV1 and gate 1 keep every note on time |
| 20 | While a loop plays, hold **STOP** ≥ 1 s | PANIC: the loop **stops**, gates drop, LED white flash, `loop stopped` |
| 21 | Play the loop, press STOP, tap ♪ four times at a new tempo, press play | The loop plays at the new tempo — the notes are in ticks, not milliseconds |
| 21a | With loop A playing, **close the switch** (B) | Log `keys -> CV B, loop B`; loop A **keeps playing on CV1 / gate 1** (its sounding note returns at its next event); the LED shows loop B: the beat tick only, `loop B  empty`. Keys now go to CV2 |
| 21b | Record a loop on B: record, play four notes on the LED's beats, record | `loop B* playing 4.00 beats` — its first note **snapped to loop A's grid** rather than moving it, so the two stay in step; CV2 / gate 2 play B while CV1 / gate 1 keep playing A |
| 21c | Press STOP, then play, then hold record ≥ 1 s | Only loop B stops, starts, undoes — `loop B* …` lines only; A never flinches |
| 21d | Turn the base pitch pot to +12 | **Both** loops shift up an octave on their jacks — the pots are global to the keys' path. Centre it |
| 21e | Open the switch (A) | `keys -> CV A, loop A`; B keeps playing on CV2; the LED shows A |
| 21f | Hold STOP ≥ 1 s | Panic stops **both** loops: `loop A* stopped`, `loop B  stopped` |

### B. Text build — the arpeggiator

| # | Do | Expect |
|---|---|---|
| 22 | Hold **A3 + C4 + E4**; short **disco** | 2 blue blinks, `arp on`; the three notes drop out and come back one at a time on 16ths of the tempo, low to high, each a tap on the toy and a step on CV1 with gate 1 pulsing at the tempo |
| 23 | Release E4, add G4 while holding | The pattern follows the held set at once |
| 24 | Long **disco** three times, holding the chord | 2 blinks `arp order down` — high to low; 3 blinks `up-down` — up then down without repeating the ends; 4 blinks `as played` — press order. One more: `up` |
| 25 | Release everything | Silence, gate low |
| 26 | Hold a chord; short **disco** | `arp off`; the keys stay **silent** until re-pressed, then sound directly again |
| 27 | Arp on; **record**, hold a chord for four beats, press record | The **arp's** notes are what got recorded — `… events` counts steps, not keys — and the loop plays the pattern with nothing held. Arp off: the loop still plays it |
| 28 | Arp on, loop playing: hold a different chord | The loop plays underneath, the arp on top — two voices on one channel |

### C. MIDI build — clock and transport

Bridge running with `--midi-in "Meowsic in" --monitor`. No text log here:
the LED, the toy and the meter are the readout.

| # | Do | Expect |
|---|---|---|
| 29 | Watch the bridge's monitor for a few seconds | Nothing — the keyboard's MIDI clock out (24 a beat) is running but the monitor hides clock bytes. Press record, play a note, press record: `realtime start` appears at the recording's start; press STOP: `realtime stop` |
| 30 | `midi_send.py clock 100 --hold 10` | The LED's beat follows 100 BPM for 10 s (`<-` lines for start and stop; clocks hidden). After the stop and 2 s of silence the beat **keeps going at 100** — the internal clock took over at the last external tempo |
| 31 | Record a 4-beat loop by tapping 120 and recording; then `clock 60 --hold 15` | The loop plays at half speed, in step with the clock; `<- realtime start` restarted it from the top. When the clock stops, the loop **stops** (MIDI stop), and the tempo stays at 60 |
| 32 | `midi_send.py continue` | The loop plays again from the top |
| 33 | `midi_send.py start`, then `stop` | Restarts from the top; stops — **both** loops, when both exist |
| 34 | `cc 110 1`, arp on with a chord held | 2 blinks; the arp steps on **8ths**. `cc 110 2`: quarters. `cc 110 0`: 16ths |
| 35 | *Optional.* FL Studio with `Meowsic out` enabled and **Send master sync** on `Meowsic in` | FL's transport starts and stops the loop and the keyboard follows FL's tempo; with sync off, FL can be set to slave to `Meowsic out` and follows the keyboard's tap tempo |

### D. Jack clock — when a clock source is to hand

A modular clock at the clock jack, 4 pulses per beat (one per 16th; set
`CLOCK_PPQN` if yours differs). The LED's beat follows it within a beat;
a loop recorded under it snaps its first note to the pulse grid and its
length to whole beats; when the clock stops, the tempo holds after 2 s.
Stage 4's AUX *clock* waveform patched to the jack (its row 12) is the
self-contained version of this check.

Pass: every row as expected, no note left hanging by an undo, a stop or
the arp switching, the beat never drifting against a loop.

---

## Stage 4 — AUX, settings that survive

**Text** build. Meter on the **AUX** jack — a scope, or a VCA / LED module
patched to it, shows the shapes far better than a meter, but a meter is
enough for every row. Tap ♪ four times at 120 first, so a beat is 0.5 s and
a bar 2 s; no loop running; switch open, defaults otherwise (saw up, per
loop). `s` in the monitor shows the AUX level as `aux 128 2.26 V`.

| # | Do | Expect |
|---|---|---|
| 1 | Watch the meter | AUX ramps **0 → 4.5 V over 2 s** and drops back on beat 1 (the LED's bright tick): saw up, and with no loop running *per loop* means per bar |
| 2 | Short **techno** | 2 blinks, `aux waveform 1 saw down`: 4.5 → 0 V over the bar |
| 3 | Short techno | `2 triangle`: up over the first half of the bar, down over the second |
| 4 | Short techno | `3 sine`: a smooth swing between 0 and 4.5 V, through 2.25 V at the quarter points |
| 5 | Short techno | `4 square`: **4.5 V for 1 s, 0 V for 1 s**, edges on beats 1 and 3 |
| 6 | Short techno | `5 random`: a new level on every beat 1, held for the bar |
| 7 | Short techno | `6 clock`: a **10 ms 4.5 V pulse every beat** (0.5 s) — a scope sees it, a meter twitches. Long techno twice → `aux rate per beat`: a pulse every **16th** (125 ms). Long techno → `per loop` |
| 8 | Short techno | `7 reset`: one pulse on **beat 1 of every bar**; at `per beat` one every beat |
| 9 | Short techno | `8 envelope`: AUX **0 V** until a key is pressed, then **4.5 V decaying to 0 over ~300 ms** — a pluck on a VCA. Every note restarts it: keys, the arp's steps, a loop on the keys' pair. `midi_send.py note 57 --ch 2` (the other pair) does **not** |
| 10 | Short techno twice | `9 mod wheel` (stage 2 row 28 covers it), then `10 off`: **0 V**. Short techno once more: back to `0 saw up` |
| 11 | Record a **2-beat loop** (record, two notes on the beats, record) | The saw now ramps over **1 s** — the loop's pass — and resets at the loop's start. Long techno → `per bar`: 2 s again; → `per beat`: 0.5 s; → `per loop`. Press STOP: the ramp falls back to the bar |
| 12 | Waveform `6 clock`, rate `per beat`; **patch the AUX jack into the clock-in jack** | Within a beat: `clock jack 120.0 bpm` — the jack input registers our own 16th pulses as a 4 PPQN clock — and the LED keeps ticking at 120. Short techno to `7 reset` (one pulse a beat: not a plausible 16th clock): 2 s later `clock internal 120.0 bpm`. Unpatch |
| 13 | Set: short blues (`quantise loop off`), long samba twice (`glide long`), short techno to `3 sine`, long disco once (`arp order down`), tap ♪ four times at ~100. Wait **3 s**. Power-cycle | The boot dump shows `quantise loop off`, `glide long`, `aux waveform 3 sine`, `arp order down`, `tempo 100`; the LED does not tick until ♪ is tapped, but a loop recorded now runs at 100 |
| 14 | Short blues (`quantise loop on`) and power-cycle **within a second** | The dump still says `off` — the write waits two seconds after the last change |
| 15 | Put every setting back: blues short, samba long (to `off`), techno short to `0 saw up`, disco long three times (to `up`), tap 120. Wait 3 s | `s` shows the defaults and `tempo 120`; they survive the next power cycle |

Pass: every shape as described, the jack round trip registers and hands
back, and the settings come back exactly as left.

---

All four runs passing is the firmware done; what is left is in
`firmware.md` §4.
