#!/usr/bin/env python3
"""Compile the actual SDK callbacks on the host, without the ARM vendor library."""
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile

SDK = Path(__file__).resolve().parents[1]
DP_HEADER = SDK / "app/app_main/include/ty_dp_define.h"
LOCK_DPS = {"TUYA_DP_DOOR_LOCK1", "TUYA_DP_DOOR_LOCK2", "TUYA_DP_DOOR_LOCK", "TUYA_DP_LOCK_SUPPORT"}
PRODUCT_DPS = LOCK_DPS | {"TUYA_DP_BLUB_SWITCH", "TUYA_DP_WORK_MODE", "TUYA_DP_SWITCH_CHANNEL", "TUYA_DP_DEVICE_SCREENSHOT", "TUYA_DP_DEVICE_ACTIVE"}


def run_test(name):
    with tempfile.TemporaryDirectory(prefix="gvs-tuya-host-") as temp:
        source = Path(temp) / "test.c"
        preamble = '#include "ty_dp_define.h"\n'
        # Exclude unrelated sample DPs, retaining the real dispatch and query code.
        enabled_dps = {"TUYA_DP_REBOOT_SYSTEM"} if name == "reboot" else PRODUCT_DPS
        for macro, value in re.findall(r"^#define\s+(TUYA_(?:RAW_)?DP_\w+)\s+(\d+)", DP_HEADER.read_text(), re.M):
            if macro not in enabled_dps:
                preamble += f"#undef {macro}\nenum {{ {macro} = {value} }};\n"
        preamble += '#include "utilities/uni_log.h"\n#undef PR_ERR\n#define PR_ERR(...) ((void)0)\n'
        body = (SDK / "tests" / (name + ".c.in")).read_text()
        if "/* SDK_AUDIO_RECEIVE */" in body:
            media_source = (SDK / "app/app_main/src/ty_sdk_media_callback.c").read_text()
            start = media_source.index("VOID TUYA_IPC_APP_rev_audio_cb(")
            end = media_source.index("VOID TUYA_IPC_APP_rev_video_cb(", start)
            body = body.replace("/* SDK_AUDIO_RECEIVE */", media_source[start:end])
        if "/* SDK_STATUS_CALLBACK */" in body:
            status_source = (SDK / "app/app_main/src/ty_sdk_status_callback.c").read_text()
            body = body.replace("/* SDK_STATUS_CALLBACK */", status_source)
        if "/* SDK_UPGRADE_UI */" in body:
            ui_source = (SDK.parent / "layout/layout_setting_senior.c").read_text()
            start = ui_source.index("void upgrade_outdoor_func(unsigned long arg1, unsigned long arg2)\n{")
            end = ui_source.index("static void senior_ota_timeout_check(lv_task_t *task)\n{", start)
            body = body.replace("/* SDK_UPGRADE_UI */", ui_source[start:end])
        if "/* SDK_MAIN */" in body:
            main_source = (SDK / "app/app_main/src/ty_sdk_main.c").read_text()
            body = body.replace("/* SDK_MAIN */", main_source[main_source.index("int ty_sdk_main("):])
        if "/* SDK_RING_CLEAR */" in body:
            sdk_source = (SDK / "tuya_sdk.c").read_text()
            start = sdk_source.index("void tuya_ring_buffer_clear(void)")
            end = sdk_source.index("int tuya_notify_call_event(", start)
            body = body.replace("/* SDK_RING_CLEAR */", sdk_source[start:end])
        if "/* SDK_TIME_SYNC */" in body:
            sdk_source = (SDK / "tuya_sdk.c").read_text()
            start = sdk_source.index("bool tuya_net_time_sync(struct tm *new_tm)")
            end = sdk_source.index("void tuya_device_unbinding(void)", start)
            body = body.replace("/* SDK_TIME_SYNC */", sdk_source[start:end])
        if "/* SDK_STARTUP */" in body:
            sdk_source = (SDK / "tuya_sdk.c").read_text()
            start = sdk_source.index("typedef struct\n{\n    tuya_init_config_t cfg;")
            end = sdk_source.index("static char tuya_network_online_check", start)
            body = body.replace("/* SDK_CONTEXT */", sdk_source[start:end])
            start = sdk_source.index("static void *tuya_sdk_thread(void *arg)")
            body = body.replace("/* SDK_STARTUP */", sdk_source[start:])
        source.write_text(preamble + body)
        include_dirs = sorted({SDK, *(p.parent for p in SDK.rglob("*.h"))})
        command = ["cc", "-std=gnu11", "-w", "-ffunction-sections", "-fdata-sections"]
        if os.environ.get("GVS_TEST_ASAN") == "1":
            command += ["-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-sanitize-recover=all"]
        command += [f"-I{p}" for p in include_dirs]
        command += [str(source), "-Wl,--gc-sections", "-o", str(Path(temp) / "test")]
        result = subprocess.run(command)
        if result.returncode:
            raise SystemExit(result.returncode)
        subprocess.run([str(Path(temp) / "test")], check=True)


if __name__ == "__main__":
    for test in sys.argv[1:] or ["lock_dp", "ring_clear", "time_sync", "reboot", "startup", "storage_init"]:
        run_test(test)
