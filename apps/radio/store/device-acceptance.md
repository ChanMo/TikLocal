# LumaFold Device Acceptance Checklist

- Target version: `0.1.0 (1)`
- Status: JuPhone local core, thumbnails, and bulk-import feedback passed; full P0 validation continues
- Updated: 2026-08-26

## Release decision

The local Library and offline Flow are the primary release scope. All related P0 items must pass before store submission. Background Radio playback, lock-screen controls, and headset behavior may appear in store copy only after their P0 checks pass. Record the device, OS version, build number, and evidence for every item; simulator results are not a substitute.

## Local Library and offline Flow

- [x] P0 — The iOS Release installs, cold-starts into Home, and runs My Flow with Metro and TikLocal Server offline.
- [ ] P0 — Photos permission is requested only after tapping Photos; full, limited, and denied access all have recoverable outcomes.
- [ ] P0 — The Files picker imports local and downloaded iCloud Drive photos, short videos, and large videos.
- [ ] P0 — App copies still open in the grid and Flow after disconnecting all networks and deleting or moving source files.
- [ ] P0 — The Library survives restart; repeated imports create no unexpected duplicates or orphaned files.
- [x] P0 — Photo count, video count, and total storage update immediately after import, deletion, and Clear.
- [x] P0 — Long-press multi-delete and Clear have explicit destructive confirmation, remove only TikLocal copies, and leave Photos/Files originals intact.
- [ ] P0 — A single-file deletion failure keeps its SQLite record and reports the unfinished item.
- [ ] P0 — The final iOS build marks `tiklocal-media/` as excluded from iCloud device backup.
- [ ] P0 — Videos play on entry, pause offscreen, support manual pause, loop, and sound; images neither flicker nor stretch incorrectly.
- [ ] P1 — Support boundaries for HEIC, HDR, Live Photo, ProRes, and common Files containers are recorded without corrupting the Library on failure.
- [ ] P1 — Measure startup, scrolling, memory, and database queries with 500, 5,000, and 20,000 media records.
- [ ] P1 — Interrupted imports, low storage, and OS termination leave no unremovable partial files.

JuPhone testing on 2026-08-26 confirmed Flow playback in airplane mode, originals remaining after local-copy deletion, accurate storage statistics, and Clear leaving originals intact. A second Release also passed old-video preview backfill, bulk-import progress, and remaining-space display. Automated tests cover low-space blocking, which still needs validation on a nearly full real device.

The LumaFold working-brand Release installed over the original bundle identifier and launched successfully the same day. The display name, icon, splash screen, and permission copy took effect without migrating local data or TikLocal Server pairing.

Known boundaries:

- The single `expo-audio` player provides system play, pause, progress, and lock-screen media sessions.
- The current SDK exposes no headset next/previous callbacks for this player. Version `0.1.x` promises only system and headset play/pause; remote track changes are outside this release scope.
- The sleep timer currently uses a JavaScript timer. Verify timely pause after extended background time before presenting it as reliable background behavior.

Android acceptance uses the production-signed `dist/android/TikLocal-Radio-0.1.0-android.apk`. Its APK SHA-256 is `8d2a73f80e04dd0b434c9192495100d17ad9980ace119da94e0a7b283e4aced4`; the signing-certificate SHA-256 is `eb883956d85ee395938d63aeccf2294426490475db3df62942a15c962e4db483`. A device with a debug-signed app under the same package must uninstall it before the first switch, so that run does not count as profile-preserving upgrade acceptance. Test in-place upgrades between later production-signed versions.

## Build and first launch

- [ ] P0 — The iOS TestFlight/preview build installs and cold-starts without Metro.
- [ ] P0 — The production-signed Android Release APK installs and cold-starts without Metro.
- [ ] P0 — App name, icon, splash screen, and version `0.1.0 (1)` are correct.
- [ ] P0 — Without a server, Demo Signal opens and all three bundled tracks play and switch.
- [ ] P1 — A saved server profile remains usable after an in-place upgrade.
- [ ] P0 — Radio uses its custom Safe Area top; Station sits at top left; the more menu works; Connection opens as a Form Sheet; Cancel from Change Server returns without changing the current connection.
- [ ] P1 — Favorite, Play, and Next use clear system icons; Signal Dial rotates during playback and remains still with Reduce Motion enabled.
- [ ] P1 — Normal Radio does not repeat the server; Offline and Empty states retain a clear, actionable Connection recovery entry.

## Server and network

