# Marblesy firmware: Marbles on a Daisy Seed. See README.md.
#
#   make setup         clone libDaisy (pinned) next to this file and build it
#   make               build/marblesy.bin
#   make program-boot  flash the Daisy bootloader (once; Seed in DFU mode)
#   make program-dfu   flash the firmware (bootloader's LED pulsing)
#
# The program runs from the Seed's SRAM: the Daisy bootloader copies it there
# from the QSPI flash at power-up (libDaisy's APP_TYPE = BOOT_SRAM). Compiler
# and linker flags follow libDaisy's core/Makefile.

TARGET = marblesy

LIBDAISY_DIR ?= lib/libDaisy
LIBDAISY_TAG = v9.0.0
LIBDAISY_URL = https://github.com/electro-smith/libDaisy

BUILD_DIR = build

# Upstream code, unchanged (vendor/), and the port (src/), whose files in
# src/marbles/ replace their upstream namesakes: src/ comes first on the
# include path.
VENDOR_DIRS = \
	vendor/marbles \
	vendor/marbles/ramp \
	vendor/marbles/random \
	vendor/stmlib/dsp \
	vendor/stmlib/system \
	vendor/stmlib/utils
PORT_DIRS = src src/marbles src/marbles/drivers src/marbles/random

CC_SOURCES = $(foreach d,$(PORT_DIRS) $(VENDOR_DIRS),$(wildcard $(d)/*.cc))
C_SOURCES = $(LIBDAISY_DIR)/core/startup_stm32h750xx.c

LDSCRIPT = $(LIBDAISY_DIR)/core/STM32H750IB_sram.lds
BOOT_BIN = $(LIBDAISY_DIR)/core/dsy_bootloader_v6_4-intdfu-2000ms.bin
QSPI_ADDRESS = 0x90040000
INTERNAL_ADDRESS = 0x08000000

PREFIX = arm-none-eabi-
CC = $(GCC_PATH)$(PREFIX)gcc
CXX = $(GCC_PATH)$(PREFIX)g++
CP = $(GCC_PATH)$(PREFIX)objcopy
SZ = $(GCC_PATH)$(PREFIX)size

MCU = -mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard

C_DEFS = \
	-DUSE_HAL_DRIVER \
	-DSTM32H750xx \
	-DHSE_VALUE=16000000 \
	-DCORE_CM7 \
	-DSTM32H750IB \
	-DARM_MATH_CM7 \
	-DUSE_FULL_LL_DRIVER \
	-DBOOT_APP \
	-DFILEIO_ENABLE_FATFS_READER

C_INCLUDES = \
	-Isrc \
	-Ivendor \
	-I$(LIBDAISY_DIR) \
	-I$(LIBDAISY_DIR)/src \
	-I$(LIBDAISY_DIR)/src/sys \
	-I$(LIBDAISY_DIR)/src/usbd \
	-I$(LIBDAISY_DIR)/src/usbh \
	-I$(LIBDAISY_DIR)/Drivers/CMSIS_5/CMSIS/Core/Include \
	-I$(LIBDAISY_DIR)/Drivers/CMSIS-Device/ST/STM32H7xx/Include \
	-I$(LIBDAISY_DIR)/Drivers/STM32H7xx_HAL_Driver/Inc \
	-I$(LIBDAISY_DIR)/Middlewares/ST/STM32_USB_Device_Library/Core/Inc \
	-I$(LIBDAISY_DIR)/Middlewares/ST/STM32_USB_Host_Library/Core/Inc \
	-I$(LIBDAISY_DIR)/Middlewares/ST/STM32_USB_Host_Library/Class/MSC/Inc \
	-I$(LIBDAISY_DIR)/Middlewares/ST/STM32_USB_Host_Library/Class/MIDI/Inc \
	-I$(LIBDAISY_DIR)/Middlewares/Third_Party/FatFs/src \
	-include stm32h7xx.h

OPT = -O2
CFLAGS = $(MCU) $(C_DEFS) $(C_INCLUDES) $(OPT) -g -ggdb \
	-Wall -Wno-missing-attributes -Wno-stringop-overflow \
	-Wno-unused-local-typedefs \
	-fasm -fdata-sections -ffunction-sections -MMD -MP
CXXFLAGS = $(CFLAGS) -std=gnu++14 \
	-fno-exceptions -fno-rtti -fno-unwind-tables -fshort-enums \
	-finline -finline-functions-called-once -fno-move-loop-invariants \
	-Wno-register

LDFLAGS = $(MCU) --specs=nano.specs --specs=nosys.specs -T$(LDSCRIPT) \
	-L$(LIBDAISY_DIR)/build -ldaisy -lc -lm -lnosys \
	-Wl,-Map=$(BUILD_DIR)/$(TARGET).map,--cref -Wl,--gc-sections \
	-Wl,--print-memory-usage

OBJECTS = \
	$(addprefix $(BUILD_DIR)/,$(CC_SOURCES:.cc=.o)) \
	$(BUILD_DIR)/libdaisy/startup_stm32h750xx.o

all: $(BUILD_DIR)/$(TARGET).bin

$(BUILD_DIR)/%.o: %.cc Makefile
	@mkdir -p $(@D)
	$(CXX) -c $(CXXFLAGS) $< -o $@

$(BUILD_DIR)/libdaisy/startup_stm32h750xx.o: $(C_SOURCES) Makefile
	@mkdir -p $(@D)
	$(CC) -c $(CFLAGS) -std=gnu11 $< -o $@

$(BUILD_DIR)/$(TARGET).elf: $(OBJECTS) $(LIBDAISY_DIR)/build/libdaisy.a
	$(CXX) $(OBJECTS) $(LDFLAGS) -o $@
	$(SZ) $@

$(BUILD_DIR)/$(TARGET).bin: $(BUILD_DIR)/$(TARGET).elf
	$(CP) -O binary -S $< $@

$(LIBDAISY_DIR)/build/libdaisy.a:
	@echo "libDaisy is not built: run 'make setup' (or point LIBDAISY_DIR at a built libDaisy $(LIBDAISY_TAG))."
	@false

setup:
	test -d $(LIBDAISY_DIR) || git clone --branch $(LIBDAISY_TAG) --depth 1 \
		--recurse-submodules --shallow-submodules $(LIBDAISY_URL) $(LIBDAISY_DIR)
	$(MAKE) -C $(LIBDAISY_DIR)

program-dfu: $(BUILD_DIR)/$(TARGET).bin
	dfu-util -a 0 -s $(QSPI_ADDRESS):leave -D $< -d ,0483:df11

program-boot:
	dfu-util -a 0 -s $(INTERNAL_ADDRESS):leave -D $(BOOT_BIN) -d ,0483:df11

clean:
	rm -rf $(BUILD_DIR)

.PHONY: all setup program-dfu program-boot clean

-include $(OBJECTS:.o=.d)
