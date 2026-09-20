# 文档索引

## 说明

本目录用于沉淀 TikLocal 的关键设计决策、版本变更与实现约束，减少后续迭代时的重复讨论与回归风险。

## 文档列表

- [Web 代码收敛执行方案](web-convergence-plan.md)：核心保护、公共资源、正式标题与向量实验隔离已落地；后端业务路由已收拢，PWA 与内置 HTTPS 已下线，后续整理前端共享交互；按影响范围做关键验证，进度与限制见交付记录。
- `docs/mixed-feed-design.md`：Flow 混合流（视频+图片）设计与实现说明。
- `docs/flow-interaction-unification.md`：Flow / Library / Favorites 交互内核，以及三处标题入口共用的配置和异步状态规则。
- `docs/media-index-and-recommendation.md`：媒体索引、安全同步、缩略图与本地推荐的数据流及实现边界。
- `docs/native-local-app-architecture.md`：LumaFold 工作品牌、原生 App 本地优先定位、离线导入与播放架构、兼容边界及后续演进顺序。
- `docs/radio-native-client-architecture.md`：LumaFold 内 Radio 模块的原生导航、TikLocal Server 连接与队列恢复、播放器边界及发布路径。
- `docs/radio-player-selection.md`：TikLocal Radio 播放器候选、许可与新架构验证，以及 `0.1.x` 系统媒体能力边界。
- `docs/openrouter-image-to-video-research.md`：OpenRouter 图片生成视频能力调研、PoC 流程与未来产品化约束。
- `docs/release_notes.md`：版本发布记录与未发布变更清单。
