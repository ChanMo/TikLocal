<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/ChanMo/TikLocal/main/brand/tiklocal-lockup-dark.svg">
    <img src="https://raw.githubusercontent.com/ChanMo/TikLocal/main/brand/tiklocal-lockup.svg" alt="TikLocal" width="260">
  </picture>
</h1>

**TikLocal** is a **mobile and tablet** **web application** built on **Flask**. It allows you to browse and manage your local videos and images in a way similar to TikTok and Pinterest.

The repository also includes **LumaFold**, a local-first native iPhone/Android
client under `apps/radio`. It can import user-selected photos and videos into a private
offline Flow without an account, network, or TikLocal Server; Radio remains an
optional connection to a user-operated server.

## Introduction

TikLocal's main features include:

* **A TikTok-like swipe-up browsing experience** with a mixed feed of local videos and images.
* **A file manager-like directory browsing** feature that allows you to easily find and manage local video files.
* **A Pinterest-like grid layout** feature that allows you to enjoy local images.
* **Search, favorites, collections, and lightweight local recommendations** backed by a per-device media index.
* **A year/month timeline** for browsing multi-year libraries through compact, lazy-loaded monthly chapters.
* **Multiple media sources and URL downloads** merged into one local library.
* **Support for light and dark modes** to suit your personal preferences.

## Screenshots

TikLocal is designed mobile-first, so the phone views are shown first for each page, with the desktop view alongside for context.

### Flow — TikTok-style swipe feed

<img src="docs/screenshots/flow-mobile.png" alt="TikLocal Flow page on a phone, showing a full-screen vertical video swipe feed with like/save/info actions" width="280" /> <img src="docs/screenshots/flow-desktop.png" alt="TikLocal Flow page on desktop, showing the same swipe feed with a sidebar navigation" width="480" />

*A mixed video/image swipe feed, similar to TikTok, with manual swipe navigation and in-feed actions.*

### Radio — ambient player

<img src="docs/screenshots/radio-mobile.png" alt="TikLocal Radio page on a phone, showing a vinyl-record player UI over an animated rain-on-window background" width="280" /> <img src="docs/screenshots/radio-desktop.png" alt="TikLocal Radio page on desktop, showing the same vinyl-record player with a wider layout" width="480" />

*An ambient audio player with a vinyl-style visualizer, room backgrounds (rain/breeze), and a local track list.*

### Library — Pinterest-style grid + timeline

<img src="docs/screenshots/library-mobile.png" alt="TikLocal Library page on a phone, showing a year/month timeline with a Pinterest-style grid of photo and video thumbnails" width="280" /> <img src="docs/screenshots/library-desktop.png" alt="TikLocal Library page on desktop, showing the same year/month timeline grid in a wider layout" width="480" />

*A Pinterest-like grid organized as a year/month timeline, for browsing multi-year libraries.*

> **Note:** the media shown above (gradient images, abstract clips, and ambient tones) is synthetic sample content generated only to populate the screenshots — not the app owner's real files. TikLocal never ships with or requires any bundled media library.

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

The default package serves HTTP and works on Android/Termux. HTTPS is provided by an external reverse proxy.

### Usage

Starting TikLocal is very simple, just run the following command:

```bash
tiklocal ~/Videos/
```

You can specify any media folder.

To close, press `Ctrl + C`. Normal shutdown (including SIGTERM) cancels unfinished downloads, stops their processes, and retains downloaded files. Interrupted jobs are not resumed automatically.

The CLI owns the download manager lifecycle. When embedding `create_app()` in a custom WSGI host, call `app.extensions['download_manager'].start()` inside the serving worker, then `.close()` in its shutdown/finally hook. Do not attach close to Flask's per-request teardown. Constructing the app alone starts no download threads; starting the manager is required before submitting jobs.

#### CLI Commands

TikLocal provides several CLI commands:

**Start the server:**
```bash
tiklocal /path/to/media           # Start with media directory
tiklocal --port 9000              # Use custom port
tiklocal --media-source photos=~/Pictures/AI  # Add a media source, repeatable
```

