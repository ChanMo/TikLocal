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
  initialServerName?: string;
  initialUrl?: string;
  onConnect(input: { baseUrl: string; password: string }): Promise<void>;
  onClaim(input: { pairingUri: string }): Promise<void>;
  onUseDemo?(): void;
};

type PairingStep = "choice" | "manual" | "link" | "confirm";

export function PairingScreen({
  initialPairingUri = "",
  initialServerName,
  initialUrl = "",
  onConnect,
  onClaim,
  onUseDemo,
}: PairingScreenProps) {
  const [step, setStep] = useState<PairingStep>(
    initialPairingUri ? "confirm" : "choice",
  );
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
      setStep("confirm");
      setError("");
    }
  }, [initialPairingUri]);

  const chooseStep = (nextStep: PairingStep) => {
    setError("");
    setStep(nextStep);
  };

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
          : "LumaFold could not connect to this Server.",
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
        contentInsetAdjustmentBehavior="automatic"
        contentContainerStyle={styles.screen}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.intro}>
          <Text style={styles.kicker}>LUMAFOLD / TIKLOCAL SERVER</Text>
          <Text style={styles.title}>
            {step === "confirm"
              ? "Confirm this Server."
              : initialServerName
                ? `Reconnect to ${initialServerName}.`
                : "Your music, on this iPhone."}
          </Text>
          <Text style={styles.description}>
            {step === "choice"
              ? "Pair once, then LumaFold will remember this Server and connect automatically."
              : step === "manual"
                ? "Enter the address shown by TikLocal and your access password. The password is used once and never saved."
                : step === "link"
                  ? "Paste the two-minute pairing link generated in TikLocal Settings."
                  : "Only continue if this is the TikLocal Server you intended to connect to."}
          </Text>
        </View>

        {step === "choice" ? (
          <>
            {initialUrl ? (
              <View style={styles.rememberedCard}>
                <View style={styles.rememberedDot} />
                <View style={styles.rememberedCopy}>
                  <Text style={styles.rememberedLabel}>REMEMBERED SERVER</Text>
                  <Text numberOfLines={1} style={styles.rememberedName}>
                    {initialServerName || "TikLocal Server"}
                  </Text>
                  <Text numberOfLines={1} style={styles.rememberedUrl}>
                    {initialUrl}
                  </Text>
                </View>
              </View>
            ) : null}

            <Pressable
              accessibilityLabel="Scan pairing QR code"
              accessibilityRole="button"
              disabled={isConnecting}
              onPress={() => setShowScanner(true)}
              style={({ pressed }) => [
                styles.primaryButton,
                pressed && styles.pressed,
                isConnecting && styles.disabled,
              ]}
            >
              <View>
                <Text style={styles.primaryTitle}>Scan Pairing QR</Text>
                <Text style={styles.primaryDetail}>
                  Fastest · no typing required
                </Text>
              </View>
              <Text style={styles.primaryIcon}>⌗</Text>
            </Pressable>

            <View style={styles.optionGroup}>
              <OptionRow
                detail={
                  initialUrl
                    ? "The remembered address is already filled in"
                    : "Use a Server address and access password"
                }
                label="Enter Manually"
                onPress={() => chooseStep("manual")}
              />
              <OptionRow
                detail="Use a link copied from TikLocal Settings"
                label="Paste Pairing Link"
                onPress={() => chooseStep("link")}
              />
            </View>

            {onUseDemo ? (
              <Pressable
                accessibilityLabel="Continue with Demo Radio"
                accessibilityRole="button"
                onPress={onUseDemo}
                style={({ pressed }) => [
                  styles.demoButton,
                  pressed && styles.pressed,
                ]}
              >
                <Text style={styles.demoText}>Continue with Demo Radio</Text>
              </Pressable>
            ) : null}
          </>
        ) : null}

        {step === "manual" ? (
          <View style={styles.formCard}>
            <BackButton onPress={() => chooseStep("choice")} />
            <Text style={styles.label}>SERVER ADDRESS</Text>
            <TextInput
              accessibilityLabel="Server address"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              onChangeText={setBaseUrl}
              placeholder="http://studio-mac.local:8888"
              placeholderTextColor="#8B908A"
              returnKeyType="next"
              style={styles.input}
              value={baseUrl}
            />

            <Text style={[styles.label, styles.passwordLabel]}>
              ACCESS PASSWORD
            </Text>
            <TextInput
              accessibilityLabel="Access password"
              autoCapitalize="none"
              autoCorrect={false}
              onChangeText={setPassword}
              onSubmitEditing={() => void connect()}
              placeholder="Password"
              placeholderTextColor="#8B908A"
              returnKeyType="go"
              secureTextEntry
              style={styles.input}
              value={password}
            />
            <ConnectionError error={error} />
            <SubmitButton
              accessibilityLabel="Connect to TikLocal Server"
              isConnecting={isConnecting}
              label="Connect"
              onPress={() => void connect()}
            />
          </View>
        ) : null}

        {step === "link" ? (
          <View style={styles.formCard}>
            <BackButton onPress={() => chooseStep("choice")} />
            <Text style={styles.label}>PAIRING LINK</Text>
            <TextInput
              accessibilityLabel="Pairing link"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              multiline
              onChangeText={setPairingUri}
              onSubmitEditing={() => void claim()}
              placeholder="tiklocal-radio://pair?…"
              placeholderTextColor="#8B908A"
              style={[styles.input, styles.linkInput]}
              value={pairingUri}
            />
            {pairingTarget ? (
              <Text style={styles.target}>SERVER · {pairingTarget}</Text>
            ) : null}
            <ConnectionError error={error} />
            <SubmitButton
              accessibilityLabel="Use pairing link"
              isConnecting={isConnecting}
              label="Continue"
              onPress={() => void claim()}
            />
          </View>
        ) : null}

        {step === "confirm" ? (
          <View style={styles.confirmCard}>
            <View style={styles.confirmMark}>
              <View style={styles.confirmDot} />
              <Text style={styles.confirmLabel}>SERVER FOUND</Text>
            </View>
            <Text style={styles.confirmTarget}>
              {pairingTarget || "Invalid pairing link"}
            </Text>
            <Text style={styles.confirmText}>
              The pairing link can be used only once and expires after two
              minutes.
            </Text>
            <ConnectionError error={error} />
            <SubmitButton
              accessibilityLabel="Confirm Server connection"
              isConnecting={isConnecting}
              label="Connect"
              onPress={() => void claim()}
            />
            <Pressable
              accessibilityLabel="Choose another pairing method"
              accessibilityRole="button"
              disabled={isConnecting}
              onPress={() => chooseStep("choice")}
              style={({ pressed }) => [
                styles.cancelButton,
                pressed && styles.pressed,
              ]}
            >
              <Text style={styles.cancelText}>Choose Another Method</Text>
            </Pressable>
          </View>
        ) : null}

        <Text style={styles.footer}>
          LOCAL FIRST · NO CLOUD ACCOUNT
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

