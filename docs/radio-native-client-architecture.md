# TikLocal Radio 原生客户端架构

- 状态: 非真机开发与扫码配对已收敛，等待真机验收
- 更新时间: 2026-07-25

## 背景/目标

Radio 是 TikLocal 日常使用频率最高、也最依赖系统媒体能力的模式。PWA 可以覆盖浏览器内体验，但无法稳定获得原生后台播放、耳机控制、锁屏媒体信息和后续车载能力。

本方案新增独立的 React Native 客户端 **TikLocal Radio**。它是 TikLocal Server 的原生伴侣，不是完整 Web 产品的移植：

- Server 继续负责媒体索引、选曲、推荐、收藏与反馈。
- App 负责播放队列、系统媒体会话、连接状态和移动端交互。
- 第一阶段以 iOS 为主，同时保留 Android 构建能力。

## 方案概述

客户端采用 React Native、Expo Development Build 和 `expo-audio`，代码位于 `apps/radio/`，与 Python Server 保持同仓库、独立版本。

只保留三个真实边界：

```text
UI → Radio Session → Player / Server / Storage
```

第一阶段完成 Demo Radio 原生播放纵向切片；第二阶段已经接入 Server API v1、设备配对、SecureStore 与真实 Radio 队列。随后补齐设备令牌生命周期、设置页管理入口、一次性二维码配对、正式图标和启动页。真机不可用期间，协议通过 Flask 测试客户端验证，Web 配对界面通过浏览器冒烟测试，iOS / Android 均通过原生配置生成与生产 Metro bundle。

## 代码设计约束

### 五条长期原则

1. 先写内聚代码，再根据真实变化拆分。
2. 第二个实现出现之前，不建立多实现抽象。
3. 状态只有一个事实来源；播放状态以原生 Player 为准。
4. 一个业务动作最多跨三个文件。
5. 新增目录必须代表真实边界，而不是架构想象。

### 当前结构

```text
apps/radio/
├── App.tsx
├── App.test.tsx
├── app.config.ts
├── eas.json
├── package.json
└── src/
    ├── RadioScreen.tsx
    ├── RadioScreen.test.tsx
    ├── PairingScreen.tsx
    ├── PairingScreen.test.tsx
    ├── PairingScanner.tsx
    ├── PairingScanner.test.tsx
    ├── radio.ts
    ├── radio.test.ts
    ├── player.ts
    ├── api.ts
    ├── api.test.ts
    ├── storage.ts
    ├── storage.test.ts
    ├── model.ts
    └── theme.ts
```

当前共有 10 个业务源码文件和 7 个测试文件。`PairingScanner.tsx` 单独存在，是因为相机权限、扫描生命周期、错误恢复和确认网络目标构成独立交互边界；没有继续拆出 Hook、Repository 或样式文件。

### 明确不做

- 不建立 `features/`、`services/`、`repositories/`、`adapters/`、`usecases/`、`entities/`、`shared/`、`common/`、`utils/` 等推测性分层。
- 不引入依赖注入容器，也不在单一播放器实现前定义 `PlaybackEngine` 接口。
- MVP 不引入 Redux、Zustand、TanStack Query、Axios、UI Kit 或日期工具库。
- 不为每个按钮、存储键或接口响应单独创建文件。
- 不把 RN 客户端代码放入根级 JavaScript workspace；客户端独立安装与锁定依赖。

### 拆分门槛

- 提取函数：能提升主流程可读性、可独立测试、真实复用，或隔离明确副作用。
- 提取组件：出现三个真实复用点，或自身已有复杂状态/交互/无障碍语义。
- 新建文件：内容有独立变化原因，而不只是为了缩短当前文件。
- 新建接口：第二个实现已经出现、平台实现确实分叉，或外部依赖明显不稳定。

### 体量预算

这些数字是警报线，不是追求拆分的 KPI：

- 首期业务源码约 10–15 个文件以内。
- `RadioScreen.tsx` 约 150–300 行。
- `radio.ts` 可容纳 300–500 行的内聚会话逻辑。
- 其他业务模块通常为 80–250 行。
- MVP 直接业务依赖约 5 个以内。

超出预算时先删除重复状态、薄包装和推测性能力，再考虑拆分。

