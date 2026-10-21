#!/usr/bin/env python3
"""Exercise the production channel helpers with deterministic device/language inputs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

def function(source, signature):
    text = (ROOT / source).read_text()
    if signature not in text:
        raise AssertionError(f"Missing migrated application helper: {signature}")
    start = text.index(signature)
    pos = text.index('{', start)
    level = 1
    end = pos + 1
    while level:
        level += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

class ChannelTests(unittest.TestCase):
    def test_device_validity_and_localized_channel_reports(self):
        bodies = '\n'.join([
            function('src/api/common/leo_monitor.c', 'bool monitor_valid_channel_check(char channel)'),
            function('src/layout/layout_define.c', 'static int tuya_channel_info_collect('),
            function('src/layout/layout_define.c', 'void tuya_channel_valid_report(void)'),
            function('src/layout/layout_define.c', 'int tuya_switch_channel_upload_results(int channel)'),
        ])
        harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
enum { MON_CH_NONE, MON_CH_DOOR_1, MON_CH_DOOR_2, MON_CH_CCTV_1, MON_CH_CCTV_2, MON_CH_TOTAL };
enum { DEVICE_OUTDOOR_1 = 7, DEVICE_OUTDOOR_2, DEVICE_CCTV_1, DEVICE_CCTV_2 };
enum { STR_TUYA_CURR_DOOR1 = 20 };
typedef struct { int ch; const char *name; } tuya_ch_info_t;
static bool online[11], enabled[11];
static int current, report_count, response_count, received_ch, received_total;
static tuya_ch_info_t received[MON_CH_TOTAL];
static const char *names[] = {"Current door 1", "Door 1", "Current door 2", "Door 2", "Current CCTV 1", "CCTV 1", "Current CCTV 2", "CCTV 2"};
static bool device_online_state_get(int device) { assert(device >= 7 && device <= 10); return online[device]; }
static bool device_enable_state_get(int device) { assert(device >= 7 && device <= 10); return enabled[device]; }
static int monitor_channel_get(void) { return current; }
static const char *text_str(int id) { assert(id >= 20 && id < 28); return names[id - 20]; }
static int capture(int ch, tuya_ch_info_t *info, int total) {
    received_ch = ch; received_total = total;
    memcpy(received, info, total * sizeof(*info)); return 7;
}
static int tuya_channel_report(int ch, tuya_ch_info_t *info, int total) { report_count++; return capture(ch, info, total); }
static int tuya_channel_response(int ch, tuya_ch_info_t *info, int total) { response_count++; return capture(ch, info, total); }
'''
        checks = r'''
int main(void) {
    for (int channel = 1; channel <= 4; channel++) {
        const int dev = channel + 6;
        for (int state = 0; state < 4; state++) {
            online[dev] = state & 1; enabled[dev] = state & 2;
            assert(monitor_valid_channel_check(channel) == (state == 3));
        }
    }
    assert(!monitor_valid_channel_check(-1));
    assert(!monitor_valid_channel_check(MON_CH_NONE));
    assert(!monitor_valid_channel_check(MON_CH_TOTAL));
    assert(!monitor_valid_channel_check(100));
    memset(online, 0, sizeof(online));
    current = MON_CH_NONE;
    tuya_channel_valid_report();
    assert(report_count == 1 && response_count == 0 && received_total == 0);
    online[DEVICE_OUTDOOR_2] = true; online[DEVICE_CCTV_2] = true;
    current = MON_CH_CCTV_2;
    tuya_channel_valid_report();
    assert(report_count == 2 && received_total == 2 && received_ch == MON_CH_CCTV_2);
    assert(received[0].ch == MON_CH_DOOR_2 && !strcmp(received[0].name, "Door 2"));
    assert(received[1].ch == MON_CH_CCTV_2 && !strcmp(received[1].name, "Current CCTV 2"));
    assert(tuya_switch_channel_upload_results(MON_CH_CCTV_2) == 7);
    assert(response_count == 1 && report_count == 2 && received_ch == MON_CH_CCTV_2);
    current = MON_CH_DOOR_2;
    tuya_channel_valid_report();
    assert(!strcmp(received[0].name, "Current door 2"));
    assert(!strcmp(received[1].name, "CCTV 2"));
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='gvs-channel-test-') as tmp:
            source = Path(tmp) / 'channels.c'
            binary = Path(tmp) / 'channels'
            source.write_text(harness + bodies + checks)
            subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

class UpgradeSourceTests(unittest.TestCase):
    def test_cloud_upgrade_cannot_be_overwritten_by_sd_image(self):
        bodies = '\n'.join([
            function('src/api/network/network_outdoor_upgrade.c', 'void network_upgrade_source_set(bool ota)'),
            function('src/api/network/network_outdoor_upgrade.c', 'const char *network_upgrade_source_get(void)'),
        ])
        source = r'''#include <assert.h>
#include <stdbool.h>
#include <string.h>
static bool network_upgrade_from_ota = false;
#define UPGRADE_FILE_PATH "/mnt/tf/cbin.update"
''' + bodies + r'''
int main(void) {
    assert(!strcmp(network_upgrade_source_get(), "/mnt/tf/cbin.update"));
    network_upgrade_source_set(true);
    assert(!strcmp(network_upgrade_source_get(), "/tmp/cbin.update"));
    network_upgrade_source_set(false);
    assert(!strcmp(network_upgrade_source_get(), "/mnt/tf/cbin.update"));
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='gvs-upgrade-source-test-') as tmp:
            test = Path(tmp) / 'source.c'
            binary = Path(tmp) / 'source'
            test.write_text(source)
            subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', str(test), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

class PairingQrTests(unittest.TestCase):
    def test_unbound_device_displays_qr_before_media_is_ready(self):
        body = function('src/layout/layout_setting_wifi.c', 'static void tuya_qrcode_display(void)')
        source = r'''#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
typedef int rom_bin_info;
static void *qr;
static const char *shorturl;
static int created, updates;
static bool ready;
enum { MODULE_ID_APP, LV_COLOR_SIZE = 32 };
static bool tuya_sdk_is_ready(void) { return ready; }
static const char *tuya_qrcode_shorturl_get(void) { return shorturl; }
static rom_bin_info rom_bin_raw_get(void) { return 0; }
static void rom_bin_raw_init(rom_bin_info image, unsigned char *data, int w, int h) { (void)image;(void)data;assert(w == 300 && h == 300); }
static unsigned char *ak_mem_alloc(int module, size_t size) { (void)module;(void)size;return (unsigned char *)"buffer"; }
static void *lv_scr_act(void) { return NULL; }
static int lv_color_hex(int value) { return value; }
static void *lv_qrcode_create(void *parent, rom_bin_info *image, int size, int dark, int light) { (void)parent;(void)image;(void)size;(void)dark;(void)light;created++;return &created; }
static void lv_obj_set_id(void *object, int id) { assert(object);(void)id; }
static void lv_obj_set_pos(void *object, int x, int y) { assert(object);(void)x;(void)y; }
static void lv_obj_set_size(void *object, int w, int h) { assert(object);(void)w;(void)h; }
static void lv_obj_set_hidden(void *object, bool hidden) { assert(object);(void)hidden; }
static void lv_qrcode_update(void *object, const void *value, size_t size) { assert(object && value == shorturl && size == strlen(shorturl));updates++; }
''' + body + r'''
int main(void) {
    assert(!tuya_sdk_is_ready());
    shorturl = "https://example.test/pair";
    tuya_qrcode_display();
    assert(created == 1 && updates == 1 && qr != NULL);
    tuya_qrcode_display();
    assert(created == 1 && updates == 1);
    qr = NULL;
    shorturl = NULL;
    tuya_qrcode_display();
    assert(created == 1);
    shorturl = "";
    tuya_qrcode_display();
    assert(created == 1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='gvs-qr-test-') as tmp:
            test = Path(tmp) / 'qr.c'
            binary = Path(tmp) / 'qr'
            test.write_text(source)
            subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', str(test), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

class StartupConfigTests(unittest.TestCase):
    def test_preserves_full_width_credentials_and_wired_storage_configuration(self):
        body = function('src/layout/layout_define.c', 'int tuya_application_start(void)')
        source = r'''#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef struct { char pid[24], uuid[36], key[36], ver[16], net_dev[8], cache_dir[64], sd_dir[64]; } tuya_init_config_t;
static struct { struct { char tuya_uuid[25], tuya_key[32]; } tuya_info; int pairing_mode; } user;
#define user_data_get() (&user)
#define IPC_APP_PID "existing-gvs-pid"
#define IPC_APP_VERSION "1.2.3"
#define TUYA_CACHE_PATH "/app/data/tuya_cache/"
#define TUYA_KEY_PATH "/app/data/tuya_key/"
#define SD_BASE_PATH2 "/mnt/tf2/"
#define WIRED_DEV "eth2"
#define WLAN_DEV "wlan0"
enum { WLAN_NET, WIRED_NET };
static int called, mkdir_failure;
static tuya_init_config_t captured;
static int mkdir(const char *path, unsigned int mode) {
    assert(!strcmp(path, TUYA_CACHE_PATH) || !strcmp(path, TUYA_KEY_PATH));
    assert(mode == 0777);
    errno = mkdir_failure;
    return mkdir_failure ? -1 : 0;
}
static int tuya_sdk_init(const tuya_init_config_t *config) { captured = *config; called++;return 12; }
''' + body + r'''
int main(void) {
    memset(user.tuya_info.tuya_uuid, 'u', 25);
    memset(user.tuya_info.tuya_key, 'k', 32);
    user.pairing_mode = WIRED_NET;
    assert(tuya_application_start() == 12 && called == 1);
    assert(!memcmp(captured.uuid, user.tuya_info.tuya_uuid, 25) && captured.uuid[25] == 0);
    assert(!memcmp(captured.key, user.tuya_info.tuya_key, 32) && captured.key[32] == 0);
    assert(!strcmp(captured.net_dev, WIRED_DEV));
    assert(!strcmp(captured.cache_dir, TUYA_CACHE_PATH));
    assert(!strcmp(captured.sd_dir, SD_BASE_PATH2));
    assert(!strcmp(captured.pid, IPC_APP_PID) && !strcmp(captured.ver, IPC_APP_VERSION));
    user.pairing_mode = WLAN_NET;
    mkdir_failure = EEXIST;
    assert(tuya_application_start() == 12 && called == 2);
    assert(!strcmp(captured.net_dev, WLAN_DEV));
    mkdir_failure = EACCES;
    assert(tuya_application_start() == -1 && called == 2);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='gvs-startup-test-') as tmp:
            test = Path(tmp) / 'startup.c'
            binary = Path(tmp) / 'startup'
            test.write_text(source)
            subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', str(test), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

if __name__ == '__main__':
    unittest.main()
