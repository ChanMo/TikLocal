# TikLocal

**TikLocal** 是一个基于 **Flask** 的 **手机和 Pad 端** 的 **Web 应用程序**。它可以让您像Tiktok和Pinterest一样浏览和管理您的短视频和图片文件。

[English](./README.md)

## 介绍

TikLocal 的主要功能包括：

* 提供类似 **Tiktok** 的 **上下滑动浏览** 体验，首页可混合浏览本地视频与图片。
* 提供类似 **普通文件管理器** 的 **目录浏览** 功能，让您可以方便地查找和管理本地短视频文件。
* 提供类似 **Pinterest** 的 **网格布局** 功能，让您可以欣赏本地图片。
* 支持 **浅色和暗色模式**，满足您的个人喜好。

## 使用场景

TikLocal 适用于以下场景：

* 您不相信Tiktok的青少年模式, 想给你的小孩提供完全可控的短视频内容。
* 您想在本地浏览和管理您的短视频和图片文件，但不想使用第三方云服务。
* 您想在手机或 Pad 上使用 Tiktok 式的视频+图片混合浏览体验。
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
tiklocal --media-source photos=~/Pictures/AI  # 追加媒体源，可重复
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

### URL 下载（Web）

TikLocal 新增了 `/download` 页面，可粘贴媒体 URL 并创建后台下载任务。

依赖要求：
- `yt-dlp`（必需）
- `gallery-dl`（建议，用于图片帖/图集）
- `ffmpeg`（建议，用于格式合并）

下载引擎说明：
- `yt-dlp`：更适合视频链接
- `gallery-dl`：更适合图片帖与图集（如 Instagram/X/Pinterest）
- 下载表单支持按任务手动选择引擎（默认 `yt-dlp`）

登录态内容（可选）：
- 将导出的 cookie 文件放到 `~/.tiklocal/cookies`
- 文件名建议包含域名，例如 `x.com.txt`、`youtube.com.cookies`
- 下载页面支持“自动匹配”或按任务手动指定 cookie 文件
- 下载页面也支持凭据文件上传/覆盖、历史删除/清空，以及失败任务重试

安装示例：
```bash
# macOS (Homebrew)
brew install yt-dlp gallery-dl ffmpeg

# Ubuntu / Debian
sudo apt install yt-dlp gallery-dl ffmpeg
```

### 首页混合流（Feed）

首页（`/`）已升级为混合沉浸流：

- 视频与图片在同一条滑动流中混排（视频主导密度，顺序随机化）
- 图片条目支持 AI 标题/标签面板（站内生成与展示）
- 图片条目支持圆形放大镜（2.5x / 5x）
- 图片条目不自动跳转，需手动滑动切换

### 配置

TikLocal 提供了一些配置选项，您可以根据自己的需要进行调整。

可以在 `~/.config/tiklocal/config.yaml` 中配置一个或多个媒体目录：

```yaml
media_sources:
  - id: default
    name: 主媒体库
    path: ~/Videos/TikLocal
  - id: photos
    name: 图片库
    path: ~/Pictures/AI
download_source: default

vision:
  enabled: true
  base_url: https://openrouter.ai/api/v1
  model_name: google/gemini-2.5-flash
  temperature: 0.6
  tags_limit: 5
  system_prompt: |
    你是图片内容分析助手。只输出 JSON。
  user_prompt: |
    请分析这张图片，生成一个简短中文标题，并给出最多 {tags_limit} 个中文标签。
    输出 JSON：{"title":"...","tags":["..."]}

embedding:
  enabled: true
  base_url: https://openrouter.ai/api/v1
  model_name: google/gemini-embedding-2
  dimensions: 768
  image_max_size: 512
  image_quality: 82
```

也可以继续使用旧的单目录配置：

```yaml
media_root: ~/Videos/TikLocal
```

多媒体源会合并为一个统一媒体库，内部媒体 URI 使用 `@source_id/path` 格式；旧的裸路径链接和收藏会自动兼容到 `@default/...`。

图片识别使用 `vision` 配置；图片向量化使用 `embedding` 配置，并把图片向量存入本地 SQLite 应用数据库（默认 `~/.tiklocal/tiklocal.sqlite3`）。图片详情页只读取本地索引用于相似图片推荐；构建或更新向量请使用 CLI：

```bash
tiklocal vectorize ~/Videos/TikLocal --limit 200 --order latest
tiklocal vectorize ~/Videos/TikLocal --dry-run
tiklocal analyze-similar ~/Videos/TikLocal --limit 500 --yes
```

API Key 通过环境变量读取：图片识别优先使用 `TIKLOCAL_VISION_API_KEY`，图片向量优先使用 `TIKLOCAL_EMBEDDING_API_KEY`，之后回退到 `TIKLOCAL_AI_API_KEY`、`OPENAI_API_KEY` 或 `OPENROUTER_API_KEY`。

### 图片向量化 CLI

批量向量化建议使用命令行，先预览再小批量执行：

```bash
tiklocal vectorize /path/to/media --dry-run
tiklocal vectorize /path/to/media --limit 200 --order latest
tiklocal vectorize /path/to/media --source photos --limit 200
tiklocal vectorize /path/to/media --cleanup
tiklocal vectorize /path/to/media --max-size 512 --quality 82
tiklocal analyze-similar /path/to/media --limit 500 --yes
tiklocal analyze-similar /path/to/media --profile --dry-run
```

推荐流程：

- 先运行 `--dry-run`，查看总图片数、已索引、缺失、过期和本次将处理的数量。
- 首次低成本执行可用 `--limit 200 --order latest`，先处理最新 200 张。
- 多媒体源场景可用 `--source <id>` 只处理某个媒体源。
- 文件删除或移动后，用 `--cleanup` 清理失效向量。
- 只有明确要重建已有向量时才使用 `--force`。
- 自动化脚本可加 `--yes` 跳过确认提示。

`vectorize` 只会上传缺失或过期的图片。文件大小、修改时间、模型、维度、`image_max_size` 或 `image_quality` 变化时，已有向量会被视为过期。发送前图片会处理 EXIF 方向、缩放、重新编码为 JPEG，并且不会携带原始 EXIF/ICC/XMP/IPTC metadata。

向量构建完成后，运行 `analyze-similar` 可把视觉相似组预生成到 SQLite。图片详情页会直接读取本地向量查询相似图片；Library 的“相似图片”模式只读取预生成分组，因此加载更快。

* 浅色模式/暗色模式：您可以选择使用浅色模式或暗色模式。
* 视频播放速度：您可以调整视频播放速度。

## 文档

- 文档索引：`docs/README.md`
- 版本记录：`docs/release_notes.md`


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
