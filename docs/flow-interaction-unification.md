# Flow 交互统一架构（Home / Library / Favorites）

- 状态: 已落地
- 更新时间: 2026-02-25

## 背景/目标

- 首页（`/`）与 Library/Favorites（`/library`、`/favorite`）曾长期维护两套交互状态机，导致行为分叉与回归风险上升。
- 典型问题：
1. 首页与 Library 的沉浸模式切换规则不一致。
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
- 目的：消除首页与 Library 的重复几何/时间逻辑，避免单点修复失效。

3. 页面适配层（保留页面特有渲染）
- 首页：`tiklocal/templates/tiktok.html`
- Library/Favorites：`tiklocal/templates/library.html`
- 仅保留页面差异（数据源、DOM 结构、按钮布局），核心状态流与通用算法走共享模块。

## 统一交互约定

1. 单击：统一切换沉浸状态（不再区分“视频沉浸 / 图片专注”双模式）。
2. 双击（视频）：播放/暂停。
3. 放大镜：图片与视频可用；视频放大镜采用实时帧采样；激活即退出沉浸；切换媒体自动关闭。
4. 关闭入口：保持右上角关闭按钮可用（Library/Favorites）。
5. Favorites：复用 `library.html`，天然继承统一规则。

## 影响范围

- 模板：
1. `tiklocal/templates/tiktok.html`
2. `tiklocal/templates/library.html`
- 静态资源：
1. `tiklocal/static/flow_state_controller.js`
2. `tiklocal/static/flow_ui_shared.js`
- 测试：
1. `tests/test_library_upgrade.py`

## 风险与权衡

- 权衡：引入共享脚本文件会增加少量模块边界，但显著降低模板内重复和状态分叉。
- 风险：
1. 模板脚本注入顺序错误会导致运行时找不到共享对象。
2. 共享层改动会同时影响首页与库页，需要明确回归清单。

## 回归清单（建议固定执行）

1. 首页视频进入沉浸后，滑到图片保持沉浸状态一致。
2. 图片/视频开启放大镜时自动退出沉浸，且可正常拖拽镜头。
3. 视频放大镜在播放中可持续刷新，暂停后仍可在当前帧拖拽观察。
4. Library 与 Favorites 的手势行为一致（上下滑切换、按钮可用）。
5. 首页与 Library 的放大镜取样均无横向压扁。

## 后续事项

- [ ] 抽取第三层共享（视频进度条与 AI 标题面板渲染助手），进一步减少模板内脚本体积。
- [ ] 增加端到端交互测试，覆盖“沉浸 ↔ 放大镜 ↔ 媒体切换”链路。
- [ ] 评估将共享脚本迁移到打包流程，减少模板内内联逻辑规模。
