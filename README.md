# TikLocal

**TikLocal** is a **mobile and tablet** **web application** built on **Flask**. It allows you to browse and manage your local videos and images in a way similar to TikTok and Pinterest.

[中文](./README_zh.md)

## Introduction

TikLocal's main features include:

* **A TikTok-like swipe-up browsing experience** with a mixed feed of local videos and images.
* **A file manager-like directory browsing** feature that allows you to easily find and manage local video files.
* **A Pinterest-like grid layout** feature that allows you to enjoy local images.
* **Search, favorites, collections, and lightweight local recommendations** backed by a per-device media index.
* **A year/month timeline** for browsing multi-year libraries through compact, lazy-loaded monthly chapters.
* **Multiple media sources and URL downloads** merged into one local library.
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

The default package supports HTTP and existing TLS certificates without compiling
`cryptography`. This is the recommended installation on Android/Termux. Install the
optional HTTPS extra only when TikLocal should generate and maintain a local CA:

```bash
pip install 'TikLocal[https]'
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

**Installable app and HTTPS:**

TikLocal ships a Web App Manifest, per-instance name, and app icons, so it can be installed from Settings on phones, tablets, and desktops. Browsers such as Chrome and Edge normally require trusted HTTPS. A public domain is optional; a stable LAN hostname is sufficient.

```bash
pip install 'TikLocal[https]'                       # Required for automatic local certificates
tiklocal ~/Videos --https --name "Studio Mac"     # Maintain a local certificate; defaults to port 8443
tiklocal tls trust                                # Trust TikLocal CA on the server Mac
tiklocal tls status                               # Inspect certificate names and CA fingerprint
tiklocal tls renew --hostname studio-mac.local    # Add a stable hostname and renew the leaf certificate
tiklocal ~/Videos --tls-cert cert.pem --tls-key key.pem  # Use an existing certificate
```

Automatic HTTPS creates a TikLocal-specific local CA under `~/.tiklocal/tls/` and renews the server certificate when names, LAN addresses, or expiry require it. On the server Mac, `tiklocal tls trust` adds that CA to the current user's login keychain. Every other client device must trust the CA once before connecting; `/install` provides an Apple-friendly `.cer`, a PEM alternative, the fingerprint, and platform instructions. Never copy or install `ca-key.pem`. Each TikLocal server has an independent CA by default, so multiple servers must be trusted separately. `--hostname` only adds a certificate name; it does not configure DNS, so make sure the name resolves through your router, mDNS/Bonjour, or local DNS.

The initial installable-app release registers a deliberately narrow Service Worker for versioned public interface assets and app icons. Dynamic pages, APIs, thumbnails, and original media are excluded, remain private, and preserve native HTTP Range behavior. Safari uses **File > Add to Dock**; Chromium browsers expose the direct button only after their install criteria are met.

On Android/Termux, use the default installation and `http://127.0.0.1:8000` when the
browser and TikLocal run on the same phone. This avoids the native Rust/OpenSSL build
required by `cryptography`. To serve other devices with TikLocal-managed HTTPS, install
`TikLocal[https]` on a supported host; providing your own `--tls-cert` and `--tls-key`
does not require that extra.

**Access authentication:**

Authentication is enabled by default. On first start, TikLocal prints a generated access password in the terminal. Every page, API, media file, and management action requires sign-in; after sign-in, all features are available.

```bash
tiklocal auth status              # Show authentication status and storage path
tiklocal auth set-password        # Set a new password and invalidate existing sessions
TIKLOCAL_AUTH_PASSWORD='a-long-private-password' tiklocal auth set-password
```

The password is stored as a scrypt hash in `~/.tiklocal/auth.json`; the plain password is never stored. Keep TikLocal on a trusted LAN. When exposing it behind an HTTPS reverse proxy, set `FLASK_AUTH_COOKIE_SECURE=true` so browsers only send the session cookie over HTTPS.

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
tiklocal analyze-similar /path/to/media --limit 500 --yes
tiklocal analyze-similar /path/to/media --profile --dry-run
```

Recommended workflow:
- Run `--dry-run` first to inspect total images, already-indexed images, missing vectors, stale vectors, and selected items.
- Use `--limit 200 --order latest` for the first low-cost batch.
- Use `--source <id>` to index one media source from `media_sources`.
- Use `--cleanup` to remove vectors for files that no longer exist.
- Use `--force` only when intentionally rebuilding existing vectors.
- Use `--yes` to skip the confirmation prompt in scripts.

`vectorize` only uploads images that are missing or stale. A vector becomes stale when file size, mtime, model, dimensions, `image_max_size`, or `image_quality` changes. Images are EXIF-transposed, resized, re-encoded as JPEG, and sent without original EXIF/ICC/XMP/IPTC metadata.

After vectors are built, run `analyze-similar` to precompute visual similarity groups into SQLite. The image detail page can query similar images directly from local vectors, while the Library `Similar Images` mode only reads precomputed groups for fast loading.

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

### Home and Flow

The home page (`/`) is a calm launchpad for choosing a session, revisiting recently indexed media, rediscovering images, and opening personal collections. The immersive mixed feed lives at `/flow`:

- Videos and images are mixed in one swipe flow (video-first density, randomized order)
- Image cards support in-feed AI caption/tags panel
- Image cards support circular magnifier (2.5x / 5x)
- Image cards do **not** auto-advance; swipe manually to move next/previous

### Media timeline

Library now opens as a year/month timeline for images and videos. Each month loads a stable representative set—up to 9 items on phones and 15 on larger screens—while the complete month remains available with Quick Viewer, favorites, and collections.

The timeline prefers image EXIF capture time, then a date embedded in the filename, and finally filesystem modification time. Resolved values are cached in the local SQLite index so unchanged files are not reopened on every startup. Random images, similar images, latest videos, and large-file browsing remain available under Explore.

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
name: Studio Mac
https: true
port: 8443
hostnames:
  - studio-mac.local

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
tiklocal analyze-similar ~/Videos/TikLocal --limit 500 --yes
```

API keys are read from environment variables, preferring `TIKLOCAL_VISION_API_KEY` for vision, `TIKLOCAL_EMBEDDING_API_KEY` for embedding, then falling back to `TIKLOCAL_AI_API_KEY`, `OPENAI_API_KEY`, or `OPENROUTER_API_KEY`.

* **Light and dark modes:** You can choose to use light or dark mode.
* **Video playback speed:** You can adjust the video playback speed.

## Documentation

- Docs index: `docs/README.md`
- Flow interaction unification: `docs/flow-interaction-unification.md`
- Media index and local recommendation architecture: `docs/media-index-and-recommendation.md`
- OpenRouter image-to-video research: `docs/openrouter-image-to-video-research.md`
- Release notes: `docs/release_notes.md`


## TODO

* [ ] Add more management operations, such as moving files and creating folders
* [x] Add basic login control
* [ ] Add a Docker image
* [ ] Add a tagging feature

## Contribution

TikLocal is an open source project that you can contribute to in the following ways:

* Submit code or documentation improvements.
* Report bugs.
* Suggest new features.

## Contact us

If you have any questions or suggestions, you can contact us in the following ways:

* GitHub project page: [https://github.com/ChanMo/TikLocal/](https://github.com/ChanMo/TikLocal/)
* Email: [chan.mo@outlook.com]
