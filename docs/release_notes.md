# Release Notes

## 未发布
- 默认启用单密码访问认证：全局保护页面、API、媒体流与管理操作，登录后保留完整功能权限。
- 新增独立登录页、长期会话、全局 CSRF 防护、登录限流与安全响应头；首次启动自动生成密码，密码仅以 scrypt 哈希保存。
- 新增 `tiklocal auth status` 与 `tiklocal auth set-password`，运行中改密会立即使已有会话失效。
- Flow 视频恢复从开头播放，保留条目顺序随机，移除会破坏叙事并增加切换竞态的随机进度起播。
- 视频首帧已预加载时直接揭示；尚未准备好时使用同步出现、仅淡出的加载层，避免切换时暴露黑帧、旧帧或遮罩亮度脉冲。

## v0.8.30 (2026-07-19)
- 新增独立 Home：以 Flow / Radio 双模式入口为主视觉，并聚合最近加入、重新遇见、个人集合与媒体库状态；首页只加载缩略图，不自动播放媒体。
- 沉浸混合流从 `/` 迁移至 `/flow`，桌面端采用窄侧栏导航，移动端保留 Flow / Radio 极简切换，并统一 Settings 与 Download 的页面顶部设计。

## v0.8.29 (2026-07-13)
- 优化 Flow 随机起播的首帧体验：随机位置准备完成后再揭示视频，并提前预 seek 下一条视频，避免封面、首帧与随机帧连续跳变。
- 修复短视频与 Live Photo 偶发闪烁放大的问题：非随机起播视频直达真实首帧，封面完成解码且仍匹配当前视频时才允许显示，隔离快速切换产生的异步竞态。

## v0.8.28 (2026-07-13)
- 修复 Library、Favorites 与 Collection 在移动端正常滚动时偶发跳回顶部的问题：仅在瀑布流宽度、列数或间距真正变化时执行重排，忽略浏览器地址栏收放引发的高度型 `resize`。

## v0.8.27 (2026-07-12)
- 新增 SQLite 媒体查询索引与启动校正：统一多媒体源查询、分页、删除及下载入库链路，并安全处理临时离线媒体源。
- 优化 Flow 与 Library 加载性能：缩小首批数据量、接入按需缩略图和索引导航，并完善请求、媒体加载失败与空状态恢复。
- 建立轻量本地推荐：基于浏览、跳过和完成记录调整排序，同时保留探索与内容多样性，并支持一键重置画像。
- 重塑底部 Dock、Library 浏览区、已保存空间与设置页，使主题、搜索、集合和页面交互更加统一细腻。
- Flow 支持会话内稳定的受控随机起播，并按真实播放时长记录消费进度，避免随机跳转污染推荐反馈。
- 集合卡片升级为自适应动态拼贴封面，详情页增加紧凑身份区、主封面状态和即时更新体验。
- 下载页收敛为单链接轻量入口：支持视频/图片模式、网站与凭证自动匹配、清晰的任务操作和低频智能轮询。
- 下载组件状态、并发数量与网站登录凭证统一迁入设置页管理，保留本机存储与同名安全更新机制。

## v0.8.26 (2026-07-04)
- Radio 启动性能优化：`/api/radio/tune` 改为轻量选曲，不再首次进入时逐首读取音频元数据，适配数百首音频库。
- 新增 `/api/radio/metadata` 单曲元数据接口，前端播放当前曲目后再懒加载 title、artist、album 与 duration，并同步系统播放面板。
- 新增 Radio 本地反馈画像：记录播放、完整听完、跳过、收藏与错误事件，并将隐式反馈纳入后续选曲权重。
- Radio 页面交互细化：修复切歌标题闪现、未知时长 `Infinity:NaN`、暂停后封面旋转重置等问题。
- Radio 布局优化：移除页面不必要上下滚动，收敛 cover、标题、进度与操作按钮的垂直节奏，并让核心内容位置更协调。
- 新增 Radio 回归测试：覆盖懒加载元数据、轻量 tune 不触发 ffprobe、反馈画像写入与分数计算。

## v0.8.25 (2026-07-04)
- 新增 Radio 电台体验：以低决策连续播放替代传统音乐管理播放器，支持默认、最近添加、收藏倾向的后台选曲策略。
- Radio 页面重构为安静的中心信号物件：支持内嵌封面、无封面生成式唱片标签、慢速碟片/封面动效与更舒适的核心操作按钮。
- 新增 Radio 前端控制器与后端服务：支持下一首、收藏、30/60/120 分钟定时、最近播放排除与播放进度恢复。
- 系统播放面板增强：Media Session 增加 artwork、播放状态、时长/进度同步与 seek 支持，适配 macOS 与 iPhone 浏览器控制面板。
- 新增 Radio artwork fallback：无音频封面时生成 512x512 Radio 风格封面，避免系统播放面板空白。
- 音频元数据增强：通过 ffprobe 读取 title、artist、album、duration，并在 API 与系统播放面板中优先使用真实音乐信息。
- 新增 Radio 测试覆盖：包含选曲策略、最近播放排除、收藏优先、fallback artwork 与音频元数据解析。

