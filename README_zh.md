# TikLocal

**TikLocal** 是一个基于 **Flask** 的 **手机和 Pad 端** 的 **Web 应用程序**。它可以让您像Tiktok和Pinterest一样浏览和管理您的短视频和图片文件。

[English](./README.md)

## 介绍

TikLocal 的主要功能包括：

* 提供类似 **Tiktok** 的 **上下滑动浏览** 体验，让您可以轻松快速地浏览本地短视频文件。
* 提供类似 **普通文件管理器** 的 **目录浏览** 功能，让您可以方便地查找和管理本地短视频文件。
* 提供类似 **Pinterest** 的 **网格布局** 功能，让您可以欣赏本地图片。
* 支持 **浅色和暗色模式**，满足您的个人喜好。

## 使用场景

TikLocal 适用于以下场景：

* 您不相信Tiktok的青少年模式, 想给你的小孩提供完全可控的短视频内容。
* 您想在本地浏览和管理您的短视频和图片文件，但不想使用第三方云服务。
* 您想在手机或 Pad 上使用 Tiktok 式的短视频浏览体验。
* 您想在手机或 Pad 上使用 Pinterest 式的图片浏览体验。

## 如何使用

### 安装

TikLocal 是一个Python应用程序，您可以通过以下方式安装：

```
pip install tiklocal
```

### 使用

TikLocal 的启动非常简单，只需执行以下命令：
```bash
tiklocal ~/Videos/
```
您可以指定任意的媒体文件夹

想要关闭时, 使用`Ctrl + C`

#### 命令行工具

TikLocal 提供了多个 CLI 命令：

**启动服务器：**
```bash
tiklocal /path/to/media           # 指定媒体目录启动
tiklocal --port 9000              # 使用自定义端口
```

**生成视频缩略图：**
```bash
tiklocal thumbs /path/to/media    # 生成缩略图
tiklocal thumbs /path --overwrite # 重新生成已有的缩略图
```

**查找和清理重复文件：**
```bash
tiklocal dedupe /path/to/media              # 查找重复文件（预演模式）
tiklocal dedupe /path --type video          # 仅检查视频文件
tiklocal dedupe /path --execute             # 执行删除
tiklocal dedupe /path --keep newest         # 保留最新的文件
```

`dedupe` 命令选项：
- `--type`: 文件类型（`video`、`image`、`all`）
- `--algorithm`: 哈希算法（`sha256`、`md5`）
- `--keep`: 保留策略（`oldest`=最早、`newest`=最新、`shortest_path`=路径最短）
- `--dry-run`: 预演模式（默认）
- `--execute`: 执行实际删除
- `--auto-confirm`: 跳过确认提示

### 配置

TikLocal 提供了一些配置选项，您可以根据自己的需要进行调整。

* 浅色模式/暗色模式：您可以选择使用浅色模式或暗色模式。
* 视频播放速度：您可以调整视频播放速度。


## TODO

* [ ] 增加搜索
* [ ] 增加更多管理操作, 比如移动文件, 创建文件夹
* [ ] 增加基础的登录控制*
* [ ] 增加收藏功能
* [ ] 增加Docker镜像
* [ ] 增加标签功能
* [ ] 使用推荐算法

## 贡献

TikLocal 是一个开源项目，您可以通过以下方式进行贡献：

* 提交代码或文档的改进。
* 报告 Bug。
* 提出新功能的建议。

## 联系我们

如果您有任何问题或建议，可以通过以下方式与我们联系：

* GitHub 项目地址：[https://github.com/ChanMo/TikLocal/](https://github.com/ChanMo/TikLocal/)
* 邮箱：[chan.mo@outlook.com]


