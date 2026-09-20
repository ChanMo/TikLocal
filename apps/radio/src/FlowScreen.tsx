import { SymbolView } from "expo-symbols";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import {
  importFromFiles,
  importFromPhotos,
  InsufficientStorageError,
  listLocalMedia,
  type ImportProgress,
  type ImportResult,
  type LocalMediaItem,
} from "./localLibrary";
import { LocalFlowScreen } from "./LocalFlowScreen";
import { colors, radii } from "./theme";

type FlowScreenProps = {
  requestedItemId?: string;
  refreshToken: number;
  onCountChange(count: number): void;
};

export function FlowScreen({
  requestedItemId,
  refreshToken,
  onCountChange,
}: FlowScreenProps) {
  const [items, setItems] = useState<LocalMediaItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [importing, setImporting] = useState<"photos" | "files" | null>(null);
  const [importProgress, setImportProgress] = useState<ImportProgress | null>(
    null,
  );
  const [session, setSession] = useState(0);
  const [sessionItemId, setSessionItemId] = useState(requestedItemId);

  useEffect(() => {
    StatusBar.setBarStyle(items.length > 0 ? "light-content" : "dark-content");
  }, [items.length]);

  useEffect(() => {
    setSessionItemId(requestedItemId);
  }, [requestedItemId]);

  const refresh = useCallback(async () => {
    const nextItems = await listLocalMedia();
    setItems(nextItems);
    onCountChange(nextItems.length);
    return nextItems;
  }, [onCountChange]);

  useEffect(() => {
    let active = true;
    void listLocalMedia()
      .then((nextItems) => {
        if (!active) {
          return;
        }
        setItems(nextItems);
        onCountChange(nextItems.length);
      })
      .catch(() => {
        if (active) {
          Alert.alert(
            "Flow unavailable",
            "LumaFold could not open the private library on this iPhone.",
          );
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [onCountChange, refreshToken]);

  const initialIndex = useMemo(() => {
    if (!sessionItemId) {
      return 0;
    }
    const index = items.findIndex((item) => item.id === sessionItemId);
    return index >= 0 ? index : 0;
  }, [items, sessionItemId]);

  const runImport = async (
    source: "photos" | "files",
    task: (
      onProgress: (progress: ImportProgress) => void,
    ) => Promise<ImportResult>,
  ) => {
    setImporting(source);
    setImportProgress(null);
    try {
      const result = await task(setImportProgress);
      const nextItems = await refresh();
      if (result.added > 0 && nextItems.length > 0) {
        setSession((value) => value + 1);
      }
    } catch (error) {
      if (error instanceof InsufficientStorageError) {
        Alert.alert(
          "Not enough room",
          "Free some space on this iPhone, then choose fewer photos or videos.",
        );
      } else {
        Alert.alert(
          "Import failed",
          "LumaFold could not finish this import. Anything already copied remains safe in your library.",
        );
      }
    } finally {
      setImporting(null);
      setImportProgress(null);
    }
  };

  if (isLoading) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator color={colors.signal} />
      </View>
    );
  }

  if (items.length === 0) {
    return (
      <EmptyFlow
        importing={importing}
        progress={importProgress}
        onImportFiles={() => void runImport("files", importFromFiles)}
        onImportPhotos={() => void runImport("photos", importFromPhotos)}
      />
    );
  }

  return (
    <LocalFlowScreen
      initialIndex={initialIndex}
      items={items}
      key={`${session}:${sessionItemId || "start"}:${items.length}`}
      onShuffle={() => {
        setItems((current) => shuffled(current));
        setSessionItemId(undefined);
        setSession((value) => value + 1);
      }}
    />
  );
}

function EmptyFlow({
  importing,
  onImportFiles,
  onImportPhotos,
  progress,
}: {
  importing: "photos" | "files" | null;
  onImportFiles(): void;
  onImportPhotos(): void;
  progress: ImportProgress | null;
}) {
  const insets = useSafeAreaInsets();
  const isImporting = importing !== null;

  return (
    <View
      style={[
        styles.empty,
        { paddingTop: insets.top + 24, paddingBottom: 28 },
      ]}
    >
      <View style={styles.brandLockup}>
        <View style={styles.brandSignal} />
        <Text style={styles.brand}>LUMAFOLD</Text>
      </View>

      <View style={styles.emptyHero}>
        <View style={styles.emptyMark}>
          <SymbolView
            name="rectangle.stack.badge.plus"
            size={42}
            tintColor={colors.brass}
            weight="medium"
          />
        </View>
        <Text style={styles.eyebrow}>YOUR PRIVATE FLOW</Text>
        <Text style={styles.title}>Bring a few moments back to life.</Text>
        <Text style={styles.summary}>
          Choose photos and videos you want to rediscover. LumaFold keeps
          private offline copies on this iPhone.
        </Text>
      </View>

      {isImporting ? (
        <View style={styles.progressCard}>
          <View style={styles.progressHeading}>
            <ActivityIndicator color={colors.white} size="small" />
            <Text style={styles.progressTitle}>BUILDING YOUR FLOW</Text>
            {progress ? (
              <Text style={styles.progressCount}>
                {progress.completed}/{progress.total}
              </Text>
            ) : null}
          </View>
          {progress ? (
            <Text numberOfLines={1} style={styles.progressFilename}>
              {progress.filename}
            </Text>
          ) : null}
        </View>
      ) : (
        <View style={styles.actions}>
          <Pressable
            accessibilityLabel="Choose photos and videos from Photos"
            accessibilityRole="button"
            onPress={onImportPhotos}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.pressed,
            ]}
          >
            <SymbolView
              name="photo.on.rectangle.angled"
              size={20}
              tintColor={colors.white}
              weight="semibold"
            />
            <Text style={styles.primaryText}>Choose from Photos</Text>
          </Pressable>
          <Pressable
            accessibilityLabel="Import photos and videos from Files"
            accessibilityRole="button"
            onPress={onImportFiles}
            style={({ pressed }) => [
              styles.secondaryButton,
              pressed && styles.pressed,
            ]}
          >
            <SymbolView
              name="folder.fill"
              size={18}
              tintColor={colors.moss}
              weight="semibold"
            />
            <Text style={styles.secondaryText}>Import from Files</Text>
          </Pressable>
        </View>
      )}

      <Text style={styles.privacy}>Local · Private · No account</Text>
    </View>
  );
}

