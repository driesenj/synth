#include "74HC595.h"

// ---------------------------------------------------------------------------
// Pointer to the CubeMX-generated SPI handle, stored at HC595_init() time.
// ---------------------------------------------------------------------------
static SPI_HandleTypeDef *hc595_spi = NULL;

// ---------------------------------------------------------------------------
// Shadow buffer – mirrors the last latched value per device so that
// HC595_setBit() can read-modify-write without re-reading the hardware.
// Index 0 = first device (closest to MCU).
// ---------------------------------------------------------------------------
static uint8_t shadowBuf[HC595_NUM_DEVICES] = {0};

// ---------------------------------------------------------------------------
// Internal: pulse the latch pin to transfer shift-register contents to the
// storage register (makes the new values visible on Qx outputs).
// ---------------------------------------------------------------------------
static inline void HC595_latch(void)
{
    HAL_GPIO_WritePin(HC595_LATCH_PORT, HC595_LATCH_PIN, GPIO_PIN_SET);
    __NOP(); __NOP();
    HAL_GPIO_WritePin(HC595_LATCH_PORT, HC595_LATCH_PIN, GPIO_PIN_RESET);
}

// ---------------------------------------------------------------------------
// HC595_init
// ---------------------------------------------------------------------------
void HC595_init(SPI_HandleTypeDef *hspi)
{
    hc595_spi = hspi;
    HC595_clear();
}

// ---------------------------------------------------------------------------
// HC595_write
// ---------------------------------------------------------------------------
void HC595_write(uint8_t data[HC595_NUM_DEVICES])
{
    // The 74HC595 daisy-chain shifts the first byte to the last device, so
    // transmit in reverse order to keep data[0] = device 0 (first chip).
    uint8_t txBuf[HC595_NUM_DEVICES];
    for (int i = 0; i < HC595_NUM_DEVICES; i++)
    {
        txBuf[i]      = data[HC595_NUM_DEVICES - 1 - i];
        shadowBuf[i]  = data[i];
    }

    HAL_SPI_Transmit(hc595_spi, txBuf, HC595_NUM_DEVICES, HAL_MAX_DELAY);
    HC595_latch();
}

// ---------------------------------------------------------------------------
// HC595_writeAll
// ---------------------------------------------------------------------------
void HC595_writeAll(uint8_t value)
{
    uint8_t data[HC595_NUM_DEVICES];
    for (int i = 0; i < HC595_NUM_DEVICES; i++)
        data[i] = value;
    HC595_write(data);
}

// ---------------------------------------------------------------------------
// HC595_setBit
// ---------------------------------------------------------------------------
void HC595_setBit(uint8_t device, uint8_t bit, uint8_t state)
{
    if (device >= HC595_NUM_DEVICES || bit > 7) return;

    if (state)
        shadowBuf[device] |=  (1u << bit);
    else
        shadowBuf[device] &= ~(1u << bit);

    HC595_write(shadowBuf);
}

// ---------------------------------------------------------------------------
// HC595_clear
// ---------------------------------------------------------------------------
void HC595_clear(void)
{
	uint8_t data[HC595_NUM_DEVICES];
	data[0] = 0x00;   // first IC  – all outputs LOW
	for (int i = 1; i < HC595_NUM_DEVICES; i++)
		data[i] = 0xFF;   // all other ICs – all outputs HIGH
	HC595_write(data);
}

void HC595_getShadow(uint8_t out[HC595_NUM_DEVICES]) {
    memcpy(out, shadowBuf, HC595_NUM_DEVICES);
}

static volatile uint8_t ledByte = 0x00;

void HC595_SetLedByte(uint8_t value)
{
    ledByte = value;
}

void HC595_WriteGates(uint8_t dev1, uint8_t dev2)
{
    /* Chain order: last device first, device 0 last. */
    uint8_t tx[HC595_NUM_DEVICES] = { dev2, dev1, ledByte };

    shadowBuf[0] = ledByte;
    shadowBuf[1] = dev1;
    shadowBuf[2] = dev2;

    HAL_SPI_Transmit(hc595_spi, tx, HC595_NUM_DEVICES, HAL_MAX_DELAY);
    HC595_latch();
}
