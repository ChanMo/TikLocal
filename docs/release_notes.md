# Release Notes

## Unreleased

## v0.8.39 (2026-09-23)

- Added the TikLocal mark: a lowercase `t` whose hook ends in an orange dot, drawn on the same 24-unit, 2px round-stroke grid as the Feather icons in the web UI.
- Replaced the `TL` text badges in the desktop rail, the page header, and the login screen with the mark, and set the wordmark as tik**Local**.
- Added favicons for every page: an SVG icon that follows the browser's light or dark scheme, a 16/32/48px `favicon.ico`, an Apple touch icon, and a public `/favicon.ico` route that works with authentication enabled.
- Added `brand/` with light, dark, and monochrome marks, outlined wordmark lockups, a 512px avatar, and usage guidelines. `scripts/build_brand.py` regenerates every asset from one geometry definition.

## v0.8.38 (2026-09-21)

- Consolidated Web Radio, media details, transfers, settings, Flow, and Library behavior into their route and service modules. Shared thumbnail, media payload, statistics, source, favorite, and recommendation logic now has one implementation.
- Removed PWA installation and built-in local HTTPS support. External reverse proxies now provide HTTPS while authentication, secure cookies, media streaming, and Range requests remain supported. Legacy TLS options fail with a clear migration message, and the retirement service worker only unregisters itself and clears TikLocal public caches.
- Simplified the downloader to one explicit concurrent queue with clean startup and shutdown. Pending work and child processes are stopped during service shutdown, registration failures remain visible and retryable, and incomplete source scans preserve existing index entries.
- Isolated vector and similar-image experiments behind a startup flag and a dedicated results page. Existing vector data is retained while the regular Library remains independent of experimental code.
- Fixed Flow pagination gaps caused by themes and source galleries, plus premature completion for image-only libraries. Page sizes now follow base media counts.
- Replaced the native mode-selection home with `Flow / Library / Music / Settings`. Flow is the default local-first experience, imported photos and videos work without an account or server, and TikLocal remains an optional folder source under Settings.
- Added a transactional SQLite local library with image and video counts, storage totals, multi-select deletion, clear-all, persistent video thumbnails, import progress, free-space reporting, and a 128 MB copy safety margin. Deletion affects only app-managed offline copies, which are excluded from device backup where supported.
- Adopted `LumaFold` as the reversible working brand and aligned the app name, launch screen, permissions, and local-library copy. Existing bundle identifiers, schemes, storage, icons, and server protocol remain compatible.
- Added the React Native and Expo Radio client with native navigation, background audio, lock-screen metadata, favorites, limited encore playback, sleep timers, and a responsive Signal Dial that honors Reduce Motion.
- Added a single-server connection model with QR, pasted-link, and manual pairing. SecureStore distinguishes paired and known servers, preserves recoverable connection details, clears credentials only on explicit forget or invalid authorization, and supports cancellable server changes.
- Added a token-free local queue snapshot that restores the station, queue, current track, and recent history using the current SecureStore token. Invalid authorization, device changes, and forgetting the server clear the snapshot.
- Fixed unwanted retuning during notification-center, control-center, navigation, and app-lifecycle events. Normal restoration performs no network request, and offline retry preserves an existing queue.
- Added `/api/v1` for native Radio: password pairing, hashed bearer tokens, real station queues, Range streaming, metadata, artwork, idempotent favorites, listening feedback, token revocation, and two-minute single-use QR authorization.
- Added QR-only camera scanning that requests camera access only when opened and stores no images. Android release artifacts were verified without microphone permission.
- Added production icons, adaptive Android assets, native launch screens, EAS preview and production profiles, iOS encryption declarations, and dedicated Android release signing outside the repository.
- Replaced deprecated React Native safe-area APIs, added the required direct `expo-asset` peer dependency, and passed Expo Doctor checks.
- Added the native client CI gate for Node.js 22, frozen lockfile install, TypeScript, Expo dependency health, production bundles for both platforms, and bundled audio resolution. Client and server regression suites cover session restoration, credentials, links, QR permissions, protocol security, Range handling, and semantic interactions.
- Improved accessibility labels for pairing, navigation, connection, stations, actions, and progress. The first client simplification audit removed unreachable URL defenses and redundant promise and test wrappers.
- Added explicit empty-library handling and best-effort token revocation when SecureStore writes fail. Added a dual-platform device acceptance checklist; background sleep timers remain a release decision gate.
- Kept `expo-audio` for `0.1.x` after an isolated player evaluation. System and headset controls promise play and pause only; track skipping remains outside the `0.1.x` commitment.
- Added English privacy, store metadata, review notes, and Google Play Data Safety drafts. Claims that require device testing remain release gates.
- Closed the `tiklocal-radio://` pairing path for cold-start and foreground events. Valid links only open and prefill pairing for confirmation; invalid links do not alter the active Radio session.
- Distinguished iOS Development Client and standalone Release workflows with `ios:device` and `ios:release`. The iPhone release build embeds its production JavaScript bundle and no longer depends on Metro.

