import { SymbolView } from "expo-symbols";
import {
  ActionSheetIOS,
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { SleepMinutes, Station } from "./model";
import type { RadioSession } from "./radio";
import { SignalDial } from "./SignalDial";
import { colors } from "./theme";

type RadioScreenProps = {
  radio: RadioSession;
  onConnectionPress(): void;
};

export function RadioScreen({ radio, onConnectionPress }: RadioScreenProps) {
  const { snapshot } = radio;
  const insets = useSafeAreaInsets();
  const { height, width } = useWindowDimensions();
  const isPlaying = snapshot.playback.kind === "playing";
  const isBuffering = snapshot.playback.kind === "buffering";
  const isPlayable =
    snapshot.sync.kind === "ready" || snapshot.sync.kind === "demo";
  const hasConnectionIssue =
    snapshot.sync.kind === "offline" || snapshot.sync.kind === "empty";
  const progress =
    snapshot.duration > 0
      ? Math.min(snapshot.currentTime / snapshot.duration, 1)
      : 0;
  const display = displayTrack(snapshot);

  return (
    <View style={styles.screen}>
      <View style={[styles.topBar, { paddingTop: insets.top }]}>
        <Pressable
          accessibilityLabel={`Choose station, ${snapshot.station.name}`}
          accessibilityRole="button"
          accessibilityState={{ disabled: !isPlayable, expanded: false }}
          disabled={!isPlayable}
          onPress={() =>
            openStationPicker(
              snapshot.station,
              snapshot.stations,
              radio.selectStation,
            )
          }
          style={({ pressed }) => [
            styles.stationButton,
            pressed && styles.pressed,
            !isPlayable && styles.controlDisabled,
          ]}
        >
          <SymbolView
            name="dot.radiowaves.left.and.right"
            size={18}
            tintColor={colors.moss}
            weight="semibold"
          />
          <Text numberOfLines={1} style={styles.stationName}>
            {snapshot.station.name}
          </Text>
          <SymbolView
            name="chevron.down"
            size={11}
            tintColor={colors.inkMuted}
            weight="bold"
          />
        </Pressable>

        <Pressable
          accessibilityLabel="More Radio options"
          accessibilityRole="button"
          hitSlop={6}
          onPress={() =>
            openRadioMenu({
              isPlayable,
              onConnectionPress,
              radio,
            })
          }
          style={({ pressed }) => [
            styles.moreButton,
            pressed && styles.pressed,
          ]}
        >
          <SymbolView
            name="ellipsis.circle"
            size={25}
            tintColor={colors.ink}
            weight="medium"
          />
          {snapshot.sync.kind === "loading" ? (
            <ActivityIndicator
              color={colors.brass}
              size="small"
              style={styles.menuStatus}
            />
          ) : hasConnectionIssue ? (
            <View style={styles.menuIssueDot} />
          ) : null}
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingBottom: Math.max(insets.bottom, 16) },
        ]}
        showsVerticalScrollIndicator={false}
      >
        <SignalDial
          accent={snapshot.track.accent}
          isPlaying={isPlaying}
          size={Math.min(width - 64, height >= 800 ? 300 : 282)}
        />

        <View style={styles.nowPlaying}>
          <Text
            accessibilityRole={hasConnectionIssue ? "alert" : undefined}
            numberOfLines={1}
            style={styles.title}
          >
            {display.title}
          </Text>
          <Text numberOfLines={1} style={styles.artist}>
            {display.artist}
          </Text>
          {snapshot.encoreCount > 0 || snapshot.sleepMinutes > 0 ? (
            <View style={styles.activeStates}>
              {snapshot.encoreCount > 0 ? (
                <ActiveState
                  kind="encore"
                  label={`Queued ×${snapshot.encoreCount}`}
                />
              ) : null}
              {snapshot.sleepMinutes > 0 ? (
                <ActiveState
                  kind="sleep"
                  label={`${snapshot.sleepMinutes} min`}
                />
              ) : null}
            </View>
          ) : null}
        </View>

        {isPlayable ? (
          <View style={styles.progressBlock}>
            <View
              accessible
              accessibilityLabel="Playback progress"
              accessibilityRole="progressbar"
              accessibilityValue={{
                min: 0,
                max: 100,
                now: Math.round(progress * 100),
                text: `${formatTime(snapshot.currentTime)} of ${formatTime(snapshot.duration)}`,
              }}
              style={styles.progressTrack}
            >
              <View
                style={[
                  styles.progressValue,
                  {
                    width: `${progress * 100}%`,
                    backgroundColor: snapshot.track.accent,
                  },
                ]}
              />
            </View>
            <View style={styles.timeRow}>
              <Text style={styles.time}>
                {formatTime(snapshot.currentTime)}
              </Text>
              <Text style={styles.time}>
                {isBuffering ? "Tuning…" : formatTime(snapshot.duration)}
              </Text>
            </View>
          </View>
        ) : (
          <View style={styles.progressPlaceholder} />
        )}

        <View style={styles.transport}>
          <IconControl
            active={snapshot.isFavorite}
            accessibilityLabel={
              snapshot.isFavorite
                ? "Remove from Favorites"
                : "Add to Favorites"
            }
            disabled={!isPlayable}
            kind="favorite"
            onPress={radio.toggleFavorite}
          />
          <IconControl
            accessibilityLabel={isPlaying ? "Pause radio" : "Play radio"}
            disabled={!isPlayable}
            kind={isPlaying ? "pause" : "play"}
            onPress={isPlaying ? radio.pause : radio.play}
            primary
          />
          <IconControl
            accessibilityLabel="Next track"
            disabled={!isPlayable}
            kind="next"
            onPress={radio.next}
          />
        </View>

        {snapshot.playback.kind === "error" ? (
          <Text accessibilityRole="alert" style={styles.error}>
            Playback interrupted · tap Play to try again
          </Text>
        ) : hasConnectionIssue ? (
          <Pressable
            accessibilityLabel="Open Server connection settings"
            accessibilityRole="button"
            onPress={onConnectionPress}
            style={({ pressed }) => [
              styles.errorAction,
              pressed && styles.pressed,
            ]}
          >
            <SymbolView
              name={
                snapshot.sync.kind === "offline"
                  ? "wifi.slash"
                  : "exclamationmark.circle"
              }
              size={13}
              tintColor={colors.signal}
              weight="semibold"
            />
            <Text style={styles.error}>
              {snapshot.sync.kind === "offline"
                ? "Connection saved · tap to reconnect"
                : "Open Connection"}
            </Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </View>
  );
}

