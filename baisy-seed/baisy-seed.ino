#include <DaisyDuino.h>
#include <Wire.h>
#include <U8g2lib.h>
#include <math.h>

// Module Layout

// A2  -  A1  -  A0
// A5  -  A4  -  A3
// A8  -  A7  -  A6
//
// A11 -  A10 -  A9
// D14 -  O0  -  O1

// Timing: everything the sound depends on (knobs, CV inputs, gate and
// encoders) is read once per audio block in AudioCallback(), 1000 times a
// second. loop() only runs the menu, the display and the flash storage, so a
// slow display update can't delay a note or lose an encoder step.

// ===== Pin Mapping =====
#define PIN_WT     A2
#define PIN_SUB    A1
#define PIN_ENV    A0
#define PIN_CUT    A5
#define PIN_RES    A4
#define PIN_DRV    A3
#define PIN_LFO    A8
#define PIN_FM     A7
#define PIN_DETUNE A6


#define PIN_1VOCT  A11
#define PIN_CV_1   A10
#define PIN_CV_2   A9

#define PIN_GATE   D5

#define PIN_ENC_1_CW D13
#define PIN_ENC_1_CCW D14
#define PIN_ENC_1_SW D8
#define PIN_ENC_2_CW D7
#define PIN_ENC_2_CCW D6
#define PIN_ENC_2_SW D9

#define OLED_SCL D11
#define OLED_SDA D12

// I2C constructor for SSD1306 128x64
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, OLED_SCL, OLED_SDA);

DaisyHardware hw;

Encoder enc1;
Encoder enc2;

// DSP objects
Oscillator osc;
Oscillator detuneOscUp;
Oscillator detuneOscDown;

Oscillator subOsc;
MoogLadder filter;
Adsr env;
Oscillator lfo;

Svf svf;

float samplerate;

// Menu stuff
#define MENU_VISIBLE 3
#define DISPLAY_FRAME_MS 40 // redraw at most 25 times a second

int menuIndex = 0;
int menuScroll = 0;

enum MenuState {
  SHOW_PARAMETERS = 0,
  SHOW_KNOBS = 1,
  SHOW_SETTINGS
};

enum LfoTarget {
  LFO_TARGET_PITCH = 0,
  LFO_TARGET_CUTOFF,
  LFO_TARGET_AMP,
  LFO_TARGET_WAVETABLE,
  LFO_TARGET_COUNT
};

enum FilterMode {
  FILTER_MOOG_LP = 0,
  FILTER_SVF_LP,
  FILTER_SVF_HP,
  FILTER_SVF_BP,
  FILTER_SVF_NOTCH,
  FILTER_MODE_COUNT
};

enum DistortionType {
  DIST_SOFT = 0,
  DIST_HARD,
  DIST_FOLD,
  DIST_BIT,
  DIST_TYPE_COUNT
};

enum WtBank {
  WT_BANK_BASIC = 0,
  WT_BANK_COUNT
  // Add more banks here as wavetables are added
};

const char* lfoShapeNames[] = { "Sine", "Tri", "Saw", "Sqr" };

const char* lfoTargetNames[LFO_TARGET_COUNT] = {
  "Pitch",
  "Cutoff",
  "Amp",
  "Wavetable"
};

const char* filterModeNames[FILTER_MODE_COUNT] = {
  "Moog LP",
  "SVF LP",
  "SVF HP",
  "SVF BP",
  "SVF Notch"
};

const char* distortionNames[DIST_TYPE_COUNT] = {
  "Soft",
  "Hard",
  "Fold",
  "Bit"
};

enum CvTarget {
  CV_TARGET_PITCH = 0,
  CV_TARGET_CUTOFF,
  CV_TARGET_AMP,
  CV_TARGET_FM,
  CV_TARGET_COUNT
};

const char* cvTargetNames[CV_TARGET_COUNT] = {
  "Pitch",
  "Cutoff",
  "Amp",
  "FM"
};

MenuState menuState = SHOW_PARAMETERS;

// The knobs page. The first twelve entries are also the ADC inputs.
enum MenuKnobs {
  KNOB_WAVETABLE = 0,
  KNOB_SUB,
  KNOB_ENV_AMT,
  KNOB_CUTOFF,
  KNOB_RESONANCE,
  KNOB_DRIVE,
  KNOB_LFO_RATE,
  KNOB_FM,
  KNOB_DETUNE,
  IN_1VOCT,
  IN_CV_1,
  IN_CV_2,
  IN_GATE,
  KNOB_COUNT
};

const char* knobLabels[KNOB_COUNT] = {
  "Wavetable",
  "Sub Amount",
  "Envelope Amount",
  "Filter Cutoff",
  "Filter Resonance",
  "Drive",
  "LFO Rate",
  "FM Amount",
  "Detune",
  "1 V/Oct Input",
  "CV 1 Input",
  "CV 2 Input",
  "Gate Input"
};

enum MenuSettings {
  SETTINGS_CAL_VOCT = 0,
  SETTINGS_CAL_CV1,
  SETTINGS_CAL_CV2,
  SETTINGS_BRIGHTNESS,
  SETTINGS_SAVE,
  SETTINGS_LOAD,
  SETTINGS_FACTORY_RESET,
  SETTINGS_COUNT
};

const char* settingsLabels[SETTINGS_COUNT] = {
  "Cal 1V/Oct",
  "Cal CV 1",
  "Cal CV 2",
  "Brightness",
  "Save State",
  "Load State",
  "Factory Reset"
};

