# OpenRouter 图片生成视频调研

- 状态: 暂缓产品化，保留为未来尝试
- 更新时间: 2026-06-04

## 背景/目标

本次调研验证 TikLocal 是否可以把本地图片作为首帧，通过 OpenRouter 的视频生成接口生成短视频，并保存回本地媒体库。

阶段目标不是立即产品化，而是确认接口可用性、关键约束、保存流程与未来集成方向。

## 结论或方案

OpenRouter 的视频生成接口可用于图片转视频。`x-ai/grok-imagine-video` 当前支持：

- `frame_images` 的 `first_frame` 输入。
- `480p` / `720p` 输出。
- `9:16` 等常见比例。
- 1 到 15 秒短视频生成。

实际 PoC 路径为：

1. 准备一个 OpenRouter/provider 可访问的 HTTPS 图片 URL。
2. 调用 `POST https://openrouter.ai/api/v1/videos` 提交异步生成任务。
3. 使用返回的 `polling_url` 轮询状态。
4. 完成后下载 `unsigned_urls[0]` 或内容接口里的 MP4。
5. 保存到本地目录，后续若落入 `MEDIA_ROOT`，TikLocal 可按普通视频扫描和展示。

仓库中保留了一个一次性验证脚本：

```bash
poetry run python scripts/openrouter_image_to_video.py \
  --image-url "https://example.com/image.jpg" \
  --prompt "Describe the desired motion and style" \
  --output outputs/grok-image-to-video.mp4
```

脚本要求通过环境变量提供 API key：

```bash
OPENROUTER_API_KEY=...
```

脚本不内置具体图片 URL 或 Prompt，避免把一次性素材和提示词固化到仓库。

## 影响范围

当前仅保留调研文档与 PoC 脚本，没有接入 TikLocal UI、路由、任务队列或设置页。

相关文件/模块：

- `scripts/openrouter_image_to_video.py`
- `tiklocal/templates/image_detail.html`
- `tiklocal/services/downloader.py`
- `tiklocal/services/metadata.py`

未来若产品化，建议新增独立的 `VideoGenerationManager`，不要把 AI 生成任务塞进 `DownloadManager`。`DownloadManager` 的队列、历史和取消模式可作为参考，但领域语义应保持分离。

## 风险与权衡

本地图片 URL 问题是最大约束。TikLocal 的 `/media/...` 通常只在本机可访问，OpenRouter provider 无法直接拉取。因此产品化前必须解决图片可访问性：

- 优先方案：将本地图片临时上传到 S3/R2/OSS，并生成短期 HTTPS URL。
- 开发验证：可用公网图片 URL 或临时 tunnel。
- 不建议：直接把 localhost、本机局域网地址或长期失效的社交媒体 CDN URL 写入配置。

其他风险：

- 视频生成是付费异步任务，需要明确费用提示、失败状态与重试策略。
- 第三方视频生成可能不适合隐私敏感图片，需要在 UI 中明确提示外部服务处理。
- Base64 图片输入在视频生成接口中没有明确官方保证，当前应以 HTTPS 图片 URL 为主。
- OpenRouter 账号 credits 不足时会返回 `402 Insufficient credits`，任务不会创建。

## 后续事项

- [ ] 若恢复产品化，先设计独立 `VideoGenerationManager` 和 `video_generation_jobs.json`。
- [ ] 增加图片详情页入口：生成短视频、参数确认、任务状态、完成后查看视频。
- [ ] 设计临时图片托管方案，优先评估 R2/S3 signed URL。
- [ ] 产品化前增加任务历史、取消、重试和错误恢复策略。
