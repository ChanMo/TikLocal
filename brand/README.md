# TikLocal 标志

本目录是 TikLocal 开源项目（Server、Web UI、README、PyPI）的标志资源。原生 App
使用独立的 LumaFold 品牌，见 `apps/radio/brand/`。

## 标志语义

小写 **t** 的竖笔向下书写，收成一个钩，指向一个橙色圆点。钩和点之间只留一线空隙，
读起来是“一笔写完，落下一滴”：t 取自 TikLocal，圆点表示“就在这里”，也就是媒体
一直留在你自己的机器上。

## 构造

- 画在 24 × 24 网格上，描边 2、圆角端点、圆角连接，和 Web UI 使用的 Feather 图标
  是同一套几何，所以可以直接放进导航栏。
- 竖笔 `(9, 3.5) → (9, 15.5)`，钩为半径 3 的四分之一圆弧，止于 `(12, 18.5)`。
- 横杠 `(5.5, 8.5) → (12.5, 8.5)`。
- 圆点圆心 `(16.6, 18.5)`，半径 2.1。
- 整套标志里只有圆点使用强调色。

几何只在 `scripts/build_brand.py` 里定义一次，所有文件都由它生成。Web 页面内联的
SVG（`tiklocal/templates/brand_mark.html`）是同一组路径的副本，修改时要同步。

## 色彩

| 角色 | 浅色背景 | 深色背景 |
| --- | --- | --- |
| 标志线条 | `#36594F` | `#B8CCBF` |
| 圆点 | `#D9633B` | `#D9633B` |
| 字标 | `#23231F` | `#E9E7DF` |
| 头像底色 | `#F7F6F2` | — |

橙色 `#D9633B` 与 LumaFold 的 Signal 色相同，用来表示两者属于同一个家族。

## 字标

写作 tik**Local**：`tik` 用 Source Serif 4 Light（300），`Local` 用 Semibold（600），
字距 −0.02em。字重对比刻意强调 “Local”，同时削弱和 TikTok 的联想。字形已经转为路径，
使用时不需要安装字体。Source Serif 4 采用 SIL Open Font License 1.1 授权。

## 文件

| 文件 | 用途 |
| --- | --- |
| `tiklocal-mark.svg` | 标志，浅色背景 |
| `tiklocal-mark-dark.svg` | 标志，深色背景 |
| `tiklocal-mark-mono.svg` | 单色标志，使用 `currentColor`，可以内联后随文字着色 |
| `tiklocal-lockup.svg` | 标志 + 字标，浅色背景（README 头部） |
| `tiklocal-lockup-dark.svg` | 标志 + 字标，深色背景 |
| `tiklocal-avatar-512.png` | 社交头像、GitHub 组织或仓库图片 |
| `../tiklocal/static/brand/favicon.svg` | 浏览器标签图标，会跟随系统深浅色切换 |
| `../tiklocal/static/brand/favicon.ico` | 旧浏览器和 `/favicon.ico`（16/32/48px，16px 版描边加粗到 2.5） |
| `../tiklocal/static/brand/apple-touch-icon.png` | iOS 添加到主屏幕（180px） |

## 使用规则

- 最小尺寸 16px；16px 以下只使用 `.ico` 里专门加粗的版本。
- 四周留白不少于 2 个网格单位（标志尺寸的 1/12）。
- 不要拉伸、旋转、加阴影或描边，也不要改变圆点的颜色和位置。
- 不要把标志放进实心圆角方块里当作 App 图标使用，那是 LumaFold 的领域。

## 重新生成

```bash
pip install fonttools brotli pillow
npm pack @fontsource/source-serif-4 && tar xzf fontsource-source-serif-4-*.tgz
python scripts/build_brand.py --font-dir package/files
```