### 2026-07-25 收敛审计

本轮在 58 项行为测试基础上执行未使用符号检查、覆盖分支检查和主路径逐文件审计，结论是保持当前模块边界：

- 删除 `normalizeBaseUrl` 中 HTTP(S) `URL` 构造成功后再次检查 hostname 的不可达分支。
- 删除测试 Deferred 中从未使用的 reject 通道、两个无状态 Screen 测试的冗余全局清理，并内联仅调用一次的成功启动 Fetch 包装。
- 保留 App 的 `profile` / `showPairing` 两个状态：已有 Profile 时仍需进入可取消的配对页，二者不是重复事实来源。
- 保留 `player.ts`、`api.ts`、`storage.ts` 和 `model.ts`：分别对应原生媒体、Server 协议、安全持久化和共享数据契约，不是薄分层。
- 保留初次 Tune 与换台的少量相似分支：抽取后需要一个捕获多个 Hook setter、Profile、Player 的回调，反而扩大依赖表和跳转成本。
- 不拆两个 Screen 的 StyleSheet。当前长文件的大部分体量是只服务本页面的视觉常量；移到独立文件不会减少业务复杂度。
- 扫码与手动连接共用一个异步连接入口，删除重复 loading / error 处理；`PairingScanner` 只负责权限、扫描与确认，不持有 Profile 或令牌。
- 用官方 `react-native-safe-area-context` 替换 React Native 已弃用的
  `SafeAreaView`；只在 App 根部增加 Provider，没有引入导航层、布局 Hook 或页面包装体系。

后续只有在样式出现跨 Screen 真实复用、Radio Session 出现第二个独立生命周期，或单个流程无法一屏连续阅读时再拆分；不以行数越线单独触发重构。

## 接口与边界

### Radio Session

`radio.ts` 是唯一业务编排核心，对 UI 暴露小型命令集：

- `play()` / `pause()` / `next()`
- `selectStation()`
- `toggleFavorite()`
- `encore()`
- `setSleepTimer()`
- `snapshot`

它持有电台、队列索引、收藏和睡眠状态，但不复制 Player 的 `playing`、进度或时长。

### Player

`player.ts` 直接包装 `expo-audio`：

- 设置后台播放音频模式。
- 装载当前音轨并暴露原生播放状态。
- 注册锁屏媒体信息。
- 不建立通用播放器接口；如果未来确实引入第二个播放器实现，再按差异抽象。

### Server 与 Storage

第二阶段已经加入：

- `api.ts`：具体的 TikLocal API v1 客户端，不复制 DTO / Entity / ViewModel。
- `storage.ts`：使用一个 SecureStore JSON 条目保存单 Server Profile 与设备令牌，不按键拆 Repository。

Server 侧没有把原生路由继续塞入 `tiklocal/app.py`；原生 API 边界位于 `tiklocal/radio_client.py`，设备令牌生命周期位于 `tiklocal/services/device_auth.py`，短期一次性授权位于 `tiklocal/services/pairing_grants.py`。

### API v1

```text
POST /api/v1/pair
POST /api/v1/pair/claim
GET  /api/v1/server
DELETE /api/v1/device
GET  /api/v1/radio/stations
GET  /api/v1/radio/tune
GET  /api/v1/radio/metadata
GET  /api/v1/radio/media
GET  /api/v1/radio/artwork
PUT  /api/v1/radio/favorite
POST /api/v1/radio/feedback

GET    /api/radio/devices
DELETE /api/radio/devices/<device_id>
POST   /api/radio/pairing-grants
```

- 浏览器端继续使用 Cookie + CSRF，行为不变。
- `/api/v1/*` 使用独立 Bearer Token，不接受浏览器 Session 代替。
- 配对时用现有访问密码换取高熵设备令牌；Server 只持久化 SHA-256 哈希。
- 已登录的 Web 设置页也可在 CSRF 保护下生成两分钟、单次使用的配对授权。Server 只在内存中保存授权哈希；扫码后 App 显示目标 Server，用户确认后才兑换为同一种设备令牌。
- 配对授权绑定当前 `auth_revision`，改密、过期、重复兑换或 Server 重启后均不可用；二维码不包含访问密码或设备令牌。
- 设备令牌绑定 `auth_revision`，TikLocal 改密后自动失效。
- App 断开 Server 时会撤销自身令牌；重新配对会尽力撤销旧令牌。
- 浏览器设置页可查看全部配对设备，并以 Cookie + CSRF 撤销单个设备。
- 收藏接口接收明确的 `favorite: boolean`，网络重试保持幂等。
- 媒体端点保留 HTTP Range，客户端音源通过请求 Header 携带 Bearer Token。

