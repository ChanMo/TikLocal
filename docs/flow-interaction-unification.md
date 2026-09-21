# Flow 交互统一架构（Flow / Library / Favorites）

- 状态: 已落地
- 更新时间: 2026-09-19

## 背景/目标

- Flow（`/flow`）与 Library/Favorites（`/library`、`/favorite`）曾长期维护两套交互状态机，导致行为分叉与回归风险上升。
- 典型问题：
1. Flow 与 Library 的沉浸模式切换规则不一致。
2. 图片放大镜与沉浸状态存在冲突，跨媒体切换后行为不稳定。
3. 同类逻辑（时间格式化、放大镜取样几何）在两个模板重复实现。
- 目标：建立“统一交互内核 + 页面适配器”模型，保证三入口行为一致并降低维护成本。

## 结论/方案

采用两层共享 + 页面适配的收敛方案：

1. 共享状态层：`flow_state_controller.js`
- 提供统一状态机：`immersive` / `magnifying`。
- 统一规则：
1. 进入沉浸时，若放大镜开启则自动关闭放大镜。
2. 开启放大镜时，自动退出沉浸。
3. 当前媒体非图片/视频时，放大镜强制不可用。
4. 媒体切换时执行 `onMediaChanged()`，确保状态不残留。

2. 共享 UI 工具层：`flow_ui_shared.js`
- 统一函数：
1. `formatTime(seconds)`
2. `getImageContainRect(imgEl)`
3. `setMagnifierPosition(lensEl, x, y)`
4. `updateMagnifierContent(...)`
- 目的：消除 Flow 与 Library 的重复几何/时间逻辑，避免单点修复失效。

3. 页面适配层（保留页面特有渲染）
- Flow：`tiklocal/templates/flow.html`
- Library/Favorites：`tiklocal/templates/library.html`
- 仅保留页面差异（数据源、DOM 结构、按钮布局），核心状态流与通用算法走共享模块。

## 统一交互约定

1. 单击：统一切换沉浸状态（不再区分“视频沉浸 / 图片专注”双模式）。
2. 双击（视频）：播放/暂停。
3. 放大镜：图片与视频可用；视频放大镜采用实时帧采样；激活即退出沉浸；切换媒体自动关闭。
4. 关闭入口：保持右上角关闭按钮可用（Library/Favorites）。
5. Favorites：复用 `library.html`，天然继承统一规则。

## 影响范围

### 正式标题能力与异步规则

- `services/captions.py` 管理 Prompt、模型配置、图片编码、远程调用及结果解析；`web/captions.py` 保持原有配置/元数据 API；`services/metadata.py` 是标题与尺寸的统一存储入口。
- `CaptionSettings.resolve()` 同时服务生成与 `/api/ai/vision-config` 的有效配置。存在有效文件 vision 字段时，Prompt 使用文件配置和默认值，不启用旧自定义 Prompt；否则使用已启用的旧 Prompt。单次覆盖始终最后应用，不写回配置。
- vision 模型或地址非空时优先使用该组，缺少的字段沿用旧 LLM 环境变量；vision 两者皆空时使用旧 LLM 环境配置与已存自定义配置。这里保留原优先级，未改为逐字段合并所有来源。
- Key 顺序统一为 `TIKLOCAL_VISION_API_KEY` → `TIKLOCAL_AI_API_KEY` → `OPENAI_API_KEY` → `OPENROUTER_API_KEY`；忽略空白值，API 仅返回是否存在，不返回密钥。
- `flow_actions_shared.js` 统一标题 HTTP 成败与覆盖参数；`flow_media_actions_controller.js` 统一标题缓存、当前资源和在途生成。Flow、Quick Viewer 和图片详情页各自保留渲染，不引入通用面板组件。
- 切图不等待标题读取。切换资源、返回缓存、切到非图片或关闭预览都会更新当前请求状态；旧响应不得覆盖新面板。生成完成仍缓存到对应 URI，用户返回时可看到结果；只有当前资源能更新按钮 loading 和错误状态。
- 同一 URI 的重复生成合并为一个在途请求。失败保留已有标题；仅有尺寸缓存不算已有标题。Flow 和详情页继续确认覆盖，Quick Viewer 保留直接刷新规则。
- 只保护同一页面内的生成并发，不提供跨浏览器/多客户端的全局模型请求去重。真实模型输出质量需单独验收。

- 模板：
1. `tiklocal/templates/flow.html`
2. `tiklocal/templates/library.html`
3. `tiklocal/templates/image_detail.html`
- 静态资源：
1. `tiklocal/static/flow_state_controller.js`
2. `tiklocal/static/flow_ui_shared.js`
3. `tiklocal/static/flow_actions_shared.js`
4. `tiklocal/static/flow_media_actions_controller.js`
- 测试：
1. `tests/test_library_upgrade.py`
2. `tests/test_captions.py`

## 风险与权衡

- 权衡：引入共享脚本文件会增加少量模块边界，但显著降低模板内重复和状态分叉。
- 风险：
1. 模板脚本注入顺序错误会导致运行时找不到共享对象。
2. 共享层改动会同时影响 Flow 与库页，需要明确回归清单。

## 回归清单（建议固定执行）

1. Flow 视频进入沉浸后，滑到图片保持沉浸状态一致。
2. 图片/视频开启放大镜时自动退出沉浸，且可正常拖拽镜头。
3. 视频放大镜在播放中可持续刷新，暂停后仍可在当前帧拖拽观察。
4. Library 与 Favorites 的手势行为一致（上下滑切换、按钮可用）。
5. Flow 与 Library 的放大镜取样均无横向压扁。
6. 延迟标题读取时切图、返回缓存、切到视频或关闭；旧结果不覆盖当前面板。生成失败保留已有标题，旧生成完成不解除新媒体的 loading。

## 后续事项

- [ ] 抽取第三层共享（视频进度条与 AI 标题面板渲染助手），进一步减少模板内脚本体积。
- [ ] 保留“沉浸 ↔ 放大镜 ↔ 媒体切换”人工验收；出现重复回归时再补小规模浏览器测试，不预建完整端到端套件。
- [ ] 评估将共享脚本迁移到打包流程，减少模板内内联逻辑规模。