enum CalibrationState {
  CAL_IDLE = 0,
  CAL_STEP1_PATCH,   // Prompt user to patch low voltage
  CAL_STEP1_HOLD,    // Averaging the ADC
  CAL_STEP2_PATCH,   // Prompt user to patch high voltage
  CAL_STEP2_HOLD     // Averaging the ADC
};

CalibrationState calState = CAL_IDLE;
int calTarget = -1; // which input is being calibrated (SETTINGS_CAL_VOCT etc.)

// Known reference voltages for two-point calibration
#define CAL_LOW_VOLTAGE  1.0f
#define CAL_HIGH_VOLTAGE 5.0f

// Assumed until calibrated: 0-8 V spans the ADC, so 1 V reads 1/8, 5 V 5/8
#define CAL_DEFAULT_LOW  0.125f
#define CAL_DEFAULT_HIGH 0.625f

#define CAL_BLOCKS   256   // audio blocks averaged per point (~0.25 s)
#define CAL_MIN_SPAN 0.05f // 1 V and 5 V must read further apart than this

float calLowReading = 0.0f; // ADC reading (0-1) at the low reference

// Written by the audio callback while it averages a calibration point
volatile int calInput = -1; // ADC input being averaged, -1 = none
volatile float calSum = 0.0f;
volatile int calCount = 0;

// Volts = calScale * reading + calOffset, for 1V/oct, CV 1 and CV 2
float calScale[3], calOffset[3];

// Feedback in a settings row ("Done!", "Failed") until the cursor moves
int resultItem = -1;
const char* resultText = "";

const char* noteNames[12] = {
  "C","C#","D","D#","E","F",
  "F#","G","G#","A","A#","B"
};

// ===== Controls =====
// Written by the audio callback once per block; loop() only displays them.
#define ADC_INPUTS IN_GATE

const uint32_t adcPins[ADC_INPUTS] = {
  PIN_WT, PIN_SUB, PIN_ENV, PIN_CUT, PIN_RES, PIN_DRV, PIN_LFO, PIN_FM, PIN_DETUNE,
  PIN_1VOCT, PIN_CV_1, PIN_CV_2
};

// Conversions averaged per block: the most for 1V/oct, where noise is pitch
const uint8_t adcOversample[ADC_INPUTS] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 16, 4, 4 };

ADC_HandleTypeDef adc;
uint32_t adcChannel[ADC_INPUTS];
bool adcOk = false; // cleared if the ADC stops answering: the knobs freeze, the rest runs

volatile float knob[IN_1VOCT];    // the nine pots, 0-1
volatile float v_oct, cv_1, cv_2; // calibrated inputs, volts
volatile bool gate = false;       // the gate as the envelope sees it
volatile bool gateLevel = false;  // the gate input itself

volatile bool gateEdge = false;   // set by the gate interrupt
uint16_t gateExtiLine;

volatile int32_t encTurns[2], encPresses[2];

float smoothedSemitones = 36.0f;
float smoothedCutoff = 4000.0f;

// Bump whenever the struct changes
#define SETTINGS_VERSION 5

#define GLIDE_MAX_TIME 0.5f // glide time constant at Glide 1.00, seconds

struct Settings {
  uint32_t version;

  int baseNote;
  float envAtt;
  float envDec;
  float envSus;
  float envRel;
  float glideAmount;

  int lfoShape;
  int lfoTarget;
  int filterMode;
  int distortionType;
  int wtBank;
  int cv1Target;
  int cv2Target;

  // Two-point calibration of 1V/oct, CV 1 and CV 2: the ADC reading (0-1)
  // with the low and with the high reference voltage patched in
  float cal[3][2];

  int displayBrightness;

  // PersistentStorage::Save() only writes when this reports a difference
  // from the stored copy. Always report one: saves are rare, and the stored
  // copy is read through the data cache, so after a save it can be stale.
  bool operator!=(const Settings &) const { return true; }
};

// QSPI pin config for Daisy Seed
#define PIN_QSPI_CLK dsy_pin(DSY_GPIOF, 10)
#define PIN_QSPI_IO0 dsy_pin(DSY_GPIOF, 8)
#define PIN_QSPI_IO1 dsy_pin(DSY_GPIOF, 9)
#define PIN_QSPI_IO2 dsy_pin(DSY_GPIOF, 7)
#define PIN_QSPI_IO3 dsy_pin(DSY_GPIOF, 6)
#define PIN_QSPI_NCS dsy_pin(DSY_GPIOG, 6)

QSPIHandle qspi;
PersistentStorage<Settings> storage(qspi);

// The live settings: the menu edits them and the audio callback applies them
// every block, so an edit, a load or a reset takes effect straight away
Settings live;

// ===== Parameter menu =====
enum ValueKind { VALUE_NOTE, VALUE_TIME, VALUE_FRACTION, VALUE_NAME, VALUE_NUMBER };

struct ParamItem {
  const char* label;
  ValueKind kind;
  void* value;              // float for VALUE_TIME and VALUE_FRACTION, else int
  float min, max;
  const char* const* names = nullptr; // for VALUE_NAME
};

