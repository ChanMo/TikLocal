# TikLocal

**TikLocal** is a **mobile and tablet** **web application** built on **Flask**. It allows you to browse and manage your local videos and images in a way similar to TikTok and Pinterest.

[中文](./README_zh.md)

## Introduction

TikLocal's main features include:

* **A TikTok-like swipe-up browsing experience** with a mixed feed of local videos and images.
* **A file manager-like directory browsing** feature that allows you to easily find and manage local video files.
* **A Pinterest-like grid layout** feature that allows you to enjoy local images.
* **Support for light and dark modes** to suit your personal preferences.

## Use cases

TikLocal is suitable for the following use cases:

* You don't trust TikTok's teen mode and want to provide your child with completely controllable video content.
* You want to browse and manage your local videos and images locally, but don't want to use third-party cloud services.
* You want to use a TikTok-style mixed media browsing experience on your phone or tablet.
* You want to use a Pinterest-style image browsing experience on your phone or tablet.

## How to use

### Installation

TikLocal is a Python application that you can install using the following command:

```
pip install tiklocal
```

### Usage

Starting TikLocal is very simple, just run the following command:

```bash
tiklocal ~/Videos/
```

You can specify any media folder.

To close, press `Ctrl + C`.

#### CLI Commands

TikLocal provides several CLI commands:

**Start the server:**
```bash
tiklocal /path/to/media           # Start with media directory
tiklocal --port 9000              # Use custom port
tiklocal --media-source photos=~/Pictures/AI  # Add a media source, repeatable
```

**Generate video thumbnails:**
```bash
tiklocal thumbs /path/to/media    # Generate thumbnails
tiklocal thumbs /path --overwrite # Regenerate existing thumbnails
```

**Find and remove duplicate files:**
```bash
tiklocal dedupe /path/to/media              # Find duplicates (dry-run mode)
tiklocal dedupe /path --type video          # Check video files only
tiklocal dedupe /path --execute             # Execute deletion
tiklocal dedupe /path --keep newest         # Keep newest files
```

Options for `dedupe`:
- `--type`: File type (`video`, `image`, `all`)
- `--algorithm`: Hash algorithm (`sha256`, `md5`)
- `--keep`: Keep strategy (`oldest`, `newest`, `shortest_path`)
- `--dry-run`: Preview mode (default)
- `--execute`: Execute actual deletion
- `--auto-confirm`: Skip confirmation prompt

**Build image vector index:**
```bash
tiklocal vectorize /path/to/media --dry-run
tiklocal vectorize /path/to/media --limit 200 --order latest
tiklocal vectorize /path/to/media --source photos --limit 200
tiklocal vectorize /path/to/media --cleanup
tiklocal vectorize /path/to/media --max-size 512 --quality 82
```

Recommended workflow:
- Run `--dry-run` first to inspect total images, already-indexed images, missing vectors, stale vectors, and selected items.
- Use `--limit 200 --order latest` for the first low-cost batch.
- Use `--source <id>` to index one media source from `media_sources`.
- Use `--cleanup` to remove vectors for files that no longer exist.
- Use `--force` only when intentionally rebuilding existing vectors.
- Use `--yes` to skip the confirmation prompt in scripts.

`vectorize` only uploads images that are missing or stale. A vector becomes stale when file size, mtime, model, dimensions, `image_max_size`, or `image_quality` changes. Images are EXIF-transposed, resized, re-encoded as JPEG, and sent without original EXIF/ICC/XMP/IPTC metadata.

### URL Download (Web)

TikLocal includes a `/download` page where you can paste a media URL and enqueue a background download job.

Requirements:
- `yt-dlp` (required)
- `gallery-dl` (recommended for image/gallery posts)
- `ffmpeg` (recommended for format merge)

Download engine:
- `yt-dlp`: video-oriented sites and links
- `gallery-dl`: image posts/albums (Instagram/X/Pinterest, etc.)
- Download form allows manual engine selection per task (default: `yt-dlp`)

