#!/usr/bin/env python3
"""Exercise package replacement and failure handling in an isolated project."""
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="gvs-build-test-")
        self.addCleanup(self.directory.cleanup)
        self.project = Path(self.directory.name) / "project with spaces"
        self.project.mkdir()
        shutil.copy2(ROOT / "build.sh", self.project / "build.sh")
        for name in ("upgrade/app", "upgrade/platform", "upgrade/ring/normal/rings",
                     "upgrade/language/bcom/gvs", "upgrade/scripts", "upgrade/tools",
                     "upgrade/upgrade_progress"):
            (self.project / name).mkdir(parents=True)
        for name in ("upgrade/app/settings.ini", "upgrade/platform/uImage",
                     "upgrade/ring/normal/rings/ring.wav",
                     "upgrade/language/bcom/gvs/language.xls",
                     "upgrade/scripts/update.sh", "upgrade/upgrade_progress/upgrade_progress"):
            (self.project / name).write_text(name)
        self.commands = Path(self.directory.name) / "commands"
        self.commands.mkdir()
        self.write_command(self.commands / "cmake", '''
if [[ $1 == --build ]]; then
    [[ ${TEST_FAILURE:-} != cmake ]] || exit 23
    mkdir -p "$2/src"
    printf '%s' "${TEST_FIRMWARE:-firmware}" > "$2/src/ANYKA37E.BIN"
    printf 'rom' > "$2/src/rom.bin"
fi
''')
        self.write_command(self.commands / "date", '''
case "$1" in
    +%m%d%H%M) printf '%s\\n' "${TEST_TIMESTAMP:0:8}" ;;
    +%m%d%H%M%S) printf '%s\\n' "$TEST_TIMESTAMP" ;;
    *) exit 26 ;;
esac
''')
        self.write_command(self.project / "upgrade/tools/mksquashfs", '''
cat "$1/ANYKA37E.BIN" > "$2"
[[ ${TEST_FAILURE:-} != squashfs ]] || exit 24
''')
        for name in ("tar", "mv"):
            real = shutil.which(name)
            self.write_command(self.commands / name, f'''
if [[ ${{TEST_FAILURE:-}} == {name} ]]; then
    if [[ {name} == tar || ${{@: -1}} == "$TEST_PROJECT"/SAT_ANYKAOS_* ]]; then
        exit 25
    fi
fi
exec "{real}" "$@"
''')
        self.env = dict(os.environ, PATH=str(self.commands) + os.pathsep + os.environ["PATH"],
                        TEST_PROJECT=str(self.project), TEST_TIMESTAMP="1021130000",
                        TEST_FAILURE="", TEST_FIRMWARE="first firmware")

    @staticmethod
    def write_command(path, body):
        path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body)
        path.chmod(0o755)

    def run_build(self, *args):
        return subprocess.run(["bash", str(self.project / "build.sh"), *args],
                              cwd=self.directory.name, env=self.env,
                              capture_output=True, text=True)

    def assert_no_temporary_packages(self):
        self.assertEqual(list((self.project / "build-tuya6").glob("package.*")), [])
        self.assertEqual(list((self.project / "build-tuya6").glob("SAT_ANYKAOS_*.tmp")), [])

    def test_success_replaces_old_packages_on_repeated_builds(self):
        old = self.project / "SAT_ANYKAOS_1019112259"
        old.write_bytes(b"old package")
        old_minute = self.project / "SAT_ANYKAOS_10191122"
        old_minute.write_bytes(b"old minute package")
        note = self.project / "SAT_ANYKAOS_notes"
        note.write_bytes(b"keep note")
        odd_names = ("SAT_ANYKAOS_101911225", "SAT_ANYKAOS_10191122599")
        for name in odd_names:
            (self.project / name).write_bytes(b"keep unrelated file")
        folder = self.project / "SAT_ANYKAOS_1017115146"
        folder.mkdir()
        link = self.project / "SAT_ANYKAOS_1017112124"
        link.symlink_to(note.name)
        for iteration, timestamp in enumerate(("1021130000", "1021130100", "1021130152")):
            firmware = "firmware " + str(iteration)
            self.env.update(TEST_TIMESTAMP=timestamp, TEST_FIRMWARE=firmware)
            result = self.run_build()
            self.assertEqual(result.returncode, 0, result.stderr)
            package = self.project / ("SAT_ANYKAOS_" + timestamp[:8])
            actual = [p.name for p in self.project.glob("SAT_ANYKAOS_*")
                      if p.is_file() and not p.is_symlink()
                      and p.name not in (note.name, *odd_names)]
            self.assertEqual(actual, [package.name], "Old generated packages must be replaced")
            with tarfile.open(package, "r:gz") as archive:
                self.assertEqual(archive.extractfile("./app.sqsh4").read(), firmware.encode())
                self.assertEqual(archive.extractfile("./update.sh").read(), b"upgrade/scripts/update.sh")
            self.assert_no_temporary_packages()
        self.assertEqual(note.read_bytes(), b"keep note")
        for name in odd_names:
            self.assertEqual((self.project / name).read_bytes(), b"keep unrelated file")
        self.assertTrue(folder.is_dir())
        self.assertTrue(link.is_symlink())

    def test_failures_preserve_old_package_and_remove_temporary_files(self):
        old = self.project / "SAT_ANYKAOS_1019112259"
        old.write_bytes(b"old package")
        for failure in ("cmake", "squashfs", "tar", "mv"):
            with self.subTest(failure=failure):
                self.env["TEST_FAILURE"] = failure
                result = self.run_build()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(old.read_bytes(), b"old package")
                self.assertEqual(list(self.project.glob("SAT_ANYKAOS_*")), [old])
                self.assert_no_temporary_packages()

    def test_failed_rebuild_in_same_minute_preserves_previous_package(self):
        old = self.project / "SAT_ANYKAOS_10211300"
        old.write_bytes(b"previous package in same minute")
        for failure in ("squashfs", "tar", "mv"):
            with self.subTest(failure=failure):
                self.env["TEST_FAILURE"] = failure
                result = self.run_build()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(old.read_bytes(), b"previous package in same minute")
                self.assertEqual(list(self.project.glob("SAT_ANYKAOS_*")), [old])
                self.assert_no_temporary_packages()

    def test_build_only_does_not_replace_packages(self):
        old = self.project / "SAT_ANYKAOS_1019112259"
        old.write_bytes(b"old package")
        result = self.run_build("--build-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(old.read_bytes(), b"old package")
        self.assertEqual(list(self.project.glob("SAT_ANYKAOS_*")), [old])
        self.assert_no_temporary_packages()

    def test_output_name_collision_does_not_modify_directory_or_link(self):
        old = self.project / "SAT_ANYKAOS_1019112259"
        old.write_bytes(b"old package")
        output = self.project / "SAT_ANYKAOS_10211300"
        output.mkdir()
        result = self.run_build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(output.iterdir()), [])
        self.assertEqual(old.read_bytes(), b"old package")
        self.assert_no_temporary_packages()
        output.rmdir()
        note = self.project / "note"
        note.write_bytes(b"keep note")
        output.symlink_to(note.name)
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(output.is_symlink())
        self.assertEqual(note.read_bytes(), b"keep note")
        self.assert_no_temporary_packages()

    def test_invalid_arguments_do_not_build(self):
        for args in (("--invalid",), ("--build-only", "extra")):
            with self.subTest(args=args):
                result = self.run_build(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("Usage:", result.stderr)
                self.assertFalse((self.project / "build-tuya6").exists())


if __name__ == "__main__":
    unittest.main()
