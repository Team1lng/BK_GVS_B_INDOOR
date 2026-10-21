#!/usr/bin/env python3
"""Check the built GVS product uses Tuya6 and retains its GVS resource inputs."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parents[1] / "bk_public_indoor"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sdk = ROOT / "src/tuya-6.2.20"
    assert (sdk / "libs/libtuyaos.a").is_file(), "Tuya6 SDK library is missing"
    assert digest(sdk / "libs/libtuyaos.a") == digest(PUBLIC / "src/tuya-6.2.20/libs/libtuyaos.a")
    for old in ("src/include/tuya", "src/lib/tuya", "src/api/wlan/tuya_sdk.c",
                "src/api/wlan/tuya_api_func.c", "src/api/wlan/tuya_stream_storage.c",
                "src/api/wlan/tuya_stream_storage.h"):
        assert not (ROOT / old).exists(), f"Legacy Tuya4 remains: {old}"
    config = (ROOT / "CMakeLists.txt").read_text()
    for expected in ('-DGVS_VERSION', '-DGVS_BALCK', '285v8xpvxwdm8a0p', '2.1.0'):
        assert expected in config, f"GVS product configuration lost: {expected}"
    build = ROOT / "build-tuya6"
    commands = json.loads((build / "compile_commands.json").read_text())
    assert any('/tuya-6.2.20/tuya_sdk.c' in row['file'] for row in commands)
    for row in commands:
        for old in ('/include/tuya ', '/wlan/tuya_sdk.c', '/wlan/tuya_api_func.c', '/wlan/tuya_stream_storage.c'):
            assert old not in row['command'], f"Legacy Tuya4 compilation: {old}"
    link = (build / "src/CMakeFiles/ANYKA37E.BIN.dir/link.txt").read_text()
    assert 'libtuyaos.a' in link
    assert 'libtuya_ipc.a' not in link and 'libmbedtls.a' not in link
    assert (build / "src/ANYKA37E.BIN").stat().st_size > 0
    assert digest(build / "src/rom.bin") == digest(ROOT / "src/layout/resource/res_black_gvs/rom.bin")
    assert digest(build / "src/layout/resource/rom.h") == digest(ROOT / "src/layout/resource/res_black_gvs/rom.h")
    print(f"PASS: {len(commands)} compile commands, Tuya6 link, GVS product and black resources")


if __name__ == "__main__":
    main()