function shuffled(items: LocalMediaItem[]) {
  if (items.length < 2) {
    return items;
  }
  const next = [...items];
  for (let index = next.length - 1; index > 0; index -= 1) {
    const target = Math.floor(Math.random() * (index + 1));
    const current = next[index]!;
    next[index] = next[target]!;
    next[target] = current;
  }
  if (next.every((item, index) => item.id === items[index]?.id)) {
    next.push(next.shift()!);
  }
  return next;
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.paper,
  },
  empty: {
    flex: 1,
    paddingHorizontal: 24,
    backgroundColor: colors.paper,
  },
  brandLockup: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  brandSignal: {
    width: 5,
    height: 20,
    borderRadius: 3,
    backgroundColor: colors.signal,
  },
  brand: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "900",
    letterSpacing: 2.8,
  },
  emptyHero: {
    flex: 1,
    justifyContent: "center",
    paddingBottom: 18,
  },
  emptyMark: {
    width: 82,
    height: 82,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 28,
    borderRadius: 41,
    backgroundColor: colors.paperRaised,
  },
  eyebrow: {
    color: colors.brass,
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1.8,
  },
  title: {
    maxWidth: 350,
    marginTop: 12,
    color: colors.ink,
    fontSize: 42,
    fontWeight: "800",
    letterSpacing: -1.7,
    lineHeight: 45,
  },
  summary: {
    maxWidth: 350,
    marginTop: 18,
    color: colors.inkMuted,
    fontSize: 15,
    lineHeight: 23,
  },
  actions: {
    gap: 10,
  },
  primaryButton: {
    minHeight: 58,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    borderRadius: radii.control,
    backgroundColor: colors.ink,
  },
  primaryText: {
    color: colors.white,
    fontSize: 16,
    fontWeight: "800",
  },
  secondaryButton: {
    minHeight: 54,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 9,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: radii.control,
    backgroundColor: colors.paperRaised,
  },
  secondaryText: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "700",
  },
  progressCard: {
    minHeight: 82,
    justifyContent: "center",
    paddingHorizontal: 18,
    borderRadius: radii.control,
    backgroundColor: colors.moss,
  },
  progressHeading: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  progressTitle: {
    flex: 1,
    color: colors.white,
    fontSize: 10,
    fontWeight: "900",
    letterSpacing: 1.4,
  },
  progressCount: {
    color: colors.white,
    fontSize: 11,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
  },
  progressFilename: {
    marginTop: 8,
    color: "#DCE8E0",
    fontSize: 12,
  },
  privacy: {
    marginTop: 17,
    color: colors.inkMuted,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.5,
    textAlign: "center",
  },
  pressed: {
    opacity: 0.72,
    transform: [{ scale: 0.985 }],
  },
});