- [ ] P0 — Web Settings explicitly generates a single-use QR code; the app asks for camera permission only after the first Scan tap.
- [ ] P0 — A valid scan shows the correct server address and exchanges the authorization only after confirmation.
- [ ] P0 — Opening a `tiklocal-radio://` pairing link while the app is stopped opens pairing and shows the target without automatic exchange.
- [ ] P0 — Opening a pairing link in the foreground updates pairing; Cancel returns to the existing Radio; an invalid URL does not alter the current screen.
- [ ] P0 — Denied camera access, permanent denial, and an invalid QR code offer recovery through paste or manual pairing.
- [ ] P0 — Expired, redeemed, and pre-password-change QR codes cannot pair again and show understandable errors.
- [ ] P0 — The app never saves the QR code or its preview to Photos, logs, or a third party.
- [ ] P0 — Trusted-LAN `http://<IPv4>:<port>` pairs and plays.
- [ ] P0 — `http://<hostname>.local:<port>` pairs and plays.
- [ ] P0 — Built-in HTTPS pairs and plays after trusting the TikLocal CA.
- [ ] P0 — Untrusted certificates, wrong passwords, unreachable addresses, and timeouts show understandable errors.
- [ ] P0 — An empty music library shows `NO AUDIO`; Play, Next, Favorite, Encore, and Sleep are disabled; the system media panel is cleared.
- [ ] P1 — A temporary server outage preserves the screen and changing stations reconnects after recovery.

## iOS system media behavior

- [ ] P0 — Music plays with the mute switch enabled.
- [ ] P0 — Playback continues for at least 10 minutes after locking without stopping in background.
- [ ] P0 — Lock screen and Control Center show the correct title, artist, and album.
- [ ] P0 — Lock-screen play, pause, and progress match app state.
- [ ] P0 — Wired and Bluetooth headset play/pause works.
- [ ] P0 — Unplugging a headset or disconnecting Bluetooth pauses without unexpected speaker playback.
- [ ] P1 — Phone, Siri, and other audio interruptions behave normally without double playback.
- [ ] P1 — Killing the app clears system media information.

## Android system media behavior

- [ ] P0 — Playback continues for at least 10 minutes with the screen off or app in background.
- [ ] P0 — Lock screen and notification shade show a media session with correct track information.
- [ ] P0 — System play, pause, and progress match app state.
- [ ] P0 — Wired and Bluetooth headset play/pause works.
- [ ] P0 — Unplugging a headset or disconnecting Bluetooth pauses.
- [ ] P0 — Swiping the app from recents follows the final playback-lifecycle decision without leaving a stale notification.
- [ ] P1 — Playback continues for 30 minutes with battery optimization enabled.

## Radio state and credentials

- [ ] P0 — Play, completion, skip, Encore, and favorite feedback reaches the user's own server.
- [ ] P0 — Rapid Next or station changes never let an old request replace the new queue.
- [ ] P0 — After changing the TikLocal password, a 401 removes only the invalid token, keeps server name and address, and opens reauthorization.
- [ ] P0 — After offline, wrong-password, or timeout failures, Connection still contains the most recent valid address.
- [ ] P0 — **Forget This Server** uses system destructive confirmation, revokes the token, and deletes the local record; local forget still works while offline.
- [ ] P1 — Entering Demo does not implicitly revoke or forget a known server.
- [ ] P0 — Revoking the current device in Web Settings returns the app to pairing on its next request.
- [ ] P1 — Pairing a new server revokes the old device token.

## Timers and extended operation

- [ ] P0 — A 30-minute foreground sleep timer pauses on time and resets the UI.
- [ ] P0 — A 30-minute sleep timer still pauses on time while locked in background.
- [ ] P1 — Two hours of playback shows no notable track-switching, memory, heat, or battery issue.
- [ ] P1 — Wi-Fi disconnect and recovery cause no request storm or duplicate feedback.

## Evidence

| Platform | Device / OS | Build | Result | Failure or evidence |
| --- | --- | --- | --- | --- |
| iOS | JuPhone / iPhone 15 / iOS 26.6.1 | `0.1.0 (1)` Release | Local core passed | 2026-08-26 confirmed airplane-mode playback, originals surviving deletion, storage statistics, and Clear. SQLite v2 installed over the previous build and launched; preview backfill and bulk-import progress still need experience review. |
| Android | Pending | `0.1.0 (1)` | Not run | |

## Related files

- `apps/radio/src/player.ts`
- `apps/radio/src/radio.ts`
- `apps/radio/app.config.ts`
- `apps/radio/store/store-metadata.md`
- `docs/radio-native-client-architecture.md`
- `docs/radio-player-selection.md`