## v0.8.15 (2026-02-25)
- release: v0.8.15 视频放大镜与交互统一
- feat: 支持视频放大镜并统一Flow放大策略


## v0.8.14 (2026-02-25)
- release: v0.8.14 集合弹层交互优化
- feat: 优化集合弹层为移动端抽屉并增强键盘操作


## v0.8.13 (2026-02-24)
- Release v0.8.13: fix 'function' object is not subscriptable on Python 3.12
- fix: add __future__ annotations to resolve 'function' object is not subscriptable


## v0.8.12 (2026-02-23)
- 架构收敛：新增 `flow_session.js`、`flow_actions_shared.js`、`flow_media_actions_controller.js`，统一 Home / Library / Favorites 的会话状态与媒体动作编排。
- 清理废弃能力：移除 `/browse`、`/gallery` 旧路由与 `/api/videos`、`/api/random-images` 旧接口，删除未使用模板 `browse.html`、`favorite.html`、`gallery.html`、`index.html`。
- 新增自定义集合基础能力：增加 `~/.tiklocal/collections.json`、`CollectionStore` 与 `/api/collections*` 接口，支持集合创建、增删媒体、按媒体反查所属集合。
- 新增集合页面与详情入口：增加 `/collections` 与 `/collection/<id>`，并在 Favorites/Collection 视图提供集合导航。
- Library/Favorites/Collection Quick Viewer 新增“加入集合”弹层，支持就地新建集合并即时勾选生效（无保存步骤），并显示“已加入数量”状态反馈。
- Collections 交互增强：集合页卡片改为极简信息展示（仅名称+数量），重命名/删除收敛到 `...` 菜单；重命名从系统 `prompt` 升级为页面内轻量弹层。
- 集合详情页顶部导航升级为“返回我的集合 + 当前集合名”的极简头部，替代原有可读性较弱的胶囊式导航。
- 修复 Quick Viewer 集合弹层点击竞态：避免触发打开后被同一次点击瞬间关闭（已加入打开后短时点击保护）。
- 首页 Flow 增加“加入集合”按钮与集合选择弹层，补齐与 Library/Favorites 的能力一致性。

## v0.8.10 (2026-02-22)
- 修复 Library/Favorites 的 Quick Viewer 关闭后页面滚动锁死问题：补齐 body 滚动状态恢复逻辑，确保关闭弹层后列表可继续滚动。
- Library API 增强媒体尺寸返回：`/api/library/items` 新增 `width` / `height` 字段，并在 `~/.tiklocal/metadata.json` 统一缓存图片与视频尺寸信息。
- 尺寸探测策略优化：图片使用 Pillow 读取，视频使用 ffprobe 读取；缓存命中后直接复用，减少重复探测开销。
- 修复图片 AI 元数据写入覆盖风险：生成标题/标签时改为 merge 写回，保留 `media_meta` 等已有字段。
- Library/Favorites 瀑布流渲染升级为固定列最短列分发引擎，替代 CSS 多列自动流，降低滚动加载时右侧列反复跳动与回流重排。
- 新增瀑布流响应式重排策略：仅在窗口变化时防抖重排，保持无限加载与 Quick Viewer 索引一致性。
- 更新 `tests/test_library_upgrade.py`，补充瀑布流脚本标记与 `width`/`height` 字段断言，覆盖关键回归点。

## v0.8.9 (2026-02-22)
- 信息架构升级：底部导航调整为 `Flow / Library / Favorites / Download / Settings`，其中 `Library` 成为视频+图片统一入口，`Favorites` 独立为一级入口。
- Library 交互重构为极简 Masonry：移除顶部传统筛选表单与卡片冗余文本，仅保留媒体本身的沉浸式浏览。
- 新增 `/api/library/items` 与前端无限加载：支持按 `scope=all/favorite` 分页拉取，满足大规模素材连续浏览。
- 新增 Library Quick Viewer Flow：列表内就地预览视频/图片，支持上下滑切换并保留“进入独立详情页”入口，降低跳转割裂感。
- 交互统一收敛：首页与 Library/Favorites 改为同一沉浸状态模型（视频/图片一致），放大镜作为图片工具态独立控制。
- 新增共享交互内核：`flow_state_controller.js`（状态）与 `flow_ui_shared.js`（时间/放大镜几何），降低多入口行为分叉风险。
- 兼容迁移：`/browse`、`/gallery` 改为重定向到 `/library`，详情页与删除后的回跳统一指向新 Library 入口。

