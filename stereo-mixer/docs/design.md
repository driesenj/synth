# Stereo mixer: design

Every designator matches `hardware/tools/netlist.py` and the EasyEDA project.

## Signal flow

```
mono ch k (1-6)
  IN k ─ LEVEL k (A100k) ─ follower ─ MUTE k ─┬─ 10k ─ PLk ─ 100k ─▶ SUM_L    PAN k (B10k) between
                                              ├─ 10k ─ PRk ─ 100k ─▶ SUM_R    PLk and PRk, wiper to GND
                                              └─ SEND k (A100k) ─ 100k ─▶ SUM_S
stereo ch c (7, 8)
  IN c L ─┐ LEVEL c        followers   MUTE c   ┬─ 200k ─▶ SUM_L
  IN c R ─┘ (dual A100k)   (2×)        (DPDT)   ├─ 200k ─▶ SUM_R
                                                └─ 10k + 10k = (L+R)/2 ─ SEND c ─ 100k ─▶ SUM_S
RETURN L/R ─ RETURN (dual A100k) ─ 200k ─▶ SUM_L / SUM_R
DRUMS ─ DRUMS (A100k) ─ 300k ─▶ SUM_L,  300k ─▶ SUM_R
FX IN ─ 100k ─▶ SUM_S

SUM_L ─ summer (100k ∥ 22p) ─ MASTER gang A (A10k) ─ 100k ─ inverter ×2 (200k) ─ 1k ─ OUT L
SUM_R ─ summer (100k ∥ 22p) ─ MASTER gang B         ─ 100k ─ inverter ×2 (200k) ─ 1k ─ OUT R
SUM_S ─ summer (100k ∥ 22p) ─ 100k ─ inverter ×1 (100k) ─ 1k ─ SEND
```

Every path inverts twice, so every output is in phase with every input. That
matters for the send: Clouds' wet signal comes back in phase with the dry
channel and doesn't cancel it.

## The channel strip

**Mono (channels 1–6).**
- **LEVEL and buffer.** The A100k LEVEL pot is a divider from the jack to
  ground, so the input impedance is 100k. Its wiper feeds a TL074 follower,
  so nothing downstream loads the pot.
- **Mute.** The follower drives the mute toggle, and everything else hangs
  off the toggle's common (net CHk). When muted, CHk is grounded, which
  silences the pan network and the send together. The send is therefore
  post-fader and post-mute.
- **Pan network.** CHk feeds the pan pot through two 10k resistors, one to
  each end (PLk and PRk). The B10k pan pot's wiper is grounded, and each end
  feeds its bus through 100k. This is the same idea as the pan stage in your
  output module's manual: turning the knob grounds more of one side. At a
  hard pan, that side's end sits on the grounded wiper, so hard left really
  is left only.
- **Send.** The A100k SEND pot, after the mute, goes through 100k into the
  send bus.

**Stereo (channels 7–8).**
- **Inputs.** IN R's switch lug is wired to IN L, so a mono cable plays on
  both sides.
- **Level, buffers and mute.** The dual-gang A100k level feeds two
  followers, then a DPDT mute: one pole per side, each grounding its side
  when muted.
- **Buses.** Each side goes into its own bus through 200k.
- **Send.** The two sides are averaged through 10k each into net AVc, which
  drives the SEND pot. A mono signal sends at the same level as a mono
  channel.

## Return, drums and FX IN

- **RETURN:** dual-gang A100k, with the wipers going straight into the buses
  through 200k. There's no send here, to avoid feeding Clouds back into
  itself, and no mute: turn RETURN down instead. The input impedance is
  about 67k at full.
- **DRUMS:** the A100k level feeds 300k into each bus. That gives 0.67 per
  side (−3.5 dB), the same as a centred mono channel. This knob is the drum
  mixer's missing master level. It has no send; the drum mixer's own send
  goes to FX IN instead.
- **FX IN:** 100k straight into the send bus (unity). It's meant for the drum
  mixer's send, so the drums share the Clouds reverb.

## Buses, master and outputs

- **Summers:** inverting, with 100k feedback and 22 pF across it (a pole at
  72 kHz, for stability with a long summing node).
