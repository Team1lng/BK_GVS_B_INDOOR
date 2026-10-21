#!/usr/bin/env python3
"""Compile production Wi-Fi functions; replace only device/process/UI boundaries."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import re

ROOT = Path(__file__).resolve().parents[2]


def body(path, signature):
    source = (ROOT / path).read_text()
    if signature not in source:
        raise AssertionError('Missing public Wi-Fi behavior: ' + signature)
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 0
    # Count code braces, ignoring configuration strings, char literals and comments.
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', source[brace:], re.S):
        if token[0] == '{':
            depth += 1
        elif token[0] == '}':
            depth -= 1
            if depth == 0:
                return source[start:brace + token.end()]
    raise AssertionError('Unterminated function: ' + signature)


def run_c(source, arguments=()):
    with tempfile.TemporaryDirectory(prefix='gvs-public-wifi-') as tmp:
        tmp = Path(tmp)
        source = source.replace('"/tmp/wpa_supplicant.conf"', '"' + str(tmp / 'candidate.conf') + '"')
        file = tmp / 'test.c'
        binary = tmp / 'test'
        file.write_text(source)
        subprocess.run(['cc', '-std=gnu99', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-pthread', str(file), '-o', str(binary)], check=True)
        subprocess.run([str(binary), *arguments], cwd=tmp, check=True)


class WifiTests(unittest.TestCase):
    def test_rejected_start_is_reported_immediately_on_every_wifi_page(self):
        for page, signature in (
            ('add_wifi', 'static void wpa_cli_connect_task('),
            ('connect_wifi', 'else if (ext->btnm.pattern_p[btn_id]->offset == ROM_RES_KB_APPLY_PNG)'),
            ('setting_wifi', 'static void wifibtn_up('),
        ):
            with self.subTest(page=page):
                production = body('src/layout/layout_' + page + '.c', signature)
                if page == 'connect_wifi':
                    production = 'static void attempt(void) { lv_keyboard_ext_t *ext = &keyboard; int btn_id = 0; if (false) {} ' + production + ' }'
                    invocation = 'attempt();'
                elif page == 'add_wifi':
                    invocation = 'wpa_cli_connect_task(&task);'
                else:
                    invocation = 'wifibtn_up(&button);'
                harness = (Path(__file__).parent / 'start_rejected.c.in').read_text()
                run_c(harness.replace('@PRODUCTION@', production).replace('@INVOKE@', invocation))

    def test_health_recovers_once_and_rearms_after_success(self):
        path = ROOT / 'src/api/network/ping_host.c'
        self.assertTrue(path.exists(), 'Public Wi-Fi health monitoring must be included')
        production = body('src/api/network/ping_host.c', 'int Wlan0HealthCheck(')
        run_c(r'''
#include <assert.h>
#include <stdio.h>
#include <time.h>
static int now = 1, device_error, association = 1, ping_error = 1, recoveries;
static unsigned long long DiffClockTimeMs(struct timespec *previous) { return now - previous->tv_sec; }
static void GetClockTimeMs(struct timespec *value) { value->tv_sec = now; }
static int Wlan0DeviceCheak(void) { return device_error; }
static int Wlan0WapStateCheck(void) { return association; }
static int PingGateway(const char *interface) { return ping_error; }
static void recover(void *arg) { recoveries++; }
''' + production + r'''
static int tick(void) { now += 2001; return Wlan0HealthCheck(2000, 5, recover); }
int main(void) {
    assert(Wlan0HealthCheck(2000, 5, recover) == 0);
    for (int i = 0; i < 4; i++) assert(tick() == -1 && !recoveries);
    assert(tick() == -1 && recoveries == 1);
    for (int i = 0; i < 8; i++) assert(tick() == -1 && recoveries == 1);
    ping_error = 0; assert(tick() == 1);
    ping_error = 1;
    for (int i = 0; i < 5; i++) assert(tick() == -1);
    assert(recoveries == 2);
    association = 0; assert(tick() == 2 && recoveries == 2);
    association = -1; assert(tick() == -1 && recoveries == 2);
    device_error = -1; assert(tick() == -1);
    return 0;
}
''')

    def test_gateway_and_status_handle_missing_or_long_output(self):
        path = ROOT / 'src/api/network/ping_host.c'
        self.assertTrue(path.exists(), 'Public Wi-Fi health monitoring must be included')
        production = '\n'.join(body('src/api/network/ping_host.c', sig) for sig in (
            'int Wlan0WapStateCheck(void)', 'int GetDefaultGateway(', 'int PingGateway('))
        run_c(r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <arpa/inet.h>
static const char *output;
static int opens, closes, pings;
static FILE *fake_popen(const char *cmd, const char *mode) { FILE *fp = tmpfile(); assert(fp); opens++; fputs(output, fp); rewind(fp); return fp; }
static int fake_pclose(FILE *fp) { closes++; return fclose(fp); }
static int fake_system(const char *cmd) { assert(strstr(cmd, "192.168.1.1")); pings++; return 0; }
#define popen fake_popen
#define pclose fake_pclose
#define system fake_system
''' + production + r'''
int main(void) {
    output = ""; assert(Wlan0WapStateCheck() == -1 && opens == closes);
    output = "COMPLETED\n"; assert(Wlan0WapStateCheck() == 1);
    output = "DISCONNECTED\n"; assert(Wlan0WapStateCheck() == 0);
    output = ""; assert(PingGateway("wlan0") != 0 && !pings);
    output = "invalid-invalid-invalid-invalid-invalid-invalid-invalid-invalid\n";
    assert(PingGateway("wlan0") != 0 && !pings);
    output = "192.168.1.1\n"; assert(PingGateway("wlan0") == 0 && pings == 1 && opens == closes);
    return 0;
}
''')

    def test_worker_success_failure_cancel_and_owned_credentials(self):
        source = (ROOT / 'src/api/wlan/wlan.c').read_text()
        self.assertTrue('bool wifi_connection_check_start(void)' in source,
                      'Wi-Fi must expose the public asynchronous connection API')
        start = source.index('/* A connection attempt')
        end = source.index('int current_wlan_signal_level', start)
        production = source[start:end]
        harness = (Path(__file__).parent / 'worker.c.in').read_text()
        run_c(harness.replace('@PRODUCTION@', production))

    def test_ui_accepts_late_success_and_has_a_bounded_timeout(self):
        for page in ('add_wifi', 'connect_wifi', 'setting_wifi'):
            with self.subTest(page=page):
                callback = body('src/layout/layout_' + page + '.c', 'static void msg_task(')
                harness = '#define EXPECT_FAILURE_DELETE ' + str(int(page != 'add_wifi')) + '\n' + (Path(__file__).parent / 'ui.c.in').read_text()
                # All three callbacks share one elapsed-tick counter after migration.
                run_c(harness.replace('@PRODUCTION@', callback))

    def test_disconnect_clears_saved_networks_and_link(self):
        path = 'src/api/wlan/wlan.c'
        production = '\n'.join(body(path, sig) for sig in (
            'static const char *wlan_config_value(',
            'static bool wlan_config_line_end(',
            'static bool wlan_config_network_end(',
            'static bool wlan_config_all_networks_disabled(',
            'static bool disable_wlan_networks_in_config(void)',
            'static void disable_wlan_networks_and_save(void)',
            'void clear_linked_wifi_info(void)', 'void turn_off_wlan_break(void)'))
        run_c((Path(__file__).parent / 'disconnect.c.in').read_text().replace('@PRODUCTION@', production))

    def test_synchronous_save_persists_disconnect_before_return(self):
        production = body('src/layout/user_data.c', 'bool user_data_save_sync(void)')
        run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
typedef struct { int wifi_connected; char untouched[11]; } user_data_info;
static user_data_info user_data = {0, "unchanged"};
static bool user_data_save_flag = true;
#define USER_DATA_PATH "user.cfg"
#define Debug(...) ((void)0)
static int fake_system(const char *cmd) { (void)cmd; return 0; }
#define system fake_system
''' + production + r'''
int main(void) {
    assert(user_data_save_sync());
    assert(!user_data_save_flag);
    int fd = open(USER_DATA_PATH, O_RDONLY);
    user_data_info saved;
    assert(fd >= 0 && read(fd, &saved, sizeof(saved)) == sizeof(saved));
    assert(saved.wifi_connected == 0 && saved.untouched[0] == 'u');
    close(fd);
    return 0;
}
''')


if __name__ == '__main__':
    unittest.main()
