import { SymbolView } from "expo-symbols";
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import {
  backfillVideoThumbnails,
  clearLocalMedia,
  deleteLocalMedia,
  getLocalStorageCapacity,
  importFromFiles,
  importFromPhotos,
  InsufficientStorageError,
  listLocalMedia,
  summarizeLocalMedia,
  type DeleteResult,
  type ImportProgress,
  type ImportResult,
  type LocalMediaItem,
} from "./localLibrary";
import { colors, radii } from "./theme";

type LocalLibraryScreenProps = {
  onCountChange(count: number): void;
  onOpenFlow(items: LocalMediaItem[], initialIndex?: number): void;
};

export function LocalLibraryScreen({
  onCountChange,
  onOpenFlow,
}: LocalLibraryScreenProps) {
  const [items, setItems] = useState<LocalMediaItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [importing, setImporting] = useState<"photos" | "files" | null>(null);
  const [importProgress, setImportProgress] = useState<ImportProgress | null>(
    null,
  );
  const [isDeleting, setIsDeleting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [capacity, setCapacity] = useState(getLocalStorageCapacity);
  const stats = summarizeLocalMedia(items);
  const isLowStorage =
    capacity.available > 0 && capacity.available < 1_000_000_000;

  const refresh = useCallback(async () => {
    const nextItems = await listLocalMedia();
    setItems(nextItems);
    setCapacity(getLocalStorageCapacity());
    onCountChange(nextItems.length);
  }, [onCountChange]);

  useEffect(() => {
    let active = true;
    void listLocalMedia()
      .then((nextItems) => {
        if (!active) {
          return;
        }
        setItems(nextItems);
        setCapacity(getLocalStorageCapacity());
        onCountChange(nextItems.length);
        void backfillVideoThumbnails(nextItems, (updatedItem) => {
          if (!active) {
            return;
          }
          setItems((current) =>
            current.map((item) =>
              item.id === updatedItem.id ? updatedItem : item,
            ),
          );
        });
      })
      .catch(() => {
        if (active) {
          Alert.alert("Library unavailable", "LumaFold could not open its private library.");
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
  }, [onCountChange]);

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
      await refresh();
      if (result.added > 0 || result.skipped > 0) {
        Alert.alert(
          result.added > 0 ? "Ready for your Flow" : "Already imported",
          importSummary(result),
        );
      }
    } catch (error) {
      if (error instanceof InsufficientStorageError) {
        Alert.alert(
          "Not enough room",
          `This selection needs ${formatBytes(error.required)}. This iPhone has ${formatBytes(error.available)} free, and LumaFold keeps a small safety reserve.`,
        );
      } else {
        Alert.alert(
          "Import failed",
          "LumaFold could not copy one of the selected files. Items imported before the problem remain available.",
        );
      }
    } finally {
      setImporting(null);
      setImportProgress(null);
    }
  };

  const runDelete = async (task: () => Promise<DeleteResult>) => {
    setIsDeleting(true);
    try {
      const result = await task();
      setSelectedIds(new Set());
      await refresh();
      if (result.failed.length > 0) {
        Alert.alert(
          "Some items remain",
          `${result.deleted} deleted · ${result.failed.length} could not be removed.`,
        );
      }
    } catch {
      Alert.alert(
        "Delete failed",
        "LumaFold could not remove the selected local copies. Your originals are unchanged.",
      );
    } finally {
      setIsDeleting(false);
    }
  };

  const confirmDelete = (ids: string[]) => {
    const count = ids.length;
    Alert.alert(
      `Delete ${count} local ${count === 1 ? "copy" : "copies"}?`,
      "This removes only LumaFold's offline copies. Your originals in Photos or Files stay where they are.",
      [
        { style: "cancel", text: "Cancel" },
        {
          style: "destructive",
          text: "Delete",
          onPress: () => void runDelete(() => deleteLocalMedia(ids)),
        },
      ],
    );
  };

  const confirmClear = () => {
    Alert.alert(
      "Clear this local library?",
      `LumaFold will remove ${stats.count} offline ${stats.count === 1 ? "copy" : "copies"} using ${formatBytes(stats.totalSize)}. Your originals stay where they are.`,
      [
        { style: "cancel", text: "Cancel" },
        {
          style: "destructive",
          text: "Clear Library",
          onPress: () => void runDelete(clearLocalMedia),
        },
      ],
    );
  };

  const toggleSelection = (id: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <View style={styles.screen}>
      <FlatList
        ListEmptyComponent={
          isLoading ? (
            <View style={styles.loading}>
              <ActivityIndicator color={colors.signal} />
            </View>
          ) : (
            <EmptyLibrary />
          )
        }
        ListHeaderComponent={
          <View style={styles.header}>
            <Text style={styles.eyebrow}>PRIVATE · OFFLINE</Text>
            <Text style={styles.title}>Library</Text>
            <Text style={styles.summary}>
              LumaFold keeps imported copies inside this iPhone. Originals stay
              where they are.
            </Text>

            <View style={styles.importRow}>
              <ImportButton
                disabled={importing !== null}
                icon="photo.on.rectangle.angled"
                label="Photos"
                loading={importing === "photos"}
                onPress={() => void runImport("photos", importFromPhotos)}
              />
              <ImportButton
                disabled={importing !== null}
                icon="folder.fill"
                label="Files"
                loading={importing === "files"}
                onPress={() => void runImport("files", importFromFiles)}
              />
            </View>

            {importing && importProgress ? (
              <View style={styles.importProgressCard}>
                <View style={styles.importProgressHeading}>
                  <Text style={styles.importProgressLabel}>
                    BUILDING YOUR FLOW
                  </Text>
                  <Text style={styles.importProgressCount}>
                    {importProgress.completed}/{importProgress.total}
                  </Text>
                </View>
                <Text numberOfLines={1} style={styles.importProgressFilename}>
                  {importProgress.filename}
                </Text>
                <View
                  accessible
                  accessibilityLabel="Import progress"
                  accessibilityRole="progressbar"
                  accessibilityValue={{
                    max: importProgress.total,
                    min: 0,
                    now: importProgress.completed,
                  }}
                  style={styles.importProgressTrack}
                >
                  <View
                    style={[
                      styles.importProgressFill,
                      {
                        width: `${Math.round(
                          (importProgress.completed /
                            Math.max(1, importProgress.total)) *
                            100,
                        )}%`,
                      },
                    ]}
                  />
                </View>
              </View>
            ) : null}

            {items.length > 0 ? (
              <>
                <View style={styles.storageCard}>
                  <View style={styles.storageCopy}>
                    <Text style={styles.storageEyebrow}>ON THIS IPHONE</Text>
                    <Text style={styles.storageValue}>
                      {formatBytes(stats.totalSize)}
                    </Text>
                    <Text style={styles.storageMeta}>
                      {stats.images} {stats.images === 1 ? "photo" : "photos"} · {stats.videos} {stats.videos === 1 ? "video" : "videos"}
                    </Text>
                    {capacity.available > 0 ? (
                      <Text
                        style={[
                          styles.storageFree,
                          isLowStorage && styles.storageFreeWarning,
                        ]}
                      >
                        {formatBytes(capacity.available)} free on this iPhone
                      </Text>
                    ) : null}
                  </View>
                  <Pressable
                    accessibilityLabel="Clear local library"
                    accessibilityRole="button"
                    disabled={isDeleting || importing !== null}
                    onPress={confirmClear}
                    style={({ pressed }) => [
                      styles.clearButton,
                      pressed && styles.pressed,
                    ]}
                  >
                    <Text style={styles.clearText}>Clear</Text>
                  </Pressable>
                </View>

                {selectedIds.size > 0 ? (
                  <View style={styles.selectionBar}>
                    <Pressable
                      accessibilityLabel="Exit selection"
                      accessibilityRole="button"
                      onPress={() => setSelectedIds(new Set())}
                      style={styles.selectionDismiss}
                    >
                      <SymbolView
                        name="xmark"
                        size={14}
                        tintColor={colors.white}
                        weight="bold"
                      />
                    </Pressable>
                    <Text style={styles.selectionCount}>
                      {selectedIds.size} selected
                    </Text>
                    <Pressable
                      accessibilityLabel="Select all local media"
                      accessibilityRole="button"
                      onPress={() =>
                        setSelectedIds(new Set(items.map((item) => item.id)))
                      }
                    >
                      <Text style={styles.selectAllText}>All</Text>
                    </Pressable>
                    <Pressable
                      accessibilityLabel={`Delete ${selectedIds.size} selected local ${selectedIds.size === 1 ? "copy" : "copies"}`}
                      accessibilityRole="button"
                      disabled={isDeleting}
                      onPress={() => confirmDelete([...selectedIds])}
                      style={styles.deleteSelection}
                    >
                      {isDeleting ? (
                        <ActivityIndicator color={colors.white} size="small" />
                      ) : (
                        <SymbolView
                          name="trash.fill"
                          size={15}
                          tintColor={colors.white}
                          weight="semibold"
                        />
                      )}
                      <Text style={styles.deleteSelectionText}>Delete</Text>
                    </Pressable>
                  </View>
                ) : (
                  <>
                    <Pressable
                      accessibilityLabel={`Play local Flow with ${items.length} ${items.length === 1 ? "item" : "items"}`}
                      accessibilityRole="button"
                      onPress={() => onOpenFlow(items)}
                      style={({ pressed }) => [
                        styles.playButton,
                        pressed && styles.pressed,
                      ]}
                    >
                      <SymbolView
                        name="play.fill"
                        size={16}
                        tintColor={colors.white}
                        weight="bold"
                      />
                      <Text style={styles.playText}>Play all</Text>
                      <Text style={styles.playCount}>{items.length}</Text>
                    </Pressable>
                    <Text style={styles.selectionHint}>
                      Touch and hold an item to manage local copies.
                    </Text>
                  </>
                )}
              </>
            ) : null}
          </View>
        }
        columnWrapperStyle={items.length > 0 ? styles.gridRow : undefined}
        contentContainerStyle={styles.content}
        data={items}
        keyExtractor={(item) => item.id}
        numColumns={3}
        renderItem={({ item, index }) => (
          <Pressable
            accessibilityLabel={
              selectedIds.size > 0
                ? `${selectedIds.has(item.id) ? "Deselect" : "Select"} ${item.kind}, ${item.filename}`
                : `Open ${item.kind}, ${item.filename}`
            }
            accessibilityRole="button"
            accessibilityState={{ selected: selectedIds.has(item.id) }}
            onLongPress={() => toggleSelection(item.id)}
            onPress={() =>
              selectedIds.size > 0
                ? toggleSelection(item.id)
                : onOpenFlow(items, index)
            }
            style={({ pressed }) => [
              styles.tile,
              selectedIds.has(item.id) && styles.selectedTile,
              pressed && styles.pressed,
            ]}
          >
            {item.kind === "image" || item.thumbnailUri ? (
              <Image
                source={{ uri: item.thumbnailUri || item.uri }}
                style={styles.tileMedia}
              />
            ) : (
              <View style={styles.videoTile}>
                <SymbolView
                  name="play.rectangle.fill"
                  size={25}
                  tintColor={colors.white}
                  weight="medium"
                />
              </View>
            )}
            <View style={styles.kindBadge}>
              <SymbolView
                name={item.kind === "image" ? "photo.fill" : "video.fill"}
                size={10}
                tintColor={colors.white}
                weight="bold"
              />
            </View>
            {selectedIds.has(item.id) ? (
              <View style={styles.selectionMark}>
                <SymbolView
                  name="checkmark"
                  size={13}
                  tintColor={colors.white}
                  weight="bold"
                />
              </View>
            ) : null}
          </Pressable>
        )}
      />
    </View>
  );
}

function ImportButton({
  disabled,
  icon,
  label,
  loading,
  onPress,
}: {
  disabled: boolean;
  icon: "photo.on.rectangle.angled" | "folder.fill";
  label: string;
  loading: boolean;
  onPress(): void;
}) {
  return (
    <Pressable
      accessibilityLabel={`Import from ${label}`}
      accessibilityRole="button"
      accessibilityState={{ disabled, busy: loading }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.importButton,
        pressed && styles.pressed,
        disabled && styles.disabled,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={colors.moss} size="small" />
      ) : (
        <SymbolView
          name={icon}
          size={19}
          tintColor={colors.moss}
          weight="semibold"
        />
      )}
      <Text style={styles.importLabel}>{label}</Text>
    </Pressable>
  );
}

function EmptyLibrary() {
  return (
    <View style={styles.empty}>
      <View style={styles.emptyMark}>
        <SymbolView
          name="rectangle.stack.badge.plus"
          size={38}
          tintColor={colors.brass}
          weight="medium"
        />
      </View>
      <Text style={styles.emptyTitle}>A quiet library.</Text>
      <Text style={styles.emptyBody}>
        Choose a few photos or videos. LumaFold copies them locally so the Flow
        still works in airplane mode.
      </Text>
    </View>
  );
}

function importSummary(result: ImportResult) {
  const parts: string[] = [];
  if (result.added > 0) {
    parts.push(`${result.added} ${result.added === 1 ? "item" : "items"} imported`);
  }
  if (result.skipped > 0) {
    parts.push(`${result.skipped} already in your library`);
  }
  return `${parts.join(" · ")}.`;
}

function formatBytes(bytes: number) {
  if (bytes < 1_000) {
    return `${bytes} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1_000;
  let unit = units[0];
  for (let index = 1; value >= 1_000 && index < units.length; index += 1) {
    value /= 1_000;
    unit = units[index];
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${unit}`;
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.paper,
  },
  content: {
    flexGrow: 1,
    paddingHorizontal: 18,
    paddingBottom: 32,
  },
  header: {
    paddingHorizontal: 6,
    paddingTop: 14,
    paddingBottom: 22,
  },
  eyebrow: {
    color: colors.brass,
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1.7,
  },
  title: {
    marginTop: 7,
    color: colors.ink,
    fontSize: 40,
    fontWeight: "800",
    letterSpacing: -1.5,
  },
  summary: {
    maxWidth: 350,
    marginTop: 10,
    color: colors.inkMuted,
    fontSize: 14,
    lineHeight: 21,
  },
  importRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 22,
  },
  importButton: {
    minHeight: 52,
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 9,
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: radii.control,
    backgroundColor: colors.paperRaised,
  },
  importLabel: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "700",
  },
  importProgressCard: {
    marginTop: 10,
    paddingHorizontal: 15,
    paddingVertical: 13,
    borderRadius: radii.control,
    backgroundColor: colors.moss,
  },
  importProgressHeading: {
    flexDirection: "row",
    alignItems: "center",
  },
  importProgressLabel: {
    flex: 1,
    color: "#C7D4CC",
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 1.35,
  },
  importProgressCount: {
    color: colors.white,
    fontSize: 11,
    fontWeight: "800",
  },
  importProgressFilename: {
    marginTop: 6,
    color: colors.white,
    fontSize: 14,
    fontWeight: "700",
  },
  importProgressTrack: {
    height: 3,
    overflow: "hidden",
    marginTop: 11,
    borderRadius: 2,
    backgroundColor: "rgba(255,255,255,0.16)",
  },
  importProgressFill: {
    height: "100%",
    borderRadius: 2,
    backgroundColor: colors.signal,
  },
  playButton: {
    minHeight: 52,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginTop: 12,
    paddingHorizontal: 18,
    borderRadius: radii.control,
    backgroundColor: colors.ink,
  },
  playText: {
    flex: 1,
    color: colors.white,
    fontSize: 15,
    fontWeight: "800",
  },
  playCount: {
    color: "#C8D1CA",
    fontSize: 12,
    fontWeight: "700",
  },
  storageCard: {
    minHeight: 104,
    flexDirection: "row",
    alignItems: "center",
    marginTop: 12,
    paddingHorizontal: 18,
    paddingVertical: 15,
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: radii.control,
    backgroundColor: colors.paperRaised,
  },
  storageCopy: {
    flex: 1,
  },
  storageEyebrow: {
    color: colors.brass,
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 1.4,
  },
  storageValue: {
    marginTop: 5,
    color: colors.ink,
    fontSize: 25,
    fontWeight: "800",
    letterSpacing: -0.7,
  },
  storageMeta: {
    marginTop: 3,
    color: colors.inkMuted,
    fontSize: 12,
    fontWeight: "600",
  },
  storageFree: {
    marginTop: 5,
    color: colors.moss,
    fontSize: 11,
    fontWeight: "700",
  },
  storageFreeWarning: {
    color: colors.signal,
  },
  clearButton: {
    minWidth: 64,
    minHeight: 42,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radii.pill,
    backgroundColor: "#EFE2D5",
  },
  clearText: {
    color: colors.signal,
    fontSize: 13,
    fontWeight: "800",
  },
  selectionBar: {
    minHeight: 58,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginTop: 12,
    paddingHorizontal: 10,
    borderRadius: radii.control,
    backgroundColor: colors.moss,
  },
  selectionDismiss: {
    width: 34,
    height: 34,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 17,
    backgroundColor: "rgba(255,255,255,0.12)",
  },
  selectionCount: {
    flex: 1,
    color: colors.white,
    fontSize: 14,
    fontWeight: "800",
  },
  selectAllText: {
    color: "#D6E2DA",
    fontSize: 13,
    fontWeight: "800",
  },
  deleteSelection: {
    minHeight: 38,
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    paddingHorizontal: 13,
    borderRadius: radii.pill,
    backgroundColor: colors.signal,
  },
  deleteSelectionText: {
    color: colors.white,
    fontSize: 12,
    fontWeight: "800",
  },
  selectionHint: {
    marginTop: 9,
    color: colors.inkMuted,
    fontSize: 11,
    textAlign: "center",
  },
  gridRow: {
    gap: 7,
  },
  tile: {
    aspectRatio: 0.78,
    flex: 1,
    maxWidth: "32.2%",
    overflow: "hidden",
    marginBottom: 7,
    borderRadius: 14,
    backgroundColor: colors.ink,
  },
  selectedTile: {
    borderColor: colors.signal,
    borderWidth: 3,
  },
  tileMedia: {
    width: "100%",
    height: "100%",
    resizeMode: "cover",
  },
  videoTile: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.moss,
  },
  kindBadge: {
    position: "absolute",
    top: 8,
    right: 8,
    width: 22,
    height: 22,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 11,
    backgroundColor: "rgba(11, 33, 28, 0.72)",
  },
  selectionMark: {
    position: "absolute",
    top: 8,
    left: 8,
    width: 25,
    height: 25,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 13,
    backgroundColor: colors.signal,
  },
  empty: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 30,
    paddingBottom: 70,
  },
  emptyMark: {
    width: 82,
    height: 82,
    alignItems: "center",
    justifyContent: "center",
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: 41,
    backgroundColor: colors.paperRaised,
  },
  emptyTitle: {
    marginTop: 21,
    color: colors.ink,
    fontSize: 24,
    fontWeight: "800",
    letterSpacing: -0.6,
  },
  emptyBody: {
    maxWidth: 310,
    marginTop: 9,
    color: colors.inkMuted,
    fontSize: 14,
    lineHeight: 21,
    textAlign: "center",
  },
  loading: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingBottom: 80,
  },
  pressed: {
    opacity: 0.68,
    transform: [{ scale: 0.98 }],
  },
  disabled: {
    opacity: 0.5,
  },
});
