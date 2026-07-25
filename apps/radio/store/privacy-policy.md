# TikLocal Radio Privacy Policy / 隐私政策

- Effective date / 生效日期: 2026-07-25
- Applies to / 适用产品: TikLocal Radio

## English

TikLocal Radio is a companion app for a TikLocal Server that you operate. The
app does not require a TikLocal cloud account, and the TikLocal project does not
operate a service that receives your listening activity.

### Information handled by the app

When you pair with a TikLocal Server, the app sends the server address, the
access password you enter, and a generic device name directly to that server.
The password is used only for the pairing request and is not saved by the app.
You can instead scan a one-time QR code created in TikLocal's web settings. The
camera is active only while the scanner is open; the app does not save or send
camera images. The QR code contains a server address and a short-lived pairing
grant, not the access password or a device token. The server keeps only a
one-way hash of that grant in memory, and it expires after two minutes or one
successful use.
After pairing:

- The app stores the server address, server name, device identifier, and
  revocable device token in the operating system's secure storage.
- The server stores the device name, pairing time, and a one-way hash of the
  device token on the computer running TikLocal.
- The app requests station information, audio, metadata, and artwork directly
  from that server.
- Favorites and lightweight listening events — such as play, completion,
  replay, skip, error, and playback ratio — are sent directly to that server
  and stored locally there to improve radio selection.

Demo Signal uses only media bundled with the app and does not require a server.

### What the TikLocal project does not collect

The production app contains no advertising SDK, third-party analytics,
cross-app tracking, or developer-operated telemetry endpoint. The TikLocal
project does not receive the server address, access password, device token,
media library, favorites, or listening history described above.

### Network security

TikLocal Radio supports HTTPS and also permits HTTP for user-controlled servers
on a trusted local network. HTTP traffic is not encrypted and could be observed
by other parties with access to that network. Use TikLocal HTTPS whenever
practical and do not pair over an untrusted network.

### Retention and deletion

Disconnecting from a server clears the saved profile and attempts to revoke its
device token. You can also revoke any paired Radio client from TikLocal's web
settings. Changing the TikLocal access password invalidates existing device
tokens.

Uninstalling the app removes its app data on Android. On iOS, Keychain entries
may persist after uninstall and reinstall as an operating-system behavior; a
token revoked on the server can no longer access the server even if such an
entry remains.

Listening feedback, favorites, and paired-device records remain on the
user-controlled TikLocal Server until the user removes or resets them.

### Children

TikLocal Radio is not directed to children and does not knowingly collect
personal information from children.

### Changes and contact

Material changes will be reflected in this document and its effective date.
Questions and privacy requests can be filed at:

https://github.com/ChanMo/TikLocal/issues

## 中文

TikLocal Radio 是用户自有 TikLocal Server 的伴侣客户端。它不要求 TikLocal
云账号，TikLocal 项目也不运营接收用户收听活动的云端服务。

### App 处理的信息

配对 TikLocal Server 时，App 会把用户填写的 Server 地址、访问密码和通用设备
名称直接发送到该 Server。访问密码只用于本次配对请求，不会由 App 保存。用户也可
扫描 TikLocal Web 设置页生成的一次性二维码：相机只在扫描器打开期间工作，App
不会保存或传输相机图像。二维码包含 Server 地址和短期配对授权，不含访问密码或
设备令牌；Server 仅在内存中保存授权的单向哈希，并在两分钟后或成功使用一次后
失效。配对后：

- App 在操作系统安全存储中保存 Server 地址、Server 名称、设备标识和可撤销设备令牌。
- Server 在运行 TikLocal 的电脑上保存设备名称、配对时间和设备令牌的单向哈希。
- App 直接从该 Server 获取电台信息、音频、元数据和封面。
- 收藏和轻量收听事件（播放、听完、重播、跳过、错误及播放比例）直接发送到该
  Server，并仅在本地保存，用于改善电台选曲。

Demo Signal 只使用 App 内置媒体，不需要连接 Server。

### TikLocal 项目不收集的信息

正式版 App 不包含广告 SDK、第三方分析、跨 App 追踪或开发者运营的遥测端点。
TikLocal 项目不会收到上述 Server 地址、访问密码、设备令牌、媒体库、收藏或收听
历史。

### 网络安全

TikLocal Radio 支持 HTTPS，也允许用户在可信局域网中连接自己控制的 HTTP
Server。HTTP 流量没有加密，可能被能够访问该网络的其他方观察。条件允许时应使用
TikLocal HTTPS，不要在不可信网络中完成配对。

### 保留与删除

断开 Server 会清除本地 Profile，并尝试撤销设备令牌。用户也可以在 TikLocal Web
设置中撤销任一已配对 Radio 客户端；修改 TikLocal 访问密码会让既有设备令牌失效。

Android 卸载 App 后会移除其 App 数据。受 iOS Keychain 行为影响，安全存储条目在
卸载、重装后可能继续存在；即使如此，已在 Server 撤销的令牌也无法再访问 Server。

收听反馈、收藏和配对设备记录保留在用户控制的 TikLocal Server 上，直到用户在该
Server 中删除或重置。

### 儿童

TikLocal Radio 不面向儿童，也不会有意收集儿童个人信息。

### 变更与联系

重要变更会更新本文及其生效日期。如有隐私问题或请求，请通过以下地址联系：

https://github.com/ChanMo/TikLocal/issues
