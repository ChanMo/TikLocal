import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";

import type { SleepMinutes, Station } from "./model";
import type { RadioSession } from "./radio";
import { colors, radii } from "./theme";

type RadioScreenProps = {
  radio: RadioSession;
  onConnectionPress(): void;
};

export function RadioScreen({ radio, onConnectionPress }: RadioScreenProps) {
  const { snapshot } = radio;
  const isPlaying = snapshot.playback.kind === "playing";
  const isBuffering = snapshot.playback.kind === "buffering";
  const isPlayable = snapshot.sync.kind !== "empty";
  const connectionLabel =
    snapshot.sync.kind === "ready"
      ? snapshot.sync.serverName
      : snapshot.sync.kind === "loading"
        ? "TUNING"
        : snapshot.sync.kind === "empty"
          ? "NO AUDIO"
          : snapshot.sync.kind === "offline"
            ? "OFFLINE"
            : "DEMO SIGNAL";
  const progress =
    snapshot.duration > 0
      ? Math.min(snapshot.currentTime / snapshot.duration, 1)
      : 0;

  return (
    <ScrollView
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.masthead}>
        <View>
          <Text style={styles.eyebrow}>TIKLOCAL / PRIVATE FREQUENCY</Text>
          <Text style={styles.brand}>Radio</Text>
        </View>
        <Pressable
          accessibilityLabel="Change TikLocal Server"
          accessibilityRole="button"
          onPress={onConnectionPress}
          style={({ pressed }) => [styles.onAir, pressed && styles.pressed]}
        >
          <View style={styles.onAirDot} />
          <Text numberOfLines={1} style={styles.onAirText}>
            {connectionLabel.toUpperCase()}
          </Text>
        </Pressable>
      </View>

      <ScrollView
        horizontal
        contentContainerStyle={styles.stations}
        showsHorizontalScrollIndicator={false}
      >
        {snapshot.stations.map((station) => (
          <StationPill
            key={station.id}
            station={station}
            selected={station.id === snapshot.station.id}
            onPress={() => radio.selectStation(station.id)}
          />
        ))}
      </ScrollView>

      <View style={styles.stationNote}>
        <Text style={styles.stationNumber}>
          CH {String(snapshot.stations.indexOf(snapshot.station) + 1).padStart(2, "0")}
        </Text>
        <Text style={styles.stationDescription}>{snapshot.station.description}</Text>
      </View>

      <View style={[styles.signalCard, { borderColor: snapshot.track.accent }]}>
        <View style={styles.signalGrid}>
          <View
            style={[
              styles.orbit,
              styles.orbitOuter,
              { borderColor: snapshot.track.accent },
            ]}
          />
          <View style={[styles.orbit, styles.orbitMiddle]} />
          <View
            style={[
              styles.record,
              isPlaying && styles.recordActive,
              { backgroundColor: snapshot.track.accent },
            ]}
          >
            <View style={styles.recordLine} />
            <View style={styles.recordLineSmall} />
            <View style={styles.label}>
              <Text style={styles.labelMark}>TL</Text>
              <Text style={styles.labelIndex}>
                {String(
                  snapshot.stations.indexOf(snapshot.station) + 1,
                ).padStart(2, "0")}
              </Text>
            </View>
          </View>
          <View style={styles.signalRule} />
          <Text style={styles.signalType}>LOCAL TRANSMISSION</Text>
        </View>
      </View>

      <View style={styles.nowPlaying}>
        <Text style={styles.album}>{snapshot.track.album.toUpperCase()}</Text>
        <Text style={styles.title}>{snapshot.track.title}</Text>
        <Text style={styles.artist}>{snapshot.track.artist}</Text>
      </View>

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
          <Text style={styles.time}>{formatTime(snapshot.currentTime)}</Text>
          <Text style={styles.time}>
            {isBuffering ? "TUNING…" : formatTime(snapshot.duration)}
          </Text>
        </View>
      </View>

      <View style={styles.transport}>
        <Pressable
          accessibilityLabel={
            isPlaying ? "Pause radio" : "Play radio"
          }
          accessibilityRole="button"
          disabled={!isPlayable}
          onPress={isPlaying ? radio.pause : radio.play}
          style={({ pressed }) => [
            styles.playButton,
            pressed && styles.pressed,
            !isPlayable && styles.disabled,
          ]}
        >
          <Text style={styles.playIcon}>
            {isPlaying ? "Ⅱ" : "▶"}
          </Text>
        </Pressable>
        <Pressable
          accessibilityLabel="Next track"
          accessibilityRole="button"
          disabled={!isPlayable}
          onPress={radio.next}
          style={({ pressed }) => [
            styles.nextButton,
            pressed && styles.pressed,
            !isPlayable && styles.disabled,
          ]}
        >
          <Text style={styles.nextIcon}>→</Text>
          <Text style={styles.nextLabel}>NEXT</Text>
        </Pressable>
      </View>

      <View style={styles.actions}>
        <ActionButton
          active={snapshot.isFavorite}
          disabled={!isPlayable}
          label={snapshot.isFavorite ? "KEPT" : "KEEP"}
          mark={snapshot.isFavorite ? "♥" : "♡"}
          onPress={radio.toggleFavorite}
        />
        <ActionButton
          active={snapshot.encoreCount > 0}
          disabled={!isPlayable}
          label={snapshot.encoreCount > 0 ? `ENCORE ×${snapshot.encoreCount}` : "ENCORE"}
          mark="↺"
          onPress={radio.encore}
        />
        <ActionButton
          active={snapshot.sleepMinutes > 0}
          disabled={!isPlayable}
          label={
            snapshot.sleepMinutes > 0
              ? `SLEEP ${snapshot.sleepMinutes}`
              : "SLEEP"
          }
          mark="◷"
          onPress={() =>
            radio.setSleepTimer(nextSleepMinutes(snapshot.sleepMinutes))
          }
        />
      </View>

      {snapshot.playback.kind === "error" ? (
        <Text accessibilityRole="alert" style={styles.error}>
          Signal interrupted: {snapshot.playback.message}
        </Text>
      ) : snapshot.sync.kind === "offline" || snapshot.sync.kind === "empty" ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {snapshot.sync.message}
        </Text>
      ) : (
        <Text style={styles.footer}>
          {snapshot.sync.kind === "ready"
            ? "PRIVATE LIBRARY · DEVICE TOKEN · API V1"
            : "ORIGINAL DEMO AUDIO · NATIVE BACKGROUND READY"}
        </Text>
      )}
    </ScrollView>
  );
}