type ControlKind = "favorite" | "play" | "pause" | "next";

function IconControl({
  accessibilityLabel,
  active = false,
  disabled,
  kind,
  onPress,
  primary = false,
}: {
  accessibilityLabel: string;
  active?: boolean;
  disabled: boolean;
  kind: ControlKind;
  onPress(): void;
  primary?: boolean;
}) {
  const name =
    kind === "favorite"
      ? active
        ? "heart.fill"
        : "heart"
      : kind === "play"
        ? "play.fill"
        : kind === "pause"
          ? "pause.fill"
          : "forward.end.fill";
  return (
    <Pressable
      accessibilityLabel={accessibilityLabel}
      accessibilityRole="button"
      accessibilityState={{ disabled, selected: active }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.control,
        primary && styles.controlPrimary,
        active && styles.controlActive,
        pressed && styles.controlPressed,
        disabled && styles.controlDisabled,
      ]}
    >
      <SymbolView
        animationSpec={
          active
            ? {
                effect: { type: "bounce", wholeSymbol: true },
                repeatCount: 1,
              }
            : undefined
        }
        name={name}
        size={primary ? 28 : 23}
        tintColor={primary || active ? colors.white : colors.ink}
        weight="semibold"
      />
    </Pressable>
  );
}

function ActiveState({
  kind,
  label,
}: {
  kind: "encore" | "sleep";
  label: string;
}) {
  return (
    <View style={styles.activeState}>
      <SymbolView
        name={kind === "encore" ? "repeat.1" : "moon.zzz"}
        size={12}
        tintColor={colors.moss}
        weight="semibold"
      />
      <Text style={styles.activeStateText}>{label}</Text>
    </View>
  );
}

function displayTrack(snapshot: RadioSession["snapshot"]) {
  switch (snapshot.sync.kind) {
    case "loading":
      return {
        title: "Tuning in",
        artist: "Finding a frequency in your library",
      };
    case "offline":
      return {
        title: "Signal interrupted",
        artist: "Your connection is saved",
      };
    case "empty":
      return {
        title: "Your library is quiet",
        artist: "Add playable audio in TikLocal",
      };
    default:
      return {
        title: snapshot.track.title,
        artist: snapshot.track.artist,
      };
  }
}

function openRadioMenu({
  isPlayable,
  onConnectionPress,
  radio,
}: {
  isPlayable: boolean;
  onConnectionPress(): void;
  radio: RadioSession;
}) {
  const { snapshot } = radio;
  const encoreLabel =
    snapshot.encoreCount > 0
      ? `Play Again · ${snapshot.encoreCount} queued`
      : "Play Again";
  const sleepLabel =
    snapshot.sleepMinutes > 0
      ? `Sleep Timer · ${snapshot.sleepMinutes} min`
      : "Sleep Timer";
  ActionSheetIOS.showActionSheetWithOptions(
    {
      cancelButtonIndex: 3,
      disabledButtonIndices: isPlayable ? [] : [0, 1],
      options: [encoreLabel, sleepLabel, "Connection", "Cancel"],
      title: "Radio",
    },
    (index) => {
      if (index === 0) {
        radio.encore();
      } else if (index === 1) {
        requestAnimationFrame(() =>
          openSleepTimer(snapshot.sleepMinutes, radio.setSleepTimer),
        );
      } else if (index === 2) {
        onConnectionPress();
      }
    },
  );
}

