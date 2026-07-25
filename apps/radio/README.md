# TikLocal Radio

TikLocal 的原生 Radio 伴侣客户端。当前版本可扫描 TikLocal Web 设置页生成的一次性二维码完成单 Server 配对，也保留粘贴配对链接、手动地址与访问密码以及内置 Demo Signal。

## 本地运行

```bash
cd apps/radio
npm install
npm run typecheck
npm test
npm run ios:device
```

`npm run ios:device` 会生成并安装 iOS Development Build。它不包含可独立运行的
JavaScript bundle；之后日常开发必须先启动 Metro：

```bash
npm start
```

在手机打开 TikLocal Radio 后，从 Expo Development Client 选择自动发现的 Metro
开发服务器。该界面的 URL 是 JavaScript 开发服务器，通常使用 `8081` 端口；不要
在这里输入 TikLocal Server 地址，否则 HTML 会被当作 JavaScript bundle，并出现
`Expected MIME-Type ... but got text/html`。

进入真正的 TikLocal Radio 配对页后，才输入或扫描 TikLocal Server 地址，例如
`http://192.168.0.128:8888`。

原生模块或 `app.config.ts` 发生变化后，需要重新执行 `npm run ios:device`。

如果希望像普通 App 一样独立启动、不依赖 Metro，安装本地 Release：

```bash
npm run ios:release
```

Release 会把生产 JavaScript bundle 和 Demo 音频嵌入 App；安装后直接进入 TikLocal
Radio，不会显示 Development Client 启动页。

首次进入 Radio 配对页时，优先在 TikLocal Web 设置页生成两分钟有效的一次性二维码并扫描。App 会显示目标 Server，确认后才兑换设备令牌；也可粘贴配对链接，或手动输入 Server 地址和访问密码，例如：

```text
https://studio-mac.local:8443
```

二维码不含访问密码或设备令牌，Server 只在内存中保存一次性授权的哈希。配对成功后，访问密码和一次性授权都不会保存；App 只在 SecureStore 中保存 Server 返回的设备令牌。修改 TikLocal 访问密码会让既有授权与设备令牌失效并要求重新配对。

切换到 Demo Signal 时，App 会尽力撤销当前设备令牌。也可以在 TikLocal Web 设置页的“Radio 客户端”区域查看并撤销指定设备。

## 构建分发

首次使用 EAS 时先登录并关联 Expo 项目：

```bash
npx eas-cli login
npx eas-cli init
npx eas-cli build:configure
```

`eas init` 会把 Expo 项目的真实 `projectId` 写入 App 配置；不要手工编造该 ID。现有
`eas.json` 已完成 Build profile 配置，`build:configure` 只用于让 CLI 检查并补齐
项目状态。

内部安装包：

```bash
npx eas-cli build --profile preview --platform ios
npx eas-cli build --profile preview --platform android
```

iOS Simulator 包不需要物理设备签名，可单独生成：

```bash
npx eas-cli build --profile preview-simulator --platform ios
```

商店构建：

```bash
npx eas-cli build --profile production --platform ios
npx eas-cli build --profile production --platform android
```

应用标识、正式图标、启动页和 EAS profiles 位于 `app.config.ts`、`assets/` 与 `eas.json`。版本从 `0.1.0 (1)` 起步，EAS production 构建会递增远端 build version，避免本地反复改号。

`.easignore` 会排除本地生成的原生工程、依赖、测试、商店材料与构建输出。EAS 上传仍
包含运行所需的 `src/`、入口、配置、锁文件和 `assets/`；修改忽略规则后应先用
`eas build:inspect --stage archive` 检查实际上传内容。

隐私政策、中英文商店文案草案和逐项真机验收表位于 `store/`。仓库已公开，因此合并到 `main` 后可将隐私政策文件的 GitHub 页面用作首版公开 URL；正式外部分发仍需签名账号、商店截图和真机验收结果。

在无法使用真机时，可先执行不安装 App 的静态验证：

```bash
npx expo prebuild --no-install
npx expo export:embed --platform ios --dev false --entry-file index.ts --bundle-output /tmp/tiklocal-radio-ios.jsbundle
npx expo export:embed --platform android --dev false --entry-file index.ts --bundle-output /tmp/tiklocal-radio-android.bundle
```

仓库主 CI 会在 Node.js 22 下从 `package-lock.json` 执行 `npm ci`、TypeScript、58 项 App / Session / API / Storage / Screen 测试、固定版本 Expo Doctor，以及带 Demo 音频资源复制的 iOS / Android production bundle。该门禁不需要 Expo、Apple 或 Google 凭据，也不替代真机相机与媒体行为验收。

### Android 本地原生构建

React Native 使用 JDK 17。首次准备构建机：

```bash
brew install openjdk@17
brew install --cask android-commandlinetools
export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export ANDROID_HOME="$HOME/Library/Android/sdk"
yes | sdkmanager --sdk_root="$ANDROID_HOME" --licenses
sdkmanager --sdk_root="$ANDROID_HOME" \
  "platform-tools" "platforms;android-36" "build-tools;36.0.0" \
  "ndk;27.1.12297006" "cmake;3.22.1"
```

生成并验证本地安装包：

```bash
npx expo prebuild --clean --no-install --platform android
cd android
NODE_ENV=production ./gradlew :app:assembleRelease :app:bundleRelease
```

生成物位于 `android/app/build/outputs/apk/release/` 与 `android/app/build/outputs/bundle/release/`。生成工程默认用 Android Debug 证书签署 release 产物，仅用于本地验证，不能提交商店；正式签名使用 EAS production profile 或独立 keystore。

`app.config.ts` 会阻止悬浮窗、外部存储、生物识别和录音等未使用权限。扫码只申请相机权限；修改权限后必须重新 `prebuild`，并以最终 APK / AAB 的 merged Manifest 为准。

iOS 同样显式移除了依赖默认带入、但当前产品不使用的麦克风和 Face ID 用途说明；`Info.plist` 保留扫码相机、后台音频、局域网访问与标准加密声明所需配置。

### iOS 本机构建前置

首次使用当前 Xcode 时先完成组件初始化：

```bash
sudo xcodebuild -runFirstLaunch
```

连接新 iPhone 后，需要在手机信任 Mac、开启 Developer Mode，并在 Xcode 的
Signing & Capabilities 中选择自己的 Team。若 Xcode 报对应 iOS platform 未安装，
可执行 `xcodebuild -downloadPlatform iOS`。

## 代码约束

不要在这里预建通用分层。新增依赖、模块或目录前，先检查 `docs/radio-native-client-architecture.md` 中的真实边界与拆分门槛。更换播放器或增加系统远程控制前，还必须复核 `docs/radio-player-selection.md` 的许可、新架构和复杂度门槛。

会话测试直接运行 `useRadioSession`，只在原生播放器边界使用稳定替身，并通过 Fetch 响应驱动真实 API 客户端。不要为了测试把会话复制成 reducer、Repository 或第二套状态机。

App 测试只替换页面渲染、API 和存储边界，验证 Profile 的拥有权与令牌顺序；Storage 测试直接约束单个 SecureStore JSON 条目。测试文件与其边界对应，不按单个动作继续拆分。

API 测试直接替换 Fetch，覆盖请求与响应协议，不复制 DTO 或另建假客户端。除超时使用 Jest fake timers 外，测试不依赖真实时钟或网络。

Screen 测试以 role、accessible name、state 和 value 驱动真实用户动作，不保存组件树 Snapshot，也不根据 StyleSheet 断言视觉实现。新增控件时应先提供可理解的无障碍名称，再编写语义查询。
