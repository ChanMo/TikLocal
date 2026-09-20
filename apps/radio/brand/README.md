# LumaFold 品牌候选

本目录保存 TikLocal 原生 App 的独立消费品牌候选。当前用于产品与真机视觉验证；
显示名称、图标和品牌文案可以接入预览构建，但不迁移 Bundle ID、URL Scheme、数据
存储或 Server 协议。

2026-08-26 起，LumaFold 已作为真机预览工作品牌接入显示名称、图标、启动页与用户
可见文案，但仍不是最终商标决策。初步公开检索发现同名多屏支架、灯具商品及公司记录；
虽然暂未发现同名照片/视频 App，也必须在商业发布前完成目标市场的正式商标与名称
可用性核查，并保留整体换名能力。

## 品牌定义

- 名称：`LumaFold`
- 定位：私密、离线的个人媒体 Flow
- 英文主张：`Your media, alive again.`
- 中文表达：`让自己的影像，再次流动。`
- 品牌关系：LumaFold 可以连接用户自行运行的 TikLocal Server；TikLocal 继续作为
  开源项目与 Server 品牌。

## 标志语义

标志内部称为 **The Fold**：两个折叠平面保护一条连续的内部路径。偏离中心且被部分
遮挡的橙色圆点称为 **Luma**，代表一段正在重新浮现的私人记忆。标志应首先被识别为
抽象折叠结构，第二眼才产生安静生命体的联想；不得绘制成明确的瞳孔、眼白或具体角色。

## 色彩

| 角色 | 色值 | 来源 |
| --- | --- | --- |
| Ink | `#17231D` | `src/theme.ts` |
| Paper | `#F1EBDD` | `src/theme.ts` |
| Signal / Luma | `#D9633B` | `src/theme.ts` |
| Muted text | `#657068` | `src/theme.ts` |

## 文件

- `lumafold-mark.svg`：默认深色背景标志。
- `lumafold-mark-light.svg`：浅色背景标志。
- `lumafold-mark-mono.svg`：单色适配验证。
- `lumafold-foreground.svg`：Android Adaptive Icon 与启动页的安全区前景。
- `lumafold-lockup.svg`：横向字标概念；当前使用系统字体，正式定稿前需要确定字标字体
  授权或把字形转为路径。
- `concepts/`：图像生成阶段的探索稿，不作为生产素材。

## 定稿门槛

- 在 24px、32px、64px 与 1024px 下保持可识别。
- 默认、深色、透明和系统单色 Tint 下保持同一核心轮廓。
- 不被多数测试者首先识别为眼睛、监控、安全工具或已有影视角色。
- 名称完成 App Store、域名和相关市场商标检索。
- 通过后再统一修改生产名称、图标、启动页、配对 Scheme 与文案。
