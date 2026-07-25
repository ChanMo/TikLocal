# TikLocal Radio 播放器选型

- 状态: 已决策
- 决策日期: 2026-07-25
- 适用版本: TikLocal Radio `0.1.x`

## 决策摘要

`0.1.x` 继续使用 Expo SDK 57 自带的 `expo-audio`，明确支持 App 内下一首、系统播放/暂停、锁屏媒体信息和耳机断开自动暂停；不承诺耳机或锁屏“下一首 / 上一首”。

当前不安装 RN Track Player，也不为一个尚未通过真机验证的交互自建原生播放引擎。远程切歌变成核心需求后，先检查稳定版 `expo-audio` 是否已经补齐事件；仍未提供时，再在“取得 RN Track Player v5 的书面再分发许可”和“自建一方原生播放器”之间重新决策。

## 决策上下文

### 必须满足

- 兼容 Expo SDK 57、React Native 0.86 和强制启用的新架构。
- 支持后台音频、锁屏元数据、系统播放/暂停和带 Bearer Header 的远程媒体。
- 能随 TikLocal 的 MIT 开源仓库合法构建、修改和再分发。
- 不显著扩大当前 8 个业务源码文件和约 5 个直接业务依赖的复杂度预算。
- 能通过 Expo CNG / EAS 重建原生工程，不依赖长期维护手改生成目录。

### 希望满足

- 耳机、锁屏和车载的下一首 / 上一首。
- 原生队列、缓存和更强的后台恢复。
- iOS 与 Android 使用一致的业务 API。

远程切歌是重要体验，但不是 `0.1.x` 的发布阻断项；后台稳定性、播放/暂停和凭证媒体流才是第一阶段的发布门槛。

## 候选方案

| 方案 | 社区健康 25 | 依赖质量 20 | 文档 20 | 可信度 20 | 项目适配 15 | 总分 | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `expo-audio` 57 | 24 | 19 | 18 | 19 | 11 | **91** | `0.1.x` 采用 |
| RN Track Player v5 | 23 | 14 | 18 | 18 | 9 | **82** | 许可门槛，不采用 |
| 一方 Expo 原生模块 / 播放引擎 | 18 | 15 | 14 | 13 | 8 | **68** | 条件性后备 |
| RN Track Player v4 | 10 | 7 | 16 | 14 | 4 | **51** | 架构与构建风险，不采用 |

分数是针对 TikLocal 当前约束的工程判断，不代表库的通用质量。存在硬性门槛时，总分不能覆盖淘汰条件。

### `expo-audio` 57

优点：

- Expo 官方维护，与当前 SDK、CNG、EAS 和新架构同一升级节奏。
- 当前实现已经覆盖后台模式、锁屏元数据、系统播放/暂停、进度和带 Header 的音源。
- 无需增加播放器依赖、后台服务注册和第二套状态模型。

限制：

- 当前单 `AudioPlayer` 没有向 JavaScript 暴露系统下一首 / 上一首事件。
- `AudioPlaylist` 有队列动作，但当前没有对应的锁屏媒体控件激活接口，不能据此承诺耳机远程切歌。
- 极端后台恢复、Header 保留和长时间睡眠定时仍需真机验证。

### RN Track Player v5

技术能力最接近长期目标：新架构、远程媒体事件、原生队列、缓存和车载能力都优于当前方案。但 v5 使用自定义许可；公开许可文本限制商业使用和再分发，商业授权页面也按 App 收费。TikLocal 是可公开构建和派生分发的 MIT 项目，在取得明确书面再分发许可前不能引入。

这不是单纯的价格判断。即使购买商业订阅，也必须确认它是否允许把依赖纳入公开源码、CI 构建和第三方派生 App；不能把“可在一个 App 中使用”推定为“允许开源再分发”。

### RN Track Player v4

v4 使用 Apache-2.0，许可更适合开源项目，但不再是当前主线。隔离 PoC 得到以下结果：

- Expo Doctor 将 `react-native-track-player` 标记为不支持新架构。
- 包内原生构建基线仍包含较旧的 Android Gradle Plugin、Kotlin 和 React Native 设置。
- Android 构建需要从 JitPack 解析 KotlinAudio；即使网络端点可访问，Gradle 依赖解析仍失败。
- React Native 0.82 起新架构已无法关闭，因此不能把关闭新架构当作 Expo 57 的兼容方案。

