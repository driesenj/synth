#include "sequencer.h"
#include <string.h>
#include "74HC595.h"
#include <assert.h>

#define CLAMP(x, lo, hi)  ((x) < (lo) ? (lo) : ((x) > (hi) ? (hi) : (x)))

static_assert(sizeof(SeqPreset_t) % 8 == 0,"Size of SeqPreset_t must remain a multiple of 8 bytes for the doubleword flash write loop");

/* ── Transport time base ─────────────────────────────────────────────────── */
static volatile uint32_t s_now_ms = 0;

uint32_t Seq_NowMs(void) { return s_now_ms; }

/* ── ISR-safe PRNG ───────────────────────────────────────────────────────────
   newlib's rand() touches per-thread reentrancy state and is not safe to call
   from an interrupt. xorshift32 is ~5 cycles and fully deterministic.          */
static uint32_t s_rng = 0xA5C3F17Bu;

static inline uint32_t seq_rand(void)
{
    s_rng ^= s_rng << 13;
    s_rng ^= s_rng >> 17;
    s_rng ^= s_rng << 5;
    return s_rng;
}

// (device, bit) pair for each output channel, index 0 = OUT1
static const struct { uint8_t device; uint8_t bit; } gate_map[SEQ_NUM_CHANNELS] = {
    {1, 3},  // OUT1
    {1, 4},  // OUT2
    {2, 4},  // OUT3
    {2, 3},  // OUT4
    {2, 5},  // OUT5
    {1, 2},  // OUT6
    {1, 5},  // OUT7
    {1, 7},  // OUT8
    {2, 2},  // OUT9
    {2, 6},  // OUT10
    {1, 1},  // OUT11
    {1, 6},  // OUT12
    {1, 0},  // OUT13
    {2, 0},  // OUT14
    {2, 7},  // OUT15
};

void Seq_Init(Sequencer_t *seq, void (*clock_output)(uint8_t high))
{
    memset(seq, 0, sizeof(Sequencer_t));

	seq->clock_mode = 1;

	seq->last_clock_ms = 0;
	seq->clock_period_ms = 0;
	seq->gate_off_ms = UINT32_MAX;
	seq->current_bpm = 0;

	seq->last_clk_tick = 0;
	seq->internal_bpm = 120;
	seq->pending_internal_bpm = seq->internal_bpm;
	seq->has_pending_internal_bpm = 0;

	seq->current_channel = 0;
	seq->solo_channel    = -1;
	seq->live_mode = 1;
	seq->global_step = 0;
	seq->global_mute = 0;
	seq->global_rand = 0;
	seq->global_swing = 0;

	seq->roll_division = 0;
	seq->last_roll_ms = 0;

	seq->clock_output = clock_output;

    for (int i = 0; i < SEQ_NUM_CHANNELS; i++) {
    	seq->channels[i].custom_bpm   = 0; // 0 => Use global bpm, 1 => Use custom channel bpm
    	seq->channels[i].bpm          = seq->internal_bpm; // or pass internal_bpm
		seq->channels[i].last_tick_ms = 0;
        seq->channels[i].gate_on_ms   = 0;
		seq->channels[i].gate_off_ms  = UINT32_MAX;
		seq->channels[i].gate_forced = 0;

		seq->channels[i].length      = 16; // sensible default
        seq->channels[i].view_offset = 0;
        seq->channels[i].active_bank = 0;
        seq->channels[i].current_step = 0;
        seq->channels[i].muted = 0;
        seq->channels[i].rand_amount = 0;
        seq->channels[i].swing_amount = 0;

        seq->channels[i].has_pending = 0;

        seq->channels[i].ratchet_remaining  = 0;
        seq->channels[i].ratchet_interval_ms = 0;
        seq->channels[i].next_ratchet_ms    = 0;

        // initialise all ratchet values to 1
        for (uint8_t b = 0; b < SEQ_NUM_BANKS; b++)
            for (uint8_t s = 0; s < SEQ_MAX_STEPS; s++)
                seq->channels[i].ratchet[b][s] = 1;
    }
}