**Browser access and HTTPS:**

Open TikLocal directly in your browser. PWA installation, offline asset caching, built-in HTTPS, and local certificate management have been removed. Existing media and saved data are unchanged.

For HTTPS, terminate TLS at an external reverse proxy and forward requests to TikLocal's HTTP server:

```bash
FLASK_AUTH_COOKIE_SECURE=true tiklocal ~/Videos --host 127.0.0.1 --port 8000 --name "Studio Mac"
```

The proxy handles certificates and should preserve the original Host header and media Range requests. Use the secure-cookie setting only when browsing through HTTPS. For direct LAN HTTP, omit it and bind to the appropriate interface.

When upgrading, remove `https`, `tls_cert`, `tls_key`, and `hostnames` from the YAML configuration. Active old TLS settings stop startup instead of silently switching to HTTP; the old `--https`, `--tls-cert`, `--tls-key`, `--hostname` options, `tls` commands and `[https]` package extra are no longer supported. Certificate files under `~/.tiklocal/tls/` and system trust records are left untouched.

Previously installed shortcuts can be removed manually. Revisit the same origin to retire its old TikLocal worker and public asset cache; browsers cannot clean another origin's state. `/service-worker.js` remains only as a retirement endpoint. New visits do not register a worker, and the browser's ordinary HTTP caching remains available.

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

The CLI and Web share thumbnail caches keyed by media-source URI. Valid legacy
caches for the default source remain readable. CLI generation first tries a frame
near 20% of the video duration; Web generation keeps its short fixed-time fallback.

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

After vectors are built, run `analyze-similar` to precompute visual similarity groups into SQLite. The image detail page can query similar images directly from local vectors, while the experimental page at `/experiments/similarity` reads precomputed groups. Open it from Settings when enabled; old Library links redirect there.

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
port: 8000

vision:
  enabled: true
  base_url: https://openrouter.ai/api/v1
  model_name: google/gemini-2.5-flash
  temperature: 0.6
  tags_limit: 5
  system_prompt: |
    You are an image analysis assistant. Return JSON only.
  user_prompt: |
    Analyze this image and return a short English title plus up to {tags_limit} English tags.
    Output JSON: {"title":"...","tags":["..."]}

experiments:
  similarity:
    enabled: true

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

`experiments.similarity.enabled` is the startup switch for the experiment, including its CLI commands. Explicit `false` disables it without deleting vectors or groups. When omitted, a valid legacy `embedding.enabled: true` enables it; saved `embedding_config.json` takes precedence over the YAML configuration. Existing vectors alone do not enable the feature: set the new switch explicitly to view those results. Restart the server after changing the switch.

For read-only access, enable the experiment and set the effective `embedding.enabled` to `false`. Building vectors still requires `embedding.enabled: true`; viewing results never invokes a model. CLI configuration precedence is defaults < YAML < saved embedding configuration < CLI overrides. Preview with `--dry-run` and a bounded `--limit` before building; estimated cost is unknown. Synchronous Web builds have been retired: `POST /api/ai/embedding-index/run` returns 410 with CLI guidance (404 when the experiment is disabled).

API keys are read from environment variables, preferring `TIKLOCAL_VISION_API_KEY` for vision, `TIKLOCAL_EMBEDDING_API_KEY` for embedding, then falling back to `TIKLOCAL_AI_API_KEY`, `OPENAI_API_KEY`, or `OPENROUTER_API_KEY`.

* **Light and dark modes:** You can choose to use light or dark mode.
* **Video playback speed:** You can adjust the video playback speed.

## Documentation

- Docs index: `docs/README.md`
- Flow interaction unification: `docs/flow-interaction-unification.md`
- Media index and local recommendation architecture: `docs/media-index-and-recommendation.md`
- Native local-first app architecture: `docs/native-local-app-architecture.md`
- TikLocal Radio native client architecture: `docs/radio-native-client-architecture.md`
- TikLocal Radio player selection: `docs/radio-player-selection.md`
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