### 连接与状态流

```text
SecureStore Profile
        ↓
Web QR → POST /api/v1/pair/claim
        或
地址 + 密码 → POST /api/v1/pair
        ↓
stations + tune
        ↓
Radio Session → expo-audio
        ↓
favorite / feedback
```

- 无 Profile 时进入配对页，优先扫码；也可粘贴配对链接、手动输入地址和密码，或选择 Demo Signal。
- 冷启动和前台均监听 `tiklocal-radio://pair`。深链必须先通过与扫码相同的严格解析，只负责打开配对页并显示目标 Server；用户确认前不发出兑换请求，取消后保留原有 Profile。
- Token 返回 401 时清除 SecureStore 并重新配对。
- 普通网络错误不清空 Profile，保留当前队列并显示离线状态。
- 收藏先乐观更新，Server 失败时回滚。

## MVP 范围

包含：

- 单 Server 配对。
- 默认、最近添加、收藏倾向三个电台。
- 播放、暂停、下一首、收藏、有限再听和睡眠定时。
- 后台播放、锁屏信息、耳机播放/暂停和基础断线恢复。
- 用于开发和商店审核的 Demo Mode。

暂不包含：

- 多 Server、媒体库浏览与搜索、离线下载。
- mDNS 自动发现。
- Siri、CarPlay、Android Auto。
- Flow、Room、视频与下载管理。

## 版本与发布

- 产品名：`TikLocal Radio`
- Expo slug：`tiklocal-radio`
- URL scheme：`tiklocal-radio://`
- iOS Bundle ID / Android Application ID：`com.chanmo.tiklocal.radio`
- App 初始版本：`0.1.0 (1)`，本地配置作为首版 seed；EAS production 使用远端版本源并自动递增 build version。
- Server 与 App 独立版本，协议使用 `/api/v1` 演进。

开发使用 Expo Development Build；内部测试使用 EAS `preview`；无设备签名的 iOS 静态安装检查可使用 `preview-simulator`；正式发布使用 TestFlight / App Store 与 Android APK / Google Play。

本地真机有两种明确模式：

- Development Build 由 `npm run ios:device` 安装，运行时必须由 `npm start` 提供
  Metro bundle；Development Client 中的 URL 不是 TikLocal Server 地址。
- 本地独立体验由 `npm run ios:release` 安装，生产 JavaScript bundle 内嵌，不依赖
  Metro。只有进入 Radio 配对页后，才输入或扫描 TikLocal Server 地址。

`apps/radio/store/` 已准备双语隐私政策和中英文商店元数据草案。公开 GitHub 仓库可承载首版 Privacy Policy URL；文案刻意不承诺尚未真机验收的锁屏、后台与耳机行为。iOS 明确声明不使用非豁免加密，EAS preview 固定输出内部安装包，production 输出 App Store 构建与 Android App Bundle。

`.easignore` 明确排除本地 `android/`、`ios/`、依赖、测试与商店材料，让云端使用
受版本控制的 Expo 配置重新生成原生工程，并避免上传本地构建产物。首次账号接入使用
`eas init` 写入真实 project ID，不在仓库中预填或猜测。

Android 本地发布门槛已经验证：

- JDK 17、SDK / target 36、Build Tools 36.0.0、NDK 27.1.12297006、CMake 3.22.1。
- `assembleDebug`、`assembleRelease` 与 `bundleRelease` 均通过。
- 本地 release APK 内含 Hermes bundle 与 Demo 音频，可脱离 Metro 启动。
- 本地 APK / AAB 使用仓库生成工程中的 Android Debug 证书，只用于编译与安装验证；商店发布必须交给 EAS 或正式 keystore 重新签名。

## 风险与权衡