function OptionRow({
  detail,
  label,
  onPress,
}: {
  detail: string;
  label: string;
  onPress(): void;
}) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.optionRow,
        pressed && styles.optionPressed,
      ]}
    >
      <View style={styles.optionCopy}>
        <Text style={styles.optionTitle}>{label}</Text>
        <Text style={styles.optionDetail}>{detail}</Text>
      </View>
      <Text style={styles.chevron}>›</Text>
    </Pressable>
  );
}

function BackButton({ onPress }: { onPress(): void }) {
  return (
    <Pressable
      accessibilityLabel="Back to connection options"
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [
        styles.backButton,
        pressed && styles.pressed,
      ]}
    >
      <Text style={styles.backText}>‹ Connection options</Text>
    </Pressable>
  );
}

function ConnectionError({ error }: { error: string }) {
  return error ? (
    <Text accessibilityRole="alert" style={styles.error}>
      {error}
    </Text>
  ) : (
    <Text style={styles.securityNote}>
      Your password is exchanged for a revocable device key.
    </Text>
  );
}

function SubmitButton({
  accessibilityLabel,
  isConnecting,
  label,
  onPress,
}: {
  accessibilityLabel: string;
  isConnecting: boolean;
  label: string;
  onPress(): void;
}) {
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      disabled={isConnecting}
      onPress={onPress}
      style={({ pressed }) => [
        styles.submitButton,
        pressed && styles.pressed,
        isConnecting && styles.disabled,
      ]}
    >
      {isConnecting ? (
        <ActivityIndicator color={colors.white} />
      ) : (
        <>
          <Text style={styles.submitText}>{label}</Text>
          <Text style={styles.submitArrow}>→</Text>
        </>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  frame: {
    flex: 1,
    backgroundColor: colors.ink,
  },
  screen: {
    flexGrow: 1,
    paddingHorizontal: 20,
    paddingTop: 18,
    paddingBottom: 26,
    backgroundColor: colors.ink,
  },
  intro: {
    paddingTop: 8,
    paddingBottom: 28,
  },
  kicker: {
    color: colors.signal,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.7,
  },
  title: {
    maxWidth: 350,
    marginTop: 13,
    color: colors.white,
    fontFamily: "Georgia",
    fontSize: 39,
    lineHeight: 44,
  },
  description: {
    maxWidth: 365,
    marginTop: 14,
    color: "#B8C0BA",
    fontSize: 14,
    lineHeight: 21,
  },
  rememberedCard: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 13,
    borderColor: "#48564F",
    borderWidth: 1,
    borderRadius: radii.control,
    padding: 15,
  },
  rememberedDot: {
    width: 9,
    height: 9,
    marginRight: 13,
    borderRadius: 5,
    backgroundColor: colors.signal,
  },
  rememberedCopy: {
    flex: 1,
  },
  rememberedLabel: {
    color: "#8E9A92",
    fontSize: 8,
    fontWeight: "900",
    letterSpacing: 1.2,
  },
  rememberedName: {
    marginTop: 4,
    color: colors.white,
    fontSize: 15,
    fontWeight: "700",
  },
  rememberedUrl: {
    marginTop: 2,
    color: "#9FA9A2",
    fontSize: 10,
  },
  primaryButton: {
    minHeight: 76,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderRadius: radii.control,
    paddingHorizontal: 20,
    backgroundColor: colors.signal,
  },
  primaryTitle: {
    color: colors.white,
    fontSize: 16,
    fontWeight: "800",
  },
  primaryDetail: {
    marginTop: 4,
    color: "rgba(255,255,255,0.74)",
    fontSize: 11,
  },
  primaryIcon: {
    color: colors.white,
    fontSize: 28,
  },
  optionGroup: {
    overflow: "hidden",
    marginTop: 13,
    borderRadius: radii.control,
    backgroundColor: colors.paperRaised,
  },
  optionRow: {
    minHeight: 72,
    flexDirection: "row",
    alignItems: "center",
    paddingLeft: 17,
    paddingRight: 14,
    borderBottomColor: colors.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  optionPressed: {
    backgroundColor: colors.white,
  },
  optionCopy: {
    flex: 1,
    paddingVertical: 12,
  },
  optionTitle: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "700",
  },
  optionDetail: {
    marginTop: 3,
    color: colors.inkMuted,
    fontSize: 11,
    lineHeight: 16,
  },
  chevron: {
    marginLeft: 12,
    color: colors.inkMuted,
    fontSize: 28,
    fontWeight: "300",
  },
  demoButton: {
    minHeight: 52,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 14,
  },
  demoText: {
    color: "#C3CBC5",
    fontSize: 13,
    fontWeight: "700",
  },
  formCard: {
    borderRadius: radii.card,
    padding: 20,
    backgroundColor: colors.paperRaised,
  },
  backButton: {
    alignSelf: "flex-start",
    minHeight: 44,
    justifyContent: "center",
    marginBottom: 10,
  },
  backText: {
    color: colors.moss,
    fontSize: 13,
    fontWeight: "700",
  },
  label: {
    marginBottom: 8,
    color: colors.ink,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.3,
  },
  passwordLabel: {
    marginTop: 18,
  },
  input: {
    minHeight: 52,
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 13,
    color: colors.ink,
    fontSize: 15,
    backgroundColor: colors.white,
  },
  linkInput: {
    minHeight: 112,
    paddingTop: 14,
    textAlignVertical: "top",
  },
  target: {
    marginTop: 9,
    color: colors.moss,
    fontSize: 9,
    fontWeight: "800",
    lineHeight: 14,
    letterSpacing: 0.8,
  },
  securityNote: {
    minHeight: 48,
    paddingTop: 12,
    color: colors.inkMuted,
    fontSize: 10,
    lineHeight: 16,
  },
  error: {
    minHeight: 48,
    paddingTop: 11,
    color: colors.signal,
    fontSize: 11,
    fontWeight: "700",
    lineHeight: 16,
  },
  submitButton: {
    minHeight: 56,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderRadius: radii.pill,
    paddingHorizontal: 20,
    backgroundColor: colors.moss,
  },
  submitText: {
    color: colors.white,
    fontSize: 14,
    fontWeight: "800",
  },
  submitArrow: {
    color: colors.white,
    fontSize: 22,
  },
  confirmCard: {
    borderRadius: radii.card,
    padding: 22,
    backgroundColor: colors.paperRaised,
  },
  confirmMark: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  confirmDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.moss,
  },
  confirmLabel: {
    color: colors.moss,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.2,
  },
  confirmTarget: {
    marginTop: 24,
    color: colors.ink,
    fontFamily: "Georgia",
    fontSize: 25,
    lineHeight: 31,
  },
  confirmText: {
    marginTop: 12,
    color: colors.inkMuted,
    fontSize: 12,
    lineHeight: 18,
  },
  cancelButton: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 6,
  },
  cancelText: {
    color: colors.inkMuted,
    fontSize: 12,
    fontWeight: "700",
  },
  footer: {
    marginTop: "auto",
    paddingTop: 24,
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
    opacity: 0.62,
  },
});
