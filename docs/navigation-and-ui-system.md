# 方案 A：Flow 作为首页与 daisyUI 组件体系

- 状态：已实施。路由结构、导航、登录、设置、下载、集合、详情页菜单已完成；
  Flow、Radio、Library 的沉浸式与版面 CSS 按下方边界保留。
- 制定日期：2026-09-21。
- 范围：Flask Web 的信息架构、导航、样式基线。
- 不涉及：`apps/radio/` 的 React Native 实现、媒体索引与推荐逻辑、下载引擎。

## 1. 为什么改

改动前的三条结构性问题：

| 问题 | 证据 |
| --- | --- |
| 信息架构过重 | 一级入口 8 项；移动端与桌面端是两套并行渲染的导航 DOM，互相覆盖 |
| 技术栈骑墙 | 13 个模板中只有 2 个在用 Tailwind 类，其余是 4,147 行模板内联 CSS，而 `output.css` 仍每页加载 |
| 渲染策略不统一 | Library 服务端渲染、Flow 是空壳加 fetch、首页是 6 个并行 XHR |

首页本身不承载内容，只是一个"选择去哪"的目录页，而它的三块内容在别处都已存在：
Recently Added 对应 Library Timeline，Rediscover 对应 Library 的 `image_random` 模式，
Collections 对应 Saved。因此直接删除，而不是换个位置重建。

另有三处从未生效的死代码：`tailwind.config.js`（v4 不再自动读取）、
base.html 中被 app_navigation.css 完全覆盖的胶囊底栏样式、
以及 DOM 中无对应节点的 `.nav-icon-outline` / `.nav-icon-filled` 动画。

## 2. 信息架构

四个内容目的地，Settings 作为工具位：

```
/                    Flow        打开即播放，首页第一页服务端渲染
/library             Library     timeline / explore / month 三种视图
/radio               Radio       音频
/saved               Saved       收藏
/saved/collections   Saved       用户集合
/settings            Settings    外观、媒体库、Radio 客户端、安全、下载
/download            Download    下载队列，从 Settings 进入
```

旧地址 `/flow`、`/favorite`、`/collections` 保留为重定向。

导航实现：移动端 daisyUI `dock` 底栏，`md` 及以上为 `menu` 竖栏，
两者都在 `base.html` 中，`aria-current="page"` 即选中态。
改动前手机上没有常驻导航，必须点网格图标打开一张底部弹层。

## 3. 样式基线

顺序是：**daisyUI 组件 → Tailwind 工具类 → 自写 CSS**。第三项需要理由。

主题 `light` / `dark` 定义在 `tiklocal/static/input.css`，颜色取自应用原有的暖纸色系。
chrome 保持近单色，让缩略图承担色彩。`data-theme` 同时写到 `<html>` 与 `<body>`：
daisyUI 从 `<html>` 着色页面底色，而页面样式里 `data-theme` 与 `data-nav-context`
的复合选择器依赖 `<body>`。

### 已迁移

| 页面 | 内联 CSS | 主要组件 |
| --- | --- | --- |
| 登录 | 157 → 0 | card / input / checkbox / alert / btn |
| 设置 | 270 → 0 | card / list / join / fieldset / modal / toast |
| 下载 | 263 → 0 | card / join / progress / dropdown / modal / alert |
| 集合 | 386 → 0 | modal / dropdown / menu / loading |
| 详情页菜单 | 109（在 input.css）→ 0 | dropdown / menu |
| 导航 | 298（在 base.html）→ 0 | dock / menu / tooltip |

弹窗统一改用原生 `<dialog class="modal">` 加 `showModal()`，
背景遮罩、焦点捕获、Escape 由浏览器提供，不再自己实现。
下拉菜单使用 daisyUI 基于焦点的 `dropdown`，因此不需要 toggle 状态、
外部点击监听与 `aria-expanded` 维护。

### 保留自写 CSS 的边界

以下三处 daisyUI 没有对应组件，其内联 CSS 是布局引擎而非装饰，保留：

- `flow.html`：全屏滑动信息流、视频覆盖控件、图集舞台、主题卡片、放大镜
- `radio.html`：黑胶唱片播放器、环境背景、信号刻度
- `library.html`：瀑布流网格与年月时间线

这三个页面中的按钮、吐司、弹窗等 chrome 仍应优先使用 daisyUI，后续按需迁移。

## 4. 构建

CSS 由 Tailwind v4 CLI 从 `input.css` 构建，daisyUI 与主题通过 `@plugin` 配置，
不存在 `tailwind.config.js`。`@source` 显式限定扫描范围，
避免 `feather.min.js`、`hammer.min.js` 等压缩包污染类名扫描。

**改完模板里的类名后必须跑 `npm run build`**，否则新类不会出现在 `output.css` 中。

产物体积：109KB minified / 约 18KB gzip。改动前是 35KB / 7KB，
但那是在 4,147 行不可缓存的模板内联 CSS 之上。