- `expo-audio` 当前能覆盖 MVP，但系统队列、车载或极端后台场景可能暴露平台差异；先用真机验收数据决定是否更换播放器。
- 播放器选型已收敛：`0.1.x` 继续使用 `expo-audio`，只承诺系统及耳机播放/暂停，不支持耳机、锁屏或通知的下一首/上一首。RN Track Player v5 存在开源再分发许可门槛，v4 不满足当前新架构与构建要求；详见 `docs/radio-player-selection.md`。
- 睡眠定时当前依赖 JavaScript timer，后台冻结可能影响触发时间；真机 30 分钟锁屏测试属于 P0，未通过时需移除后台可靠性暗示或改用原生定时能力。
- Bearer Header 已进入 `expo-audio` 音源，但后台恢复是否始终保留 Header 仍需真机验证；只有验证失败时才引入短期签名 URL。
- 手动输入允许局域网 HTTP：iOS 仅声明 Local Networking，Android 通过官方 `expo-build-properties` 开启 cleartext。配对页明确提示只在可信局域网使用 HTTP；正式分发仍优先推荐 TikLocal HTTPS。
- 扫码使用 `expo-camera`，只在用户主动打开扫描器后申请相机权限，限制为 QR 类型且不保存图像。Android 最终 release APK 有 `CAMERA`、没有 `RECORD_AUDIO`；iOS 只有相机用途说明、没有麦克风用途说明。
- 二维码可能被同一空间中的其他人拍到，因此授权保持两分钟、单次使用，并在 App 端兑换前再次显示 Server 地址要求确认。它适合可信现场配对，不替代 TLS。
- 同仓库能降低协议联调成本，但根目录不能演化为混杂的 JS monorepo。
- Demo Mode 会增加少量资源体积，但能让原生播放在 Server API 完成前可测，也为商店审核提供稳定入口。
- 小型模块化单体会保留少数较长文件；这是为了保证业务流程连续可读，而不是忽略边界。
- Android 通过 `blockedPermissions` 显式移除 Expo 模板或依赖带入、但 Radio 不需要的悬浮窗、外部存储和生物识别权限。release 包只保留网络、音频、前台媒体服务、唤醒与通知振动所需权限。
- iOS 在 config plugin 层显式移除未使用的麦克风与 Face ID 用途说明；最终 `Info.plist` 保留 `audio` 后台模式、局域网说明及 `ITSAppUsesNonExemptEncryption=false`。
- 2026-07-25 的 npm 公告库对完整依赖树报告 26 项 high、11 项 moderate、无 critical；`--omit=dev` 仍报告 10 项 high、11 项 moderate。结果同时包含 React Native 随包发布的 Jest preset、构建工具和虚拟列表依赖，不能等同于最终二进制攻击面，但也不再宣称“无 high”。自动修复建议把 React Native 降至 0.84、Expo 降至 46 或 `jest-expo` 降至 32，均破坏 SDK 57 兼容性，因此不执行 `audit fix --force`，等待兼容的上游修复并持续复核。

## 验证方式

- 纯状态转换与 API 协议使用确定性测试。
- 原生 Player 不做大规模 Mock，以 iPhone 真机检查清单为主。
- 客户端采用 Expo 官方的 `jest-expo` 与 React Native Testing Library，不另建 reducer 或依赖注入层。测试直接运行 `useRadioSession`，只替换原生 Player，并通过 Fetch 替身经过真实 `api.ts`。
- 当前 58 项客户端测试按现有边界组织：
  - Radio Session：受保护音源装载、快速切换电台的旧响应隔离、401、离线保留、空库控制和睡眠定时。
  - App 生命周期：启动恢复、冷启动/前台深链、非法 URL 隔离、SecureStore 读取失败、401 断开、保存失败撤销新令牌、切换 Server、进入 Demo。
  - Server API：地址与配对链接规范化、一次性授权兑换、协议版本、Bearer Header、曲目映射、收藏/反馈、错误 Envelope、网络失败和 12 秒超时。
  - Storage：有效 Profile、未存储状态、损坏 JSON、不完整数据，以及单 JSON 条目的保存与清理。
  - Pairing / Scanner / Radio UI：扫码权限、QR-only、无效码恢复、目标确认、粘贴与手动配对、错误提示、异步禁用、配对导航、电台选择、播放动作、活动状态、空库禁用和播放进度语义。