## v0.8.8 (2026-02-22)
- 首页沉浸流升级为混合媒体 Feed：在同一滑动流中混排视频与图片，替代原纯视频首页链路。
- 新增 `/api/feed/mix`，统一返回 typed media items（`video` / `image`），并使用“目标比率 + 轻随机约束”混排，避免固定节奏可预测性。
- 首页图片条目复用 Gallery 关键交互：AI 标题/标签面板、2.5x/5x 圆形放大镜、单击专注模式（仅隐藏左下信息层）。
- 交互收敛：视频不显示 AI 按钮，图片不显示倍速按钮；图片不再自动计时切换，改为手动滑动切换。
- 修复首页放大镜取样计算：按 `object-fit: contain` 的真实内容框计算，避免横向压扁。
- 修复首页图片 AI 标题/标签不显示问题：调整 `currentCaptionUri` 生命周期，避免异步回写被错误丢弃。
- 清理首页混合流过期代码：移除无效 `controls-active` 状态切换与不可触发的播放图标点击监听。
- 新增 `tests/test_feed_mix.py` 覆盖混合 Feed API 基本行为，并新增混合流设计文档索引。

## v0.8.7 (2026-02-21)
- 新增“来源回跳”能力：下载成功后将文件与原始 URL 建立映射，并新增 `~/.tiklocal/download_sources.json` 持久化来源索引。
- 新增来源解析三层兜底：优先来源映射，其次 `.info.json`（`webpage_url/original_url`），最后按文件名结构推断平台链接（x/youtube/tiktok/instagram）。
- 新增来源查询 API：`GET /api/source` 与 `POST /api/source/batch`，用于详情页与下载列表按文件获取来源信息。
- 视频/图片详情页“操作”区新增“查看来源”入口；下载列表输出文件旁新增来源链接展示。
- `yt-dlp` 输出命名升级为结构化短名，并启用 `--write-info-json` 以增强跨平台回跳恢复能力。
- 新增来源相关测试覆盖：来源映射写入、历史清理保留、info.json/文件名回退、批量查询与删除文件同步清理映射。

## v0.8.6 (2026-02-21)
- URL 下载中心升级为双引擎：支持按任务手动选择 `yt-dlp` / `gallery-dl`，并在运行状态中展示双引擎可用性与版本。
- 下载任务模型增强：新增 `engine`、`engine_version`、`output_files_rel`、`file_count` 字段；兼容旧任务历史记录恢复。
- 新增 `gallery-dl` 下载链路：支持 cookie 文件复用、`download-archive` 去重归档、临时目录收敛后写回媒体根目录（含重名自动避让）。
- 修复下载列表“查看文件”跳转：图片文件改为进入 `/image` 详情页；并为 `/detail/<image>` 增加后端自动重定向兜底。
- 更新中英文 README 与下载测试覆盖，补充双引擎使用与安装说明。

## v0.8.5 (2026-02-20)
- 新增 URL 下载中心（`/download`）与后台任务队列：支持任务创建、取消、删除、清空历史与失败重试。
- 新增 cookie 文件方案：支持 `~/.tiklocal/cookies` 自动匹配/手动指定、页面上传即同名覆盖更新。
- 下载链路增强网络容错：启用 `yt-dlp` 继续下载与重试参数，提升断网恢复能力。
- 完成下载页交互重构：单主操作流、上传入口收敛、状态标签降饱和、Toast 反馈替代 alert。
- 新增 `tests/test_download.py`，覆盖下载配置、cookie 处理、重试与历史清理接口。

## v0.8.4 (2026-02-20)
- 新增 AI Prompt 配置能力：支持在设置页自定义 system/user prompt、temperature、tags_limit，并支持重置默认值。
- 新增 LLM 运行时配置：支持在设置页配置 `base_url`、`model_name`，并展示 API Key 是否已配置。
- 图片详情页支持“仅本次覆盖生成”高级参数；元数据返回 `prompt_source` 与 `llm_source` 便于追踪来源。
- Gallery 弹层新增单击图片专注模式：仅隐藏左下角 AI 标题/标签覆层，保留右下角工具按钮可操作。
- 新增 `tests/test_prompt_config.py`，覆盖 prompt/llm 配置 API 与元数据来源优先级。
