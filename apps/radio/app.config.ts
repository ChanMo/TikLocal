import type { ConfigContext, ExpoConfig } from "expo/config";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "LumaFold",
  slug: "tiklocal-radio",
  version: "0.1.0",
  icon: "./assets/lumafold-icon.png",
  orientation: "portrait",
  scheme: "tiklocal-radio",
  plugins: [
    "expo-asset",
    "expo-document-picker",
    [
      "expo-image-picker",
      {
        microphonePermission: false,
        photosPermission:
          "LumaFold imports only the photos and videos you choose for your private offline Flow.",
      },
    ],
    "expo-sqlite",
    "expo-video",
    [
      "expo-splash-screen",
      {
        image: "./assets/lumafold-foreground.png",
        imageWidth: 220,
        resizeMode: "contain",
        backgroundColor: "#17231D",
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
          "LumaFold uses the camera only to scan a TikLocal Server pairing QR code.",
        microphonePermission: false,
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
        "LumaFold connects to the TikLocal Server on your local network.",
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
      foregroundImage: "./assets/lumafold-foreground.png",
      backgroundColor: "#17231D",
    },
  },
});