## v0.8.37 (2026-07-23)

- Added a limited encore feature that can replay a favorite current track one to three times without expanding the main controls.
- Added persistent `RAIN / BREEZE / OFF` room ambience using lightweight, silent, seamless H.264 loops with posters.
- Tuned ambience for theme and viewport size, including reduced-motion and data-saving behavior.

## v0.8.36 (2026-07-22)

- Removed the mandatory `cryptography` dependency that caused Android and Termux installs to fall back to local Rust and OpenSSL builds.
- Moved automatic local HTTPS certificate management to the optional `TikLocal[https]` extra with clear CLI guidance when it is unavailable.
- Retained regular HTTP, user-provided certificates, HTTPS tests in CI, and same-device Termux guidance using `http://127.0.0.1:8000`.

## v0.8.35 (2026-07-22)

- Added an installable Web App with instance-specific manifests, generated icons, standalone metadata, and browser-specific installation guidance.
- Added `tiklocal tls init/status/renew/trust`, automatic local CA and certificate renewal, user-supplied certificate support, and native TLS serving through Cheroot.
- Added an installation diagnostics and CA download page plus a minimal service worker that cached only versioned public assets and icons.
- Fixed an installation-page failure when a new template was served by an older process and expanded PWA, certificate, CLI, cache-boundary, and HTTPS Range coverage.

## v0.8.34 (2026-07-21)

- Redesigned Radio as an editorial record station with dynamic ambience, vinyl texture, an on-air state, and clearer playback feedback.
- Added a two-column desktop stage while retaining a compact mobile layout and support for short screens, dark mode, and reduced motion.
- Improved semantic playback states and fixed overflow and positioning in the media details menu.

## v0.8.33 (2026-07-20)

- Added an editorial year and month Library timeline with representative media, responsive item limits, year navigation, and complete month views.
- Added a persistent media-time index using EXIF, filename dates, then file timestamps, with cached results for unchanged files.
- Added a lightweight timeline summary API and bounded concurrent thumbnail loading.
- Moved random, similar, recent-video, and large-file modes into Explore while keeping Favorites and Collections intact.
- Required downloaded media to finish indexing before a task reports success.

## v0.8.32 (2026-07-20)

- Fixed Python 3.10 compatibility where `datetime.UTC` was unavailable and added Python 3.10, 3.12, and 3.14 to the release gate.

## v0.8.31 (2026-07-20)

- Enabled single-password access by default across pages, APIs, media streams, and administrative actions.
- Added a dedicated login page, long-lived sessions, global CSRF protection, login throttling, security headers, scrypt password storage, and authentication CLI commands.
- Restored Flow video playback from the beginning while retaining randomized item order.
- Improved first-frame presentation to avoid black frames, stale frames, and brightness pulses during transitions.

## v0.8.30 (2026-07-19)

- Added a dedicated Home centered on Flow and Radio, with recent media, rediscovery, collections, and library status using thumbnails only.
- Moved the immersive feed to `/flow` and unified desktop side navigation, mobile switching, Settings, and Download headers.

## v0.8.29 (2026-07-13)

- Revealed randomly positioned videos only after seeking completed and pre-seeked the next item.
- Fixed occasional enlargement flashes for short videos and Live Photos by validating decoded covers and isolating asynchronous transitions.

## v0.8.28 (2026-07-13)

- Fixed mobile Library, Favorites, and Collection pages occasionally jumping to the top during normal scrolling by rebuilding masonry only when width, columns, or gaps change.

## v0.8.27 (2026-07-12)

- Added a SQLite media query index and startup reconciliation for multi-source queries, pagination, deletion, and downloads, including temporarily unavailable sources.
- Improved Flow and Library startup with smaller initial payloads, on-demand thumbnails, indexed navigation, and clearer recovery from request and media failures.
- Added local recommendations based on views, skips, and completions while preserving exploration and diversity, plus profile reset.
- Unified the dock, Library, saved areas, Settings, themes, search, collections, and page interactions.
- Added stable per-session randomized starts and consumption tracking based on actual play time.
- Added adaptive collage covers for collections and improved collection details and immediate updates.
- Simplified Download to a single-link entry with media modes, automatic site and credential matching, clearer actions, and low-frequency polling.
- Moved downloader status, concurrency, and credentials into Settings with safe local updates.