function StationPill({
  station,
  selected,
  onPress,
}: {
  station: Station;
  selected: boolean;
  onPress(): void;
}) {
  return (
    <Pressable
      accessibilityLabel={station.name}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.stationPill, selected && styles.stationPillSelected]}
    >
      <Text
        style={[
          styles.stationPillText,
          selected && styles.stationPillTextSelected,
        ]}
      >
        {station.name}
      </Text>
    </Pressable>
  );
}

function ActionButton({
  active,
  disabled,
  label,
  mark,
  onPress,
}: {
  active: boolean;
  disabled?: boolean;
  label: string;
  mark: string;
  onPress(): void;
}) {
  return (
    <Pressable
      accessibilityLabel={label}
      accessibilityRole="button"
      accessibilityState={{ disabled, selected: active }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.actionButton,
        active && styles.actionButtonActive,
        pressed && styles.pressed,
        disabled && styles.disabled,
      ]}
    >
      <Text style={[styles.actionMark, active && styles.actionTextActive]}>
        {mark}
      </Text>
      <Text style={[styles.actionLabel, active && styles.actionTextActive]}>
        {label}
      </Text>
    </Pressable>
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

function nextSleepMinutes(current: SleepMinutes): SleepMinutes {
  const values: SleepMinutes[] = [0, 30, 60, 120];
  const currentIndex = values.indexOf(current);
  return values[(currentIndex + 1) % values.length] ?? 0;
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: 22,
    paddingTop: 18,
    paddingBottom: 38,
  },
  masthead: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
  },
  eyebrow: {
    color: colors.inkMuted,
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 1.7,
  },
  brand: {
    color: colors.ink,
    fontFamily: "Georgia",
    fontSize: 40,
    lineHeight: 46,
  },
  onAir: {
    maxWidth: 150,
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: radii.pill,
    paddingHorizontal: 11,
    paddingVertical: 8,
  },
  onAirDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.signal,
  },
  onAirText: {
    flexShrink: 1,
    color: colors.ink,
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 1,
  },
  stations: {
    gap: 8,
    paddingVertical: 18,
  },
  stationPill: {
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: radii.pill,
    paddingHorizontal: 15,
    paddingVertical: 10,
  },
  stationPillSelected: {
    backgroundColor: colors.ink,
    borderColor: colors.ink,
  },
  stationPillText: {
    color: colors.inkMuted,
    fontSize: 12,
    fontWeight: "700",
  },
  stationPillTextSelected: {
    color: colors.white,
  },
  stationNote: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 12,
  },
  stationNumber: {
    color: colors.signal,
    fontSize: 10,
    fontWeight: "900",
    letterSpacing: 1.5,
  },
  stationDescription: {
    color: colors.inkMuted,
    fontSize: 11,
  },
  signalCard: {
    height: 292,
    overflow: "hidden",
    borderWidth: 1,
    borderRadius: radii.card,
    backgroundColor: colors.paperRaised,
  },
  signalGrid: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  orbit: {
    position: "absolute",
    borderRadius: radii.pill,
    borderWidth: 1,
  },
  orbitOuter: {
    width: 350,
    height: 350,
    opacity: 0.22,
  },
  orbitMiddle: {
    width: 250,
    height: 250,
    borderColor: colors.line,
  },
  record: {
    width: 184,
    height: 184,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 92,
    shadowColor: colors.ink,
    shadowOffset: { width: 0, height: 16 },
    shadowOpacity: 0.18,
    shadowRadius: 22,
    elevation: 8,
    transform: [{ rotate: "-6deg" }],
  },
  recordActive: {
    transform: [{ rotate: "4deg" }, { scale: 1.02 }],
  },
  recordLine: {
    position: "absolute",
    width: 148,
    height: 148,
    borderColor: "rgba(255,255,255,0.28)",
    borderWidth: 1,
    borderRadius: 74,
  },
  recordLineSmall: {
    position: "absolute",
    width: 116,
    height: 116,
    borderColor: "rgba(255,255,255,0.22)",
    borderWidth: 1,
    borderRadius: 58,
  },
  label: {
    width: 76,
    height: 76,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 38,
    backgroundColor: colors.paper,
  },
  labelMark: {
    color: colors.ink,
    fontFamily: "Georgia",
    fontSize: 25,
    fontWeight: "700",
  },
  labelIndex: {
    color: colors.inkMuted,
    fontSize: 8,
    fontWeight: "800",
    letterSpacing: 2,
  },
  signalRule: {
    position: "absolute",
    right: 20,
    bottom: 25,
    width: 42,
    height: 1,
    backgroundColor: colors.ink,
  },
  signalType: {
    position: "absolute",
    left: 20,
    bottom: 20,
    color: colors.inkMuted,
    fontSize: 8,
    fontWeight: "800",
    letterSpacing: 1.5,
  },
  nowPlaying: {
    alignItems: "center",
    paddingTop: 22,
  },
  album: {
    color: colors.signal,
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 1.6,
  },
  title: {
    marginTop: 5,
    color: colors.ink,
    fontFamily: "Georgia",
    fontSize: 31,
    lineHeight: 38,
  },
  artist: {
    marginTop: 2,
    color: colors.inkMuted,
    fontSize: 13,
  },
  progressBlock: {
    marginTop: 20,
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
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 0.7,
  },
  transport: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 12,
    marginTop: 18,
  },
  playButton: {
    width: 72,
    height: 72,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 36,
    backgroundColor: colors.ink,
  },
  playIcon: {
    marginLeft: 2,
    color: colors.white,
    fontSize: 22,
  },
  nextButton: {
    height: 54,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderColor: colors.ink,
    borderWidth: 1,
    borderRadius: radii.pill,
    paddingHorizontal: 18,
  },
  nextIcon: {
    color: colors.ink,
    fontSize: 21,
  },
  nextLabel: {
    color: colors.ink,
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 1.2,
  },
  actions: {
    flexDirection: "row",
    gap: 8,
    marginTop: 22,
  },
  actionButton: {
    flex: 1,
    minHeight: 62,
    alignItems: "center",
    justifyContent: "center",
    borderColor: colors.line,
    borderWidth: 1,
    borderRadius: radii.control,
    backgroundColor: "rgba(250,246,236,0.58)",
  },
  actionButtonActive: {
    backgroundColor: colors.moss,
    borderColor: colors.moss,
  },
  actionMark: {
    color: colors.ink,
    fontSize: 17,
  },
  actionLabel: {
    marginTop: 3,
    color: colors.inkMuted,
    fontSize: 8,
    fontWeight: "900",
    letterSpacing: 1,
  },
  actionTextActive: {
    color: colors.white,
  },
  pressed: {
    opacity: 0.7,
    transform: [{ scale: 0.98 }],
  },
  disabled: {
    opacity: 0.42,
  },
  error: {
    marginTop: 18,
    color: colors.signal,
    fontSize: 11,
    textAlign: "center",
  },
  footer: {
    marginTop: 20,
    color: colors.inkMuted,
    fontSize: 8,
    fontWeight: "700",
    letterSpacing: 1.2,
    textAlign: "center",
  },
});
