# LumaFold Native App

LumaFold is TikLocal's local-first client. It opens directly into a private Flow, imports user-selected photos and videos from Photos or Files, stores offline copies and a SQLite index in the app sandbox, and supports vertical browsing and playback without an account, network connection, or TikLocal Server.

The app has four top-level spaces: `Flow`, `Library`, `Music`, and `Settings`. Flow and Library are the primary photo and video experience. Radio lives under Music, while Settings exposes server connections as an optional TikLocal Folder Source. Music can pair with one server through a single-use QR code from TikLocal Web Settings, a pasted pairing link, or a manually entered address and access password. Demo Signal works without a server. The visible brand and candidate icon use LumaFold; the bundle identifier, Expo slug, URL scheme, database, and pairing protocol retain their existing internal identifiers to avoid migration during brand testing.

## Local development

```bash
cd apps/radio
npm install
npm run typecheck
npm test
npm run ios:device
```

`npm run ios:device` builds and installs an iOS Development Build. It does not include a standalone JavaScript bundle, so start Metro for normal development:

```bash
npm start
```

Open LumaFold on the phone and select the automatically discovered Metro server in Expo Development Client. That screen expects the JavaScript development server, usually on port `8081`. Do not enter a TikLocal Server address there, or its HTML response will be treated as a JavaScript bundle and produce `Expected MIME-Type ... but got text/html`.

Enter or scan the TikLocal Server address only after opening LumaFold's pairing screen, for example `http://192.168.0.128:8888`.

Re-run `npm run ios:device` after changing native modules or `app.config.ts`. The local `tiklocal-storage` Expo Module contains only native backup-exclusion and video-frame functions. SQLite, imports, and file lifecycle remain owned by the single TypeScript library module.

For a standalone app that does not depend on Metro, install a local Release build:

```bash
npm run ios:release
```

Release builds embed the production JavaScript bundle and Demo audio, then open directly into LumaFold Flow.

Flow copies explicitly selected media into the app's private directory and stores its local manifest in SQLite. Library shows actual storage use. Long-press selection and Clear remove only app-managed copies, never the originals in Photos or Files. On iOS, media-copy directories are excluded from iCloud device backup; the SQLite index and preferences may still be included in system backups. Video imports receive local previews, older records are backfilled, multi-item imports show deterministic progress, and known file sizes reserve a 128 MB device-space margin before copying.

For Radio pairing, generate and scan a single-use QR code from TikLocal Web Settings. The app shows the target server and exchanges the authorization only after confirmation. You can also paste a pairing link or manually enter a server address and access password:

```text
https://studio-mac.local:8443
```

The QR code contains neither the password nor a device token. The server keeps only a hash of the single-use authorization in memory. After pairing, the password and one-time authorization are discarded; SecureStore retains the server address, name, and returned device token. Changing the TikLocal access password invalidates device tokens while preserving the remembered server address and name for reauthorization.

When a server is offline, the app keeps the connection profile and offers Retry. It also remembers the most recent valid address after a failed connection. Only confirming **Forget This Server** removes the local connection and attempts to revoke the device token. Individual devices can also be revoked under **Radio Clients** in TikLocal Web Settings.

Notification Center, Control Center, navigation, and ordinary foreground/background transitions do not retune Radio. A cold start restores the station, queue, and current track from a credential-free snapshot and rebuilds media requests with the current SecureStore token. Offline Retry reconnects an existing queue without replacing it randomly.

## Distribution builds

Sign in and link the Expo project before using EAS for the first time:

```bash
npx eas-cli login
npx eas-cli init
npx eas-cli build:configure
```

`eas init` writes the real Expo `projectId`; do not invent it manually. `eas.json` already defines the build profiles, and `build:configure` only checks and completes project state.

Internal builds:

```bash
npx eas-cli build --profile preview --platform ios
npx eas-cli build --profile preview --platform android
```

iOS Simulator build:

```bash
npx eas-cli build --profile preview-simulator --platform ios
```

Store builds:

```bash
npx eas-cli build --profile production --platform ios
npx eas-cli build --profile production --platform android
```

App identifiers, production artwork, splash configuration, and EAS profiles live in `app.config.ts`, `assets/`, and `eas.json`. Versioning starts at `0.1.0 (1)`; EAS production builds increment the remote build version.

`.easignore` excludes generated native projects, dependencies, tests, store materials, and build output. EAS still uploads the runtime `src/`, entry points, configuration, lockfile, and assets. After changing ignore rules, inspect the archive with `eas build:inspect --stage archive`.