void Seq_SelectChannel(Sequencer_t *seq, int delta)
{
	int ch = (int)seq->current_channel + delta;
	// Wrap: 15 → 0, -1 → 14
	ch = ((ch % SEQ_NUM_CHANNELS) + SEQ_NUM_CHANNELS) % SEQ_NUM_CHANNELS;
	seq->current_channel = (uint8_t)ch;
}

void Seq_SetLength(Sequencer_t *seq, int delta)
{
    SeqChannel_t *ch = &seq->channels[seq->current_channel];
    int len = (int)ch->length + delta;
    if (len < 1)            len = 1;
    if (len > SEQ_MAX_STEPS) len = SEQ_MAX_STEPS;
    if (seq->live_mode) {
        ch->length = (uint8_t)len;
    } else {
    	// Copy live to pending on first edit if not already pending
		if (!ch->has_pending) {
			Seq_InitPending(seq, seq->current_channel);
		}
		ch->pending.length = (uint8_t)len;
    }

	// Clamp view offset now that length may have shrunk
	int max_offset = (int)len - SEQ_VIEW_SIZE;
	if (max_offset < 0) max_offset = 0;
	if ((int)ch->view_offset > max_offset)
		ch->view_offset = (uint8_t)max_offset;
}

uint8_t Seq_GetLength(Sequencer_t *seq) {
	SeqChannel_t *ch = &seq->channels[seq->current_channel];

	if (ch->has_pending) return ch->pending.length;

	return ch->length;
}

void Seq_SetGlobalBPM(Sequencer_t *seq, int delta) {
	if (seq->live_mode) {
		seq->internal_bpm = (uint16_t)CLAMP((int)seq->internal_bpm + delta, 20, 300);

	} else {
		seq->pending_internal_bpm = (uint16_t)CLAMP((int)seq->pending_internal_bpm + delta, 20, 300);
		seq->has_pending_internal_bpm = 1;
	}
}
uint16_t Seq_GetGlobalBPM(Sequencer_t *seq) {
	if (seq->has_pending_internal_bpm) return seq->pending_internal_bpm;

	return seq->internal_bpm;
}

void Seq_SetChannelBPM(Sequencer_t *seq, int delta)
{
	SeqChannel_t *ch = &seq->channels[seq->current_channel];
	uint16_t current_global = seq->clock_mode ? seq->internal_bpm : seq->current_bpm;

	if (seq->live_mode) {
		if (!ch->custom_bpm)
			ch->bpm = current_global;
		ch->bpm = (uint16_t)CLAMP((int)ch->bpm + delta, 20, 300);
		ch->custom_bpm = (ch->bpm != current_global);
	} else {
		if (!ch->has_pending) {
			Seq_InitPending(seq, seq->current_channel);
		}
		if (!ch->pending.custom_bpm)
			ch->pending.bpm = current_global;
		ch->pending.bpm = (uint16_t)CLAMP((int)ch->pending.bpm + delta, 20, 300);
		ch->pending.custom_bpm = (ch->pending.bpm != current_global);
		ch->has_pending = 1;
	}
}
uint16_t Seq_GetChannelBPM(Sequencer_t *seq) {
	SeqChannel_t *ch = &seq->channels[seq->current_channel];

	if (ch->has_pending) return ch->pending.bpm;

	return ch->bpm;
}

void Seq_SetViewOffset(Sequencer_t *seq, int delta)
{
    SeqChannel_t *ch = &seq->channels[seq->current_channel];
    int max_offset = (int)ch->length - SEQ_VIEW_SIZE;
    if (max_offset <= 0) {
        ch->view_offset = 0; // window covers entire pattern
        return;
    }
    int offset = (int)ch->view_offset + delta;
    if (offset < 0)           offset = 0;
    if (offset > max_offset)  offset = max_offset;
    ch->view_offset = (uint8_t)offset;
}

