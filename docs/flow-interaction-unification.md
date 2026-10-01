# Flow 交互统一架构（Flow / Library / Favorites）

- 状态: 已落地
- 更新时间: 2026-09-30

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
- `FlowUIShared.formatTime(seconds)`
- `FlowUIShared.createMagnifier(...)`：镜头定位、图片/视频取样、视频逐帧刷新与暂停轮询、缩放档位、拖动与窗口缩放。页面只传入 DOM、样式类名和 `target()`（返回当前 `{ type, el }`），并在状态层回调中调用 `onStateChange`，在视频 `play`/`seeked` 时调用 `onVideoPlay`/`onVideoSeeked`。
- 目的：消除 Flow 与 Library 的重复几何/时间/帧循环逻辑，避免单点修复失效。

3. 集合选择器：`collection_picker.js`
- `TikLocalCollections.createPicker(...)` 负责集合弹层的读取、新建并加入、勾选/取消、成员缓存和按钮计数；页面传入 DOM、列表类名和 `currentUri()`。
- `TikLocalCollections.request(...)` 是集合 API 的统一请求入口，Library 设置集合封面也使用它。
- Flow 的图集卡片以当前显示的图片作为集合成员，与收藏一致。

4. 页面适配层（保留页面特有渲染）
- Flow：`tiklocal/templates/flow.html` + `tiklocal/static/flow_page_controller.js`
- Library/Favorites：`tiklocal/templates/library.html` + `tiklocal/static/library_page_controller.js`
- 仅保留页面差异（数据源、DOM 结构、按钮布局、分页与手势），核心状态流与通用算法走共享模块。

## 统一交互约定

以下 1–2 条目前只描述 Library/Favorites 的 Quick Viewer；Flow 的手势见下一节，Quick Viewer 待真机验证后再迁移。

1. 单击：统一切换沉浸状态（不再区分“视频沉浸 / 图片专注”双模式）。
2. 双击（视频）：播放/暂停。
3. 放大镜：图片与视频可用；视频放大镜采用实时帧采样；激活即退出沉浸；切换媒体自动关闭。
4. 关闭入口：保持右上角关闭按钮可用（Library/Favorites）。
5. Favorites：复用 `library.html`，天然继承统一规则。

## Flow 手势（2026-09-30）

| 操作 | 视频 | 图片 / 图集 |
| --- | --- | --- |
| 单击 | 播放/暂停（等待 250ms 排除双击） | 显示/隐藏界面 |
| 双击 | 收藏 | 收藏 |
| 长按 450ms | 按住期间 2 倍速，松手恢复所选倍速并继续播放；按住时移动不翻页 | 显示/隐藏界面 |
| 上下拖动 / 滚轮 / ↑↓ | 翻页 | 翻页 |
| 左右拖动 | 从起点相对调进度，全屏宽度对应 `min(时长, 90s)`；支持 `fastSeek` 的浏览器拖动中预览画面，否则松手时跳转 | 图集内切换 |
| ←→ | 后退/前进 5 秒 | 图集内切换，否则翻页 |

- 倍速按钮点开一排档位（0.75–2x），所选倍速对之后的视频持续生效。
- 视频上长按不再切换界面，因此切到视频时自动退出沉浸；沉浸只在图片上进入。
- 长按和调进度通过顶部提示条反馈；进度条触控高度 32px，沉浸时离底边至少 6px 以避开系统手势。
- 媒体无法播放时不弹窗（2026-10-01）：网络错误先静默重试一次；其余错误用顶部提示条说明，0.7 秒后按上次翻页方向跳过。图集内单张失败只提示不跳过。连续跳过 3 次后才显示完整的错误状态（重试/下一个），以免服务不可用时一路跳到底；任一视频开始播放或图片加载成功即清零。

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
3. `tiklocal/static/collection_picker.js`
4. `tiklocal/static/flow_actions_shared.js`
5. `tiklocal/static/flow_media_actions_controller.js`
6. `tiklocal/static/flow_page_controller.js`、`tiklocal/static/library_page_controller.js`
- 测试：
1. `tests/test_library_upgrade.py`
2. `tests/test_captions.py`

## 风险与权衡

- 权衡：引入共享脚本文件会增加少量模块边界，但显著降低模板内重复和状态分叉。
- 风险：
1. 模板脚本注入顺序错误会导致运行时找不到共享对象：共享模块与 `hammer.min.js` 须在页面控制器之前加载。
2. 共享层改动会同时影响 Flow 与库页，需要明确回归清单。

## 回归清单（建议固定执行）

0. Flow 视频：长按 2 倍速、松手恢复所选倍速；左右拖动调进度且不翻页；暂停时长按开始播放。
0. Flow 遇到无法播放的文件：显示提示并按翻页方向跳过；往回翻时向前跳过。

1. Flow 图片进入沉浸后，滑到下一张图片保持沉浸；滑到视频自动恢复界面。
2. 图片/视频开启放大镜时自动退出沉浸，且可正常拖拽镜头。
3. 视频放大镜在播放中可持续刷新，暂停后仍可在当前帧拖拽观察。
4. Library 与 Favorites 的手势行为一致（上下滑切换、按钮可用）。
5. Flow 与 Library 的放大镜取样均无横向压扁。
6. 延迟标题读取时切图、返回缓存、切到视频或关闭；旧结果不覆盖当前面板。生成失败保留已有标题，旧生成完成不解除新媒体的 loading。

## 后续事项

- [ ] 抽取第三层共享（视频进度条与 AI 标题面板渲染助手），进一步减少模板内脚本体积。
- [ ] 保留“沉浸 ↔ 放大镜 ↔ 媒体切换”人工验收；出现重复回归时再补小规模浏览器测试，不预建完整端到端套件。
- [x] 模板内联脚本已移入静态文件，模板只保留 boot 数据；未引入打包流程。
