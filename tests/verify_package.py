#!/usr/bin/env python3
"""Unpack a generated upgrade package and compare all intended GVS assets."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    package = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else max(
        ROOT.glob("SAT_ANYKAOS_*"), key=lambda p: p.stat().st_mtime)
    checked = []
    with tempfile.TemporaryDirectory(prefix="gvs-package-check-") as directory:
        platform = Path(directory) / "platform"
        platform.mkdir()
        with tarfile.open(package, "r:gz") as archive:
            archive.extractall(platform)
        app = Path(directory) / "app"
        subprocess.run(["unsquashfs", "-d", str(app), str(platform / "app.sqsh4")],
                       check=True, stdout=subprocess.DEVNULL)
        assets = {p.relative_to(ROOT / "upgrade/app"): p
                  for p in (ROOT / "upgrade/app").rglob("*")
                  if p.is_file() and "rings" not in p.relative_to(ROOT / "upgrade/app").parts}
        assets.update({Path("ANYKA37E.BIN"): ROOT / "build-tuya6/src/ANYKA37E.BIN",
                       Path("rom.bin"): ROOT / "src/layout/resource/res_black_gvs/rom.bin",
                       Path("language.xls"): ROOT / "upgrade/language/bcom/gvs/language.xls"})
        for ring in (ROOT / "upgrade/ring/normal/rings").iterdir():
            if ring.is_file():
                assets[Path("rings") / ring.name] = ring
        for name, source in assets.items():
            assert digest(app / name) == digest(source), f"Wrong packaged asset: {name}"
            checked.append("app/" + str(name))
        assert {p.relative_to(app) for p in app.rglob("*") if p.is_file()} == set(assets), "Unexpected app files"
        for source in (ROOT / "upgrade/platform").iterdir():
            if not source.is_file() or source.name in {"app.sqsh4", "update.sh", "upgrade_progress"}:
                continue
            assert digest(platform / source.name) == digest(source), source.name
            checked.append("platform/" + source.name)
        for name, source in (("update.sh", ROOT / "upgrade/scripts/update.sh"),
                             ("upgrade_progress", ROOT / "upgrade/upgrade_progress/upgrade_progress")):
            assert digest(platform / name) == digest(source), name
            checked.append("platform/" + name)
    result = {"package": str(package), "sha256": digest(package), "verified_files": checked}
    (ROOT / "build-tuya6/package-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: {package.name}, {len(checked)} firmware/resource/platform files match")


if __name__ == "__main__":
    main()