void Seq_ToggleSolo(Sequencer_t *seq)
{
    // Press again on the already-soloed channel to un-solo
    if (seq->solo_channel == (int8_t)seq->current_channel)
        seq->solo_channel = -1;
    else
        seq->solo_channel = (int8_t)seq->current_channel;
}

uint8_t Seq_IsChannelActive(const Sequencer_t *seq, uint8_t channel)
{
	// SOLO overrides MUTE
	if (seq->solo_channel >= 0)  return (channel == (uint8_t)seq->solo_channel);
	if (seq->channels[channel].muted) return 0;
	return 1;
}

uint8_t *Seq_GetVisibleSteps(Sequencer_t *seq, uint8_t bank)
{
    SeqChannel_t *ch = &seq->channels[seq->current_channel];
    return &ch->steps[bank][ch->view_offset];
}

uint8_t Seq_GetVisibleLength(const Sequencer_t *seq)
{
    const SeqChannel_t *ch = &seq->channels[seq->current_channel];
    int visible = (int)ch->length - (int)ch->view_offset;
    if (visible > SEQ_VIEW_SIZE) visible = SEQ_VIEW_SIZE;
    if (visible < 0)             visible = 0;
    return (uint8_t)visible;
}

void Seq_UpdateGateOutputs(Sequencer_t *seq, uint32_t now)
{
	uint8_t dev[HC595_NUM_DEVICES] = { 0, 0, 0 };

    for (uint8_t ch = 0; ch < SEQ_NUM_CHANNELS; ch++) {
		SeqChannel_t *channel = &seq->channels[ch];

		if (channel->ratchet_remaining > 0 && now >= channel->next_ratchet_ms) {
			channel->gate_on_ms  = now;
			channel->gate_off_ms = now + channel->ratchet_interval_ms / 2;
			channel->next_ratchet_ms += channel->ratchet_interval_ms;
			channel->ratchet_remaining--;
		 }

		// Swing: gate not yet open
		if (now < channel->gate_on_ms) continue;

		// Expire gate window
		if (channel->gate_off_ms != UINT32_MAX && now >= channel->gate_off_ms) {
			channel->gate_off_ms = UINT32_MAX;
			channel->gate_forced = 0;
		}

		uint8_t rolling = (seq->roll_division > 0 && ch == seq->current_channel);

		uint8_t step_on = !rolling
                		  && channel->steps[channel->active_bank][channel->current_step]
						  && !channel->rand_gate_suppress
						  && Seq_IsChannelActive(seq, ch);

		if (!rolling && !step_on && channel->rand_gate_inject && Seq_IsChannelActive(seq, ch))
			step_on = 1;

		if (channel->gate_off_ms != UINT32_MAX && (step_on || channel->gate_forced))
			dev[gate_map[ch].device] |= (1 << gate_map[ch].bit);
	}

    HC595_WriteGates(dev[1], dev[2]);
}

void Seq_AllGatesOff(Sequencer_t *seq)
{
	(void)seq;
	HC595_WriteGates(0x00, 0x00);
}

void Seq_UpdateRoll(Sequencer_t *seq, uint32_t now) {
    if (seq->roll_division == 0 || seq->clock_period_ms == 0) return;

    uint32_t roll_period = (seq->clock_period_ms * 16u) / seq->roll_division;
    uint32_t gate_dur    = roll_period / 2;
    if (gate_dur < 5) gate_dur = 5;

    if (now - seq->last_roll_ms >= roll_period) {
        seq->last_roll_ms += roll_period;
        if (now - seq->last_roll_ms >= roll_period) seq->last_roll_ms = now;

        SeqChannel_t *ch = &seq->channels[seq->current_channel];
        ch->gate_on_ms         = now;
        ch->gate_off_ms        = now + gate_dur;
        ch->gate_forced        = 1;
        ch->rand_gate_suppress = 0;
        ch->rand_gate_inject   = 0;
    }
}

void Seq_SetStep(Sequencer_t *seq, uint8_t channel, uint8_t bank, uint8_t step, uint8_t state)
{
    if (channel >= SEQ_NUM_CHANNELS) return;
    if (bank    >= SEQ_NUM_BANKS)    return;
    if (step    >= SEQ_MAX_STEPS)    return;

    seq->channels[channel].steps[bank][step] = state ? 1 : 0;
}

