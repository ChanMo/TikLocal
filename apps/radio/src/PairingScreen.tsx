import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { parsePairingUri, TikLocalApiError } from "./api";
import { PairingScanner } from "./PairingScanner";
import { colors, radii } from "./theme";

type PairingScreenProps = {
  initialPairingUri?: string;
  initialUrl?: string;
  onConnect(input: { baseUrl: string; password: string }): Promise<void>;
  onClaim(input: { pairingUri: string }): Promise<void>;
  onCancel?(): void;
  onUseDemo(): void;
};

export function PairingScreen({
  initialPairingUri = "",
  initialUrl = "",
  onConnect,
  onClaim,
  onCancel,
  onUseDemo,
}: PairingScreenProps) {
  const [baseUrl, setBaseUrl] = useState(initialUrl);
  const [password, setPassword] = useState("");
  const [pairingUri, setPairingUri] = useState(initialPairingUri);
  const [showScanner, setShowScanner] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState("");
  const pairingTarget = useMemo(() => {
    try {
      return pairingUri ? parsePairingUri(pairingUri).baseUrl : "";
    } catch {
      return "";
    }
  }, [pairingUri]);

  useEffect(() => {
    if (initialPairingUri) {
      setPairingUri(initialPairingUri);
    }
  }, [initialPairingUri]);

  const runConnection = async (task: () => Promise<void>) => {
    if (isConnecting) {
      return;
    }
    setError("");
    setIsConnecting(true);
    try {
      await task();
    } catch (caught) {
      setError(
        caught instanceof TikLocalApiError
          ? caught.message
          : "The private frequency could not be opened.",
      );
    } finally {
      setIsConnecting(false);
    }
  };

  const connect = () =>
    runConnection(() => onConnect({ baseUrl, password }));

  const claim = (value = pairingUri) =>
    runConnection(() => onClaim({ pairingUri: value }));

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={styles.frame}
    >
      <ScrollView
        contentContainerStyle={styles.screen}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
      <View style={styles.topRule}>
        <Text style={styles.kicker}>TIKLOCAL / RADIO LINK</Text>
        {onCancel ? (
          <Pressable
            accessibilityLabel="Return to radio"
            accessibilityRole="button"
            onPress={onCancel}
          >
            <Text style={styles.step}>RETURN ↙</Text>
          </Pressable>
        ) : (
          <Text style={styles.step}>PATCH 01</Text>
        )}
      </View>

      <View style={styles.intro}>
        <Text style={styles.title}>Tune into your own library.</Text>
        <Text style={styles.description}>
          Paste a two-minute pairing link from TikLocal Settings, or connect
          with the Server address and access password. Passwords are exchanged
          once for a revocable device key.
        </Text>
      </View>

      <View style={styles.panel}>
        <View style={styles.panelMark}>
          <View style={styles.signalDot} />
          <Text style={styles.panelMarkText}>PRIVATE PATCH BAY</Text>
        </View>

        <Pressable
          accessibilityLabel="Scan pairing QR code"
          accessibilityRole="button"
          disabled={isConnecting}
          onPress={() => setShowScanner(true)}
          style={({ pressed }) => [
            styles.scanButton,
            pressed && styles.pressed,
            isConnecting && styles.disabled,
          ]}
        >
          <Text style={styles.scanButtonText}>SCAN PAIRING QR</Text>
          <Text style={styles.scanButtonIcon}>⌗</Text>
        </Pressable>

        <Text style={styles.label}>PAIRING LINK</Text>
        <TextInput
          accessibilityLabel="Pairing link"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          onChangeText={setPairingUri}
          onSubmitEditing={() => void claim()}
          placeholder="tiklocal-radio://pair?…"
          placeholderTextColor="#8B908A"
          returnKeyType="go"
          style={styles.input}
          value={pairingUri}
        />
        {pairingTarget ? (
          <Text style={styles.pairingTarget}>
            TARGET SERVER · {pairingTarget}
          </Text>
        ) : null}
        <Pressable
          accessibilityLabel="Use pairing link"
          accessibilityRole="button"
          disabled={isConnecting}
          onPress={() => void claim()}
          style={({ pressed }) => [
            styles.linkButton,
            pressed && styles.pressed,
            isConnecting && styles.disabled,
          ]}
        >
          <Text style={styles.linkButtonText}>USE PAIRING LINK</Text>
          <Text style={styles.linkButtonArrow}>↘</Text>
        </Pressable>

        <View style={styles.divider}>
          <View style={styles.dividerLine} />
          <Text style={styles.dividerText}>OR MANUAL</Text>
          <View style={styles.dividerLine} />
        </View>

        <Text style={styles.label}>SERVER ADDRESS</Text>
        <TextInput
          accessibilityLabel="Server address"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          onChangeText={setBaseUrl}
          placeholder="studio-mac.local:8443"
          placeholderTextColor="#8B908A"
          returnKeyType="next"
          style={styles.input}
          value={baseUrl}
        />

        <Text style={[styles.label, styles.passwordLabel]}>ACCESS PASSWORD</Text>
        <TextInput
          accessibilityLabel="Access password"
          autoCapitalize="none"
          autoCorrect={false}
          onChangeText={setPassword}
          onSubmitEditing={() => void connect()}
          placeholder="••••-••••-••••-••••"
          placeholderTextColor="#8B908A"
          returnKeyType="go"
          secureTextEntry
          style={styles.input}
          value={password}
        />

        {error ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {error}
          </Text>
        ) : (
          <Text style={styles.securityNote}>
            DEVICE TOKEN · STORED IN SECURESTORE
          </Text>
        )}

        <Pressable
          accessibilityLabel="Open private frequency"
          accessibilityRole="button"
          disabled={isConnecting}
          onPress={() => void connect()}
          style={({ pressed }) => [
            styles.connectButton,
            pressed && styles.pressed,
            isConnecting && styles.disabled,
          ]}
        >
          {isConnecting ? (
            <ActivityIndicator color={colors.white} />
          ) : (
            <>
              <Text style={styles.connectText}>OPEN FREQUENCY</Text>
              <Text style={styles.connectArrow}>→</Text>
            </>
          )}
        </Pressable>
      </View>

      <Pressable
        accessibilityLabel={
          initialUrl ? "Disconnect and use Demo" : "Listen without a server"
        }
        accessibilityRole="button"
        onPress={onUseDemo}
        style={({ pressed }) => [
          styles.demoButton,
          pressed && styles.pressed,
        ]}
      >
        <Text style={styles.demoIndex}>00</Text>
        <View style={styles.demoCopy}>
          <Text style={styles.demoTitle}>
            {initialUrl ? "Disconnect and use Demo" : "Listen without a server"}
          </Text>
          <Text style={styles.demoText}>
            {initialUrl ? "Revoke this device key when online" : "Use the built-in Demo Signal"}
          </Text>
        </View>
        <Text style={styles.demoArrow}>↗</Text>
      </Pressable>

      <Text style={styles.footer}>
        LOCAL FIRST · NO CLOUD ACCOUNT · API V1
      </Text>
      </ScrollView>
      {showScanner ? (
        <PairingScanner
          onCancel={() => setShowScanner(false)}
          onConfirm={(value) => {
            setPairingUri(value);
            setShowScanner(false);
            void claim(value);
          }}
        />
      ) : null}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  frame: {
    flex: 1,
    backgroundColor: colors.ink,
  },
  screen: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingTop: 22,
    paddingBottom: 24,
    backgroundColor: colors.ink,
  },
  topRule: {
    flexDirection: "row",
    justifyContent: "space-between",
    borderBottomColor: "#4B554F",
    borderBottomWidth: 1,
    paddingBottom: 12,
  },
  kicker: {
    color: "#AAB3AC",
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 1.5,
  },
  step: {
    color: colors.signal,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.4,
  },
  intro: {
    paddingTop: 30,
    paddingBottom: 26,
  },
  title: {
    maxWidth: 330,
    color: colors.white,
    fontFamily: "Georgia",
    fontSize: 40,
    lineHeight: 45,
  },
  description: {
    maxWidth: 360,
    marginTop: 14,
    color: "#B8C0BA",
    fontSize: 13,
    lineHeight: 20,
  },
  panel: {
    borderRadius: radii.card,
    padding: 20,
    backgroundColor: colors.paperRaised,
  },
  panelMark: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 22,
  },
  signalDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.signal,
  },
  panelMarkText: {
    color: colors.inkMuted,
    fontSize: 8,
    fontWeight: "900",
    letterSpacing: 1.5,
  },
  label: {
    marginBottom: 8,
    color: colors.ink,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.3,
  },
  scanButton: {
    height: 52,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 20,
    borderRadius: radii.pill,
    paddingHorizontal: 18,
    backgroundColor: colors.signal,
  },
  scanButtonText: {
    color: colors.white,
    fontSize: 10,
    fontWeight: "900",
    letterSpacing: 1.4,
  },
  scanButtonIcon: {
    color: colors.white,
    fontSize: 22,
  },
  passwordLabel: {
    marginTop: 18,
  },
  linkButton: {
    height: 44,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 10,
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: radii.pill,
    paddingHorizontal: 16,
    backgroundColor: colors.white,
  },
  pairingTarget: {
    marginTop: 8,
    color: colors.moss,
    fontSize: 9,
    fontWeight: "800",
    lineHeight: 14,
    letterSpacing: 0.8,
  },
  linkButtonText: {
    color: colors.ink,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.3,
  },
  linkButtonArrow: {
    color: colors.moss,
    fontSize: 17,
  },
  divider: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginVertical: 20,
  },
  dividerLine: {
    height: 1,
    flex: 1,
    backgroundColor: colors.line,
  },
  dividerText: {
    color: colors.inkMuted,
    fontSize: 8,
    fontWeight: "800",
    letterSpacing: 1.2,
  },
  input: {
    height: 52,
    borderColor: colors.line,
    borderBottomColor: colors.ink,
    borderWidth: 1,
    borderBottomWidth: 2,
    borderRadius: 10,
    paddingHorizontal: 13,
    color: colors.ink,
    fontSize: 15,
    backgroundColor: colors.white,
  },
  securityNote: {
    minHeight: 34,
    paddingTop: 11,
    color: colors.inkMuted,
    fontSize: 8,
    fontWeight: "800",
    letterSpacing: 1,
  },
  error: {
    minHeight: 34,
    paddingTop: 9,
    color: colors.signal,
    fontSize: 11,
    fontWeight: "700",
  },
  connectButton: {
    height: 56,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderRadius: radii.pill,
    paddingHorizontal: 20,
    backgroundColor: colors.moss,
  },
  connectText: {
    color: colors.white,
    fontSize: 10,
    fontWeight: "900",
    letterSpacing: 1.5,
  },
  connectArrow: {
    color: colors.white,
    fontSize: 22,
  },
  demoButton: {
    minHeight: 76,
    flexDirection: "row",
    alignItems: "center",
    marginTop: 14,
    borderColor: "#4B554F",
    borderWidth: 1,
    borderRadius: radii.control,
    paddingHorizontal: 16,
  },
  demoIndex: {
    color: colors.brass,
    fontFamily: "Georgia",
    fontSize: 28,
  },
  demoCopy: {
    flex: 1,
    paddingHorizontal: 14,
  },
  demoTitle: {
    color: colors.white,
    fontSize: 13,
    fontWeight: "700",
  },
  demoText: {
    marginTop: 3,
    color: "#949F98",
    fontSize: 10,
  },
  demoArrow: {
    color: colors.white,
    fontSize: 18,
  },
  footer: {
    marginTop: "auto",
    paddingTop: 18,
    color: "#77827A",
    fontSize: 8,
    fontWeight: "800",
    letterSpacing: 1.5,
    textAlign: "center",
  },
  pressed: {
    opacity: 0.72,
    transform: [{ scale: 0.99 }],
  },
  disabled: {
    opacity: 0.65,
  },
});
