# GVS Black Tuya6 Migration Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the application integration task and requesting-code-review before delivery. Work in the requested directory; this extracted project has no Git repository.

**Goal:** Replace GVS Black's Tuya4 integration with the Tuya 6.2.20 SDK from `bk_public_indoor`, removing the old SDK and preserving GVS behavior.

**Architecture:** Keep GVS layout, hardware configuration, user data and resources. Import the public SDK into `src/tuya-6.2.20`, adapt its DP definitions and the GVS application calls, and build/link only the new SDK. Use an independent build directory and package the existing GVS assets with the new executable.

**Tech Stack:** C/C++, CMake, ARM Anyka GCC 4.9.4, Tuya 6.2.20, Bash, Python verification.

## 1. Baseline and migration contract

- [x] Inspect GVS Tuya4 and public Tuya6 integration; record original source and asset hashes outside the project.
- [x] Add and run `python3 tests/verify_migration.py`; initially expect failure because the Tuya6 SDK and fresh build are absent.
- [x] Preserve PID `285v8xpvxwdm8a0p`, firmware version `2.1.0`, `GVS_VERSION`, `GVS_BALCK`, existing screen settings, `res_black_gvs`, GVS language table and normal rings.

## 2. SDK and build replacement

- [x] Copy public `src/tuya-6.2.20` excluding generated build outputs.
- [x] Remove GVS `src/include/tuya`, `src/lib/tuya` and the four old `src/api/wlan/tuya*` files after retaining the baseline outside the project.
- [x] Update root, `src` and `src/api` CMake files to build `ANYKA37E.BIN` using `tuya` and `libtuyaos.a`; remove hard-coded stale application archives.
- [x] Generate ROM inputs under the build directory using `configure_file(... COPYONLY)` and retain GVS assets in packaging.
- [x] Replace `build.sh` with a fail-fast script supporting `--build-only`, using `build-tuya6`, independent packaging staging and the original platform updater. Archive the extracted Tuya4 package outside the project; preserve subsequent Tuya6 packages.

## 3. GVS application adaptation

- [x] Adapt initialization, QR code/unbinding, online/readiness state, channels, notifications, stream data and storage calls in `src/main.c`, `src/layout` and `src/api` to the public Tuya6 API without replacing GVS screens or data structures.
- [x] Preserve GVS DP148/232/233 locks, DP234 lock support (`148,232`), DP138 light, DP189 work mode, DP231 channels, DP235 activation and DP236 screenshot.
- [x] Connect Tuya6 upgrade events to the existing UI/network upgrade path, preserving local SD upgrades.
- [x] Exercise behavior-sensitive adaptations with host regression tests; inspect public-reference error paths for initialization, audio buffers and OTA before delivery.

## 4. Verification and delivery

- [x] Run host tests and `./build.sh --build-only`; fix integration errors, then run `./build.sh` to produce the upgrade package.
- [x] Verify compile commands and link inputs use only Tuya6; verify the copied SDK library matches the public reference.
- [x] Unpack the new package and compare firmware, black ROM, language, fonts, rings, updater, DTB and logo with their intended sources.
- [x] Review requirements and code independently; address material findings and re-run affected checks.
- [x] Document output paths, removed Tuya4 content, verification evidence and hardware acceptance steps in `docs/tuya6-migration.md`.
