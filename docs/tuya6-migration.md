# GVS 黑色版 Tuya 6.2.20 移植

参考 `BK/APP/Indoor/bk_public_indoor`，SDK、平台适配层和原版 `libtuyaos.a` 放在 `src/tuya-6.2.20`。GVS 的界面、用户数据结构、硬件宏和资源保留。

后续 OTA 与 Wi-Fi 已进一步对齐 public，详见 [本轮修改说明](public-ota-wifi.md)。

## 构建与输出

```sh
./build.sh --build-only  # 编译
./build.sh               # 编译并生成升级包
```

使用工程 `compilat_tool/arm-anykav500-linux-uclibcgnueabi/bin` 下的 ARM/uClibc 工具链。构建目录为 `build-tuya6`；固件为 `build-tuya6/src/ANYKA37E.BIN`；升级包为根目录 `SAT_ANYKAOS_月日时分`，与 public 一致，时间戳为八位数字，例如 `SAT_ANYKAOS_10211401`。同一分钟再次构建成功时覆盖同名包。新包完整生成并放入根目录后，删除该目录内此前生成的八位或旧十位数字时间戳普通升级包，只保留本次包；编译或打包失败保留旧包。`--build-only` 不替换升级包。`upgrade/make_image.sh` 也调用此构建入口，避免打包旧程序。

编译不再改写源资源；黑色版 ROM 头文件和数据复制到构建目录。打包采用独立的 `build-tuya6/package.*` 暂存目录，包含本次编译程序、GVS 黑色 ROM、GVS 语言表、normal 铃声及原平台文件；脚本退出时清理本次暂存目录和临时包。

## 保留的产品配置

- PID：`285v8xpvxwdm8a0p`；App 固件版本：`2.1.0`。
- `GVS_VERSION`、`GVS_BALCK`、机械门钟、SD 分区、信箱、原屏幕及指纹/卡片管理配置保留。
- 图片：`src/layout/resource/res_black_gvs`；语言：`upgrade/language/bcom/gvs/language.xls`；铃声：`upgrade/ring/normal/rings`。
- DP148：原主锁事件；DP232：原 gate1 事件；DP233：室内 gate2；DP234：锁支持列表 `148,232`。
- DP138：灯；DP189：工作模式；DP231：通道；DP235：激活状态；DP236：截图。DP231 保留通道列表与切换成功应答两种格式，名称取 GVS 当前语言。

公版的 DP234 主锁、DP233 锁列表、DP244 室内锁映射没有直接套用。GVS 原来的锁事件、定时脉冲和锁选择设置继续由原界面处理。

## 接入与修复

- 初始化、Wi-Fi/有线网络选择、二维码、在线状态、解绑、音视频推流、RTSP 摄像头、App 对讲、通知、本地及云存储接入 Tuya6 接口。
- 首次绑定时二维码只依赖已取得的链接，不等待 MQTT 上线或媒体就绪；设置页保留 Tuya ID 显示。
- 本地流/存储使用独立的 SDK 就绪状态，初始化成功后的 MQTT 断线不清除就绪状态；初始化失败不会被当作成功。冷启动仍沿用参考实现等待网络/MQTT 的流程。
- 对讲按实际 PCM/G711A/G711U 与 8/16 kHz 元数据转换为门口机使用的 G711A 16 kHz，使用固定容量分块缓冲。
- DP 查询不执行开锁、重启等控制命令。非法类型和通道输入被拒绝；通道名称进行 JSON 转义并检查容量。DP235 在上线、初始化状态上报和查询时回报 `false`。
- App 重启保留背光关闭、LCD 复位和延时；时间同步失败不覆盖原时间。
- OTA 检查打开、写入、刷新、关闭及完整长度，下载或解包失败不启动安装。室内机按 public 将净化后的 `SAT_ANYKAOS_*` 包名传给更新脚本；脚本来自 public，仅在成功写入后生成版本标记。门口机接入 public 的监控退出、升级界面和两线发送流程，云端文件 `/tmp/cbin.update` 与 SD 文件 `/mnt/tf/cbin.update` 分开选择。
- 后续按用户要求接入公版的新门口机型号/三段版本协议和附属模块版本上报；旧门口机继续使用原版本与编译日期。同型号双门口机按公版选择较低版本，不同型号组合不公布单一可升级模块。

原授权数据结构保留。Tuya6 缓存位于 `/app/data/tuya_cache/`，授权目录位于 `/app/data/tuya_key/`；更换授权时清理新缓存。

## Tuya4 清理

工程内移除了 `src/include/tuya`、`src/lib/tuya` 及 `src/api/wlan/tuya_sdk.c`、`tuya_api_func.c`、`tuya_stream_storage.c`、`tuya_stream_storage.h`。旧 CMake 缓存、对象目录、含旧接口的应用静态库、Tuya4 固件和升级包也已移出工程。

迁移前源码及移除内容保存在 `/tmp/gvs-b-tuya6-20261017-_s7wbe3d/`。这只是本机回查备份，不参与新工程编译。原始 `tar_gz/GVS_B-Indoor.tar.gz` 未修改。

## 验证

```sh
python3 src/tuya-6.2.20/tests/run_host_tests.py
python3 tests/sdk_safety/run_host_tests.py
python3 tests/application/run_channel_tests.py
python3 tests/run_build_tests.py
python3 tests/verify_migration.py
python3 tests/verify_package.py
```

主机回归检查覆盖 DP 分发/回报/查询、缓冲区清理、时间同步、LCD 重启、SDK/存储启动、音频和 OTA 失败路径、通道语言、SD/云升级来源、首次二维码和初始化配置。两个 SDK 测试入口还通过了 ASan/UBSan；运行命令前加 `ASAN_OPTIONS=detect_leaks=0 GVS_TEST_ASAN=1`，此环境未运行泄漏扫描。

ARM 全量编译和链接通过。迁移检查核对 237 个编译单元及最终链接，使用 Tuya6 SDK 和原版库；后续对齐 public 后，2824 个图片、字体、语言、铃声和 logo 文件哈希不变；升级及 Wi-Fi 恢复脚本已按要求更新。升级包解包核对 19 个固件、资源与平台文件；具体包名、哈希和核对文件见 `build-tuya6/package-verification.json`。

未连接实机。仍需验证首次升级后的绑定/重新绑定、App 监控及双向声音、通道切换、三个锁事件、录像/回放、断线恢复、解绑和 OTA；主机测试与编译不能替代这些设备验收。
