# Release Notes

## Unreleased
- 待补充

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