const ParamItem params[] = {
  { "Base Note",        VALUE_NOTE,     &live.baseNote,       0,      50 },
  { "Envelope Attack",  VALUE_TIME,     &live.envAtt,         0.001f, 10 },
  { "Envelope Decay",   VALUE_TIME,     &live.envDec,         0.001f, 10 },
  { "Envelope Sustain", VALUE_FRACTION, &live.envSus,         0,      1 },
  { "Envelope Release", VALUE_TIME,     &live.envRel,         0.001f, 10 },
  { "Glide",            VALUE_FRACTION, &live.glideAmount,    0,      1 },
  { "LFO Shape",        VALUE_NAME,     &live.lfoShape,       0,      3,                     lfoShapeNames },
  { "LFO Target",       VALUE_NAME,     &live.lfoTarget,      0,      LFO_TARGET_COUNT - 1,  lfoTargetNames },
  { "Filter Mode",      VALUE_NAME,     &live.filterMode,     0,      FILTER_MODE_COUNT - 1, filterModeNames },
  { "Distortion Type",  VALUE_NAME,     &live.distortionType, 0,      DIST_TYPE_COUNT - 1,   distortionNames },
  { "Wavetable Bank",   VALUE_NUMBER,   &live.wtBank,         0,      WT_BANK_COUNT - 1 },
  { "CV 1 Target",      VALUE_NAME,     &live.cv1Target,      0,      CV_TARGET_COUNT - 1,   cvTargetNames },
  { "CV 2 Target",      VALUE_NAME,     &live.cv2Target,      0,      CV_TARGET_COUNT - 1,   cvTargetNames },
};

#define PARAMETER_COUNT (int)(sizeof(params) / sizeof(params[0]))

// WAVE knob: sine, triangle, saw, square. Saw and square are the band-limited
// (polyBLEP) versions; the plain triangle barely aliases to begin with.
const uint8_t oscWaves[4] = {
  Oscillator::WAVE_SIN, Oscillator::WAVE_TRI,
  Oscillator::WAVE_POLYBLEP_SAW, Oscillator::WAVE_POLYBLEP_SQUARE
};
// DaisySP scales its band-limited square by 0.707; undo that to keep the level
const float oscAmps[4] = { 0.8f, 0.8f, 0.8f, 0.8f / 0.707f };

const uint8_t lfoWaves[4] = {
  Oscillator::WAVE_SIN, Oscillator::WAVE_TRI, Oscillator::WAVE_SAW, Oscillator::WAVE_SQUARE
};

// ===== Gate =====
void onGateRise() { gateEdge = true; }

// True once per rising edge on the gate input, however short the pulse. The
// gate interrupt can't run during the audio callback, so an edge that came in
// during this callback is still pending: take it here.
bool takeGateEdge()
{
  bool edge = gateEdge;
  gateEdge = false;
  if (__HAL_GPIO_EXTI_GET_IT(gateExtiLine)) {
    __HAL_GPIO_EXTI_CLEAR_IT(gateExtiLine);
    edge = true;
  }
  return edge;
}

// ===== ADC =====
// analogRead() powers the ADC up, calibrates it and powers it down again on
// every call, which takes ~50 us. Set ADC1 up once instead: a conversion then
// takes ~2 us, cheap enough to read every input in the audio callback.
void adcInit()
{
  adc.Instance = ADC1;
  adc.Init.ClockPrescaler = ADC_CLOCK_SYNC_PCLK_DIV4; // the clock analogRead() uses
  adc.Init.Resolution = ADC_RESOLUTION_16B;
  adc.Init.ScanConvMode = ADC_SCAN_DISABLE;
  adc.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  adc.Init.LowPowerAutoWait = DISABLE;
  adc.Init.ContinuousConvMode = DISABLE;
  adc.Init.NbrOfConversion = 1;
  adc.Init.DiscontinuousConvMode = DISABLE;
  adc.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  adc.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_NONE;
  adc.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DR;
  adc.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
  adc.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
  adc.Init.OversamplingMode = DISABLE;
  bool ok = HAL_ADC_Init(&adc) == HAL_OK;
  HAL_ADCEx_Calibration_Start(&adc, ADC_CALIB_OFFSET_LINEARITY, ADC_SINGLE_ENDED);

  ADC_ChannelConfTypeDef channel = {};
  channel.Rank = ADC_REGULAR_RANK_1;
  channel.SamplingTime = ADC_SAMPLETIME_32CYCLES_5;
  channel.SingleDiff = ADC_SINGLE_ENDED;
  channel.OffsetNumber = ADC_OFFSET_NONE;
  for (int i = 0; i < ADC_INPUTS; i++) {
    pinMode(adcPins[i], INPUT_ANALOG);
    adcChannel[i] = channel.Channel = get_adc_channel(digitalPinToPinName(adcPins[i]), NULL);
    HAL_ADC_ConfigChannel(&adc, &channel);
  }

  ok = ok && HAL_ADC_Start(&adc) == HAL_OK // enables the ADC
          && HAL_ADC_PollForConversion(&adc, 10) == HAL_OK;
  adcOk = ok;
  if (!ok) Serial.println("ADC setup failed: knobs and CV inputs won't respond");
}

// One 16-bit conversion (~2 us). A conversion that takes far longer means the
// ADC has stopped: give up on it for good rather than stall the audio.
uint32_t adcConvert(uint32_t channel)
{
  LL_ADC_REG_SetSequencerRanks(ADC1, LL_ADC_REG_RANK_1, channel);
  LL_ADC_REG_StartConversion(ADC1);
  for (int i = 0; !LL_ADC_IsActiveFlag_EOC(ADC1); i++) {
    if (i > 1000) {
      adcOk = false;
      return 0;
    }
  }
  return LL_ADC_REG_ReadConversionData32(ADC1);
}

