import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import type { StoredConnection, SyncState } from "./model";
import { colors, radii } from "./theme";

type ConnectionScreenProps = {
  connection: StoredConnection | null;
  sync: SyncState;
  onChangeServer(): void;
  onDisconnect(): void;
  onReconnect(): void;
  onRetry(): void;
};

export function ConnectionScreen({
  connection,
  sync,
  onChangeServer,
  onDisconnect,
  onReconnect,
  onRetry,
}: ConnectionScreenProps) {
  const server =
    connection?.kind === "paired"
      ? connection.profile
      : connection?.kind === "known"
        ? connection.server
        : null;
  const status = connectionStatus(connection, sync);

  return (
    <ScrollView
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      <Text style={styles.intro}>
        TikLocal Radio connects directly to one private library on your
        network.
      </Text>

      <View style={styles.serverCard}>
        <View style={styles.statusRow}>
          <View style={[styles.statusDot, { backgroundColor: status.color }]} />
          <Text style={[styles.status, { color: status.color }]}>
            {status.label}
          </Text>
        </View>
        <Text style={styles.serverName}>
          {server?.serverName || (server ? "TikLocal Server" : "Demo Radio")}
        </Text>
        <Text numberOfLines={2} style={styles.serverAddress}>
          {server?.baseUrl || "Built-in audio · no Server connected"}
        </Text>
      </View>

      {sync.kind === "offline" && connection?.kind === "paired" ? (
        <View style={styles.notice}>
          <View style={styles.noticeCopy}>
            <Text style={styles.noticeTitle}>Server unavailable</Text>
            <Text style={styles.noticeText}>
              Your connection is still saved. Make sure TikLocal is running
              and this iPhone is on the same network.
            </Text>
          </View>
          <Pressable
            accessibilityLabel="Retry Server connection"
            accessibilityRole="button"
            onPress={onRetry}
            style={({ pressed }) => [
              styles.compactButton,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.compactButtonText}>Retry</Text>
          </Pressable>
        </View>
      ) : null}

      {connection?.kind === "known" ? (
        <Pressable
          accessibilityLabel={`Reconnect to ${
            server?.serverName || "TikLocal Server"
          }`}
          accessibilityRole="button"
          onPress={onReconnect}
          style={({ pressed }) => [
            styles.primaryButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>Reconnect</Text>
        </Pressable>
      ) : null}

      {!connection ? (
        <Pressable
          accessibilityLabel="Connect a TikLocal Server"
          accessibilityRole="button"
          onPress={onChangeServer}
          style={({ pressed }) => [
            styles.primaryButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>Connect a Server</Text>
        </Pressable>
      ) : null}

      <View style={styles.group}>
        <SettingsRow
          detail={
            connection
              ? "Keep the current connection until the new one succeeds"
              : "Scan a QR code or enter an address"
          }
          label={connection ? "Change Server" : "Choose Server"}
          onPress={onChangeServer}
        />
      </View>

      {connection ? (
        <View style={styles.dangerGroup}>
          <Pressable
            accessibilityLabel="Forget this Server"
            accessibilityRole="button"
            onPress={() => {
              Alert.alert(
                "Forget this Server?",
                "TikLocal Radio will remove this device connection. You can pair it again later.",
                [
                  { text: "Cancel", style: "cancel" },
                  {
                    text: "Forget Server",
                    style: "destructive",
                    onPress: onDisconnect,
                  },
                ],
              );
            }}
            style={({ pressed }) => [
              styles.dangerButton,
              pressed && styles.pressed,
            ]}
          >
            <Text style={styles.dangerText}>Forget This Server</Text>
          </Pressable>
        </View>
      ) : null}

      <Text style={styles.footer}>
        Passwords are never saved. A revocable device key is stored securely
        on this iPhone.
      </Text>
    </ScrollView>
  );
}

function SettingsRow({
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
        styles.settingsRow,
        pressed && styles.rowPressed,
      ]}
    >
      <View style={styles.rowCopy}>
        <Text style={styles.rowLabel}>{label}</Text>
        <Text style={styles.rowDetail}>{detail}</Text>
      </View>
      <Text style={styles.chevron}>›</Text>
    </Pressable>
  );
}

function connectionStatus(
  connection: StoredConnection | null,
  sync: SyncState,
): { color: string; label: string } {
  if (connection?.kind === "known") {
    return { color: colors.signal, label: "AUTHORIZATION REQUIRED" };
  }
  if (!connection || sync.kind === "demo") {
    return { color: colors.brass, label: "DEMO MODE" };
  }
  if (sync.kind === "loading") {
    return { color: colors.brass, label: "CONNECTING" };
  }
  if (sync.kind === "offline") {
    return { color: colors.signal, label: "OFFLINE · CONNECTION SAVED" };
  }
  if (sync.kind === "empty") {
    return { color: colors.brass, label: "CONNECTED · LIBRARY EMPTY" };
  }
  return { color: colors.moss, label: "CONNECTED" };
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 42,
    backgroundColor: colors.paper,
  },
  intro: {
    marginBottom: 20,
    color: colors.inkMuted,
    fontSize: 14,
    lineHeight: 20,
  },
  serverCard: {
    minHeight: 178,
    justifyContent: "flex-end",
    borderRadius: radii.card,
    padding: 22,
    backgroundColor: colors.paperRaised,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: "auto",
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  status: {
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.2,
  },
  serverName: {
    color: colors.ink,
    fontFamily: "Georgia",
    fontSize: 30,
    lineHeight: 36,
  },
  serverAddress: {
    marginTop: 5,
    color: colors.inkMuted,
    fontSize: 12,
    lineHeight: 17,
  },
  notice: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginTop: 14,
    borderRadius: radii.control,
    padding: 16,
    backgroundColor: "#F8E7DC",
  },
  noticeCopy: {
    flex: 1,
  },
  noticeTitle: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "800",
  },
  noticeText: {
    marginTop: 4,
    color: colors.inkMuted,
    fontSize: 11,
    lineHeight: 16,
  },
  compactButton: {
    minWidth: 68,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radii.pill,
    backgroundColor: colors.white,
  },
  compactButtonText: {
    color: colors.ink,
    fontSize: 12,
    fontWeight: "800",
  },
  primaryButton: {
    minHeight: 54,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 14,
    borderRadius: radii.pill,
    backgroundColor: colors.moss,
  },
  primaryButtonText: {
    color: colors.white,
    fontSize: 14,
    fontWeight: "800",
  },
  group: {
    overflow: "hidden",
    marginTop: 22,
    borderRadius: radii.control,
    backgroundColor: colors.paperRaised,
  },
  settingsRow: {
    minHeight: 70,
    flexDirection: "row",
    alignItems: "center",
    paddingLeft: 17,
    paddingRight: 14,
    borderBottomColor: colors.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  rowPressed: {
    backgroundColor: colors.white,
  },
  rowCopy: {
    flex: 1,
    paddingVertical: 13,
  },
  rowLabel: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "700",
  },
  rowDetail: {
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
  dangerGroup: {
    marginTop: 22,
  },
  dangerButton: {
    minHeight: 50,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radii.control,
    backgroundColor: colors.paperRaised,
  },
  dangerText: {
    color: colors.signal,
    fontSize: 14,
    fontWeight: "700",
  },
  footer: {
    marginTop: 22,
    paddingHorizontal: 12,
    color: colors.inkMuted,
    fontSize: 11,
    lineHeight: 17,
    textAlign: "center",
  },
  pressed: {
    opacity: 0.72,
    transform: [{ scale: 0.99 }],
  },
});
