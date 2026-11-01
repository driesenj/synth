// Copyright 2026 the Plaitsy authors. MIT licence, see plaits/firmware/LICENSE.
//
// Plaitsy: the user data block in QSPI flash (see plaits/user_data.h).

#include "plaits/user_data.h"

#include "hal.h"

namespace plaits {

using namespace plaitsy;

// After the 64 kB of settings (plaits/settings.cc).
const uint32_t kUserDataFlashOffset = 0x10000;

uint8_t UserData::data_[UserData::SIZE + UserData::kReadMargin];
volatile bool UserData::dirty_ = false;

/* static */
void UserData::Init() {
  hal::FlashRead(kUserDataFlashOffset, data_, SIZE);
  dirty_ = false;
}

/* static */
void UserData::Persist() {
  if (!dirty_) {
    return;
  }
  // Save() only runs once a whole block has come in through the TIMBRE
  // input, which takes many seconds, so the copy does not change under us.
  dirty_ = false;
  if (hal::FlashErase(kUserDataFlashOffset, SIZE)) {
    hal::FlashWrite(kUserDataFlashOffset, data_, SIZE);
  }
}

}  // namespace plaits