继续修补 Gradle 文件只能把第三方兼容成本转移到 TikLocal，不符合首版复杂度目标。

### 一方 Expo 原生模块 / 播放引擎

Expo Modules API 可以构建新架构兼容的本地模块，但“监听一个远程按键事件”并不是可靠解法：Android 后台媒体按键由拥有 `MediaSession` 和前台服务的播放器处理，JavaScript 还可能被冻结。若 `expo-audio` 不转发下一首事件，一方方案最终很可能需要自己拥有原生队列、播放器服务和媒体会话。

因此它是可控但昂贵的后备路线，不应伪装成一个很薄的桥接模块。只有远程切歌、CarPlay 或 Android Auto 被确认为产品核心后，才值得启动限定范围的原生引擎 PoC。

## 已排除方案

- `react-native-audio-pro`：仓库已于 2026-02-17 归档，不接受新维护投入。
- `react-native-audio-api`：定位是实时音频生成、处理和分析，不是系统后台媒体队列。
- 在生成的 `ios/`、`android/` 中直接补媒体按键：会绕过 CNG，并与 `expo-audio` 的媒体会话所有权冲突。
- 同时保留 `expo-audio` 与另一套播放器：会复制播放状态、媒体会话和平台生命周期，违反单一事实来源。

## 实施边界

`0.1.x` 的能力口径固定为：

- App 内：播放、暂停、下一首、收藏、Encore 和睡眠定时。
- 系统媒体：播放、暂停、进度和曲目信息，必须经真机验收后才写入商店描述。
- 耳机：播放/暂停与断开自动暂停，必须经真机验收。
- 不支持：耳机、锁屏或系统通知的下一首 / 上一首。

暂不修改 `player.ts` 的抽象结构，也不预建 `PlaybackEngine` 接口。未来出现第二个可用实现时，先按真实 API 差异改造调用点，再提取最小接口。

## 风险与复审触发器

| 风险 / 变化 | 当前处理 | 触发动作 |
| --- | --- | --- |
| 用户强烈依赖耳机下一首 | `0.1.x` 明确不承诺 | 将远程切歌提升为 P0，重新选型 |
| Expo 新稳定版暴露远程下一首事件 | 跟随 SDK 57 | 升级 PoC 后优先保留官方方案 |
| RNTP v5 许可变化或取得书面许可 | 当前禁用 | 复核公开源码、CI 和派生分发权 |
| 真机后台播放或 Header 恢复失败 | 保留发布门槛 | 先定位平台缺口，再决定签名 URL 或播放器替换 |
| CarPlay / Android Auto 进入近期路线图 | 当前不做 | 直接重新评估原生队列和媒体服务所有权 |

复审时必须重新运行 Expo Doctor、双平台 production bundle、至少一个 Android 原生构建，并在真机验证后台、锁屏和耳机事件；不能只比较 JavaScript API。

## 资料来源

- [Expo Audio（SDK 57）](https://docs.expo.dev/versions/v57.0.0/sdk/audio/)：官方 API 与后台播放配置；2026-07-25 查阅。
- [Expo Modules API](https://docs.expo.dev/modules/overview/)：官方新架构原生模块方案；2026-07-25 查阅。
- [Expo SDK 57 发布说明](https://expo.dev/changelog/sdk-57)：官方 React Native 版本和 SDK 基线；2026-07-25 查阅。
- [React Native 0.82：新架构成为唯一运行时](https://reactnative.dev/blog/2025/10/08/react-native-0.82)：官方兼容边界；2026-07-25 查阅。
- [RN Track Player 仓库](https://github.com/doublesymmetry/react-native-track-player)：版本、维护状态与源码；2026-07-25 查阅。
- [RN Track Player v5 许可](https://github.com/doublesymmetry/react-native-track-player/blob/main/license.txt)：使用与再分发限制的一手文本；2026-07-25 查阅。
- [RN Track Player 商业授权](https://www.rntp.dev/pricing)：官方授权口径与价格；2026-07-25 查阅。
- [RN Track Player v4 安装文档](https://rntp.dev/docs/basics/installation)：旧主线官方文档；2026-07-25 查阅。
- [react-native-audio-pro 仓库](https://github.com/evergrace-co/react-native-audio-pro)：归档状态；2026-07-25 查阅。
