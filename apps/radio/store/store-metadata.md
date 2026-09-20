# LumaFold 商店元数据草案

- 状态：LumaFold 工作品牌已接入；名称与 Logo 仍可调整，等待最终可用性确认
- 更新时间：2026-08-26

## 产品标识

- 当前 App Name: `LumaFold`
- 建议发布名: `LumaFold`（正式使用前仍需完成 App Store 与商标可用性确认）
- Bundle ID / Application ID: `com.chanmo.tiklocal.radio`
- Version: `0.1.0`
- iOS Build Number / Android Version Code: `1`
- 建议 Primary Category: Photo & Video
- 建议 Secondary Category: Utilities
- Suggested age rating: 4+ / Everyone
- Copyright: 待发布账号主体确认

## App Store — zh-CN

### 副标题

私密、离线的个人影像 Flow

### 推广文本

从照片或文件导入你自己的图片和视频，在 iPhone 上建立无需账号、网络或 Server 的私人离线 Flow。

### 关键词

本地相册,离线视频,私人媒体,影像浏览,照片整理,视频播放,本地优先,隐私

### 描述

LumaFold 把你主动选择的图片和视频变成一个安静、私密、随时可用的个人 Flow。

主要能力：

- 从系统 Photos 或 Files 明确选择并导入图片与视频
- 在 App 私有空间保存离线副本，不依赖原资源持续可用
- 使用带视频预览的网格资料库浏览，并通过纵向 Flow 连续观看
- 多项目导入显示进度，并在空间不足前给出明确提示
- 在资料库中查看占用空间，选择删除或清空 App 管理的副本
- 无需账号、网络或 TikLocal Server
- 可选连接用户自行运行的 TikLocal Server，使用 Radio 与 Demo Signal

导入媒体留在设备上，不会上传给 TikLocal 项目。删除 App 内条目只移除 LumaFold
管理的副本，不会删除 Photos 或 Files 中的原件。App 不包含广告、第三方分析或跨
App 追踪。

## App Store — en-US

### Subtitle

Your private offline media flow

### Promotional text

Import your own photos and videos into a private, offline flow that needs no account, network, or server.

### Keywords

offline photos,local video,private media,photo viewer,media flow,local first,privacy

### Description

LumaFold turns photos and videos you explicitly choose into a calm, private,
always-available personal flow.

Highlights:

- Import photos and videos through the system Photos or Files picker
- Keep managed offline copies in the app's private storage
- Browse a visual library with video previews and watch a continuous vertical Flow
- See multi-item import progress and receive a clear warning before storage runs out
- See storage usage, select items to delete, or clear managed copies
- Works without an account, network connection, or TikLocal Server
- Optionally connect to a TikLocal Server you operate for Radio; Demo Signal is bundled

Imported media stays on the device and is not uploaded to the TikLocal project.
Deleting an item removes only LumaFold's managed copy, not the original in
Photos or Files. The app contains no ads, third-party analytics, or cross-app
tracking.

## App Review Notes

Review of the primary local experience does not require an account, network, or
TikLocal Server:

1. Launch the app and open **My Flow**.
2. Choose **Photos** or **Files** and select test images or videos with the
   system picker. Permissions are requested only after that explicit action.
3. Imported items appear in the local grid. Choose **Play all** to enter the
   offline vertical Flow.
4. Touch and hold an item to select and delete it. **Clear** removes all copies
   managed by LumaFold; neither action deletes the original selected item.

The optional Radio section can be reviewed without a server by choosing
**Demo Signal**. Real-server pairing connects only to a user-operated TikLocal
instance. The optional camera scanner reads a one-time QR code created by that
server, is opened by explicit user action, and does not save images.

## App Privacy — 初步答案

基于当前 production 代码：

- Tracking: No
- Data linked to the user: None collected by the developer
- Data not linked to the user: None collected by the developer
- Advertising: None
- Third-party analytics: None

用户选择的媒体、设备内 SQLite 索引，以及用户设备与自有 TikLocal Server 之间的
Radio 数据均不传输给 TikLocal 项目。App Store Connect 中的“收集”以开发者或第三方
接收数据为边界；提交前仍需按最终二进制中的 SDK、网络端点和付费组件重新核对。

## Google Play Data Safety — 初步答案

- Does the app collect or share user data with the developer or third parties? No
- Ads: No
- Account creation: No
- User deletion request: 不适用开发者后台；用户可删除本地副本、断开并撤销设备
- Data in transit: HTTPS 可用；用户也可主动连接可信局域网中的自有 HTTP Server

不要声称“所有流量始终加密”，因为可选 Radio 明确支持用户控制的局域网 HTTP。

## URL

- Support URL: `https://github.com/ChanMo/TikLocal/issues`
- Marketing URL: `https://github.com/ChanMo/TikLocal`
- Privacy Policy URL（文件合并到公开 main 后）:
  `https://github.com/ChanMo/TikLocal/blob/main/apps/radio/store/privacy-policy.md`

## 截图计划

至少准备以下真实 App 状态，避免使用私人文件名或敏感媒体：

1. 本地优先 Home 与 My Flow 入口。
2. 空资料库及 Photos / Files 导入入口。
3. 已导入媒体的网格资料库与空间统计。
4. 图片与视频混合的纵向离线 Flow。
5. 长按选择、删除和清空副本的确认界面。
6. 可选 Radio / Demo Signal，作为次要能力放在最后。

正式提交前必须再次确认 LumaFold 名称、图标、截图标题和商店分类；TikLocal 只作为
开源项目与用户自有 Server 品牌出现，Radio 只作为可选能力。