- **Master:** dual-gang A10k on the summer outputs. 10k keeps the loading by
  the next stage's 100k input small, so the gangs track.
- **Output stages:** inverting with a gain of 2 (100k in, 200k feedback),
  then 1k to the jack. The ×2 here makes up the half gain in front of the
  summer: the stereo, return and drum resistors are 200k and 300k, and the
  pan network loses half. Splitting the gain this way gives the summers 6 dB
  more headroom than the outputs.
- **Send output:** the send summer, then a unity inverter (100k/100k) and 1k.
  It has no master knob; Clouds' IN GAIN does that job.

## Gains

| Source, at full LEVEL | Gain to OUT, MASTER at full |
|---|---|
| Mono, hard panned | 0.95 on that side (−0.4 dB) |
| Mono, centred | 0.65 per side (−3.8 dB) |
| Stereo channel | 1.0 per side |
| RETURN | 1.0 per side |
| DRUMS | 0.67 per side (−3.5 dB) |
| Any SEND (mono, stereo (L+R)/2, FX IN) to SEND OUT | 1.0 (stereo 0.95) |

Pan law (linear B10k, rotation from fully CCW):

| PAN | 0 | ¼ | ½ | ¾ | 1 |
|---|---|---|---|---|---|
| L | −0.4 dB | −1.7 dB | −3.8 dB | −8.1 dB | off |
| R | off | −8.1 dB | −3.8 dB | −1.7 dB | −0.4 dB |
| L² + R² | −0.4 dB | −0.8 dB | −0.8 dB | −0.8 dB | −0.4 dB |

That's close to constant power: a source keeps its loudness, within 0.4 dB,
as you pan it.

**Headroom.** The TL074s swing about ±10.5 V on ±12 V.
- **Outputs:** they clip at about 2× Eurorack level (±10.5 V).
- **Summers:** they clip at the equivalent of about 4× (±21 V at the output),
  because they run at half gain.
- **Output module:** set its IN at noon or below.

**Noise.** With every input wired, the L bus sees about 13k of input
branches, a noise gain of 8.6. That is about −98 dB below a ±5 V signal at
the output, so it's not an issue.

## Orientation

- **PAN:** fully CCW is left. CW end (pin 3) is on PLk, CCW end (pin 1) on
  PRk.
- **MUTE (ATE1D, mono):** common is pin 2. Pin 3 is ON (from the follower)
  and pin 1 is MUTE (GND). On a toggle the lever points away from the
  connected terminal. Check with a meter and mount it so lever up means on.
- **MUTE (ATE2D, stereo):** poles 1-2-3 and 4-5-6, commons 2 and 5. Pins 1
  and 4 are ON, 3 and 6 are MUTE.
- **Dual-gang pots:** gang A is pins 1-2-3 (L), gang B pins 4-5-6 (R),
  wipers 2 and 5. The CW ends, pins 3 and 6, are the input side.
- **Jacks (WQP518MA):** 1 is sleeve, 2 is the switch lug, 3 is tip.
  Unpatched mono inputs are grounded through the switch lug. The switch lugs
  of IN 7 R, IN 8 R and RETURN R go to their L inputs. On the output jacks
  the switch lugs are open.

## Op-amps

Section 1 of each TL074 carries the supply pins in your library symbol. So
the section-1 slots take the inverting stages, which are drawn on page 3 next
to the decoupling.

| | Section 1 (1/2/3) | Section 2 (7/6/5) | Section 3 (8/9/10) | Section 4 (14/13/12) |
|---|---|---|---|---|
| U1 | L summer | follower ch 1 | follower ch 2 | follower ch 3 |
| U2 | R summer | follower ch 4 | follower ch 5 | follower ch 6 |
| U3 | send summer | follower 7 L | follower 7 R | follower 8 L |
| U4 | OUT L stage | follower 8 R | OUT R stage | SEND stage |

Two notes for whoever lays it out:

- **Summing nodes.** SUM_L, SUM_R and SUM_S reach every channel, so they are
  long nets. Put each bus resistor's summing-node end next to its op-amp.
  Then the long wires carry the low-impedance channel side, and the summing
  node stays short.