// ===== Controls =====
// Knobs and CV inputs
void readAdcInputs()
{
  float reading[ADC_INPUTS]; // 0-1 of the ADC range
  for (int i = 0; i < ADC_INPUTS; i++) {
    uint32_t sum = 0;
    for (int n = 0; n < adcOversample[i] && adcOk; n++) sum += adcConvert(adcChannel[i]);
    if (!adcOk) return;
    reading[i] = sum / (adcOversample[i] * 65536.0f);

    if (i == calInput) {
      calSum += reading[i];
      calCount++;
    }
  }

  // Knobs: smooth out ADC noise (~10 ms)
  for (int i = 0; i < IN_1VOCT; i++) knob[i] += 0.1f * (reading[i] - knob[i]);

  // 1V/oct: jump to a new note at once, smooth out noise on a held one
  float v = calScale[0] * reading[IN_1VOCT] + calOffset[0];
  v_oct = (fabsf(v - v_oct) > 0.02f) ? v : v_oct + 0.2f * (v - v_oct);

  cv_1 += 0.4f * (calScale[1] * reading[IN_CV_1] + calOffset[1] - cv_1);
  cv_2 += 0.4f * (calScale[2] * reading[IN_CV_2] + calOffset[2] - cv_2);
}

// Once per audio block
void readControls()
{
  if (adcOk) readAdcInputs();

  // Gate: an edge starts a note, even a trigger shorter than a block, and
  // the level holds it
  gateLevel = digitalRead(PIN_GATE);
  bool rose = takeGateEdge();
  if (rose) {
    env.Retrigger(false);
    lfo.Reset();
  }
  gate = rose || (gate && gateLevel);

  // Encoders: count turns and presses for loop()
  enc1.Debounce();
  enc2.Debounce();
  encTurns[0] += enc1.Increment();
  encTurns[1] += enc2.Increment();
  if (enc1.RisingEdge()) encPresses[0]++;
  if (enc2.RisingEdge()) encPresses[1]++;
}

int waveIndex(float wt)
{
  return constrain((int)(wt * 4.0f), 0, 3);
}

// Wavefolder: folds anything beyond +/-1 back in, however far out
float fold(float x)
{
  float t = 0.25f * (x + 1.0f);
  t -= floorf(t);
  return 1.0f - 4.0f * fabsf(t - 0.5f);
}

