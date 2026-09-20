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
  type NavigatorScreenParams,
  useNavigationContainerRef,
} from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import {
  createNativeStackNavigator,
  type NativeStackScreenProps,
} from "@react-navigation/native-stack";
import { SymbolView } from "expo-symbols";
import { SafeAreaProvider } from "react-native-safe-area-context";

import {
  claimPairingGrant,
  normalizeServerUrl,
  pairServer,
  parsePairingUri,
  revokeServer,
} from "./src/api";
import { ConnectionScreen } from "./src/ConnectionScreen";
import {
  countLocalMedia,
  initializeLocalLibrary,
} from "./src/localLibrary";
import { FlowScreen } from "./src/FlowScreen";
import { LocalLibraryScreen } from "./src/LocalLibraryScreen";
import type {
  KnownServer,
  ServerProfile,
  StoredConnection,
} from "./src/model";
import { PairingScreen } from "./src/PairingScreen";
import { RadioScreen } from "./src/RadioScreen";
import { useRadioSession } from "./src/radio";
import { clearRadioResume } from "./src/radioResume";
import { SettingsScreen } from "./src/SettingsScreen";
import {
  clearStoredConnection,
  loadStoredConnection,
  saveKnownServer,
  saveServerProfile,
} from "./src/storage";
import { colors } from "./src/theme";

type RootStackParamList = {
  Main: NavigatorScreenParams<MainTabParamList> | undefined;
  Connection: undefined;
  Pairing: { pairingUri?: string } | undefined;
};

type MainTabParamList = {
  Flow: undefined;
  Library: undefined;
  Music: undefined;
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<MainTabParamList>();

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
  const [localMediaCount, setLocalMediaCount] = useState(0);
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
      let mediaCount = 0;
      await Promise.all([
        loadStoredConnection()
          .then((value) => {
            stored = value;
          })
          .catch(() => {
            // Local and Demo modes remain available without secure storage.
          }),
        initializeLocalLibrary()
          .then(() => countLocalMedia())
          .then((value) => {
            mediaCount = value;
          })
          .catch(() => {
            // The Library screen provides a visible error if opened.
          }),
      ]);
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
      setLocalMediaCount(mediaCount);
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
      routes: [{ name: "Main", params: { screen: "Music" } }],
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
      routes: [{ name: "Main", params: { screen: "Music" } }],
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
        initialRouteName="Main"
        screenOptions={{
          contentStyle: { backgroundColor: colors.paper },
          headerShadowVisible: false,
          headerStyle: { backgroundColor: colors.paper },
          headerTintColor: colors.ink,
        }}
      >
        <Stack.Screen name="Main" options={{ headerShown: false }}>
          {({ navigation }) => (
            <MainTabs
              connection={connection}
              mediaCount={localMediaCount}
              onCountChange={setLocalMediaCount}
              onOpenTikLocalSource={() => navigation.navigate("Connection")}
              radio={radio}
            />
          )}
        </Stack.Screen>

        <Stack.Screen
          name="Connection"
          options={{
            presentation: Platform.OS === "ios" ? "formSheet" : "card",
            title: "TikLocal Source",
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
                        routes: [
                          { name: "Main", params: { screen: "Music" } },
                        ],
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

function MainTabs({
  connection,
  mediaCount,
  onCountChange,
  onOpenTikLocalSource,
  radio,
}: {
  connection: StoredConnection | null;
  mediaCount: number;
  onCountChange(count: number): void;
  onOpenTikLocalSource(): void;
  radio: ReturnType<typeof useRadioSession>;
}) {
  const [flowRefreshToken, setFlowRefreshToken] = useState(0);
  const [requestedItemId, setRequestedItemId] = useState<string>();

  return (
    <Tab.Navigator
      initialRouteName="Flow"
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.signal,
        tabBarInactiveTintColor: colors.inkMuted,
        tabBarHideOnKeyboard: true,
        tabBarIcon: ({ color, focused }) => (
          <TabIcon color={color} focused={focused} route={route.name} />
        ),
        tabBarLabelStyle: {
          fontSize: 10,
          fontWeight: "700",
        },
        tabBarStyle: {
          backgroundColor: colors.paperRaised,
          borderTopColor: colors.line,
        },
      })}
    >
      <Tab.Screen
        listeners={{
          focus: () =>
            StatusBar.setBarStyle(
              mediaCount > 0 ? "light-content" : "dark-content",
            ),
          tabPress: () => setFlowRefreshToken((value) => value + 1),
        }}
        name="Flow"
      >
        {() => (
          <FlowScreen
            onCountChange={onCountChange}
            refreshToken={flowRefreshToken}
            requestedItemId={requestedItemId}
          />
        )}
      </Tab.Screen>
      <Tab.Screen
        listeners={{ focus: () => StatusBar.setBarStyle("dark-content") }}
        name="Library"
      >
        {({ navigation }) => (
          <LocalLibraryScreen
            onCountChange={onCountChange}
            onOpenFlow={(items, initialIndex = 0) => {
              setRequestedItemId(items[initialIndex]?.id);
              setFlowRefreshToken((value) => value + 1);
              navigation.navigate("Flow");
            }}
          />
        )}
      </Tab.Screen>
      <Tab.Screen
        listeners={{ focus: () => StatusBar.setBarStyle("dark-content") }}
        name="Music"
      >
        {() => (
          <RadioScreen
            onConnectionPress={onOpenTikLocalSource}
            radio={radio}
          />
        )}
      </Tab.Screen>
      <Tab.Screen
        listeners={{ focus: () => StatusBar.setBarStyle("dark-content") }}
        name="Settings"
      >
        {() => (
          <SettingsScreen
            connection={connection}
            mediaCount={mediaCount}
            onOpenTikLocalSource={onOpenTikLocalSource}
          />
        )}
      </Tab.Screen>
    </Tab.Navigator>
  );
}

function TabIcon({
  color,
  focused,
  route,
}: {
  color: string;
  focused: boolean;
  route: keyof MainTabParamList;
}) {
  if (route === "Flow") {
    return (
      <SymbolView
        name={focused ? "rectangle.stack.fill" : "rectangle.stack"}
        size={22}
        tintColor={color}
        weight="semibold"
      />
    );
  }
  if (route === "Library") {
    return (
      <SymbolView
        name={focused ? "photo.on.rectangle.angled" : "photo.on.rectangle"}
        size={21}
        tintColor={color}
        weight="semibold"
      />
    );
  }
  if (route === "Music") {
    return (
      <SymbolView
        name="music.note"
        size={21}
        tintColor={color}
        weight={focused ? "bold" : "medium"}
      />
    );
  }
  return (
    <SymbolView
      name={focused ? "gearshape.fill" : "gearshape"}
      size={21}
      tintColor={color}
      weight="semibold"
    />
  );
}

type PairingScreenProps = NativeStackScreenProps<
  RootStackParamList,
  "Pairing"
>;

function deviceName() {
  return `LumaFold · ${Platform.OS}`;
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