- **Followers.** With ±5 V Eurorack audio the TL074 is far inside its input
  range. A ±10 V source at full LEVEL gets near its negative input limit, so
  turn that channel down a little.

## Power

- **Header J18:** 16-pin 2.54 mm box header (your C3406 footprint). Pins 1–2
  are −12 V (red stripe), 3–10 GND, 11–12 +12 V. Pins 13–16 (+5 V, CV, gate)
  are not used.
- **Reverse protection:** a series 1N5819 per rail, then 10 Ω.
  - **+12 V:** the anode is on the header (D1).
  - **−12 V:** the cathode is on the header and the anode faces the board
    (D2). This is the correct way round, so don't copy D2's orientation
    from your module PCBs.
- **Bulk and decoupling:** 10 µF (178MU0033, 35 V) per rail, and 100 nF per
  TL074 per rail.
- **Current:** about 30 mA per rail.

## Panel

28HP, laid out in `hardware/tools/panel.py`; holes are in `hardware/panel/stereo-mixer-panel-holes.csv`.

- **Columns:** channels are 13 mm apart, which leaves 3 mm between 10 mm knobs.
- **Rows:** SEND 23 mm, PAN 38, LEVEL 54, MUTE 69, IN / L 86, R 101 (from
  the top). RETURN sits in the LEVEL row too, so every level knob is in one
  row.
- **Master section:** two columns at 120.5 and 132.5 mm.
  - SEND (out) and FX IN at the top.
  - RETURN L/R, then the RETURN knob.
  - The DRUMS knob and jack.
  - A 14 mm MASTER knob.
  - OUT L/R at the bottom right.
- **Outputs** are in dark boxes. Dotted lines show the normals (R follows L).
- **Holes:**
  - 7.5 mm for the pots (M7 bushing).
  - 6.5 mm for the jacks.
  - 5 mm for the toggles. The ATE toggles have an unthreaded neck and no
    panel nut, so the faceplate board holds them. Check that the lever
    swings freely.
  - 3.2 mm mounting holes at 7.5 and 134.5 mm.

## Bill of materials

| Qty | Part | Where |
|---|---|---|
| 4 | TL074 (+ 14-pin sockets) | U1–U4 |
| 28 | 100k 1 % | bus feeds, sends, summer feedback, inverter inputs |
| 16 | 10k 1 % | pan feeds (12), stereo send average (4) |
| 8 | 200k 1 % | stereo and return bus feeds (6), output feedback (2) |
| 2 | 300k 1 % | drums into L and R |
| 3 | 1k | output series |
| 2 | 10 Ω | supply filter |
| 3 | 22 pF C0G | summer feedback |
| 8 | 100 nF | decoupling |
| 2 | 10 µF 35 V electrolytic | bulk |
| 2 | 1N5819 | reverse protection |
| 15 | A100k 9 mm pot (PTV09A-4030F-A104) | LEVEL 1–6, SEND 1–8, DRUMS |
| 6 | B10k 9 mm pot (PTV09A-4025F-B103) | PAN 1–6 |
| 3 | A100k 9 mm dual-gang pot | LEVEL 7, LEVEL 8, RETURN |
| 1 | A10k 9 mm dual-gang pot | MASTER |
| 6 | ATE1D-2M3-10-Z (SPDT on-on) | MUTE 1–6 |
| 2 | ATE2D-2M3-10-Z (DPDT on-on) | MUTE 7–8 |
| 17 | WQP518MA jack | 12 inputs incl. FX IN, 2 returns, SEND, OUT L, OUT R |
| 1 | 2×8 2.54 mm box header + ribbon | J18 |

## Choices behind it

- **No MONO switch:** the output module's pan knobs already do this at
  centre.
- **Post-fader sends:** a fade-out takes its reverb with it. That's the usual
  choice for live mixing.
- **No sends on RETURN or DRUMS:** RETURN can't feed Clouds back into itself.
  DRUMS uses the drum mixer's own send pots through FX IN.
- **Followers on every LEVEL pot:** without them the pan network and the send
  pot would load the LEVEL pot, and LEVEL, PAN and SEND would interact.
- **Mutes are plain toggles:** switching a loud signal can click.