Privacy policy, store metadata, and device acceptance materials live in `store/`. Once merged to public `main`, the privacy policy's GitHub page can serve as the initial public URL. External distribution still requires signing accounts, store screenshots, and completed device acceptance.

Static verification without installing the app:

```bash
npx expo prebuild --no-install
npx expo export:embed --platform ios --dev false --entry-file index.ts --bundle-output /tmp/tiklocal-radio-ios.jsbundle
npx expo export:embed --platform android --dev false --entry-file index.ts --bundle-output /tmp/tiklocal-radio-android.bundle
```

The main CI workflow uses Node.js 22 and `package-lock.json` to run `npm ci`, TypeScript, client tests, a pinned Expo Doctor, and production iOS/Android bundle builds with Demo audio copied in. These checks require no Expo, Apple, or Google credentials and do not replace device testing for camera, import, deletion, and playback behavior.

### Local Android native builds

React Native uses JDK 17. Prepare a build machine with:

```bash
brew install openjdk@17
brew install --cask android-commandlinetools
export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export ANDROID_HOME="$HOME/Library/Android/sdk"
yes | sdkmanager --sdk_root="$ANDROID_HOME" --licenses
sdkmanager --sdk_root="$ANDROID_HOME" \
  "platform-tools" "platforms;android-36" "build-tools;36.0.0" \
  "ndk;27.1.12297006" "cmake;3.22.1"
```

Build unsigned-for-production local artifacts:

```bash
npx expo prebuild --clean --no-install --platform android
cd android
NODE_ENV=production ./gradlew :app:assembleRelease :app:bundleRelease
```

Artifacts are written under `android/app/build/outputs/apk/release/` and `android/app/build/outputs/bundle/release/`. CNG-generated projects sign release artifacts with the Android debug certificate by default; those builds are only for local verification.

A dedicated TikLocal Radio keystore was created on the current release machine on 2026-07-26. Its password is stored in macOS Keychain and the key file is outside the repository:

```text
~/Library/Application Support/TikLocal/signing/tiklocal-radio-release.jks
```

Signed `0.1.0 (1)` APK and AAB copies are stored at:

```text
dist/android/TikLocal-Radio-0.1.0-android.apk
dist/android/TikLocal-Radio-0.1.0-android.aab
```

The APK certificate SHA-256 is `eb883956d85ee395938d63aeccf2294426490475db3df62942a15c962e4db483`. Back up the keystore securely before distribution; every upgrade must use the same key. A device with a debug-signed build of the same package must uninstall it before installing the production-signed APK, which clears local app data.

Signing wiring currently exists only in the ignored generated project and is overwritten by `npx expo prebuild --clean`. It is sufficient for release-package verification but is not yet a reproducible repository workflow. After device acceptance, move credential-free signing wiring into a versioned build script or Expo config plugin. `dist/` also remains untracked.

`app.config.ts` blocks unused overlay, external-storage, biometric, and microphone permissions. QR scanning requests only camera permission. After permission changes, run `prebuild` again and inspect the final APK/AAB merged Manifest.

iOS also removes unused microphone and Face ID usage descriptions inherited from dependencies. `Info.plist` retains only the declarations required for QR scanning, background audio, local-network access, and standard encryption reporting.

### Local iOS prerequisites

Initialize a new Xcode installation with:

```bash
sudo xcodebuild -runFirstLaunch
```

For a new iPhone, trust the Mac, enable Developer Mode, and select your Team under **Signing & Capabilities** in Xcode. If the required iOS platform is missing, run `xcodebuild -downloadPlatform iOS`.

## Code constraints

Do not prebuild generic layers here. Before adding dependencies, modules, or directories, review the real boundaries and split thresholds in `docs/radio-native-client-architecture.md`. Before replacing the player or adding system remote controls, review the licensing, new-architecture, and complexity constraints in `docs/radio-player-selection.md`.

Session tests run `useRadioSession` directly, substitute only the native-player boundary, and drive the real API client with Fetch responses. Do not duplicate the session as a reducer, repository, or second state machine for testing.

App tests replace only rendering, API, and storage boundaries. They verify profile ownership, token ordering, and that foreground/background transitions do not trigger Retry. Storage tests constrain the single SecureStore JSON entry, and Radio resume tests constrain the token-free queue file. Keep each test file aligned to that boundary.

API tests replace Fetch directly and cover request and response contracts without duplicating DTOs or creating a fake client. Apart from timeouts that use Jest fake timers, tests do not depend on a real clock or network.

Screen tests drive real user actions through roles, accessible names, state, and values. They do not store component-tree snapshots or assert StyleSheet implementation. Give new controls a clear accessible name before adding semantic queries.
