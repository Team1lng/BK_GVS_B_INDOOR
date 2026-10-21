#!/usr/bin/env python3
"""Check persisted App lock selection using the real user-data layout and loader."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from run_channel_tests import ROOT, function


class UserDataTests(unittest.TestCase):
    def test_lock_selection_survives_save_and_repeated_startup(self):
        production = "\n".join(function("src/layout/user_data.c", signature) for signature in (
            "bool user_data_save(void)",
            "bool user_data_save_sync(void)",
            "bool app_updata_check(void)",
            "bool user_data_init(void)",
        ))
        harness = r'''
#include <assert.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "user_data.h"
typedef int ak_pthread_t;
static user_data_info user_data;
static user_data_info user_data_default = {.app_versions = APP_VERSION_V};
static bool user_data_save_flag;
#define Debug(...) ((void)0)
#define ANYKA_THREAD_MIN_STACK_SIZE 0
static int fake_system(const char *command) {
    if (!strcmp(command, "sync")) return 0;
    assert(!strcmp(command, "rm -rf " USER_DATA_PATH));
    return unlink(USER_DATA_PATH);
}
#define system fake_system
user_data_info *user_data_get(void) { return &user_data; }
void monitor_device_init(door_info *a, door_info *b, camera_info *c, camera_info *d) {}
void ring_init(void) {}
void network_local_family_set(int id) {}
static void user_language_control(void) {}
static void *user_data_task(void *arg) { return NULL; }
static int ak_thread_create(ak_pthread_t *id, void *(*task)(void *), void *arg, int stack, int prio) {
    *id = 1; return 0; /* Keep device background threads outside the host test. */
}
'''
        checks = r'''
int main(int argc, char **argv) {
    assert(argc == 2);
    if (!strcmp(argv[1], "new-file")) {
        assert(user_data_init());
        assert(!user_data.tuya_info.lock_id && user_data_save_flag);
        return 0;
    }
    bool gate2 = !strcmp(argv[1], "gate2") || !strcmp(argv[1], "old-version");
    user_data = user_data_default;
    user_data.other.network_device = 3;
    user_data.other.family_id = 2;
    user_data.door1.unlock_delay = 4;
    user_data.tuya_info.lock_id = gate2;
    strcpy(user_data.tuya_info.tuya_uuid, "stale-test-uuid");
    strcpy(user_data.tuya_info.tuya_key, "stale-test-key");
    user_data.tuya_info.index = 7;
    user_data.tuya_info.used = true;
    if (!strcmp(argv[1], "old-version")) user_data.app_versions = APP_VERSION_V - 1;
    assert(user_data_save_sync());
    memset(&user_data, 0, sizeof(user_data));
    assert(user_data_init());
    if (!strcmp(argv[1], "old-version")) {
        assert(user_data.app_versions == APP_VERSION_V);
        assert(!user_data.tuya_info.lock_id && user_data_save_flag);
        return 0;
    }
    for (int boot = 0; boot < 2; boot++) {
        if (user_data.tuya_info.lock_id != gate2) {
            fprintf(stderr, "App lock selection lost: expected Gate%d after startup\n", gate2 ? 2 : 1);
            return 1;
        }
        assert(user_data.other.network_device == 3 && user_data.other.family_id == 2);
        assert(user_data.door1.unlock_delay == 4);
        assert(!user_data.tuya_info.tuya_uuid[0] && !user_data.tuya_info.tuya_key[0]);
        assert(!user_data.tuya_info.index && !user_data.tuya_info.used);
        assert(user_data_save_sync());
        memset(&user_data, 0, sizeof(user_data));
        assert(user_data_init());
    }
    assert(user_data.tuya_info.lock_id == gate2);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="gvs-user-data-test-") as directory:
            directory = Path(directory)
            source = directory / "user_data.c"
            binary = directory / "user_data"
            source.write_text(harness + production + checks)
            sdk = ROOT / "src/tuya-6.2.20"
            include_dirs = [ROOT / "src/layout", ROOT / "src/include/api",
                            ROOT / "src/api/network", ROOT / "src/tuya_batch_production_sdk/xls",
                            sdk, sdk / "include/base/include"]
            subprocess.run(["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-parameter", '-DUSER_FILE_PATH="./"',
                            *(f"-I{path}" for path in include_dirs), str(source), "-o", str(binary)],
                           check=True)
            for scenario in ("gate1", "gate2", "new-file", "old-version"):
                with self.subTest(scenario=scenario):
                    workdir = directory / scenario
                    workdir.mkdir()
                    subprocess.run([str(binary), scenario], cwd=workdir, check=True)


if __name__ == "__main__":
    unittest.main()
