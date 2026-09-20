# TikLocal 本地优先原生 App 架构

- 状态：第一阶段纵向链路与本地存储生命周期已落地，iPhone Release 已安装启动，等待完整真机与大媒体库验收
- 更新时间：2026-08-26

## 背景与目标

TikLocal 原生客户端最初只承载依赖 TikLocal Server 的 Radio 能力。新的产品方向不是把 Flask / Python Server 原样嵌入 iPhone，而是把移动端高频、可独立成立的核心能力下沉到设备：用户从系统照片或文件导入自己的图片和视频，App 在无账号、无网络、无 Server 的情况下完成持久化、浏览和沉浸式播放。

这一方向把产品从“Server 遥控器”扩展为“本地优先的私人媒体 App”，同时保留 TikLocal Server 作为可选增强源，而不是首屏前置条件。

## 关键决策

### 1. 不在 iOS 内嵌现有 Flask 后端

现有后端包含 Python 运行时、目录扫描、Web 路由和面向桌面文件系统的假设。把它整体移入 iOS 会增加包体、签名、沙盒适配、后台执行和 App Review 风险，也会形成两套难以同步的运行环境。

原生 App 只复用产品概念与数据语义，不复刻 Server 进程：

- 原生 UI 负责导入、浏览与播放。
- App Documents 目录保存由用户明确导入的媒体副本。
- SQLite 保存本地媒体事实与后续推荐信号。
- TikLocal Server 继续提供 Radio、远端媒体库和跨设备能力，并逐步变成可选 Source。

### 2. 导入即建立受 App 管理的离线副本

第一阶段支持 Photos 与 Files 两种显式导入入口。选中的图片或视频复制到 App Documents 下的 `tiklocal-media/`，不依赖原资源继续存在，也不修改或删除系统相册与文件中的原件。

这个选择以占用额外存储为代价，换取稳定的离线可用性、统一文件 URI 和更清晰的隐私边界。未来如果增加“仅引用系统相册”模式，必须单独处理权限变化、iCloud 占位文件和资源失效，不能暗中改变当前语义。

### 3. SQLite 是本地媒体清单的事实来源

数据库 `tiklocal-local-library.db` 保存媒体 ID、类型、文件名、URI、来源、尺寸、时长、大小、导入时间、来源去重键和派生缩略图 URI。读取清单时会移除已丢失文件对应的失效记录。

当前数据模型保持小而直接，后续可在真实需求出现时增加：

- 感知哈希；
- 收藏、隐藏和集合；
- 查看、停留、跳过等本地推荐信号；
- Server Source 与同步状态；
- 可解释的设备内推荐分数。

不要在第二种 Source 出现前预建通用 Repository、同步引擎或多层领域模型。

### 4. 网络下载器不属于首个商店版本

当前范围明确不包含第三方短视频 URL 下载、平台解析、去水印或绕过访问控制。这些能力会显著增加版权、平台条款、内容审核和 App Review 风险，也会模糊“用户管理自己的媒体”这一清晰定位。

首个可营收版本应围绕用户主动选择、拥有或有权访问的本地媒体建立价值。

## 当前产品结构

```text
Flow（默认入口）
├── 空状态直接从 Photos / Files 导入
├── 独立读取 Local SQLite index
├── Full-screen offline Flow
└── Shuffle session
Library
├── 导入、网格浏览与本地副本管理
└── 指定媒体跳转到 Flow
Music
├── Built-in Demo Signal
└── Optional TikLocal source
Settings
├── 本机私人资料库状态
├── 隐私边界
└── Optional TikLocal Folder
```

App 启动时并行读取本地媒体数量和已有 Radio 连接，随后直接进入 Flow，不再经过模式选择首页。底部固定为 `Flow / Library / Music / Settings` 四个顶层空间：前两项构成照片与视频主产品，Music 是次级体验空间，TikLocal 则在 Settings 中表现为可选 Folder Source。本地能力不因 Source 缺失或离线而降级；进入 Music 时继续沿用现有 `known` / `paired` 连接状态、SecureStore 令牌和队列恢复逻辑。

## 第一阶段实现

### 本地资料库

- `apps/radio/src/localLibrary.ts`：文件复制、SQLite 版本迁移、索引、去重、空间预检、视频缩略图、删除和失效记录清理。
- `apps/radio/src/FlowScreen.tsx`：默认产品入口、独立资料库读取、空 Flow 导入、指定媒体启动和 Shuffle 会话。
- `apps/radio/src/LocalLibraryScreen.tsx`：Photos / Files 导入、确定进度、剩余空间、视频预览、三列媒体网格、长按多选、删除 / 清空和 Play all。
- `apps/radio/src/LocalFlowScreen.tsx`：纵向分页、图片展示、视频自动播放与循环、离屏暂停、手动暂停与根 Flow 内容层。
- `apps/radio/src/SettingsScreen.tsx`：本机资料库、隐私说明和可选 TikLocal Folder Source 入口。
- `apps/radio/App.tsx`：四个顶层空间，以及连接 / 配对模态流程的统一导航入口。
- `apps/radio/modules/tiklocal-storage/`：最小 Expo 本地模块，设置 iOS backup exclusion，并通过 AVFoundation / MediaMetadataRetriever 为本地视频生成持久化 JPEG 预览。

### 原生依赖

