import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Platform,
  Pressable,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from "react-native";
import {
  NavigationContainer,
  useNavigationContainerRef,
} from "@react-navigation/native";
import {
  createNativeStackNavigator,
  type NativeStackScreenProps,
} from "@react-navigation/native-stack";
import { SafeAreaProvider } from "react-native-safe-area-context";

import {
  claimPairingGrant,
  normalizeServerUrl,
  pairServer,
  parsePairingUri,
  revokeServer,
} from "./src/api";
import { ConnectionScreen } from "./src/ConnectionScreen";
import type {
  KnownServer,
  ServerProfile,
  StoredConnection,
} from "./src/model";
import { PairingScreen } from "./src/PairingScreen";
import { RadioScreen } from "./src/RadioScreen";
import { useRadioSession } from "./src/radio";
import { clearRadioResume } from "./src/radioResume";
import {
  clearStoredConnection,
  loadStoredConnection,
  saveKnownServer,
  saveServerProfile,
} from "./src/storage";
import { colors } from "./src/theme";

type RootStackParamList = {
  Radio: undefined;
  Connection: undefined;
  Pairing: { pairingUri?: string } | undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  return (
    <SafeAreaProvider>
      <AppContent />
    </SafeAreaProvider>
  );
}

function AppContent() {
  const navigationRef = useNavigationContainerRef<RootStackParamList>();
  const [connection, setConnection] = useState<StoredConnection | null>(null);
  const [pendingPairingUri, setPendingPairingUri] = useState<string | null>(
    null,
  );
  const [isBooting, setIsBooting] = useState(true);
  const profile =
    connection?.kind === "paired" ? connection.profile : null;

  const requireAuthorization = useCallback(() => {
    if (!profile) {
      return;
    }
    const server: KnownServer = {
      baseUrl: profile.baseUrl,
      serverName: profile.serverName,
    };
    setConnection({ kind: "known", server });
    clearRadioResume();
    void saveKnownServer(server).catch(() => {
      // The in-memory reauthorization flow remains available.
    });
    if (navigationRef.isReady()) {
      navigationRef.reset({
        index: 0,
        routes: [{ name: "Pairing" }],
      });
    }
  }, [navigationRef, profile]);
  const radio = useRadioSession(profile, requireAuthorization);

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
      if (navigationRef.isReady()) {
        navigationRef.navigate("Pairing", { pairingUri });
      }
    });

    const restore = async () => {
      let stored: StoredConnection | null = null;
      try {
        stored = await loadStoredConnection();
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
      setConnection(stored);
      setPendingPairingUri(pairingUri);
      setIsBooting(false);
    };
    void restore();

    return () => {
      isActive = false;
      subscription.remove();
    };
  }, [navigationRef]);

  if (isBooting) {
    return (
      <View style={styles.boot}>
        <StatusBar barStyle="light-content" />
        <ActivityIndicator color={colors.signal} />
      </View>
    );
  }

  const initialRouteName =
    connection?.kind === "paired" ? "Radio" : "Pairing";

  const knownServer =
    connection?.kind === "paired"
      ? {
          baseUrl: connection.profile.baseUrl,
          serverName: connection.profile.serverName,
        }
      : connection?.kind === "known"
        ? connection.server
        : null;

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
    setConnection({ kind: "paired", profile: paired });
    navigationRef.reset({
      index: 0,
      routes: [{ name: "Radio" }],
    });
  };

  const rememberAttempt = async (server: KnownServer) => {
    if (profile) {
      return;
    }
    setConnection({ kind: "known", server });
    await saveKnownServer(server);
  };

  const disconnect = () => {
    if (profile) {
      void revokeServer(profile).catch(() => {
        // Forgetting the local connection must work while the Server is offline.
      });
    }
    setConnection(null);
    setPendingPairingUri(null);
    clearRadioResume();
    void clearStoredConnection().catch(() => {
      // The current session must still forget the connection immediately.
    });
    navigationRef.reset({
      index: 0,
      routes: [{ name: "Pairing" }],
    });
  };

  return (
    <NavigationContainer
      onReady={() => {
        if (pendingPairingUri) {
          navigationRef.navigate("Pairing", {
            pairingUri: pendingPairingUri,
          });
        }
      }}
      ref={navigationRef}
    >
      <StatusBar barStyle="dark-content" />
      <Stack.Navigator
        initialRouteName={initialRouteName}
        screenOptions={{
          contentStyle: { backgroundColor: colors.paper },
          headerShadowVisible: false,
          headerStyle: { backgroundColor: colors.paper },
          headerTintColor: colors.ink,
        }}
      >
        <Stack.Screen
          name="Radio"
          options={{ headerShown: false }}
        >
          {({ navigation }) => (
            <RadioScreen
              onConnectionPress={() => navigation.navigate("Connection")}
              radio={radio}
            />
          )}
        </Stack.Screen>

        <Stack.Screen
          name="Connection"
          options={{
            presentation: Platform.OS === "ios" ? "formSheet" : "card",
            title: "Connection",
          }}
        >
          {({ navigation }) => (
            <ConnectionScreen
              connection={connection}
              onChangeServer={() => navigation.navigate("Pairing")}
              onDisconnect={disconnect}
              onReconnect={() => navigation.navigate("Pairing")}
              onRetry={radio.retry}
              sync={radio.snapshot.sync}
            />
          )}
        </Stack.Screen>

        <Stack.Screen
          name="Pairing"
          options={({ navigation }) => ({
            contentStyle: { backgroundColor: colors.ink },
            gestureEnabled: false,
            headerLeft: navigation.canGoBack()
              ? () => (
                  <Pressable
                    accessibilityLabel="Cancel changing Server"
                    accessibilityRole="button"
                    hitSlop={10}
                    onPress={() => {
                      setPendingPairingUri(null);
                      navigation.goBack();
                    }}
                  >
                    <Text style={styles.cancelAction}>Cancel</Text>
                  </Pressable>
                )
              : undefined,
            headerStyle: { backgroundColor: colors.ink },
            headerTintColor: colors.white,
            statusBarStyle: "light",
            presentation:
              Platform.OS === "ios" ? "fullScreenModal" : "card",
            title: "Connect",
          })}
        >
          {({ navigation, route }: PairingScreenProps) => (
            <PairingScreen
              initialPairingUri={
                route.params?.pairingUri
                || pendingPairingUri
                || undefined
              }
              initialServerName={knownServer?.serverName}
              initialUrl={knownServer?.baseUrl}
              onClaim={async ({ pairingUri }) => {
                const parsed = parsePairingUri(pairingUri);
                await rememberAttempt({
                  baseUrl: parsed.baseUrl,
                  serverName:
                    knownServer?.baseUrl === parsed.baseUrl
                      ? knownServer.serverName
                      : undefined,
                });
                await activateProfile(
                  await claimPairingGrant({
                    pairingUri,
                    deviceName: deviceName(),
                  }),
                );
              }}
              onConnect={async ({ baseUrl, password }) => {
                const normalizedUrl = normalizeServerUrl(baseUrl);
                await rememberAttempt({
                  baseUrl: normalizedUrl,
                  serverName:
                    knownServer?.baseUrl === normalizedUrl
                      ? knownServer.serverName
                      : undefined,
                });
                await activateProfile(
                  await pairServer({
                    baseUrl: normalizedUrl,
                    password,
                    deviceName: deviceName(),
                  }),
                );
              }}
              onUseDemo={
                profile
                  ? undefined
                  : () => {
                      setPendingPairingUri(null);
                      navigation.reset({
                        index: 0,
                        routes: [{ name: "Radio" }],
                      });
                    }
              }
            />
          )}
        </Stack.Screen>
      </Stack.Navigator>
    </NavigationContainer>
  );
}

type PairingScreenProps = NativeStackScreenProps<
  RootStackParamList,
  "Pairing"
>;

function deviceName() {
  return `TikLocal Radio · ${Platform.OS}`;
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
  boot: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.ink,
  },
  cancelAction: {
    color: colors.white,
    fontSize: 16,
  },
});