// ===== Audio Callback =====
void AudioCallback(float **in, float **out, size_t size)
{
  readControls();

  // ===== Settings, applied every block =====
  env.SetTime(ADSR_SEG_ATTACK, live.envAtt);
  env.SetTime(ADSR_SEG_DECAY, live.envDec);
  env.SetTime(ADSR_SEG_RELEASE, live.envRel);
  env.SetSustainLevel(live.envSus);

  float lfoRate = knob[KNOB_LFO_RATE];
  lfo.SetFreq(fmap(lfoRate, 0.01f, 20.0f, Mapping::EXP));
  lfo.SetWaveform(lfoWaves[live.lfoShape]);

  // ===== CV targets =====
  // Pitch: 1 V per semitone. Cutoff: 10 V adds 9 kHz. Amp and FM: 10 V is full.
  float cvPitch = 0.0f, cvCutoff = 0.0f, cvAmp = 1.0f, cvFm = 0.0f;
  const int cvTargets[2] = { live.cv1Target, live.cv2Target };
  const float cvVolts[2] = { cv_1, cv_2 };
  for (int c = 0; c < 2; c++) {
    switch (cvTargets[c]) {
      case CV_TARGET_PITCH:  cvPitch  += cvVolts[c];                            break;
      case CV_TARGET_CUTOFF: cvCutoff += cvVolts[c] / 10.0f * 9000.0f;          break;
      case CV_TARGET_AMP:    cvAmp    *= fclamp(cvVolts[c] / 10.0f, 0.0f, 1.0f); break;
      case CV_TARGET_FM:     cvFm     += cvVolts[c] / 10.0f;                    break;
    }
  }

  // ===== Pitch =====
  // 1V/oct: each volt = 12 semitones; baseNote is the MIDI note at 0V.
  // Glide follows the note; LFO and FM go on top, so glide doesn't damp them.
  float note = fclamp(live.baseNote + v_oct * 12.0f + cvPitch, 0.0f, 127.0f);
  float glideTime = GLIDE_MAX_TIME * live.glideAmount * live.glideAmount;
  float glideCoeff = (glideTime > 0.0f) ? 1.0f - expf(-1.0f / (glideTime * samplerate)) : 1.0f;

  // Detune: knob 0-1 spreads the two extra oscillators up to +/-50 cents
  float detune = knob[KNOB_DETUNE];
  float detuneRatio = exp2f(detune * 50.0f / 1200.0f);

  float wt = knob[KNOB_WAVETABLE];
  float subLvl = knob[KNOB_SUB];
  float fmDepth = fclamp(knob[KNOB_FM] + cvFm, 0.0f, 1.0f);

  // ===== Drive settings =====
  float driveK = knob[KNOB_DRIVE];
  float drive = 1.0f + driveK * 30.0f;
  float clipLevel = 1.0f - driveK * 0.85f;                          // Hard: 1.0 down to 0.15
  float crushLevels = exp2f((float)(int)(16.0f - driveK * 14.0f)); // Bit: 16 down to 2 bits

  // ===== Filter settings =====
  float cutoffK = fmap(knob[KNOB_CUTOFF], 20.0f, 18000.0f, Mapping::EXP);
  float envAmt = knob[KNOB_ENV_AMT] * 4000.0f;
  float res = knob[KNOB_RESONANCE] * 0.9f;
  svf.SetRes(fclamp(res, 0.0f, 0.95f));

  for (size_t i = 0; i < size; i++)
  {
    float envOut = env.Process(gate);
    float lfoOut = lfo.Process(); // -1 to +1

    // ===== Pitch =====
    fonepole(smoothedSemitones, note, glideCoeff);
    float semitones = smoothedSemitones;
    if (live.lfoTarget == LFO_TARGET_PITCH)
      semitones += lfoOut * lfoRate * 12.0f; // depth via lfoRate, ±1 octave max
    float freq = mtof(fclamp(semitones, 0.0f, 127.0f));

    subOsc.SetFreq(freq * 0.5f);
    detuneOscUp.SetFreq(freq * detuneRatio);
    detuneOscDown.SetFreq(freq / detuneRatio);

    // ===== Wavetable Shape =====
    float wtMod = wt;
    if (live.lfoTarget == LFO_TARGET_WAVETABLE)
      wtMod = fclamp(wt + lfoOut * 0.5f, 0.0f, 1.0f);

    int shape = waveIndex(wtMod);
    osc.SetWaveform(oscWaves[shape]);
    detuneOscUp.SetWaveform(oscWaves[shape]);
    detuneOscDown.SetWaveform(oscWaves[shape]);
    osc.SetAmp(oscAmps[shape]);
    detuneOscUp.SetAmp(oscAmps[shape]);
    detuneOscDown.SetAmp(oscAmps[shape]);

    // ===== Osc Mix =====
    float subSample = subOsc.Process();
    float fmOffset = subSample * fmDepth * freq * 2.0f;
    osc.SetFreq(fclamp(freq + fmOffset, 20.0f, 18000.0f));

    float sig      = osc.Process();
    float sigUp    = detuneOscUp.Process();
    float sigDown  = detuneOscDown.Process();
    float sub      = subSample * subLvl;

    // detune fades in the unison voices as the knob moves from 0:
    // at 0 only the main oscillator sounds, at 1 all three are equal
    float mix = (sig + (sigUp + sigDown) * detune + sub) / (1.0f + detune * 2.0f);

    // ===== Drive =====
    // Every type ends within +/-1, so the filters never see the raw x31
    switch (live.distortionType) {
      case DIST_SOFT:
        mix = SoftClip(mix * drive);
        break;
      case DIST_HARD:
        // High drive = lower threshold = more clipping, normalized back to +/-1
        mix = fclamp(mix * drive, -clipLevel, clipLevel) / clipLevel;
        break;
      case DIST_FOLD:
        mix = fold(mix * drive);
        break;
      case DIST_BIT:
        // Drive sets the bit depth only: extra gain would clip the signal
        // flat before there was anything left to crush
        mix = roundf(fclamp(mix, -1.0f, 1.0f) * crushLevels) / crushLevels;
        break;
    }

    // ===== Filter =====
    fonepole(smoothedCutoff, cutoffK, 0.01f);

    float cutoff = smoothedCutoff + envOut * envAmt + cvCutoff;
    if (live.lfoTarget == LFO_TARGET_CUTOFF)
      cutoff += lfoOut * 2000.0f; // ±2000Hz
    cutoff = fclamp(cutoff, 20.0f, 18000.0f);

    float filtered;
    if (live.filterMode == FILTER_MOOG_LP) {
      filter.SetFreq(cutoff);
      filter.SetRes(res);
      filtered = filter.Process(mix);
    } else {
      svf.SetFreq(fminf(cutoff, 16000.0f)); // tighter clamp for SVF stability
      svf.Process(mix);                     // SVF processes once then exposes all outputs
      switch (live.filterMode) {
        case FILTER_SVF_HP:    filtered = svf.High();  break;
        case FILTER_SVF_BP:    filtered = svf.Band();  break;
        case FILTER_SVF_NOTCH: filtered = svf.Notch(); break;
        default:               filtered = svf.Low();   break;
      }
    }

    // ===== VCA =====
    float ampMod = cvAmp; // CV: 0V or negative = silence, +10V = unity
    if (live.lfoTarget == LFO_TARGET_AMP)
      ampMod *= 0.5f + lfoOut * 0.5f;

    float outSig = filtered * envOut * ampMod;

    // A filter that blew up would stay silent until a reboot: start it over
    if (!isfinite(outSig)) {
      filter.Init(samplerate);
      svf.Init(samplerate);
      svf.SetRes(fclamp(res, 0.0f, 0.95f));
      outSig = 0.0f;
    }

    out[0][i] = outSig;
    out[1][i] = outSig;
  }
}