void Seq_ToggleStep(Sequencer_t *seq, uint8_t ch, uint8_t bank, uint8_t step)
{
    if (ch >= SEQ_NUM_CHANNELS) return;
    if (bank    >= SEQ_NUM_BANKS)    return;
    if (step    >= SEQ_MAX_STEPS)    return;

    SeqChannel_t *channel = &seq->channels[ch];

    if (seq->live_mode) {
    	channel->steps[bank][step] ^= 1;
    } else {
		// Copy live to pending on first edit if not already pending
		if (!channel->has_pending) {
			Seq_InitPending(seq, ch);
		}
		channel->pending.steps[bank][step] ^= 1;
	}
}

uint8_t Seq_GetStep(const Sequencer_t *seq, uint8_t ch, uint8_t bank, uint8_t step)
{
    if (ch >= SEQ_NUM_CHANNELS) return 0;
    if (bank    >= SEQ_NUM_BANKS)    return 0;
    if (step    >= SEQ_MAX_STEPS)    return 0;

    SeqChannel_t *channel = &seq->channels[ch];
	if (!seq->live_mode && channel->has_pending)
		return channel->pending.steps[bank][step];
	return channel->steps[bank][step];
}

void Seq_AdvanceChannel(Sequencer_t *seq, uint8_t ch_index,
        				uint32_t period_ms, uint32_t now)
{
	SeqChannel_t *ch = &seq->channels[ch_index];

	ch->current_step++;
	if (ch->current_step >= ch->length)
		ch->current_step = 0;

	// Roll owns gate timing on the current channel — don't interfere
	uint8_t rolling = (seq->roll_division > 0 && ch_index == seq->current_channel);
	if (rolling) {
		ch->ratchet_remaining  = 0;
		ch->rand_gate_suppress = 0;
		ch->rand_gate_inject   = 0;
		return;
	}

	// Swing: delay every even-indexed step (2nd, 4th, 6th...)
	// 0-100 maps to 0 to period/3 (triplet feel at max)
	uint8_t swing_pct = (ch->swing_amount > seq->global_swing)
					  ? ch->swing_amount : seq->global_swing;

	uint32_t swing_delay = 0;
	if (swing_pct > 0 && (ch->current_step % 2 == 1))
		swing_delay = (swing_pct * period_ms) / 300;

	ch->gate_on_ms  = now + swing_delay;
	ch->gate_off_ms = ch->gate_on_ms + period_ms / 2;

	// After: ch->gate_on_ms = now + swing_delay; ch->gate_off_ms = ...
	uint8_t ratchet = ch->ratchet[ch->active_bank][ch->current_step];
	if (ratchet > 1 && !ch->rand_gate_suppress) {
	    uint32_t interval        = period_ms / ratchet;
	    ch->ratchet_interval_ms  = interval;
	    ch->ratchet_remaining    = ratchet - 1;  // first sub-fire handled by gate_on/off
	    ch->next_ratchet_ms      = ch->gate_on_ms + interval;
	    ch->gate_off_ms          = ch->gate_on_ms + interval / 2;  // shorten first gate
	} else {
	    ch->ratchet_remaining = 0;
	}

	// Randomisation
	uint8_t step_on  = ch->steps[ch->active_bank][ch->current_step];
	uint8_t rand_pct = (ch->rand_amount > seq->global_rand)
					 ? ch->rand_amount : seq->global_rand;

	ch->rand_gate_suppress = 0;
	ch->rand_gate_inject   = 0;

	if (rand_pct > 0) {
		uint8_t roll = (uint8_t)(seq_rand() % 100);
		if (step_on)
			ch->rand_gate_suppress = (roll < rand_pct);
		else
			ch->rand_gate_inject   = (roll < rand_pct);
	}
}

