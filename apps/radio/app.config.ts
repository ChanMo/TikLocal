import type { ConfigContext, ExpoConfig } from "expo/config";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "TikLocal Radio",
  slug: "tiklocal-radio",
  version: "0.1.0",
  icon: "./assets/icon.png",
  orientation: "portrait",
  scheme: "tiklocal-radio",
  plugins: [
    "expo-asset",
    [
      "expo-splash-screen",
      {
        image: "./assets/icon.png",
        imageWidth: 240,
        resizeMode: "contain",
        backgroundColor: "#0B211C",
      },
    ],
    [
      "expo-build-properties",
      {
        android: {
          usesCleartextTraffic: true,
        },
      },
    ],
    [
      "expo-secure-store",
      {
        configureAndroidBackup: true,
        faceIDPermission: false,
      },
    ],
    [
      "expo-audio",
      {
        enableBackgroundPlayback: true,
        microphonePermission: false,
        recordAudioAndroid: false,
      },
    ],
    [
      "expo-camera",
      {
        cameraPermission:
          "TikLocal Radio uses the camera only to scan a pairing QR code.",
        recordAudioAndroid: false,
        barcodeScannerEnabled: true,
      },
    ],
  ],
  ios: {
    bundleIdentifier: "com.chanmo.tiklocal.radio",
    buildNumber: "1",
    supportsTablet: false,
    config: {
      usesNonExemptEncryption: false,
    },
    infoPlist: {
      NSLocalNetworkUsageDescription:
        "TikLocal Radio connects to the TikLocal Server on your local network.",
      NSAppTransportSecurity: {
        NSAllowsLocalNetworking: true,
      },
    },
  },
  android: {
    package: "com.chanmo.tiklocal.radio",
    versionCode: 1,
    predictiveBackGestureEnabled: false,
    blockedPermissions: [
      "android.permission.SYSTEM_ALERT_WINDOW",
      "android.permission.READ_EXTERNAL_STORAGE",
      "android.permission.WRITE_EXTERNAL_STORAGE",
      "android.permission.USE_BIOMETRIC",
      "android.permission.USE_FINGERPRINT",
      "android.permission.RECORD_AUDIO",
    ],
    adaptiveIcon: {
      foregroundImage: "./assets/icon.png",
      backgroundColor: "#0B211C",
    },
  },
});
