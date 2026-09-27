/**
  ******************************************************************************
  * @file    seq_lock.h
  * @brief   Critical section primitive for state shared with the 1 kHz transport.
  ******************************************************************************
  *
  * The sequencer runs from TIM6 at 1 kHz (NVIC priority SEQ_IRQ_PRIORITY). It
  * advances steps, evaluates swing/ratchet/roll timing and writes the HC595 gate
  * outputs. The main loop concurrently mutates the same Sequencer_t: toggling
  * steps, changing pattern length and BPM, switching banks, loading presets.
  *
  * Most of those edits are not single-word writes. Seq_ToggleStep followed by a
  * length change, or a Seq_LoadFromPreset memcpy, leaves the struct briefly
  * inconsistent. If the transport fires mid-update it can advance a channel past
  * the end of a pattern, or fire a gate against half-written step data.
  *
  * SEQ_LOCK raises BASEPRI to SEQ_IRQ_PRIORITY, which masks the transport and
  * everything below it while leaving SysTick (priority 0) running, so HAL
  * timeouts still work inside the section. Saving and restoring the previous
  * BASEPRI means the macros nest correctly.
  *
  * Usage:
  *     SEQ_LOCK();
  *     Seq_ToggleStep(&seq, ch, bank, step);
  *     SEQ_UNLOCK();
  *
  * Keep the body short: the transport cannot run while the lock is held, so a
  * hold longer than 1 ms drops a tick outright. Never call printf(), HAL_Delay()
  * or anything touching flash from inside a locked section — preset saves are
  * deferred to the main loop for exactly this reason.
  *
  * The lock is only needed for state the transport reads. Fields it owns
  * outright (gate_on_ms, gate_off_ms, ratchet_remaining) are written by the ISR
  * alone and need no protection; see the ownership table in the timing
  * architecture notes.
  *
  ******************************************************************************
  */
#pragma once
#include "stm32l4xx.h"          /* pulls in CMSIS core_cm4.h */

/* NVIC priority assigned to TIM6_DAC_IRQn. SEQ_LOCK masks this level and below. */
#define SEQ_IRQ_PRIORITY   1u

static inline uint32_t seq_lock(void)
{
    uint32_t prev = __get_BASEPRI();
    __set_BASEPRI((SEQ_IRQ_PRIORITY << (8U - __NVIC_PRIO_BITS)) & 0xFFU);
    __DSB();
    __ISB();
    return prev;
}

static inline void seq_unlock(uint32_t prev)
{
    __set_BASEPRI(prev);
}

/* Usage:
 *     SEQ_LOCK();
 *     ... mutate seq ...
 *     SEQ_UNLOCK();
 * Nests correctly (BASEPRI is saved and restored). Keep the body short —
 * never call printf(), HAL_Delay() or anything touching flash inside.
 */
#define SEQ_LOCK()    uint32_t _seq_basepri = seq_lock()
#define SEQ_UNLOCK()  seq_unlock(_seq_basepri)