// Feeds the interval between two external clock edges into the clock period.
// An interval much longer or shorter than the one before it (the clock stopped
// and started again, or a pulse went missing) is left out, so one odd interval
// can't throw off swing, gate lengths, ratchets and rolls. The period is the
// average of the last SEQ_CLOCK_AVERAGE intervals, which also evens out the
// 1 ms resolution the edges are timed with.
static void Seq_MeasureExternalClock(Sequencer_t *seq, uint32_t interval)
{
    uint32_t previous = seq->clock_gap_ms;
    seq->clock_gap_ms = interval;
    if (previous != 0 && (interval * 3 < previous * 2 || interval * 2 > previous * 3))
        return;

    seq->clock_intervals[seq->clock_interval_next] = interval;
    seq->clock_interval_next = (seq->clock_interval_next + 1) % SEQ_CLOCK_AVERAGE;
    if (seq->clock_interval_count < SEQ_CLOCK_AVERAGE)
        seq->clock_interval_count++;

    uint32_t count = seq->clock_interval_count;
    uint32_t sum = 0;
    for (uint32_t i = 0; i < count; i++)
        sum += seq->clock_intervals[i];

    seq->clock_period_ms = (sum + count / 2) / count;
    // Four clock intervals make a beat, rounded to the nearest BPM
    seq->current_bpm = (uint16_t)((15000u * count + sum / 2) / sum);
}

void Seq_ResetExternalClock(Sequencer_t *seq)
{
    seq->last_clock_ms        = 0;
    seq->clock_gap_ms         = 0;
    seq->clock_interval_count = 0;
    seq->clock_interval_next  = 0;
    seq->current_bpm          = 0;
}

// Returns a bitmask of which channels ticked — main loop uses it for fill_held
uint16_t Seq_AdvanceAll(Sequencer_t *seq, uint32_t now, uint8_t clock_fired) {
    uint16_t ticked_mask = 0;
    if (clock_fired) {
        if (seq->clock_mode == 0) {
            if (seq->last_clock_ms != 0)
                Seq_MeasureExternalClock(seq, now - seq->last_clock_ms);
        } else {
            // Internal ticks come exactly on time
            if (seq->last_clock_ms != 0)
                seq->clock_period_ms = now - seq->last_clock_ms;
            seq->current_bpm = seq->clock_period_ms > 0
                             ? (60000 / (seq->clock_period_ms * 4)) : 0;
        }
        seq->last_clock_ms = now;
        seq->global_step++;
    }
    for (uint8_t i = 0; i < SEQ_NUM_CHANNELS; i++) {
    	SeqChannel_t *ch = &seq->channels[i];

		 uint8_t ticked = 0;

		 if (ch->custom_bpm) {
			 uint32_t ch_period = (60000 / ch->bpm) / 4;
			 if ((now - ch->last_tick_ms) >= ch_period) {
				 ch->last_tick_ms = now;
				 Seq_AdvanceChannel(seq, i, ch_period, now);
				 ticked = 1;
			 }
		 } else {
			if (clock_fired && seq->clock_period_ms > 0) {
				Seq_AdvanceChannel(seq, i, seq->clock_period_ms, now);
				ticked = 1;
			}
		 }

        if (ticked) ticked_mask |= (1 << i);
    }
    return ticked_mask;
}

void Seq_TriggerGate(Sequencer_t *seq, uint8_t channel, uint32_t now, uint32_t duration_ms)
{
    if (channel >= SEQ_NUM_CHANNELS) return;

    SeqChannel_t *ch = &seq->channels[channel];
    ch->gate_on_ms  = now;
    ch->gate_off_ms = now + duration_ms;
    ch->gate_forced = 1;

}

void Seq_InitPending(Sequencer_t *seq, uint8_t ch) {
	SeqChannel_t *channel = &seq->channels[ch];

	channel->pending.custom_bpm = channel->custom_bpm;
	channel->pending.bpm = channel->bpm;
	channel->pending.length = channel->length;
	memcpy(channel->pending.steps, channel->steps, sizeof(channel->steps));

	channel->has_pending = 1;
}