void setup()
{
  Serial.begin(9600);
  // while (!Serial) {}

  Wire.begin();
  u8g2.begin();
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x12_tr);
  u8g2.drawStr(0, 20, "BOOT OK");
  u8g2.sendBuffer();

  delay(2000);

  hw = DAISY.init(DAISY_SEED, AUDIO_SR_48K);
  samplerate = DAISY.get_samplerate();

  // Gate input: the interrupt catches pulses shorter than an audio block
  pinMode(PIN_GATE, INPUT_PULLDOWN);
  gateExtiLine = STM_GPIO_PIN(digitalPinToPinName(PIN_GATE));
  attachInterrupt(digitalPinToInterrupt(PIN_GATE), onGateRise, RISING);

  // Encoders, debounced in the audio callback
  float controlRate = DAISY.get_callbackrate();
  enc1.Init(controlRate, PIN_ENC_1_CW, PIN_ENC_1_CCW, PIN_ENC_1_SW, INPUT_PULLUP, INPUT_PULLUP, INPUT_PULLUP);
  enc2.Init(controlRate, PIN_ENC_2_CW, PIN_ENC_2_CCW, PIN_ENC_2_SW, INPUT_PULLUP, INPUT_PULLUP, INPUT_PULLUP);

  adcInit();

  // Oscillators: waveform, level and pitch are set every sample
  osc.Init(samplerate);
  detuneOscUp.Init(samplerate);
  detuneOscDown.Init(samplerate);

  subOsc.Init(samplerate);
  subOsc.SetWaveform(Oscillator::WAVE_SIN);
  subOsc.SetAmp(1.0f);

  // Filter
  filter.Init(samplerate);
  svf.Init(samplerate);

  // Envelope: times and sustain come from the settings, every block
  env.Init(samplerate);

  lfo.Init(samplerate);
  lfo.SetAmp(1.0f);

  initStorage();

  u8g2.clearBuffer();
  u8g2.sendBuffer();

  DAISY.begin(AudioCallback);
}

void loop()
{
  handleEncoders();
  updateCalibration();
  updateDisplay();
}

// ===== Encoders =====
// How many turns or presses the audio callback counted since the last call
int takeCount(volatile int32_t &counter, int32_t &seen)
{
  int32_t now = counter;
  int count = now - seen;
  seen = now;
  return count;
}

void handleEncoders()
{
  static int32_t seen[4];
  int menuTurn   = takeCount(encTurns[0], seen[0]);
  int valueTurn  = takeCount(encTurns[1], seen[1]);
  int menuPress  = takeCount(encPresses[0], seen[2]);
  int valuePress = takeCount(encPresses[1], seen[3]);

  // ===== Encoder 1 (Menu Select) =====
  for (int i = 0; i < menuPress; i++) toggleMenuState();

  // The calibration screen only takes Set
  if (calState != CAL_IDLE) {
    if (valuePress > 0) confirmCalibrationStep();
    return;
  }

  if (menuTurn != 0) moveCursor(menuTurn);

  // ===== Encoder 2 (Value Select) =====
  if (valueTurn != 0) changeValue(valueTurn);
  if (valuePress > 0 && menuState == SHOW_SETTINGS) pressSet();
}

void moveCursor(int steps)
{
  int count = getMenuCount();
  menuIndex = ((menuIndex + steps) % count + count) % count;

  // Adjust scroll window
  if (menuIndex < menuScroll)
    menuScroll = menuIndex;
  if (menuIndex >= menuScroll + MENU_VISIBLE)
    menuScroll = menuIndex - MENU_VISIBLE + 1;

  resultItem = -1;
}

// Menu values step by 1, or by 0.01 for times and fractions
void stepParam(const ParamItem &item, int steps)
{
  if (item.kind == VALUE_TIME || item.kind == VALUE_FRACTION) {
    float *value = (float *)item.value;
    float v = roundf(*value * 100.0f + steps) / 100.0f;
    *value = (v > item.max) ? item.max : (v >= item.min) ? v : item.min; // NaN -> min
  } else {
    int *value = (int *)item.value;
    *value = constrain(*value + steps, (int)item.min, (int)item.max);
  }
}

void changeValue(int steps)
{
  if (menuState == SHOW_PARAMETERS) {
    stepParam(params[menuIndex], steps);
  }
  else if (menuState == SHOW_SETTINGS && menuIndex == SETTINGS_BRIGHTNESS) {
    // A global setting, like the calibration: keep the stored copy in step
    // so Load State doesn't undo it, and any later save keeps it
    live.displayBrightness = constrain(live.displayBrightness + steps * 5, 0, 255);
    storage.GetSettings().displayBrightness = live.displayBrightness;
    u8g2.setContrast(live.displayBrightness);
  }
}

// Encoder 2 pushed on the settings page
void pressSet()
{
  switch (menuIndex) {
    case SETTINGS_CAL_VOCT:
    case SETTINGS_CAL_CV1:
    case SETTINGS_CAL_CV2:
      calTarget = menuIndex;
      calState = CAL_STEP1_PATCH;
      return;
    case SETTINGS_SAVE:
      saveSettings();
      break;
    case SETTINGS_LOAD:
      loadSettings(); // back to the last saved state
      break;
    case SETTINGS_FACTORY_RESET:
      factoryReset();
      break;
    default:
      return;
  }
  showResult("Done!");
}

void showResult(const char* text)
{
  resultItem = menuIndex;
  resultText = text;
}

// Cycle through all three pages on enc1 press; leaving cancels a calibration
void toggleMenuState() {
  switch(menuState) {
    case SHOW_PARAMETERS: menuState = SHOW_KNOBS;      break;
    case SHOW_KNOBS:      menuState = SHOW_SETTINGS;   break;
    case SHOW_SETTINGS:   menuState = SHOW_PARAMETERS; break;
  }
  menuIndex  = 0;
  menuScroll = 0;
  resultItem = -1;
  calState = CAL_IDLE;
  calInput = -1;
}

int getMenuCount() {
  switch(menuState) {
    case SHOW_PARAMETERS: return PARAMETER_COUNT;
    case SHOW_KNOBS:      return KNOB_COUNT;
    case SHOW_SETTINGS:   return SETTINGS_COUNT;
  }
  return PARAMETER_COUNT;
}

