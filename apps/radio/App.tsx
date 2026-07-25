import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Platform,
  StyleSheet,
  StatusBar,
  View,
} from "react-native";
import {
  SafeAreaProvider,
  SafeAreaView,
} from "react-native-safe-area-context";

import {
  claimPairingGrant,
  pairServer,
  parsePairingUri,
  revokeServer,
} from "./src/api";
import type { ServerProfile } from "./src/model";
import { PairingScreen } from "./src/PairingScreen";
import { RadioScreen } from "./src/RadioScreen";
import { useRadioSession } from "./src/radio";
import {
  clearServerProfile,
  loadServerProfile,
  saveServerProfile,
} from "./src/storage";
import { colors } from "./src/theme";

export default function App() {
  return (
    <SafeAreaProvider>
      <AppContent />
    </SafeAreaProvider>
  );
}

function AppContent() {
  const [profile, setProfile] = useState<ServerProfile | null>(null);
  const [pendingPairingUri, setPendingPairingUri] = useState<string | null>(
    null,
  );
  const [isBooting, setIsBooting] = useState(true);
  const [showPairing, setShowPairing] = useState(false);

  const disconnect = useCallback(() => {
    setProfile(null);
    setShowPairing(true);
    void clearServerProfile();
  }, []);
  const radio = useRadioSession(profile, disconnect);

  useEffect(() => {
    let isActive = true;
    let receivedPairingUri: string | null = null;
    const subscription = Linking.addEventListener("url", ({ url }) => {
      const pairingUri = supportedPairingUri(url);
      if (!pairingUri) {
        return;
      }
      receivedPairingUri = pairingUri;
      setPendingPairingUri(pairingUri);
      setShowPairing(true);
    });

    const restore = async () => {
      let stored: ServerProfile | null = null;
      try {
        stored = await loadServerProfile();
      } catch {
        // Pairing remains available when secure storage cannot be read.
      }
      let initialPairingUri: string | null = null;
      try {
        initialPairingUri = supportedPairingUri(
          await Linking.getInitialURL(),
        );
      } catch {
        // A native linking failure must not prevent normal startup.
      }
      if (!isActive) {
        return;
      }
      const pairingUri = receivedPairingUri || initialPairingUri;
      setProfile(stored);
      setPendingPairingUri(pairingUri);
      setShowPairing(Boolean(pairingUri) || !stored);
      setIsBooting(false);
    };
    void restore();

    return () => {
      isActive = false;
      subscription.remove();
    };
  }, []);

  if (isBooting) {
    return (
      <View style={styles.boot}>
        <StatusBar barStyle="light-content" />
        <ActivityIndicator color={colors.signal} />
      </View>
    );
  }

  if (showPairing) {
    const activateProfile = async (paired: ServerProfile) => {
      try {
        await saveServerProfile(paired);
      } catch (error) {
        void revokeServer(paired).catch(() => {
          // The issued token can still be revoked from TikLocal Settings.
        });
        throw error;
      }
      if (profile) {
        void revokeServer(profile).catch(() => {
          // The old token remains revocable from TikLocal Settings.
        });
      }
      setPendingPairingUri(null);
      setProfile(paired);
      setShowPairing(false);
    };
    const deviceName = `TikLocal Radio · ${Platform.OS}`;
    return (
      <SafeAreaView style={styles.pairing}>
        <StatusBar barStyle="light-content" />
        <PairingScreen
          initialPairingUri={pendingPairingUri || undefined}
          initialUrl={profile?.baseUrl}
          onConnect={async ({ baseUrl, password }) => {
            await activateProfile(await pairServer({
              baseUrl,
              password,
              deviceName,
            }));
          }}
          onClaim={async ({ pairingUri }) => {
            await activateProfile(await claimPairingGrant({
              pairingUri,
              deviceName,
            }));
          }}
          onCancel={
            profile ? () => {
              setPendingPairingUri(null);
              setShowPairing(false);
            } : undefined
          }
          onUseDemo={() => {
            if (profile) {
              void revokeServer(profile).catch(() => {
                // Local disconnect must still succeed while the Server is offline.
              });
            }
            setPendingPairingUri(null);
            setProfile(null);
            setShowPairing(false);
            void clearServerProfile();
          }}
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar barStyle="dark-content" />
      <RadioScreen
        onConnectionPress={() => {
          setPendingPairingUri(null);
          setShowPairing(true);
        }}
        radio={radio}
      />
    </SafeAreaView>
  );
}

function supportedPairingUri(value: string | null): string | null {
  if (!value) {
    return null;
  }
  try {
    parsePairingUri(value);
    return value.trim();
  } catch {
    return null;
  }
}

const styles = StyleSheet.create({
  app: {
    flex: 1,
    backgroundColor: colors.paper,
  },
  pairing: {
    flex: 1,
    backgroundColor: colors.ink,
  },
  boot: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.ink,
  },
});