void Seq_CommitPending(Sequencer_t *seq, uint8_t ch)
{
    SeqChannel_t *channel = &seq->channels[ch];
    if (channel->has_pending) {
    	channel->custom_bpm = channel->pending.custom_bpm;
    	channel->bpm = channel->pending.bpm;
    	channel->length = channel->pending.length;
    	memcpy(channel->steps, channel->pending.steps, sizeof(channel->steps));

        channel->has_pending = 0;
    }
}

void Seq_CommitPendingAll(Sequencer_t *seq)
{
    for (uint8_t i = 0; i < SEQ_NUM_CHANNELS; i++)
        Seq_CommitPending(seq, i);
}

void Seq_ClearChannel(Sequencer_t *seq, uint8_t ch_index)
{
    SeqChannel_t *ch = &seq->channels[ch_index];
    memset(ch->steps[ch->active_bank], 0,
           sizeof(ch->steps[ch->active_bank]));
    ch->has_pending = 0;
}

void Seq_ClearAllChannels(Sequencer_t *seq)
{
    for (uint8_t i = 0; i < SEQ_NUM_CHANNELS; i++)
        Seq_ClearChannel(seq, i);
}

void Seq_ResetChannel(Sequencer_t *seq, uint8_t ch_index)
{
    SeqChannel_t *ch = &seq->channels[ch_index];
    ch->current_step = (seq->global_step + ch->length - 1) % ch->length;
}

void Seq_ResetAllChannels(Sequencer_t *seq)
{
    for (uint8_t i = 0; i < SEQ_NUM_CHANNELS; i++)
        Seq_ResetChannel(seq, i);
}

void Seq_MuteChannel(Sequencer_t *seq, uint8_t ch_index, uint8_t mute)
{
    SeqChannel_t *ch = &seq->channels[ch_index];
    ch->muted = mute;
}

void Seq_MuteAllChannels(Sequencer_t *seq)
{
	uint8_t mute = !seq->global_mute;
	seq->global_mute = mute;

    for (uint8_t i = 0; i < SEQ_NUM_CHANNELS; i++)
        Seq_MuteChannel(seq, i, mute);
}

uint8_t Seq_GetRatchet(const Sequencer_t *seq, uint8_t ch, uint8_t bank, uint8_t step)
{
    if (ch >= SEQ_NUM_CHANNELS || bank >= SEQ_NUM_BANKS || step >= SEQ_MAX_STEPS) return 1;
    return seq->channels[ch].ratchet[bank][step];
}

void Seq_SetRatchet(Sequencer_t *seq, uint8_t ch, uint8_t bank, uint8_t step, uint8_t count)
{
    if (ch >= SEQ_NUM_CHANNELS || bank >= SEQ_NUM_BANKS || step >= SEQ_MAX_STEPS) return;
    seq->channels[ch].ratchet[bank][step] = (uint8_t)CLAMP(count, 1, 8);
}

void Seq_SaveToPreset(const Sequencer_t *seq, SeqPreset_t *preset, uint16_t global_bpm)
{
    memset(preset, 0, sizeof(SeqPreset_t));
    preset->magic        = SEQ_MAGIC;
    preset->global_rand  = seq->global_rand;
    preset->global_swing = seq->global_swing;
    preset->internal_bpm = global_bpm;

    for (uint8_t i = 0; i < SEQ_NUM_CHANNELS; i++) {
        const SeqChannel_t *ch = &seq->channels[i];
        preset->length[i]      = ch->length;
        preset->bpm[i]         = ch->custom_bpm ? ch->bpm : 0;
        preset->rand_amount[i] = ch->rand_amount;
        preset->swing_amount[i]= ch->swing_amount;
        preset->muted[i]       = ch->muted;
        preset->active_bank[i] = ch->active_bank;
        memcpy(preset->steps[i],   ch->steps,   sizeof(ch->steps));
        memcpy(preset->ratchet[i], ch->ratchet, sizeof(ch->ratchet));
    }
}

