#!/usr/bin/env python3
"""Exercise real GVS Tuya6 audio/OTA callbacks without the ARM vendor library."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

TESTS = Path(__file__).resolve().parent
SDK = TESTS.parents[1] / "src/tuya-6.2.20"

def run_test(name):
    with tempfile.TemporaryDirectory(prefix="gvs-tuya6-safety-") as directory:
        work = Path(directory)
        body = (TESTS / (name + ".c.in")).read_text()
        if "/* SDK_AUDIO_RECEIVE */" in body:
            source = (SDK / "app/app_main/src/ty_sdk_media_callback.c").read_text()
            start = source.index("VOID TUYA_IPC_APP_rev_audio_cb(")
            end = source.index("VOID TUYA_IPC_APP_rev_video_cb(", start)
            body = body.replace("/* SDK_AUDIO_RECEIVE */", source[start:end])
        preamble = '#include "ty_sdk_common.h"\n#include "utilities/uni_log.h"\n#undef PR_ERR\n#define PR_ERR(...) ((void)0)\n'
        (work / "test.c").write_text(preamble + body)
        includes = sorted({SDK, *(path.parent for path in SDK.rglob("*.h"))})
        command = ["cc", "-std=gnu11", "-w", "-ffunction-sections", "-fdata-sections", "-pthread"]
        if os.environ.get("GVS_TEST_ASAN") == "1":
            command += ["-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-sanitize-recover=all"]
        command += [f"-I{path}" for path in includes]
        command += [str(work / "test.c"), "-Wl,--gc-sections", "-o", str(work / "test")]
        subprocess.run(command, check=True)
        subprocess.run([str(work / "test")], check=True)

if __name__ == "__main__":
    failed = False
    for name in sys.argv[1:] or ["audio_receive", "ota_guard"]:
        try:
            run_test(name)
        except subprocess.CalledProcessError:
            failed = True
    raise SystemExit(1 if failed else 0)
