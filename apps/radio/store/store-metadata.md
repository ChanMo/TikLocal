# LumaFold Store Metadata Draft

- Status: LumaFold working brand integrated; name and logo remain subject to final availability checks
- Updated: 2026-08-26

## Product identity

- Current app name: `LumaFold`
- Suggested release name: `LumaFold` (verify App Store and trademark availability before final use)
- Bundle ID / Application ID: `com.chanmo.tiklocal.radio`
- Version: `0.1.0`
- iOS Build Number / Android Version Code: `1`
- Suggested primary category: Photo & Video
- Suggested secondary category: Utilities
- Suggested age rating: 4+ / Everyone
- Copyright: Confirm with the publishing account owner

## App Store — en-US

### Subtitle

Your private offline media flow

### Promotional text

Import your own photos and videos into a private, offline flow that needs no account, network, or server.

### Keywords

offline photos,local video,private media,photo viewer,media flow,local first,privacy

### Description

LumaFold turns photos and videos you explicitly choose into a calm, private,
always-available personal flow.

Highlights:

- Import photos and videos through the system Photos or Files picker
- Keep managed offline copies in the app's private storage
- Browse a visual library with video previews and watch a continuous vertical Flow
- See multi-item import progress and receive a clear warning before storage runs out
- See storage usage, select items to delete, or clear managed copies
- Works without an account, network connection, or TikLocal Server
- Optionally connect to a TikLocal Server you operate for Radio; Demo Signal is bundled

Imported media stays on the device and is not uploaded to the TikLocal project.
Deleting an item removes only LumaFold's managed copy, not the original in
Photos or Files. The app contains no ads, third-party analytics, or cross-app
tracking.

## App Review Notes

Review of the primary local experience does not require an account, network, or
TikLocal Server:

1. Launch the app and open **My Flow**.
2. Choose **Photos** or **Files** and select test images or videos with the
   system picker. Permissions are requested only after that explicit action.
3. Imported items appear in the local grid. Choose **Play all** to enter the
   offline vertical Flow.
4. Touch and hold an item to select and delete it. **Clear** removes all copies
   managed by LumaFold; neither action deletes the original selected item.

The optional Radio section can be reviewed without a server by choosing
**Demo Signal**. Real-server pairing connects only to a user-operated TikLocal
instance. The optional camera scanner reads a one-time QR code created by that
server, is opened by explicit user action, and does not save images.

## App Privacy — preliminary answers

Based on the current production code:

- Tracking: No
- Data linked to the user: None collected by the developer
- Data not linked to the user: None collected by the developer
- Advertising: None
- Third-party analytics: None

User-selected media, the on-device SQLite index, and Radio data exchanged between the user's device and their own TikLocal Server are never transmitted to the TikLocal project. App Store Connect treats data as collected when the developer or a third party receives it. Recheck the final binary's SDKs, network endpoints, and paid components before submission.

## Google Play Data Safety — preliminary answers

- Does the app collect or share user data with the developer or third parties? No
- Ads: No
- Account creation: No
- User deletion request: No developer backend applies; users can delete local copies and disconnect or revoke devices
- Data in transit: HTTPS is available; users may also connect to their own HTTP server on a trusted local network

Do not claim that all traffic is always encrypted because optional Radio explicitly supports user-controlled LAN HTTP.

## URL

- Support URL: `https://github.com/ChanMo/TikLocal/issues`
- Marketing URL: `https://github.com/ChanMo/TikLocal`
- Privacy Policy URL (after the file reaches public `main`):
  `https://github.com/ChanMo/TikLocal/blob/main/apps/radio/store/privacy-policy.md`

## Screenshot plan

Prepare at least these real app states without private filenames or sensitive media:

1. Local-first Home and My Flow entry points.
2. Empty Library with Photos and Files import entry points.
3. Grid Library and storage statistics with imported media.
4. Vertical offline Flow with mixed photos and videos.
5. Long-press selection plus delete and clear-copy confirmations.
6. Optional Radio and Demo Signal, shown last as secondary capabilities.

Before submission, reconfirm the LumaFold name, icon, screenshot titles, and store categories. TikLocal should appear only as the open-source project and user-operated server brand, with Radio presented as optional.
