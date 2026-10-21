#!/usr/bin/env python3
"""Run updater decision logic with fake flash commands; never access a device."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(os.environ.get("GVS_TEST_UPDATER", ROOT / "upgrade/scripts/update.sh")).read_text()
start = SCRIPT.index("dd_update()")
FLASH = SCRIPT[start:SCRIPT.index("\n}", start) + 2]
TAIL = SCRIPT[SCRIPT.index('if [ "$DD_UPDATE" = 1 ]'):]


class UpdaterTests(unittest.TestCase):
    def test_flash_errors_never_report_success(self):
        fixture = r'''
CMD_CAT=fake_cat; CMD_GREP=grep; CMD_STAT=fake_stat; CMD_AWK=awk
CMD_ECHO=echo; CMD_BC=fake_bc; CMD_EXPR=expr
CMD_MTD_DEBUG=fake_erase; CMD_DD=fake_dd; CMD_SYNC=fake_sync
DD_UPDATE=0; UPDATE_FAILED=0; ERASED=0; WRITTEN=0
fake_cat() { [ "$CASE" = missing ] || echo 'mtd3: 00100000 00001000 "APP"'; }
fake_stat() { if [ "$CASE" = oversize ]; then echo 'Size: 2097152'; else echo 'Size: 1024'; fi; }
fake_bc() { read -r input; printf '%d\n' "0x${input##*;}"; }
check_file_md5() { [ "$CASE" = md5 ]; }
fake_erase() { ERASED=1; [ "$CASE" != erase ]; }
fake_dd() { WRITTEN=1; [ "$CASE" != write ]; }
fake_sync() { [ "$CASE" != sync ]; }
'''
        with tempfile.TemporaryDirectory(prefix="gvs-updater-") as directory:
            (Path(directory) / "app.sqsh4").write_bytes(b"image")
            for case in ("success", "missing", "md5", "oversize", "erase", "write", "sync"):
                with self.subTest(case=case):
                    env = dict(os.environ, CASE=case, DIR_UPDATE=directory, LC_ALL="C")
                    code = fixture + FLASH + '\ndd_update app.sqsh4 APP\nret=$?\nprintf "RESULT:%s:%s:%s:%s:%s\\n" "$ret" "$DD_UPDATE" "$UPDATE_FAILED" "$ERASED" "$WRITTEN"\n'
                    result = subprocess.run(["bash", "-c", code], env=env, capture_output=True, text=True, check=True)
                    state = result.stdout.strip().splitlines()[-1].split(":")[1:]
                    if case == "success":
                        self.assertEqual(state, ["0", "1", "0", "1", "1"])
                    else:
                        self.assertEqual(state[:3], ["1", "0", "1"], result.stdout)
                        if case in ("missing", "md5", "oversize", "erase", "sync"):
                            self.assertEqual(state[4], "0")

    def test_package_marker_requires_successful_flash(self):
        fixture = r'''
CMD_ECHO=echo; CMD_SYNC=:; CMD_SLEEP=:; CMD_REBOOT=finish
TOUCHED=0
mount() { echo '/dev/test on /app/data'; }
rm() { :; }
touch() { [ "$1" = /app/data/SAT_ANYKAOS_777 ] || exit 77; TOUCHED=1; }
finish() { printf 'MARKER:%s\n' "$TOUCHED"; }
update_failed_reboot() { printf 'MARKER:%s\n' "$TOUCHED"; exit 1; }
set -- SAT_ANYKAOS_777
'''
        for written, failed in ((0, 0), (1, 1), (1, 0)):
            with self.subTest(written=written, failed=failed):
                result = subprocess.run(["bash", "-c", fixture + TAIL],
                                        env=dict(os.environ, DD_UPDATE=str(written), UPDATE_FAILED=str(failed)),
                                        capture_output=True, text=True)
                success = written == 1 and failed == 0
                self.assertEqual(result.returncode, 0 if success else 1)
                self.assertIn(f"MARKER:{int(success)}", result.stdout)


if __name__ == "__main__":
    unittest.main()
