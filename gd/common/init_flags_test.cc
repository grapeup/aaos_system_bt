/******************************************************************************
 *
 *  Copyright 2019 The Android Open Source Project
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at:
 *
 *  http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 *
 ******************************************************************************/

#include "common/init_flags.h"

#include <gtest/gtest.h>

using bluetooth::common::InitFlags;

TEST(InitFlagsTest, test_load_nullptr) {
  InitFlags::Load(nullptr);
  ASSERT_FALSE(InitFlags::GdCoreEnabled());
}

TEST(InitFlagsTest, test_load_empty) {
  const char* input[] = {nullptr};
  InitFlags::Load(input);
  ASSERT_FALSE(InitFlags::GdCoreEnabled());
}

TEST(InitFlagsTest, test_load_garbage) {
  const char* input[] = {"some random non-existent flag", nullptr};
  InitFlags::Load(input);
  ASSERT_FALSE(InitFlags::GdCoreEnabled());
}

TEST(InitFlagsTest, test_load_core) {
  const char* input[] = {"INIT_gd_core=true", nullptr};
  InitFlags::Load(input);
  ASSERT_TRUE(InitFlags::GdCoreEnabled());
  ASSERT_TRUE(InitFlags::GdControllerEnabled());
  ASSERT_TRUE(InitFlags::GdHciEnabled());
  ASSERT_FALSE(InitFlags::BtaaHciLogEnabled());
}

TEST(InitFlagsTest, test_load_controller) {
  const char* input[] = {"INIT_gd_controller=true", nullptr};
  InitFlags::Load(input);
  ASSERT_FALSE(InitFlags::GdCoreEnabled());
  ASSERT_TRUE(InitFlags::GdControllerEnabled());
  ASSERT_TRUE(InitFlags::GdHciEnabled());
  ASSERT_FALSE(InitFlags::BtaaHciLogEnabled());
}

TEST(InitFlagsTest, test_load_hci) {
  const char* input[] = {"INIT_gd_hci=true", nullptr};
  InitFlags::Load(input);
  ASSERT_FALSE(InitFlags::GdCoreEnabled());
  ASSERT_FALSE(InitFlags::GdControllerEnabled());
  ASSERT_TRUE(InitFlags::GdHciEnabled());
  ASSERT_FALSE(InitFlags::BtaaHciLogEnabled());
}

TEST(InitFlagsTest, test_load_gatt_robust_caching) {
  const char* input[] = {"INIT_gatt_robust_caching=true", nullptr};
  InitFlags::Load(input);
  ASSERT_TRUE(InitFlags::GattRobustCachingEnabled());
}

TEST(InitFlagsTest, test_enable_debug_logging_for_all) {
  const char* input[] = {"INIT_logging_debug_enabled_for_all=true", nullptr};
  InitFlags::Load(input);
  ASSERT_TRUE(InitFlags::IsDebugLoggingEnabledForTag("foo"));
  ASSERT_TRUE(InitFlags::IsDebugLoggingEnabledForTag("bar"));
  ASSERT_TRUE(InitFlags::IsDebugLoggingEnabledForAll());
}

TEST(InitFlagsTest, test_enable_debug_logging_for_tags) {
  const char* input[] = {"INIT_logging_debug_enabled_for_tags=foo,bar,hello", nullptr};
  InitFlags::Load(input);
  ASSERT_TRUE(InitFlags::IsDebugLoggingEnabledForTag("foo"));
  ASSERT_TRUE(InitFlags::IsDebugLoggingEnabledForTag("bar"));
  ASSERT_TRUE(InitFlags::IsDebugLoggingEnabledForTag("hello"));
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForTag("Foo"));
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForAll());
}

TEST(InitFlagsTest, test_disable_debug_logging_for_tags) {
  const char* input[] = {"INIT_logging_debug_disabled_for_tags=foo,bar,hello", nullptr};
  InitFlags::Load(input);
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForTag("foo"));
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForTag("bar"));
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForTag("hello"));
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForTag("Foo"));
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForAll());
}

TEST(InitFlagsTest, test_debug_logging_multiple_flags) {
  const char* input[] = {"INIT_logging_debug_enabled_for_tags=foo,hello",
                         "INIT_logging_debug_disabled_for_tags=foo,bar",
                         "INIT_logging_debug_enabled_for_all=false",
                         nullptr};
  InitFlags::Load(input);
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForTag("foo"));
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForTag("bar"));
  ASSERT_TRUE(InitFlags::IsDebugLoggingEnabledForTag("hello"));
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForTag("Foo"));
  ASSERT_FALSE(InitFlags::IsDebugLoggingEnabledForAll());
}

TEST(InitFlagsTest, test_load_btaa_hci_log) {
  const char* input[] = {"INIT_btaa_hci=true", nullptr};
  InitFlags::Load(input);
  ASSERT_TRUE(InitFlags::BtaaHciLogEnabled());
  ASSERT_FALSE(InitFlags::GdCoreEnabled());
  ASSERT_FALSE(InitFlags::GdControllerEnabled());
  ASSERT_FALSE(InitFlags::GdHciEnabled());
}
