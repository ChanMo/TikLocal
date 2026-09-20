# 媒体索引与本地推荐架构

- 模块: Library Index / Recommendation / Thumbnail
- 更新时间: 2026-09-19

## 现状概述

- TikLocal 以文件系统作为媒体事实来源，以 `~/.tiklocal/tiklocal.sqlite3` 中的 `media_items` 作为页面查询索引。
- `media_items` 同时缓存媒体时间、原始本地日期、时间来源与可信度；图片按 EXIF、文件名、文件时间的顺序解析，未变化文件复用已有结果。
- Home Flow、Library、Favorites、Collections 与视频详情页共用规范媒体 URI：`@source_id/relative/path`。
- Library、Favorites、Collections 的页面和 API 集中于 `web/library.py`，共用分页结果组装与页面渲染；应用入口仅构造并传入依赖。集合成员清理规则由 `services/collections.py` 统一维护，收藏与集合各自保留原存储职责。
- Web Radio 位于 `web/radio.py`；媒体详情、原文件传输、删除和缩略图入口位于 `web/media.py`。首页、设置页、库统计与缓存管理位于 `web/settings.py`，页面和统计 API 使用同一份统计组装。
- 推荐保持轻量本地实现，使用收藏、完成、跳过、重播、近期曝光和媒体维度偏好参与排序，不依赖云端画像或任务系统。
- Library 列表使用按需缩略图，Quick Viewer 与详情页才加载原始媒体。

## 变更点

- 应用每次启动都会扫描可用媒体源并校正索引，覆盖外部新增、修改、删除和重命名。
- 每个来源一次遍历区分图片、视频、音频，扩展名不区分大小写。目录枚举或必要文件状态读取失败时，整个来源本轮不更新、不清理；其他完整扫描的来源正常同步。所有媒体源均不可用时 CLI 停止启动。
- 下载的可识别媒体完成索引登记后才发布成功；登记失败保留文件及输出列表，重试仅重新登记，避免重复下载。下载 HTTP 入口集中于 `web/downloads.py`，应用构造不启动任务线程；服务显式启动管理器后接单，正常退出取消未完成任务并保留文件，异常退出仍按旧规则标记中断任务。
- Flow 与 Library 默认按 24 条分页，避免为首屏提前创建过多媒体节点。
- 图片和视频列表统一使用 `/thumb`；图片缩略图最长边为 640px，首次访问同步生成并缓存。
- 缩略图读取时比较源文件 mtime，同名媒体被替换后会自动重建；删除媒体时同步删除对应缩略图。
- 视频详情页的上一条/下一条导航读取媒体索引，不再重新扫描目录。
- Radio 的选曲和列表都读取索引中的 audio，并过滤当前不存在的文件；外部新增音频在启动或手动同步后可见，下载输出登记后可见。选曲仍不探测音频标签，metadata 按原有入口懒读取。
- Flow、Library、集合与相似结果复用媒体链接生成规则；相似结果的预览使用 `/thumb`，不再请求原图。
- 公共链接与字段转换归入 `web/media_payloads.py`，Flow 混排和主题组装归入 `web/flow.py`；删除原 `view_builders.py`。内置 HTTPS 与 PWA 已下线，普通 HTTP/媒体 Range 保留，外部反向代理可提供 HTTPS。
- 向量与相似分组实现位于 `experiments/similarity/`：配置、向量构建、分组、CLI 与 HTTP 入口集中维护。命令行按需加载；`experiments.similarity.enabled` 控制实验服务注册，关闭后核心无向量运行依赖。相似结果移至 `/experiments/similarity`，状态与查询只读取本地数据；同步 Web 构建返回 410，构建沿用 CLI。存储仍使用原数据库表和 `embedding_config.json`，无需重建已有向量。

## 接口与边界

- `LibraryIndexer.sync()`：仅提交完整扫描来源的快照，以 `unavailable_sources` 和 `source_errors` 报告失败来源。全部失败时保留所有旧索引；完整扫描得到空库时允许正常清理。
- `LibraryIndexer.register_uris()`：登记下载输出，缺失或不可访问的可识别媒体必须报错；忽略不属于媒体类型的附件。
- `MediaIndexStore.page()`：统一普通、收藏和集合列表查询。SQL 处理常规筛选与分页，大文件按大小降序，再按 mtime 和 URI 确保稳定次序；集合保留成员次序；随机图片沿用固定候选排序和 seed 洗牌。
- `enrich_media_dimensions()`：列表查询后按页批量读取尺寸缓存，按需探测，再批量合并写入；序列化不再执行 IO。时间线封面不探测尺寸。
- `ImageMetadataStore.update_many()`：在同一实例锁内重新读取、合并字段并原子写入；尺寸与标题更新互不覆盖，不在远程标题生成期间持锁。旧裸路径标题在尺寸规范化时保留。
- `FavoriteService`：读改写在同一实例锁内完成，原子替换防止半写入；损坏或不可写文件不得转换为成功。收藏 API 失败返回 503，Flow/Gallery 回滚乐观状态并允许重试。
- `RecommendService.get_weighted_selection()`：从媒体索引读取候选并执行轻量加权选择。
- `ThumbnailService.get_thumbnail()`：读取有效缓存或同步生成单规格缩略图。
- `ThumbnailService.get_radio_artwork()`：Web 与原生 Radio 共用内嵌封面优先、生成封面降级；各 HTTP 入口保留自己的访问校验。`cache_stats()` / `clear_cache()` 统一缓存目录操作，清理不删除媒体或映射。
- `ThumbnailService.generate_thumbnail()`：CLI、Web 按需生成和手动选帧共用的生成入口；临时文件完成后原子替换缓存，失败保留已有缓存。CLI 默认优先时长 20% 处，Web 保留 5/1/0.1 秒尝试，显式选帧支持 0 秒。
- `/api/feed/mix`：按 seed 混排并分页；候选和权重不变时可复现，主题与本页图集不改变基础媒体分页边界。
- `/api/library/items`：返回媒体库分页数据。
- `/api/library/timeline`：返回轻量年/月统计和每月代表媒体，不读取原图或同步探测尺寸。
- `/api/library/sync`：手动触发与启动时相同的安全同步。