// ===== Display =====
void updateDisplay()
{
  static uint32_t lastFrame = 0;
  if (millis() - lastFrame < DISPLAY_FRAME_MS) return;
  lastFrame = millis();

  u8g2.clearBuffer();
  if (calState != CAL_IDLE) drawCalibration();
  else                      drawMenu();
  sendChangedRows();
}

// A full frame keeps I2C busy for ~25 ms, and most redraws change nothing or
// a row or two, so send only the 8-pixel rows that differ from the screen
void sendChangedRows()
{
  static uint8_t shown[8][128]; // what the display shows now (blank at boot)
  uint8_t *frame = u8g2.getBufferPtr();
  for (int row = 0; row < 8; row++) {
    uint8_t *line = frame + row * 128;
    if (memcmp(line, shown[row], 128) != 0) {
      u8g2.updateDisplayArea(0, row, 16, 1);
      memcpy(shown[row], line, 128);
    }
  }
}

void drawMenu()
{
  for (int i = 0; i < MENU_VISIBLE; i++)
  {
    int item = menuScroll + i;
    if (item >= getMenuCount()) break;

    char value[16];
    const char* label = formatItem(item, value);
    drawRow(i * 20, item == menuIndex, label, value);
  }
}

void drawRow(int y, bool selected, const char* label, const char* value) {
  int lineHeight = 10;
  if (selected) {
    u8g2.drawBox(0, y, 128, 2 * lineHeight);
    u8g2.setDrawColor(0);
  }
  u8g2.drawStr(2, y + lineHeight - 2, label);
  int valWidth = u8g2.getStrWidth(value);
  u8g2.drawStr(126 - valWidth, y + 2 * lineHeight - 2, value);
  if (selected) u8g2.setDrawColor(1);
}

void drawCalibration()
{
  const char* steps[] = {
    "", "Patch 1V, press Set", "Sampling 1V...", "Patch 5V, press Set", "Sampling 5V..."
  };
  u8g2.drawStr(0, 12, "Calibrating...");
  u8g2.drawStr(0, 26, steps[calState]);
}

// Writes an item's value into buf and returns its label
const char* formatItem(int item, char* buf)
{
  switch (menuState) {
    case SHOW_PARAMETERS: formatParam(params[item], buf); return params[item].label;
    case SHOW_KNOBS:      formatKnob(item, buf);          return knobLabels[item];
    default:              formatSetting(item, buf);       return settingsLabels[item];
  }
}

void formatParam(const ParamItem &item, char* buf)
{
  switch (item.kind) {
    case VALUE_NOTE:     formatNote(buf, *(int *)item.value);             break;
    case VALUE_TIME:     formatTime(buf, *(float *)item.value);           break;
    case VALUE_FRACTION: formatFloat(buf, *(float *)item.value);          break;
    case VALUE_NAME:     strcpy(buf, item.names[*(int *)item.value]);     break;
    case VALUE_NUMBER:   sprintf(buf, "%d", *(int *)item.value);          break;
  }
}

void formatKnob(int item, char* buf)
{
  switch (item) {
    case KNOB_WAVETABLE: {
      const char* shapes[] = { "Sin", "Tri", "Saw", "Sqr" };
      strcpy(buf, shapes[waveIndex(knob[KNOB_WAVETABLE])]);
      break;
    }
    case KNOB_CUTOFF:
      sprintf(buf, "%dHz", (int)fmap(knob[KNOB_CUTOFF], 20.0f, 18000.0f, Mapping::EXP));
      break;
    case KNOB_DRIVE:
      sprintf(buf, "x%d", (int)(1.0f + knob[KNOB_DRIVE] * 30.0f));
      break;
    case IN_1VOCT: formatVolts(buf, v_oct); break;
    case IN_CV_1:  formatVolts(buf, cv_1);  break;
    case IN_CV_2:  formatVolts(buf, cv_2);  break;
    case IN_GATE:  strcpy(buf, gateLevel ? "HIGH" : "LOW"); break;
    default:       formatFloat(buf, knob[item]); break; // the other pots, 0-1
  }
}

void formatSetting(int item, char* buf)
{
  if (item == resultItem)
    strcpy(buf, resultText);
  else if (item == SETTINGS_BRIGHTNESS)
    sprintf(buf, "%d%%", (live.displayBrightness * 100) / 255);
  else
    strcpy(buf, "Press Set");
}

// Format a 0.0-1.0 float as "0.00" without float sprintf
void formatFloat(char* buf, float val) {
  int i = (int)lroundf(val * 100);
  sprintf(buf, "%d.%02d", i / 100, abs(i % 100));
}

// Format seconds as "0.00s"
void formatTime(char* buf, float val) {
  int i = (int)lroundf(val * 100);
  sprintf(buf, "%d.%02ds", i / 100, abs(i % 100));
}

// Format volts as "-1.25V"
void formatVolts(char* buf, float val) {
  int i = (int)lroundf(val * 100);
  sprintf(buf, "%s%d.%02dV", i < 0 ? "-" : "", abs(i) / 100, abs(i) % 100);
}

void formatNote(char* buf, int midi)
{
  int octave = (midi / 12) - 1;
  int noteIndex = midi % 12;

  sprintf(buf, "%s%d", noteNames[noteIndex], octave);
}

