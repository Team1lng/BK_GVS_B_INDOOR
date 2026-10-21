# OTA 与 Wi-Fi 对齐 public

根据后续要求，将 `GVS_B-Indoor` 的 OTA 和 Wi-Fi 流程对齐 `bk_public_indoor`。GVS PID、固件版本、DP 映射、用户数据结构和黑色界面资源保持原配置。

## OTA

- 室内机下载完成后，将从 URL 提取并净化的 `SAT_ANYKAOS_*` 标识传给 `/tmp/update.sh`，没有可提取名称时使用 public 的 `SAT_ANYKAOS_UNKNOWN`。
- `upgrade/scripts/update.sh` 与 `upgrade/platform/update.sh` 使用 public 更新脚本。校验、分区容量、擦除、写入和同步失败走失败流程；仅成功写入后更新 `/app/data` 的升级版本标记。
- 保留下载文件打开、写入、刷新、关闭、完整长度与解包检查，失败不进入安装。
- 接入 public 新门口机型号/三段版本协议、离线信息清理和附属模块版本上报。同型号双门口机采用较低版本，不同型号不公布单一升级模块；旧型号保留两段版本及编译日期。
- 监控和待机页面按 public 退出监控/录像并进入门口机升级流程；其他页面有事件兜底。高级设置采用 public 升级确认入口并增加 Tuya 解绑，保留 GVS 原开锁设置。
- 手动 SD 与云端 OTA 明确选择各自文件，避免残留 `/tmp/cbin.update` 覆盖 SD 选择。

## Wi-Fi

- 对齐 public 的异步连接状态接口和添加网络、输入密码、开放网络连接页面。后台工作线程负责连接及回退，页面轮询结果并处理取消和超时。
- 连接成功后才提交临时配置；失败或取消恢复原配置。页面刷新 SSID/IP 等信息，保留未上线前显示二维码的行为。
- 断开连接时禁用保存的网络并持久化，清理旧连接信息。同步保存接口不改变用户数据结构。
- 接入 public 的 Wi-Fi 健康检查与 `hi3881_reload.sh`，在配置页面和录像期间暂停检查。MQTT 断线不再直接触发各页面重载 Wi-Fi。
- 对连接线程的凭据生命周期、晚到成功、超时、配置写入失败和异常网络输出增加检查。连接请求被拒绝时立即提示，不进入假连接等待；断开时只修改实际配置键，保留名称、密码和注释中的 `disabled=`。

## 构建与验证

```sh
./build.sh --build-only
python3 tests/public_wifi/run_host_tests.py
python3 tests/public_ota/run_host_tests.py
python3 tests/public_ota/test_updater.py
python3 tests/application/run_channel_tests.py
python3 src/tuya-6.2.20/tests/run_host_tests.py
python3 tests/sdk_safety/run_host_tests.py
./build.sh
python3 tests/verify_migration.py
python3 tests/verify_package.py
```

升级脚本回归使用模拟擦除、写入和重启命令，不操作真实设备。固件路径仍为 `build-tuya6/src/ANYKA37E.BIN`，新包位于工程根目录；最新核对包名及 SHA256 记录在 `build-tuya6/package-verification.json`。

本轮修改前备份为 `/tmp/gvs-public-ota-wifi-20261017-4gl_cbug/`。2824 个 GVS 图片、字体、语言、铃声和 logo 文件经哈希对照没有变化；升级脚本和 Wi-Fi 恢复脚本属于本轮有意更新内容。

仍需在实机验证路由器配网、密码错误、取消重试、断线恢复、解绑重绑及室内机/门口机 OTA。

本轮结果：ARM 编译和链接通过，22 项主机回归通过，OTA 与 Wi-Fi 独立审查通过。最终升级包为 `SAT_ANYKAOS_1017115146`，解包核对的 19 项固件、资源及平台文件全部匹配。
