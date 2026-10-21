#!/usr/bin/env python3
"""Exercise real outdoor protocol and public attachment reporting on the host."""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def function(path, signature):
    source = (ROOT / path).read_text()
    assert signature in source, f"Missing public OTA integration: {signature}"
    start = source.index(signature)
    end = source.index("\n}", start) + 2
    return source[start:end]


def main():
    network = "src/api/network/network_common.c"
    code = "\n".join((
        function(network, "int get_outdoor_model_version("),
        function(network, "static void outdoor_model_update("),
        function(network, "static void net_common_compile_time_func("),
        function("src/layout/layout_define.c", "void default_camera_status_callback("),
    ))
    preamble = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef int network_device;
enum { DEVICE_OUTDOOR_1 = 1, DEVICE_OUTDOOR_2 = 2, OLD_OUTDOOR_MODEL = 255 };
typedef struct { int model, ver, Compile_year, Compile_mon, Compile_day; } outdoor_info;
static struct { outdoor_info info[2]; } OutDoor_Info;
typedef struct { int send_device; unsigned char arg1, arg2; } net_common_pack_info;
struct ak_timeval { unsigned long sec; };
static int device_family_id;
static struct { unsigned long heart_time; } device_heart_info[1][3];
static void ak_get_ostime(struct ak_timeval *t) { t->sec = 42; }
static int status_events, reported_channel;
static char reported_version[32];
static bool dev_info_status_event_push(unsigned long a, unsigned long b) { ++status_events; return true; }
static int tuya_sub_version_report(int channel, const char *version) {
    reported_channel = channel;
    snprintf(reported_version, sizeof(reported_version), "%s", version ? version : "");
    return 0;
}
'''
    checks = r'''
static void set_version(int device, int version) {
    net_common_pack_info packet = { device, version & 255, version >> 8 };
    net_common_compile_time_func(packet);
}
int main(void) {
    int model = -1, version = -1;
    assert(get_outdoor_model_version(0, &model, &version) == -1);
    assert(get_outdoor_model_version(DEVICE_OUTDOOR_1, &model, &version) == -1);
    default_camera_status_callback(0, 0); assert(reported_channel == 0);
    outdoor_model_update(DEVICE_OUTDOOR_1, 0x20, 5);
    assert(get_outdoor_model_version(DEVICE_OUTDOOR_1, &model, &version) == 0);
    assert(model == OLD_OUTDOOR_MODEL && version == 205);
    /* Old devices still send packed compile dates rather than a new version. */
    net_common_pack_info date = { DEVICE_OUTDOOR_1, 617 & 255, (25 << 3) | (617 >> 8) };
    net_common_compile_time_func(date);
    assert(OutDoor_Info.info[0].ver == 205);
    assert(OutDoor_Info.info[0].Compile_year == 25 && OutDoor_Info.info[0].Compile_mon == 6 && OutDoor_Info.info[0].Compile_day == 17);
    default_camera_status_callback(0, 0); assert(reported_channel == 0);
    outdoor_model_update(DEVICE_OUTDOOR_1, 0, 9);
    assert(get_outdoor_model_version(DEVICE_OUTDOOR_1, &model, &version) == -1);
    set_version(DEVICE_OUTDOOR_1, 12345);
    default_camera_status_callback(0, 0);
    assert(reported_channel == 1 && !strcmp(reported_version, "1.23.45"));
    outdoor_model_update(DEVICE_OUTDOOR_2, 0, 9);
    set_version(DEVICE_OUTDOOR_2, 10203);
    default_camera_status_callback(0, 0);
    assert(reported_channel == 2 && !strcmp(reported_version, "1.2.3"));
    outdoor_model_update(DEVICE_OUTDOOR_2, 0, 10);
    set_version(DEVICE_OUTDOOR_2, 10203);
    default_camera_status_callback(0, 0); assert(reported_channel == 0);
    outdoor_model_update(DEVICE_OUTDOOR_2, 0x20, 1);
    default_camera_status_callback(0, 0); assert(reported_channel == 0);
    memset(&OutDoor_Info.info[0], 0, sizeof(OutDoor_Info.info[0]));
    outdoor_model_update(DEVICE_OUTDOOR_2, 0, 9);
    set_version(DEVICE_OUTDOOR_2, 10102);
    default_camera_status_callback(0, 0);
    assert(reported_channel == 2 && !strcmp(reported_version, "1.1.2"));
    assert(status_events > 0 && device_heart_info[0][2].heart_time == 42);
    puts("PASS: old/new outdoor protocol, model changes and public attachment selection");
}
'''
    with tempfile.TemporaryDirectory(prefix="gvs-public-ota-") as directory:
        source = Path(directory) / "protocol.c"
        binary = Path(directory) / "protocol"
        source.write_text(preamble + code + checks)
        command = ["cc", "-std=c99", "-Wall", "-Wextra", "-Wno-unused-parameter", "-Werror"]
        if os.environ.get("GVS_TEST_ASAN") == "1":
            command += ["-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        subprocess.run(command + [str(source), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
