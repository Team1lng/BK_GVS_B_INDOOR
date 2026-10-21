# Public OTA and Wi-Fi Alignment Plan

> **For agentic workers:** Use independent Wi-Fi implementation and final code review. User explicitly requested public OTA and Wi-Fi behavior; execute in the current extracted GVS project.

**Goal:** Align GVS Black's OTA and Wi-Fi flows with `bk_public_indoor` after the Tuya6 migration.

**Architecture:** Keep GVS PID, DP mapping, resources and persisted user-data layout. Adopt public asynchronous Wi-Fi connection/rollback/UI flow, OTA package-name propagation and updater, and new/old outdoor version protocol with Tuya attachment reporting. Retain existing file-failure guards and explicit SD/cloud upgrade source selection.

**Tech Stack:** C/C++, LVGL, Tuya 6.2.20, ARM Anyka, CMake, shell and host C/Python tests.

## OTA

- [x] Add failing host checks for updater receiving the sanitized SAT package identifier and outdoor version/attachment selection.
- [x] Update `src/tuya-6.2.20/app/app_user_upgrade/src/ty_sdk_upgrade.c` and both `upgrade/{scripts,platform}/update.sh` to pass and persist the public package identifier only after successful flashing.
- [x] Add outdoor model/version decoding and offline reset in `src/api/network/network_common.{c,h}`; preserve legacy version/date compatibility.
- [x] Add public attachment reporting in `src/layout/layout_define.c`, register at startup, and show new/old versions in `layout_setting_info.c`.
- [x] Align senior upgrade entry and Tuya unbinding with public while preserving GVS lock settings; keep separate SD/cloud staging and existing failed-download guards.

## Wi-Fi

- [x] Port public worker start/state/cancel and configuration rollback in `src/api/wlan/wlan.{c,h}`.
- [x] Adapt add/connect/settings screens and Wi-Fi defaults; preserve QR availability before MQTT and GVS resources.
- [x] Exercise connection success, failure, cancellation, persisted/temporary configuration, and UI gating with host tests.

## Delivery

- [x] Run prior migration regressions plus new OTA/Wi-Fi tests and the ARM build.
- [x] Independently review modified paths and fix material findings.
- [x] Rebuild the upgrade package, verify its contents and update the migration notes with new behavior and output paths.
