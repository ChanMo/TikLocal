import { SymbolView } from "expo-symbols";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { StoredConnection } from "./model";
import { colors, radii } from "./theme";

type SettingsScreenProps = {
  connection: StoredConnection | null;
  mediaCount: number;
  onOpenTikLocalSource(): void;
};

export function SettingsScreen({
  connection,
  mediaCount,
  onOpenTikLocalSource,
}: SettingsScreenProps) {
  const insets = useSafeAreaInsets();
  const source = sourceSummary(connection);

  return (
    <ScrollView
      contentContainerStyle={[
        styles.content,
        { paddingTop: insets.top + 22 },
      ]}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.brandLockup}>
        <View style={styles.brandSignal} />
        <Text style={styles.brand}>LUMAFOLD</Text>
      </View>
      <Text style={styles.title}>Settings</Text>
      <Text style={styles.summary}>
        Your Flow lives on this iPhone. Other sources are optional.
      </Text>

      <Text style={styles.sectionLabel}>ON THIS IPHONE</Text>
      <View style={styles.card}>
        <InfoRow
          detail={`${mediaCount} ${mediaCount === 1 ? "memory" : "memories"}`}
          icon="rectangle.stack.fill"
          label="Private Library"
        />
        <View style={styles.divider} />
        <InfoRow
          detail="Offline copies · originals stay untouched"
          icon="internaldrive.fill"
          label="Local Storage"
        />
      </View>

      <Text style={styles.sectionLabel}>SOURCES</Text>
      <View style={styles.card}>
        <Pressable
          accessibilityLabel="Open optional TikLocal source"
          accessibilityRole="button"
          onPress={onOpenTikLocalSource}
          style={({ pressed }) => [
            styles.row,
            pressed && styles.rowPressed,
          ]}
        >
          <View style={styles.rowIcon}>
            <SymbolView
              name="externaldrive.connected.to.line.below.fill"
              size={19}
              tintColor={colors.moss}
              weight="semibold"
            />
          </View>
          <View style={styles.rowCopy}>
            <Text style={styles.rowLabel}>TikLocal Folder</Text>
            <Text numberOfLines={1} style={styles.rowDetail}>
              {source.detail}
            </Text>
          </View>
          <View style={[styles.sourceDot, { backgroundColor: source.color }]} />
          <SymbolView
            name="chevron.right"
            size={13}
            tintColor={colors.inkMuted}
            weight="bold"
          />
        </Pressable>
      </View>
      <Text style={styles.sourceFootnote}>
        TikLocal extends LumaFold with a private remote media source. It is
        never required for your local Flow.
      </Text>

      <Text style={styles.sectionLabel}>PRIVACY</Text>
      <View style={styles.privacyCard}>
        <SymbolView
          name="hand.raised.fill"
          size={23}
          tintColor={colors.signal}
          weight="semibold"
        />
        <View style={styles.privacyCopy}>
          <Text style={styles.privacyTitle}>Private by default</Text>
          <Text style={styles.privacyText}>
            No account and no tracking. Imported media stays inside LumaFold
            unless you explicitly add another source.
          </Text>
        </View>
      </View>

      <Text style={styles.version}>LumaFold · Working Preview</Text>
    </ScrollView>
  );
}

function InfoRow({
  detail,
  icon,
  label,
}: {
  detail: string;
  icon: "internaldrive.fill" | "rectangle.stack.fill";
  label: string;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.rowIcon}>
        <SymbolView
          name={icon}
          size={19}
          tintColor={colors.moss}
          weight="semibold"
        />
      </View>
      <View style={styles.rowCopy}>
        <Text style={styles.rowLabel}>{label}</Text>
        <Text style={styles.rowDetail}>{detail}</Text>
      </View>
    </View>
  );
}

function sourceSummary(connection: StoredConnection | null) {
  if (connection?.kind === "paired") {
    return {
      color: colors.moss,
      detail: connection.profile.serverName || "Connected",
    };
  }
  if (connection?.kind === "known") {
    return {
      color: colors.signal,
      detail: `${connection.server.serverName || "Saved source"} · reconnect`,
    };
  }
  return { color: colors.line, detail: "Optional · not connected" };
}

const styles = StyleSheet.create({
  content: {
    flexGrow: 1,
    paddingHorizontal: 20,
    paddingBottom: 42,
    backgroundColor: colors.paper,
  },
  brandLockup: {
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
  },
  brandSignal: {
    width: 5,
    height: 18,
    borderRadius: 3,
    backgroundColor: colors.signal,
  },
  brand: {
    color: colors.ink,
    fontSize: 11,
    fontWeight: "900",
    letterSpacing: 2.2,
  },
  title: {
    marginTop: 24,
    color: colors.ink,
    fontSize: 42,
    fontWeight: "800",
    letterSpacing: -1.6,
  },
  summary: {
    maxWidth: 340,
    marginTop: 8,
    marginBottom: 32,
    color: colors.inkMuted,
    fontSize: 14,
    lineHeight: 21,
  },
  sectionLabel: {
    marginTop: 22,
    marginBottom: 9,
    marginLeft: 4,
    color: colors.brass,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.5,
  },
  card: {
    overflow: "hidden",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radii.control,
    backgroundColor: colors.paperRaised,
  },
  row: {
    minHeight: 70,
    flexDirection: "row",
    alignItems: "center",
    gap: 13,
    paddingHorizontal: 16,
  },
  rowPressed: {
    backgroundColor: "#EEE7D7",
  },
  rowIcon: {
    width: 38,
    height: 38,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 19,
    backgroundColor: "#E7EBDD",
  },
  rowCopy: {
    flex: 1,
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
  },
  divider: {
    height: 1,
    marginLeft: 67,
    backgroundColor: colors.line,
  },
  sourceDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  sourceFootnote: {
    marginTop: 10,
    paddingHorizontal: 4,
    color: colors.inkMuted,
    fontSize: 11,
    lineHeight: 17,
  },
  privacyCard: {
    flexDirection: "row",
    gap: 14,
    padding: 18,
    borderRadius: radii.control,
    backgroundColor: colors.ink,
  },
  privacyCopy: {
    flex: 1,
  },
  privacyTitle: {
    color: colors.white,
    fontSize: 15,
    fontWeight: "800",
  },
  privacyText: {
    marginTop: 5,
    color: "#C8D1CA",
    fontSize: 12,
    lineHeight: 18,
  },
  version: {
    marginTop: 30,
    color: colors.inkMuted,
    fontSize: 10,
    textAlign: "center",
  },
});
