import { useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import {
  CameraView,
  type BarcodeScanningResult,
  useCameraPermissions,
} from "expo-camera";

import { parsePairingUri } from "./api";
import { colors, radii } from "./theme";

type PairingScannerProps = {
  onCancel(): void;
  onConfirm(pairingUri: string): void;
};

export function PairingScanner({
  onCancel,
  onConfirm,
}: PairingScannerProps) {
  const [permission, requestPermission] = useCameraPermissions();
  const [pairingUri, setPairingUri] = useState("");
  const [serverUrl, setServerUrl] = useState("");
  const [scanError, setScanError] = useState("");
  const isPaused = Boolean(pairingUri || scanError);

  const scan = ({ data }: BarcodeScanningResult) => {
    if (isPaused) {
      return;
    }
    try {
      const parsed = parsePairingUri(data);
      setPairingUri(data);
      setServerUrl(parsed.baseUrl);
    } catch {
      setScanError("This QR code is not a TikLocal Server pairing link.");
    }
  };

  const scanAgain = () => {
    setPairingUri("");
    setServerUrl("");
    setScanError("");
  };

  return (
    <Modal
      animationType="fade"
      onRequestClose={onCancel}
      presentationStyle="fullScreen"
      visible
    >
      <View style={styles.screen}>
        {permission?.granted ? (
          <CameraView
            barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            facing="back"
            onBarcodeScanned={isPaused ? undefined : scan}
            style={StyleSheet.absoluteFill}
          />
        ) : (
          <View style={styles.permissionBackdrop}>
            {permission === null ? (
              <ActivityIndicator color={colors.signal} />
            ) : (
              <View style={styles.permissionCard}>
                <Text style={styles.permissionKicker}>CAMERA ACCESS</Text>
                <Text style={styles.permissionTitle}>Scan without typing.</Text>
                <Text style={styles.permissionCopy}>
                  The camera is used only while this screen is open to read a
                  TikLocal pairing QR code. No image is saved.
                </Text>
                {permission.canAskAgain !== false ? (
                  <Pressable
                    accessibilityLabel="Allow camera access"
                    accessibilityRole="button"
                    onPress={() => void requestPermission()}
                    style={styles.primaryButton}
                  >
                    <Text style={styles.primaryText}>ALLOW CAMERA</Text>
                  </Pressable>
                ) : (
                  <Text accessibilityRole="alert" style={styles.permissionAlert}>
                    Camera access is disabled. Enable it in system settings, or
                    paste the pairing link instead.
                  </Text>
                )}
              </View>
            )}
          </View>
        )}

        <View style={styles.topBar}>
          <View>
            <Text style={styles.kicker}>LUMAFOLD / QR PAIRING</Text>
            <Text style={styles.heading}>Pair a TikLocal Server</Text>
          </View>
          <Pressable
            accessibilityLabel="Close scanner"
            accessibilityRole="button"
            onPress={onCancel}
            style={styles.closeButton}
          >
            <Text style={styles.closeText}>×</Text>
          </Pressable>
        </View>

        {permission?.granted && !isPaused ? (
          <View pointerEvents="none" style={styles.guide}>
            <View style={styles.scanFrame} />
            <Text style={styles.guideText}>
              ALIGN THE PAIRING QR INSIDE THE FRAME
            </Text>
          </View>
        ) : null}

        {isPaused ? (
          <View style={styles.resultCard}>
            <Text style={styles.resultKicker}>
              {scanError ? "NOT A PAIRING CODE" : "SERVER FOUND"}
            </Text>
            <Text
              accessibilityRole={scanError ? "alert" : undefined}
              style={styles.resultTitle}
            >
              {scanError || serverUrl}
            </Text>
            {!scanError ? (
              <Text style={styles.resultCopy}>
                Only continue if this is the TikLocal Server you intended to
                connect to.
              </Text>
            ) : null}
            <View style={styles.resultActions}>
              <Pressable
                accessibilityLabel="Scan another code"
                accessibilityRole="button"
                onPress={scanAgain}
                style={styles.secondaryButton}
              >
                <Text style={styles.secondaryText}>SCAN AGAIN</Text>
              </Pressable>
              {pairingUri ? (
                <Pressable
                  accessibilityLabel={`Connect to ${serverUrl}`}
                  accessibilityRole="button"
                  onPress={() => onConfirm(pairingUri)}
                  style={styles.primaryButton}
                >
                  <Text style={styles.primaryText}>CONNECT</Text>
                </Pressable>
              ) : null}
            </View>
          </View>
        ) : null}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.ink,
  },
  permissionBackdrop: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
    backgroundColor: colors.ink,
  },
  permissionCard: {
    width: "100%",
    maxWidth: 390,
    borderRadius: radii.card,
    padding: 24,
    backgroundColor: colors.paperRaised,
  },
  permissionKicker: {
    color: colors.signal,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.5,
  },
  permissionTitle: {
    marginTop: 12,
    color: colors.ink,
    fontFamily: "Georgia",
    fontSize: 32,
    lineHeight: 37,
  },
  permissionCopy: {
    marginTop: 12,
    marginBottom: 22,
    color: colors.inkMuted,
    fontSize: 13,
    lineHeight: 20,
  },
  permissionAlert: {
    color: colors.signal,
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 18,
  },
  topBar: {
    position: "absolute",
    top: 0,
    right: 0,
    left: 0,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: 54,
    paddingHorizontal: 22,
    paddingBottom: 18,
    backgroundColor: "rgba(11, 33, 28, 0.82)",
  },
  kicker: {
    color: "#AAB3AC",
    fontSize: 8,
    fontWeight: "900",
    letterSpacing: 1.4,
  },
  heading: {
    marginTop: 5,
    color: colors.white,
    fontFamily: "Georgia",
    fontSize: 23,
  },
  closeButton: {
    width: 42,
    height: 42,
    alignItems: "center",
    justifyContent: "center",
    borderColor: "rgba(255, 255, 255, 0.3)",
    borderWidth: 1,
    borderRadius: 21,
    backgroundColor: "rgba(11, 33, 28, 0.4)",
  },
  closeText: {
    color: colors.white,
    fontSize: 28,
    lineHeight: 30,
  },
  guide: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    alignItems: "center",
    justifyContent: "center",
  },
  scanFrame: {
    width: 270,
    height: 270,
    borderColor: colors.signal,
    borderWidth: 2,
    borderRadius: 28,
    backgroundColor: "transparent",
  },
  guideText: {
    marginTop: 18,
    color: colors.white,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.3,
    textShadowColor: colors.ink,
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  resultCard: {
    position: "absolute",
    right: 18,
    bottom: 28,
    left: 18,
    borderRadius: radii.card,
    padding: 22,
    backgroundColor: colors.paperRaised,
  },
  resultKicker: {
    color: colors.signal,
    fontSize: 8,
    fontWeight: "900",
    letterSpacing: 1.4,
  },
  resultTitle: {
    marginTop: 10,
    color: colors.ink,
    fontFamily: "Georgia",
    fontSize: 24,
    lineHeight: 30,
  },
  resultCopy: {
    marginTop: 9,
    color: colors.inkMuted,
    fontSize: 12,
    lineHeight: 18,
  },
  resultActions: {
    flexDirection: "row",
    justifyContent: "flex-end",
    gap: 9,
    marginTop: 20,
  },
  primaryButton: {
    minHeight: 46,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radii.pill,
    paddingHorizontal: 18,
    backgroundColor: colors.moss,
  },
  primaryText: {
    color: colors.white,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.3,
  },
  secondaryButton: {
    minHeight: 46,
    alignItems: "center",
    justifyContent: "center",
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: radii.pill,
    paddingHorizontal: 16,
    backgroundColor: colors.white,
  },
  secondaryText: {
    color: colors.ink,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.2,
  },
});