## v0.8.26 (2026-07-04)

- Made `/api/radio/tune` lightweight for large audio libraries and added `/api/radio/metadata` for lazy per-track metadata.
- Added a local Radio feedback profile for plays, completions, skips, favorites, and errors.
- Fixed title flashes, unknown-duration output, cover rotation after pause, vertical rhythm, and unnecessary page scrolling.
- Added coverage for lazy metadata, tune performance boundaries, feedback persistence, and scoring.

## v0.8.25 (2026-07-04)

- Added the low-decision Radio experience with default, recent, and favorite-weighted stations.
- Added the centered signal design, generated record-label fallback, restrained motion, next, favorite, sleep timers, recent-play exclusion, and progress restoration.
- Extended Media Session with artwork, state, duration, progress, and seeking for browser and operating-system controls.
- Added ffprobe title, artist, album, and duration metadata plus Radio selection and artwork tests.

## v0.8.15 (2026-02-25)

- Added the video magnifier and unified magnification behavior across Flow interactions.

## v0.8.14 (2026-02-25)

- Reworked the collection overlay as a mobile drawer with improved keyboard interaction.

## v0.8.13 (2026-02-24)

- Added future annotations to fix `function` object subscription failures on Python 3.12.

## v0.8.12 (2026-02-23)

- Added shared session and media-action controllers across Home, Library, and Favorites.
- Removed retired browse and gallery routes, APIs, and templates.
- Added JSON-backed custom collections, collection APIs and pages, reverse media lookup, and consistent collection navigation.
- Added an inline collection picker and creation flow to quick viewers and Home, with immediate membership updates.
- Simplified collection cards and moved rename and delete into a menu with an in-page rename dialog.
- Fixed the click race that immediately closed a newly opened collection picker.

## v0.8.10 (2026-02-22)

- Fixed body scroll remaining locked after closing the Library or Favorites quick viewer.
- Added width and height to the Library API with cached Pillow and ffprobe probing.
- Preserved existing metadata when writing generated image titles and tags.
- Replaced CSS columns with deterministic shortest-column masonry and debounced responsive rebuilding.
- Expanded regression coverage for dimensions and masonry behavior.

## v0.8.9 (2026-02-22)

- Changed the primary navigation to `Flow / Library / Favorites / Download / Settings` and made Library the unified image and video entry point.
- Added a minimal masonry Library, paginated `/api/library/items`, and an inline image and video quick viewer.
- Unified the immersive state model and shared time and magnifier geometry across Flow, Library, and Favorites.
- Redirected legacy browse and gallery paths to Library.

## v0.8.8 (2026-02-22)

- Upgraded Home to a mixed image and video feed through `/api/feed/mix` with ratio targets and light randomization.
- Reused Gallery captions, tags, focus mode, and magnification for images while keeping media-specific controls.
- Fixed contained-image magnifier geometry and stale asynchronous caption updates.
- Removed obsolete interaction code and added mixed-feed API coverage.

## v0.8.7 (2026-02-21)

- Added persistent source links for downloads with fallbacks to sidecar metadata and filename patterns.
- Added single and batch source APIs plus source links in media details and download output.
- Adopted structured short output names and sidecar metadata from yt-dlp.
- Added coverage for source persistence, cleanup, fallback parsing, batch lookup, and synchronized deletion.

## v0.8.6 (2026-02-21)

- Added selectable yt-dlp and gallery-dl engines with availability and version reporting.
- Extended task history with engine, version, output files, and file counts while retaining compatibility.
- Added gallery-dl cookie reuse, archive deduplication, temporary staging, and collision-safe moves into the media root.
- Fixed image output links and added an image redirect fallback from detail routes.

## v0.8.5 (2026-02-20)

- Added the `/download` queue with create, cancel, delete, clear-history, and retry actions.
- Added automatic and manual cookie-file selection with safe same-name replacement.
- Added downloader resume and retry options, simplified task controls, lower-emphasis states, and toast feedback.
- Added download configuration, cookie, retry, and history tests.

## v0.8.4 (2026-02-20)

- Added configurable image-generation system and user prompts, temperature, tag limits, reset behavior, model URL, model name, and API key status.
- Added per-request overrides on image details and returned prompt and model source metadata.
- Added focus mode to the Gallery overlay while retaining access to tools.
- Added prompt configuration and metadata precedence tests.
