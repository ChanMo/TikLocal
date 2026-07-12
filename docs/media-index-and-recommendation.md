# 媒体索引与本地推荐架构

- 模块: Library Index / Recommendation / Thumbnail
- 更新时间: 2026-07-12

## 现状概述

- TikLocal 以文件系统作为媒体事实来源，以 `~/.tiklocal/tiklocal.sqlite3` 中的 `media_items` 作为页面查询索引。
- Home Flow、Library、Favorites、Collections 与视频详情页共用规范媒体 URI：`@source_id/relative/path`。
- 推荐保持轻量本地实现，使用收藏、完成、跳过、重播、近期曝光和媒体维度偏好参与排序，不依赖云端画像或任务系统。
- Library 列表使用按需缩略图，Quick Viewer 与详情页才加载原始媒体。

## 变更点

- 应用每次启动都会扫描可用媒体源并校正索引，覆盖外部新增、修改、删除和重命名。
- 不可访问的媒体源不会参与本次清理，其既有索引会保留；所有媒体源均不可用时 CLI 停止启动。
- Flow 与 Library 默认按 24 条分页，避免为首屏提前创建过多媒体节点。
- 图片和视频列表统一使用 `/thumb`；图片缩略图最长边为 640px，首次访问同步生成并缓存。
- 缩略图读取时比较源文件 mtime，同名媒体被替换后会自动重建；删除媒体时同步删除对应缩略图。
- 视频详情页的上一条/下一条导航读取媒体索引，不再重新扫描目录。

## 接口与边界

- `LibraryIndexer.sync()`：扫描文件系统并生成当前可访问来源的索引快照。
- `MediaIndexStore.page()`：为 Library 提供类型、大小、搜索与分页查询。
- `RecommendService.get_weighted_selection()`：从媒体索引读取候选并执行轻量加权选择。
- `ThumbnailService.get_thumbnail()`：读取有效缓存或同步生成单规格缩略图。
- `/api/feed/mix`：按 seed 返回稳定的混合媒体分页。
- `/api/library/items`：返回媒体库分页数据。
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
```

## 兼容性与迁移

- 旧的裸相对路径继续映射到默认媒体源。
- `/media?uri=...` 保留兼容；新生成的页面数据直接使用 `/media/<path>`，避免额外重定向。
- 收藏、集合、行为记录和向量数据不会因媒体源暂时离线而被级联删除。
- 缩略图缓存不需要迁移；旧缓存会在源文件更新后按需重建。

## 影响范围

- 启动时间会包含一次完整文件扫描，但页面查询可以稳定使用 SQLite 索引。
- 第一次访问未缓存缩略图时会发生同步生成，后续访问直接复用。
- 推荐排序面向单机个人媒体库，优先可读性与维护成本，不计划引入 Celery、Redis 或云端推荐服务。

## 风险与权衡

- 暂时离线来源仍会出现在索引查询中，对应原始媒体在重新挂载前不可播放；保留索引可以避免误删用户状态。
- 单规格缩略图不追求响应式图片的极限带宽收益，但能以较少代码显著降低列表原图传输和解码成本。
- 推荐会读取较大的本地候选池；当前规模优先保持实现简单，只有出现真实瓶颈时再考虑缓存。

## 后续事项

- [ ] 结合实际媒体规模评估 Library 的筛选与排序信息架构。
- [ ] 若缩略图缓存空间成为问题，再增加基于现有目录的简单清理策略。
- [ ] 仅在明确出现查询瓶颈时，评估把更多媒体元数据迁入 `media_items`。

## 相关文件/模块

- `tiklocal/services/library_index.py`
- `tiklocal/services/database.py`
- `tiklocal/services/thumbnail.py`
- `tiklocal/services/__init__.py`
- `tiklocal/view_builders.py`
- `tiklocal/app.py`
- `tiklocal/static/home_feed_controller.js`
- `tiklocal/static/library_page_controller.js`
- `tests/test_feed_mix.py`
- `tests/test_library_upgrade.py`