- `expo-image-picker`：由用户选择 Photos 资源。
- `expo-document-picker`：由用户选择 Files 资源。
- `expo-file-system`：复制和管理 App 沙盒内媒体。
- `expo-sqlite`：持久化本地媒体清单。
- `expo-video`：播放导入的视频。
- `@react-navigation/bottom-tabs`：承载稳定的四个顶层产品空间。

这些依赖包含原生模块。修改依赖或 `app.config.ts` 后，Development Build、Release 和商店包都必须重新生成原生工程并构建；只重启 Metro 不足以验证。

## 隐私与 App Store 边界

- Photos 权限只在用户主动点击导入时申请。
- Files 通过系统文档选择器获取用户明确选择的项目。
- 导入媒体只保存在 App 沙盒和本地 SQLite 中，第一阶段不上传、不建账号、不跟踪用户。
- 导入媒体目录及新复制文件在 iOS 上标记为不进入 iCloud 设备备份，避免大媒体副本占用用户云空间；SQLite 索引和偏好仍可能随操作系统备份。
- 单项删除与清空先删除 App 管理的文件，再删除 SQLite 记录；系统 Photos / Files 中的原件不受影响。
- App 必须清晰说明清空资料库或删除 App 会删除 App 管理的离线副本，原件不受影响。
- 商店隐私标签、隐私政策和截图应与实际数据流一致；增加分析、云同步或订阅校验前必须重新审查。

## 兼容与迁移

- 原生 App 的当前工作品牌为 `LumaFold`，定位是私密、离线的照片与视频 Flow；Music 是次级空间，`TikLocal` 继续作为开源项目与远程媒体来源品牌。连接能力在产品中称为可选 `TikLocal Folder`，配对步骤仍准确说明它由 TikLocal Server 提供。
- 工作品牌只改变用户可见名称、候选图标、启动页和产品文案。Expo slug、`tiklocal-radio://` URL Scheme、`com.chanmo.tiklocal.radio` bundle/application ID、SQLite 路径、SecureStore Key 与 Server `/api/v1` 协议暂不改动，因此覆盖安装不需要本地数据或配对迁移。
- 原 TikLocal Radio 配对、设备令牌、Demo Signal、后台音频和恢复链路保持不变。
- 已保存的 Radio Profile 无需迁移；四 Tab 导航与 TikLocal Source 文案不修改 SecureStore 数据格式。
- LumaFold 名称与 The Fold 标志仍允许在正式发布前调整；品牌源文件集中在 `apps/radio/brand/`，旧 `assets/icon.png` 保留，不以覆盖旧资源的方式锁死方向。
- 本地媒体数据库使用 `PRAGMA user_version` 管理 schema。当前为版本 2：未标记数据库先建立 v1 表与索引，v1 再通过独立事务增加 `thumbnail_uri`；高于客户端支持版本的数据库会停止打开，避免旧代码误写新 schema。
- 任何破坏性 schema 变化都必须提供事务迁移或明确、可恢复的重建路径，并增加从上一版本升级的测试。

## 已知限制与风险

- 导入会产生完整副本，大视频可能快速占用设备空间；当前显示实际占用与设备剩余空间，并在复制前按已知文件大小预检、保留 128 MB 安全余量。来源未提供大小时仍只能依赖复制错误恢复。
- Files 提供的尺寸、时长等元数据可能不完整；第一阶段允许为空。
- 视频缩略图在导入时生成；v1 旧视频进入资料库后逐项回填。生成失败只回退到类型占位，不影响原视频播放。
- 尚未验证 HEIC、Live Photo、HDR、ProRes 和少见容器在真实设备上的完整行为。
- 当前列表适用于第一阶段规模，超大资料库仍需分页、缩略图并发限制和可跨进程恢复的导入任务状态。
- iOS 后台不适合作为无限制媒体扫描环境；后续索引应围绕用户触发与可恢复的小批任务设计。

## 发布前验收

- 在真实 iPhone 上分别从 Photos 与 Files 导入图片、短视频和大视频。
- 开启飞行模式并彻底退出 Server，确认 Flow 默认入口、资料库和本地播放全链路可用。
- 验证重复导入、导入中断、磁盘空间不足、权限拒绝和源文件随后被删除。
- 验证删除 / 清空只影响 App 副本，重启后记录不再出现，系统 Photos / Files 原件仍可打开。
- 用最终 iOS 构建核验 `tiklocal-media/` 的 backup exclusion 标记，并确认 SQLite 与偏好保留正常系统备份语义。
- 验证视频声音、暂停、循环、切页离屏暂停，以及来电和前后台切换。
- 分别使用 500、5,000 和 20,000 条媒体测试启动时间、滚动、内存和数据库查询。
- 重新生成 iOS / Android 原生工程，核验最终权限清单与商店隐私声明。
- 完成 LumaFold 名称可用性、最终图标、bundle identifier 是否迁移、订阅或买断方案及现有 Radio 用户迁移决策。

## 后续建议顺序

1. 完成双平台真机与大媒体库验收，修复导入和播放边界。
2. 增加媒体详情、导入取消 / 恢复，以及磁盘空间不足后的批次恢复提示。
3. 增加收藏、隐藏、集合与本地行为信号，形成可解释的个人 Flow。
4. 将已配对 TikLocal Server 作为第二种可选媒体 Source，而不是登录门槛。
5. 用真实留存与付费访谈验证高级功能，再决定买断、订阅或混合定价。

## 相关文档

- `docs/radio-native-client-architecture.md`
- `docs/media-index-and-recommendation.md`
- `apps/radio/brand/README.md`
- `docs/mixed-feed-design.md`
- `docs/release_notes.md`