// ===== Calibration =====
// Set pressed on the calibration screen: average the patched reference
void confirmCalibrationStep()
{
  if (calState != CAL_STEP1_PATCH && calState != CAL_STEP2_PATCH) return;

  calSum = 0.0f;
  calCount = 0;
  calInput = IN_1VOCT + calTarget; // 1V/oct, CV 1, CV 2 are in the same order in both lists
  calState = (calState == CAL_STEP1_PATCH) ? CAL_STEP1_HOLD : CAL_STEP2_HOLD;
}

// Finishes a calibration point once the audio callback has averaged enough
void updateCalibration()
{
  if (calState != CAL_STEP1_HOLD && calState != CAL_STEP2_HOLD) return;
  if (calCount < CAL_BLOCKS) return;

  calInput = -1; // the audio callback stops adding
  float reading = calSum / calCount;

  if (calState == CAL_STEP1_HOLD) {
    calLowReading = reading;
    calState = CAL_STEP2_PATCH;
    return;
  }

  calState = CAL_IDLE;
  if (fabsf(reading - calLowReading) < CAL_MIN_SPAN) {
    showResult("Failed"); // nothing patched? keep the old calibration
    return;
  }

  // Calibration is global: store it at once
  Settings &stored = storage.GetSettings();
  live.cal[calTarget][0] = stored.cal[calTarget][0] = calLowReading;
  live.cal[calTarget][1] = stored.cal[calTarget][1] = reading;
  computeCalCoefficients();
  storage.Save();
  showResult("Done!");
}

// Volts = scale * reading + offset, through the readings at 1 V and 5 V
void computeCalCoefficients()
{
  for (int i = 0; i < 3; i++) {
    float low = live.cal[i][0], high = live.cal[i][1];
    if (!(fabsf(high - low) >= CAL_MIN_SPAN)) { // unusable: fall back to the default
      low = CAL_DEFAULT_LOW;
      high = CAL_DEFAULT_HIGH;
    }
    calScale[i]  = (CAL_HIGH_VOLTAGE - CAL_LOW_VOLTAGE) / (high - low);
    calOffset[i] = CAL_LOW_VOLTAGE - calScale[i] * low;
  }
}

// ===== Storage =====
void initStorage() {
  QSPIHandle::Config qspiConfig;
  qspiConfig.device = QSPIHandle::Config::IS25LP064A;
  qspiConfig.mode   = QSPIHandle::Config::MEMORY_MAPPED;
  qspiConfig.pin_config.clk = PIN_QSPI_CLK;
  qspiConfig.pin_config.io0 = PIN_QSPI_IO0;
  qspiConfig.pin_config.io1 = PIN_QSPI_IO1;
  qspiConfig.pin_config.io2 = PIN_QSPI_IO2;
  qspiConfig.pin_config.io3 = PIN_QSPI_IO3;
  qspiConfig.pin_config.ncs = PIN_QSPI_NCS;
  qspi.Init(qspiConfig);

  // Defaults, used on first boot and by Factory Reset
  Settings defaults = {};
  defaults.version = SETTINGS_VERSION;
  defaults.baseNote = 36;
  defaults.envAtt = 0.1f;
  defaults.envDec = 0.1f;
  defaults.envSus = 0.7f;
  defaults.envRel = 0.2f;
  for (auto &input : defaults.cal) {
    input[0] = CAL_DEFAULT_LOW;
    input[1] = CAL_DEFAULT_HIGH;
  }
  defaults.displayBrightness = 255;

  storage.Init(defaults);

  Settings &stored = storage.GetSettings();
  if (stored.version == 4) {
    migrateFromVersion4(stored);
    storage.Save();
  }
  else if (stored.version != SETTINGS_VERSION) {
    Serial.println("Settings update, resetting all settings");
    storage.RestoreDefaults();
  }

  loadSettings();
}

// Version 4 stored the calibration as 10-bit ADC counts, had a glide that was
// nearly on/off, and never applied the stored envelope: until edited, the
// voice played A 0.1s, D 0.1s, S 0.7, R 0.2s whatever the menu showed.
// Convert, so the update keeps the calibration and the sound.
void migrateFromVersion4(Settings &s)
{
  for (auto &input : s.cal)
    for (float &point : input) point = (point + 0.5f) / 1024.0f;

  // A menu edit can't set a time to exactly 0, so 0 means never edited
  if (s.envAtt == 0.0f && s.envDec == 0.0f && s.envRel == 0.0f) s.envSus = 0.7f;
  if (s.envAtt == 0.0f) s.envAtt = 0.1f;
  if (s.envDec == 0.0f) s.envDec = 0.1f;
  if (s.envRel == 0.0f) s.envRel = 0.2f;

  // Old glide: per-sample smoothing coefficient 1 - glide * 0.9999
  if (s.glideAmount > 0.0f) {
    float oldTime = -1.0f / (logf(s.glideAmount * 0.9999f) * 48000.0f);
    s.glideAmount = sqrtf(oldTime / GLIDE_MAX_TIME); // rounded and clamped on load
  }

  s.version = SETTINGS_VERSION;
}

// Load State: back to the last saved settings. Also used at boot.
void loadSettings() {
  live = storage.GetSettings();
  for (const ParamItem &item : params) stepParam(item, 0); // keep values in range
  live.displayBrightness = constrain(live.displayBrightness, 0, 255);
  u8g2.setContrast(live.displayBrightness);
  computeCalCoefficients();
}

void saveSettings()
{
  storage.GetSettings() = live;
  storage.Save();

  Serial.println("Settings saved");
}

// Back to the defaults, calibration included
void factoryReset() {
  storage.RestoreDefaults();
  loadSettings();
}