- 每个阶段记录源码文件数、直接依赖数和最长文件，判断复杂度是否收敛。
- 服务端全量回归为 119 项通过；TypeScript strict、Expo 配置、原生工程生成以及 iOS / Android production bundle 均通过。此次 Expo Doctor 在线检查因 Expo API TLS 连接中断未完成，不能作为当前绿色证据。
- 仓库主 GitHub Actions 的独立 `radio` job 使用 Node.js 22 + `npm ci`、TypeScript、客户端测试、固定版 Expo Doctor、双平台 production bundle 与 Demo 音频资源解析构成无真机静态门禁；Python 发布构建依赖该 job。
- 当前业务源码为 10 个、共 2676 行；7 个测试文件共 1703 行。新增的 `PairingScanner.tsx` 是相机生命周期边界；扫码、粘贴、深链和手动配对共享连接流程，没有新增 Hook、Repository、依赖注入或共享测试框架。
- UI 测试只查询 role、accessible name、state、value 和用户可见文本，不保存结构 Snapshot。测试暴露并促成配对输入、自定义按钮与播放进度的显式无障碍语义；布局和视觉状态保持不变。
- 客户端正式图标由项目专属视觉稿生成，并接入 iOS App Icon、Android adaptive icon 与原生启动页。
- Android Debug APK、含生产 bundle 的本地 release APK 和 release AAB 均完成原生编译；加入扫码、安全区和深链处理后再次完成 release APK 编译。最终 APK 已核验 `tiklocal-radio` 的 VIEW/BROWSABLE intent filter，权限仍只有相机而没有录音。
- iOS Pods 已成功安装 99 个 Pod，包含 Expo Camera 的条码扫描实现和安全区原生模块；完成 Xcode 首次运行与 iOS 平台组件准备后，已使用 Personal Team 在 iPhone 真机完成 Release 编译、签名、安装和进程启动。Release 内嵌生产 JavaScript bundle，不依赖 Metro。

## 后续事项

- [x] 固化架构与复杂度约束。
- [x] 完成首轮 code-slim 审计，删除不可达防御与测试偶然复杂度。
- [x] 完成 Demo Radio 原生播放纵向切片。
- [ ] 在 iPhone Development Build 验证后台播放、锁屏信息和耳机操作。
- [x] 实现 `/api/v1` 配对、设备令牌与受保护的 Range 媒体流。
- [x] 实现 Web 一次性二维码授权、App 扫码确认与手动配对回退。
- [x] 闭合 `tiklocal-radio://` 冷启动与前台深链，并在兑换前显示目标 Server。
- [ ] 真机验证相机授权、二维码识别、过期/重复授权提示和目标确认流程。
- [x] 接入真实电台、收藏、反馈和基础断线恢复。
- [ ] 真机确认 Bearer Header 后决定是否需要短期签名播放 URL。
- [x] 补充设备列表、自撤销与浏览器单设备撤销入口。
- [x] 接入正式图标、Android adaptive icon 与原生启动页。
- [x] 完成 Android Debug / release APK 与 release AAB 原生编译和权限核验。
- [x] 固化首版版本号、EAS profiles、加密声明、双语隐私政策与商店文案草案。
- [x] 将 Radio 类型、Expo 依赖健康度和双平台 production bundle 纳入主 CI。
- [x] 为 Radio Session 增加确定性测试，并纳入主 CI。
- [x] 完成播放器选型，固定 `0.1.x` 的远程媒体能力边界。
- [x] 修复本机 Xcode 系统组件并完成 iPhone 真机 Release 编译、签名、安装与启动。
- [ ] 登录 Expo / Apple / Google 账号，关联 EAS project 并建立 preview、TestFlight 与 Play 内测流程。
- [ ] 按 `apps/radio/store/device-acceptance.md` 完成双平台 P0 验收；远程切歌不属于 `0.1.x` 验收范围。

## 相关文件/模块

- `apps/radio/`
- `tiklocal/radio_client.py`
- `tiklocal/services/device_auth.py`
- `tiklocal/services/pairing_grants.py`
- `tiklocal/services/radio.py`
- `tests/test_radio.py`
- `tests/test_radio_client.py`
- `docs/radio-player-selection.md`