## 数据流与状态

```text
文件系统
  → 启动/手动扫描
  → media_items
  → Library / Flow / Detail 查询

浏览与收藏行为
  → media_events
  → media_affinity / preference_dimensions
  → RecommendService 轻量排序

媒体文件
  → /thumb 首次访问
  → 本地 JPEG 缓存
  → Library / Feed 预览

图片 / 视频文件
  → EXIF / 文件名 / 文件时间
  → captured_at / captured_local_date / time_source
  → Timeline 年月聚合与月份详情
```

## 兼容性与迁移

- 旧的裸相对路径继续映射到默认媒体源。
- `/media?uri=...` 保留兼容；新生成的页面数据直接使用 `/media/<path>`，避免额外重定向。
- 收藏、集合、行为记录和向量数据不会因媒体源暂时离线而被级联删除。
- 新缩略图统一以规范 URI 计算缓存键。默认来源的旧裸路径缓存仅在源文件可访问、缓存非空且不早于源文件时复用；其他来源不复用裸路径缓存，避免同名资源串图。旧文件和 `thumbs.json` 保留，不做全量迁移。
- CLI 生成、检查覆盖率与清理共用缩略图服务；单目录清理跳过未知来源和离线来源。手动选帧和删除操作使用同一规范缓存键。
- 下载历史增加可选字段 `failure_stage`；`index` 表示文件已经下载、登记未完成，状态仍为 `failed`。原重试 API 复用同一任务完成登记；输出缺失则明确拒绝并提示重新创建下载任务。没有该字段的旧失败任务仍创建新的下载任务，重启仍将未完成任务标为失败。

## 影响范围

- 启动时间会包含一次完整文件扫描，但页面查询可以稳定使用 SQLite 索引。
- 第一次访问未缓存缩略图时会发生同步生成，后续访问直接复用。
- 推荐排序面向单机个人媒体库，优先可读性与维护成本，不计划引入 Celery、Redis 或云端推荐服务。

## 风险与权衡

- 暂时离线来源仍会出现在索引查询中，对应原始媒体在重新挂载前不可播放；保留索引可以避免误删用户状态。
- 单规格缩略图不追求响应式图片的极限带宽收益，但能以较少代码显著降低列表原图传输和解码成本。
- 推荐会读取较大的本地候选池；当前规模优先保持实现简单，只有出现真实瓶颈时再考虑缓存。
- 随机浏览仍读取当前候选再洗牌，不承诺索引发生变化时跨页保持同一快照。
- 尺寸缓存不可用时不阻断浏览；首次访问未缓存视频仍可能同步执行 FFprobe。这里没有引入后台任务系统。
- 收藏和元数据的锁保护当前单进程服务的线程并发；多个进程共用 JSON 不具备事务保证。原文件无法解析时保留内容并报错，不能用空状态覆盖。

## 后续事项

- [ ] 结合实际媒体规模评估 Library 的筛选与排序信息架构。
- [ ] 若缩略图缓存空间成为问题，再增加基于现有目录的简单清理策略。
- [ ] 仅在明确出现查询瓶颈时，评估把更多媒体元数据迁入 `media_items`。

## 相关文件/模块

- `tiklocal/services/library_index.py`
- `tiklocal/services/database.py`
- `tiklocal/services/thumbnail.py`
- `tiklocal/services/library.py`：来源、URI 和文件扫描。
- `tiklocal/services/favorites.py`：收藏存储与写入失败传播。
- `tiklocal/services/media_info.py`：按页尺寸读取与探测。
- `tiklocal/services/metadata.py`：标题与尺寸的字段合并存储。
- `tiklocal/services/captions.py`：正式命名配置、模型请求与生成编排；HTTP 入口见 `web/captions.py`。
- `tiklocal/services/json_storage.py`：收藏、元数据共用的原子文件替换。
- `tiklocal/services/recommendation.py`：本地推荐权重。
- `tiklocal/services/radio.py`：音频候选与电台选择。
- `tiklocal/thumbs.py`：缩略图 CLI 编排。
- `tiklocal/view_builders.py`
- `tiklocal/app.py`
- `tiklocal/static/home_feed_controller.js`
- `tiklocal/static/library_page_controller.js`
- `tests/test_feed_mix.py`
- `tests/test_library_upgrade.py`