Cookie for login-only content (optional):
- Put exported cookie files in `~/.tiklocal/cookies`
- Filename should include domain, e.g. `x.com.txt`, `youtube.com.cookies`
- The download page supports `Auto match` or manual file selection per task
- The download page also supports cookie file upload/replace, history delete/clear, and retry for failed tasks

Example installs:
```bash
# macOS (Homebrew)
brew install yt-dlp gallery-dl ffmpeg

# Ubuntu / Debian
sudo apt install yt-dlp gallery-dl ffmpeg
```

### Home Mixed Feed

The home page (`/`) now uses a mixed immersive feed:

- Videos and images are mixed in one swipe flow (video-first density, randomized order)
- Image cards support in-feed AI caption/tags panel
- Image cards support circular magnifier (2.5x / 5x)
- Image cards do **not** auto-advance; swipe manually to move next/previous

### Configuration

TikLocal provides some configuration options that you can adjust to your needs.

You can configure one or more media directories in `~/.config/tiklocal/config.yaml`:

```yaml
media_sources:
  - id: default
    name: Main Library
    path: ~/Videos/TikLocal
  - id: photos
    name: Photos
    path: ~/Pictures/AI
download_source: default

vision:
  enabled: true
  base_url: https://openrouter.ai/api/v1
  model_name: google/gemini-2.5-flash
  temperature: 0.6
  tags_limit: 5
  system_prompt: |
    You are an image analysis assistant. Return JSON only.
  user_prompt: |
    Analyze this image and return a short Chinese title plus up to {tags_limit} Chinese tags.
    Output JSON: {"title":"...","tags":["..."]}

embedding:
  enabled: true
  base_url: https://openrouter.ai/api/v1
  model_name: google/gemini-embedding-2
  dimensions: 768
  image_max_size: 512
  image_quality: 82
```

The legacy single-directory configuration still works:

```yaml
media_root: ~/Videos/TikLocal
```

Multiple media sources are merged into one unified library. Internal media URIs use the `@source_id/path` format, while old bare-path links and favorites remain compatible through the default source.

Image recognition uses `vision`; image vectorization uses `embedding` and stores image vectors in the local SQLite application database (`~/.tiklocal/tiklocal.sqlite3` by default). The image detail page only reads the local index for similar-image recommendations. Use the CLI to build or update vectors:

```bash
tiklocal vectorize ~/Videos/TikLocal --limit 200 --order latest
tiklocal vectorize ~/Videos/TikLocal --dry-run
```

API keys are read from environment variables, preferring `TIKLOCAL_VISION_API_KEY` for vision, `TIKLOCAL_EMBEDDING_API_KEY` for embedding, then falling back to `TIKLOCAL_AI_API_KEY`, `OPENAI_API_KEY`, or `OPENROUTER_API_KEY`.

* **Light and dark modes:** You can choose to use light or dark mode.
* **Video playback speed:** You can adjust the video playback speed.

## Documentation

- Docs index: `docs/README.md`
- Flow interaction unification: `docs/flow-interaction-unification.md`
- OpenRouter image-to-video research: `docs/openrouter-image-to-video-research.md`
- Release notes: `docs/release_notes.md`


## TODO

* [ ] Add search
* [ ] Add more management operations, such as moving files and creating folders
* [ ] Add basic login control
* [ ] Add a bookmarking feature
* [ ] Add a Docker image
* [ ] Add a tagging feature
* [ ] Use recommendation algorithms

## Contribution

TikLocal is an open source project that you can contribute to in the following ways:

* Submit code or documentation improvements.
* Report bugs.
* Suggest new features.

## Contact us

If you have any questions or suggestions, you can contact us in the following ways:

* GitHub project page: [https://github.com/ChanMo/TikLocal/](https://github.com/ChanMo/TikLocal/)
* Email: [chan.mo@outlook.com]