void Seq_LoadFromPreset(Sequencer_t *seq, const SeqPreset_t *preset, uint16_t *global_bpm_out)
{
    if (preset->magic != SEQ_MAGIC) return;

    seq->global_rand  = preset->global_rand;
    seq->global_swing = preset->global_swing;
    if (global_bpm_out) *global_bpm_out = preset->internal_bpm;

    for (uint8_t i = 0; i < SEQ_NUM_CHANNELS; i++) {
        SeqChannel_t *ch = &seq->channels[i];
        ch->length       = preset->length[i];
        ch->custom_bpm = (preset->bpm[i] != 0);
        if (ch->custom_bpm) ch->bpm = preset->bpm[i];
        ch->last_tick_ms = 0; // resync custom-clock channels
        ch->rand_amount  = preset->rand_amount[i];
        ch->swing_amount = preset->swing_amount[i];
        ch->muted        = preset->muted[i];
        ch->active_bank  = preset->active_bank[i];
        // Reset runtime state
        ch->current_step      = 0;
        ch->has_pending       = 0;
        ch->ratchet_remaining = 0;
        ch->gate_off_ms       = UINT32_MAX;
        ch->gate_on_ms        = 0;
        ch->gate_forced       = 0;
        memcpy(ch->steps,   preset->steps[i],   sizeof(ch->steps));
        memcpy(ch->ratchet, preset->ratchet[i], sizeof(ch->ratchet));
    }
}

uint32_t Seq_HalfPeriodMs(Sequencer_t *seq)
{
	uint32_t hp = seq->clock_mode ? ((60000u / seq->internal_bpm) / 4u / 2u)
			: (seq->clock_period_ms / 2u);
	return (hp < 5u) ? 5u : hp;   // floor at 5 ms
}

uint8_t Seq_TickClock(Sequencer_t *seq, uint32_t now) {
    if (seq->clock_mode != 1) return 0;
    uint32_t period = (60000 / seq->internal_bpm) / 4;
    if ((now - seq->last_clk_tick) >= period) {
        seq->last_clk_tick += period;
        if ((now - seq->last_clk_tick) >= period) seq->last_clk_tick = now;
        seq->gate_off_ms = seq->last_clk_tick + period / 2;
        if (seq->clock_output) seq->clock_output(1);
        return 1;
    }
    if (now >= seq->gate_off_ms) {
        seq->gate_off_ms = UINT32_MAX;
        if (seq->clock_output) seq->clock_output(0);
    }
    return 0;
}

void Seq_ResetChannelSettings(Sequencer_t *seq, uint8_t ch_index)
{
    SeqChannel_t *ch = &seq->channels[ch_index];
    uint16_t global_bpm = seq->clock_mode ? seq->internal_bpm : seq->current_bpm;

    ch->bpm         = global_bpm;
    ch->custom_bpm  = 0;
    ch->rand_amount = 0;
    ch->swing_amount = 0;

    // Clear pending BPM state too so commit mode doesn't restore old values
    ch->pending.bpm        = global_bpm;
    ch->pending.custom_bpm = 0;
}

void Seq_ResetAllChannelSettings(Sequencer_t *seq)
{
    for (uint8_t i = 0; i < SEQ_NUM_CHANNELS; i++)
        Seq_ResetChannelSettings(seq, i);
}

uint16_t Seq_ServiceTick(Sequencer_t *seq, uint8_t ext_clock_edge)
{
    uint32_t now = ++s_now_ms;

    uint8_t clock_fired = (seq->clock_mode == 1)
                        ? Seq_TickClock(seq, now)
                        : ext_clock_edge;

    uint16_t ticked = Seq_AdvanceAll(seq, now, clock_fired);

    /* FILL: hold the current channel's gate open on every tick it advances.
       Done here rather than in the caller so the forced gate is visible to
       Seq_UpdateGateOutputs on the SAME tick, not one millisecond later. */
    if (seq->fill_held && (ticked & (1u << seq->current_channel)))
        seq->channels[seq->current_channel].gate_forced = 1;

    Seq_UpdateRoll(seq, now);
    Seq_UpdateGateOutputs(seq, now);

    return ticked;
}
