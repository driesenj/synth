#ifndef SSD1306_H
#define SSD1306_H

#include "main.h"
#include <string.h>

/* ── Configuration ───────────────────────────────────────────────────────── */
#define SSD1306_I2C_ADDR    0x3C   // 7-bit address (0x3C or 0x3D depending on SA0 pin)
#define SSD1306_WIDTH       128
#define SSD1306_HEIGHT      64

#define SSD1306_PAGES  (SSD1306_HEIGHT / 8)   /* 8 */

/* ── Public API ──────────────────────────────────────────────────────────── */

/**
 * @brief  Initialise the display. Call once after HAL_Init.
 * @param  hi2c  Pointer to the I2C handle (e.g. &hi2c1).
 */
void SSD1306_Init(I2C_HandleTypeDef *hi2c);

/**
 * @brief  Fill the entire frame-buffer with one colour.
 * @param  colour  0 = black, 1 = white.
 */
void SSD1306_Fill(uint8_t colour);

/**
 * @brief  Set a single pixel in the frame-buffer (does NOT call Update).
 * @param  x, y   Pixel coordinates (0-based).
 * @param  colour 0 = off, 1 = on.
 */
void SSD1306_DrawPixel(int16_t x, int16_t y, uint8_t colour);

/**
 * @brief  Draw a horizontal line.
 */
void SSD1306_DrawHLine(int16_t x, int16_t y, int16_t w, uint8_t colour);

/**
 * @brief  Draw a vertical line.
 */
void SSD1306_DrawVLine(int16_t x, int16_t y, int16_t h, uint8_t colour);

/**
 * @brief  Draw a filled rectangle.
 */
void SSD1306_FillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t colour);

/**
 * @brief  Draw a single ASCII character using the built-in 5×7 font.
 *         Cursor advances automatically.
 * @param  x, y   Top-left corner of the character cell.
 * @param  ch     ASCII character (32–126).
 * @param  colour 0 = black, 1 = white.
 */
void SSD1306_DrawChar(int16_t x, int16_t y, char ch, uint8_t colour);

/**
 * @brief  Draw a null-terminated string using the built-in 5×7 font.
 *         Wraps to the next line when it reaches the right edge.
 * @param  x, y   Top-left corner of the first character.
 * @param  str    Pointer to the string.
 * @param  colour 0 = black, 1 = white.
 */
void SSD1306_DrawString(int16_t x, int16_t y, const char *str, uint8_t colour);

/* ── Async frame push ────────────────────────────────────────────────────── */

/**
 * @brief  Begin pushing the page buffer to the display. Returns 0 and does
 *         nothing if a previous frame is still in flight.
 *         Blocks for ~150 µs to set the GDDRAM window, then returns; the eight
 *         129-byte page strips are transferred by DMA and pumped by
 *         SSD1306_Service().
 */
uint8_t SSD1306_UpdateStart(void);

/**
 * @brief  Main-loop pump. Kicks the next page strip if the bus is idle and the
 *         current frame is unfinished. Call every loop iteration.
 */
void SSD1306_Service(void);

/** 1 while a DMA transfer is actually on the wire. Gate all other I2C1 traffic
 *  (i.e. MCP23017_Poll) on this being 0. */
uint8_t SSD1306_BusBusy(void);

/** 1 while a frame is still being pushed (any strip outstanding). Gate
 *  re-rendering on this being 0 so you never draw into a buffer being sent. */
uint8_t SSD1306_UpdateBusy(void);

/* ── ISR hooks — call from HAL_I2C_MasterTxCpltCallback / ErrorCallback ──── */
void SSD1306_TxCpltISR(void);
void SSD1306_ErrorISR(void);

#endif /* SSD1306_H */
