# TikLocal Radio 商店元数据草案

- 状态: 文案与隐私答案已准备，等待真机验收、公开隐私 URL 与签名账号
- 更新时间: 2026-07-25

## 产品标识

- App Name: `TikLocal Radio`
- Bundle ID / Application ID: `com.chanmo.tiklocal.radio`
- Version: `0.1.0`
- iOS Build Number / Android Version Code: `1`
- Primary Category: Music
- Secondary Category: Utilities
- Suggested age rating: 4+ / Everyone
- Copyright: 待发布账号主体确认

## App Store — zh-CN

### 副标题

你的私人本地电台

### 推广文本

连接自己的 TikLocal Server，让本地音乐变成无需反复选择的私人电台。也可直接使用内置 Demo Signal 体验。

### 关键词

本地音乐,私人电台,自托管,音乐播放,局域网,音频,收藏,后台播放

### 描述

TikLocal Radio 是 TikLocal Server 的原生 Radio 伴侣。

它不试图把完整媒体库塞进手机，而是把你自己的本地音乐整理成一个低决策、可持续收听的私人电台。

主要能力：

- 连接用户自己运行的 TikLocal Server
- 默认、最近添加与收藏倾向电台
- 播放、暂停、下一首、收藏与有限再听
- 睡眠定时与断线状态提示
- 安全保存可撤销设备令牌
- 无需 Server 即可使用 Demo Signal

你的媒体和收听反馈保留在你自己的 TikLocal Server。App 不包含广告、第三方分析或跨 App 追踪。

> 发布前验收门槛：只有在真机通过锁屏、后台音频和耳机播放/暂停测试后，才在描述中增加这些系统体验声明。`0.1.x` 不支持耳机、锁屏或通知的下一首/上一首；App 内“下一首”不受影响。

## App Store — en-US

### Subtitle

Your private local radio

### Promotional text

Connect to your own TikLocal Server and turn a local music library into a calm, low-decision radio. Demo Signal works without a server.

### Keywords

local music,private radio,self hosted,audio,personal music,LAN,favorites,radio

### Description

TikLocal Radio is the native Radio companion for TikLocal Server.

Instead of putting another full library manager on your phone, it turns your own local music into a low-decision station designed for continuous listening.

Highlights:

- Connect to a TikLocal Server you operate
- Default, Recently Added, and Favorites-oriented stations
- Play, pause, next, favorite, and limited encore
- Sleep timer and clear connection status
- Revocable device credentials stored securely
- A bundled Demo Signal that works without a server

Your media and listening feedback remain on your own TikLocal Server. The app contains no ads, third-party analytics, or cross-app tracking.

> Release gate: mention lock-screen controls, background audio, and headset play/pause only after they pass physical-device acceptance. Version 0.1.x does not support next/previous from a headset, lock screen, or media notification; the in-app Next action is unaffected.

## App Review Notes

TikLocal Radio normally connects to a TikLocal Server on the user's local
network. Review does not require a server:

1. Launch the app.
2. Choose **Use Demo Signal** on the pairing screen.
3. The bundled station supports playback, pause, next, favorite, encore, and
   sleep-timer interactions without an account or network service.

The real-server flow accepts an address for a user-operated TikLocal instance.
The access password is exchanged once for a revocable device token and is not
stored by the app. The optional camera scanner reads only QR codes created by
TikLocal's web settings, is opened by an explicit user action, and does not
save images. Reviewers can use Demo Signal or manual pairing without granting
camera permission.

## App Privacy — 初步答案

基于当前 production 代码：

- Tracking: No
- Data linked to the user: None collected by the developer
- Data not linked to the user: None collected by the developer
- Advertising: None
- Third-party analytics: None

说明：Server 地址、设备凭证、媒体请求、收藏和收听反馈只在用户设备与用户自有
TikLocal Server 之间处理，不传输给 TikLocal 项目或其他开发者服务。

最终填写 App Store Connect 时仍应以当时二进制中的 SDK 和网络端点重新核对。

## Google Play Data Safety — 初步答案

- Does the app collect or share user data with the developer or third parties? No
- Ads: No
- Account creation: No
- User deletion request: 不适用开发者后台；App 可断开并撤销设备，Server 数据由用户自行管理
- Data in transit: HTTPS 可用；用户也可主动选择可信局域网 HTTP，隐私政策已披露

最终填写 Play Console 时不要声称“所有流量始终加密”，因为产品明确支持用户控制的
局域网 HTTP。

## URL

- Support URL: `https://github.com/ChanMo/TikLocal/issues`
- Marketing URL: `https://github.com/ChanMo/TikLocal`
- Privacy Policy URL（文件合并到公开 main 后）:
  `https://github.com/ChanMo/TikLocal/blob/main/apps/radio/store/privacy-policy.md`

## 截图计划

至少准备以下状态，且所有系统体验声明以真机结果为准：

1. Radio 主界面与正在播放状态。
2. 电台切换。
3. 收藏、Encore 与睡眠定时。
4. Server 扫码与手动配对界面（真机验收后使用扫描画面）。
5. Demo Signal / 离线可体验说明。
6. 真机锁屏媒体面板（仅在验收通过后使用）。

不要在商店截图中展示可兑换的真实二维码、配对链接、Server 地址、访问密码、设备
令牌或私人媒体文件名。