function openStationPicker(
  current: Station,
  stations: Station[],
  selectStation: RadioSession["selectStation"],
) {
  if (Platform.OS !== "ios") {
    const currentIndex = stations.findIndex(({ id }) => id === current.id);
    const next = stations[(currentIndex + 1) % stations.length];
    if (next) {
      selectStation(next.id);
    }
    return;
  }
  ActionSheetIOS.showActionSheetWithOptions(
    {
      cancelButtonIndex: stations.length,
      options: [...stations.map(({ name }) => name), "Cancel"],
      title: "Choose a Station",
    },
    (index) => {
      const station = stations[index];
      if (station && station.id !== current.id) {
        selectStation(station.id);
      }
    },
  );
}

function openSleepTimer(
  current: SleepMinutes,
  setSleepTimer: (minutes: SleepMinutes) => void,
) {
  const values: SleepMinutes[] = [0, 30, 60, 120];
  if (Platform.OS !== "ios") {
    const currentIndex = values.indexOf(current);
    setSleepTimer(values[(currentIndex + 1) % values.length] ?? 0);
    return;
  }
  ActionSheetIOS.showActionSheetWithOptions(
    {
      cancelButtonIndex: 4,
      options: ["Off", "30 Minutes", "1 Hour", "2 Hours", "Cancel"],
      title: "Sleep Timer",
    },
    (index) => {
      const minutes = values[index];
      if (minutes !== undefined) {
        setSleepTimer(minutes);
      }
    },
  );
}

function formatTime(value: number) {
  if (!Number.isFinite(value) || value <= 0) {
    return "0:00";
  }
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.paper,
  },
  topBar: {
    minHeight: 54,
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    backgroundColor: colors.paper,
  },
  stationButton: {
    maxWidth: "78%",
    minHeight: 48,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    paddingHorizontal: 6,
  },
  stationName: {
    flexShrink: 1,
    color: colors.ink,
    fontSize: 17,
    fontWeight: "700",
    letterSpacing: -0.2,
  },
  moreButton: {
    width: 48,
    height: 48,
    alignItems: "center",
    justifyContent: "center",
  },
  menuStatus: {
    position: "absolute",
    right: 3,
    bottom: 3,
    transform: [{ scale: 0.55 }],
  },
  menuIssueDot: {
    position: "absolute",
    right: 8,
    bottom: 8,
    width: 7,
    height: 7,
    borderColor: colors.paper,
    borderWidth: 1.5,
    borderRadius: 4,
    backgroundColor: colors.signal,
  },
  content: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingTop: 24,
  },
  nowPlaying: {
    minHeight: 65,
    paddingTop: 18,
  },
  title: {
    color: colors.ink,
    fontSize: 29,
    fontWeight: "700",
    letterSpacing: -0.7,
  },
  artist: {
    marginTop: 4,
    color: colors.inkMuted,
    fontSize: 15,
    fontWeight: "500",
  },
  activeStates: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    marginTop: 9,
  },
  activeState: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
  },
  activeStateText: {
    color: colors.moss,
    fontSize: 11,
    fontWeight: "600",
  },
  progressBlock: {
    marginTop: 24,
  },
  progressPlaceholder: {
    height: 37,
    marginTop: 24,
  },
  progressTrack: {
    height: 3,
    overflow: "hidden",
    borderRadius: 2,
    backgroundColor: colors.line,
  },
  progressValue: {
    height: "100%",
    borderRadius: 2,
  },
  timeRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 7,
  },
  time: {
    color: colors.inkMuted,
    fontSize: 10,
    fontVariant: ["tabular-nums"],
  },
  transport: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 32,
    marginTop: 30,
  },
  control: {
    width: 56,
    height: 56,
    alignItems: "center",
    justifyContent: "center",
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: 28,
    backgroundColor: colors.paperRaised,
  },
  controlPrimary: {
    width: 72,
    height: 72,
    borderColor: colors.ink,
    borderRadius: 36,
    backgroundColor: colors.ink,
    shadowColor: colors.ink,
    shadowOffset: { width: 0, height: 9 },
    shadowOpacity: 0.2,
    shadowRadius: 16,
    elevation: 6,
  },
  controlActive: {
    borderColor: colors.moss,
    backgroundColor: colors.moss,
  },
  controlPressed: {
    opacity: 0.72,
    transform: [{ scale: 0.94 }],
  },
  controlDisabled: {
    opacity: 0.32,
  },
  errorAction: {
    minHeight: 38,
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "center",
    gap: 6,
    marginTop: 12,
    paddingHorizontal: 10,
  },
  error: {
    color: colors.signal,
    fontSize: 11,
    fontWeight: "600",
    textAlign: "center",
  },
  pressed: {
    opacity: 0.58,
  },
});
