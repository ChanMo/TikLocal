import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AppState } from "react-native";

import { createRadioApi, TikLocalApiError } from "./api";
import type {
  PlaybackState,
  RadioSnapshot,
  ServerProfile,
  SleepMinutes,
  Station,
  StationId,
  SyncState,
  Track,
} from "./model";
import { useRadioPlayer } from "./player";
import {
  loadRadioResume,
  saveRadioResume,
} from "./radioResume";

const demoStations: Station[] = [
  {
    id: "default",
    name: "Daily Signal",
    description: "A quiet mix from your library",
  },
  {
    id: "recent",
    name: "New Air",
    description: "Recently arrived frequencies",
  },
  {
    id: "favorites",
    name: "Kept Close",
    description: "Guided by your favorites",
  },
];

const demoTracks: Track[] = [
  {
    id: "paper-sun",
    uri: "demo:paper-sun",
    title: "Paper Sun",
    artist: "TikLocal Field Unit",
    album: "Private Frequency No. 01",
    source: require("../assets/paper-sun.mp3"),
    accent: "#D9633B",
    isFavorite: false,
  },
  {
    id: "moss-window",
    uri: "demo:moss-window",
    title: "Moss Window",
    artist: "TikLocal Field Unit",
    album: "Private Frequency No. 02",
    source: require("../assets/moss-window.mp3"),
    accent: "#476F5B",
    isFavorite: false,
  },
  {
    id: "late-platform",
    uri: "demo:late-platform",
    title: "Late Platform",
    artist: "TikLocal Field Unit",
    album: "Private Frequency No. 03",
    source: require("../assets/late-platform.mp3"),
    accent: "#B78D42",
    isFavorite: false,
  },
];

const demoStationStarts: Record<StationId, number> = {
  default: 0,
  recent: 1,
  favorites: 2,
};

const emptyTrack: Track = {
  id: "empty-library",
  uri: "demo:empty-library",
  title: "No audio found",
  artist: "Add music to TikLocal Server",
  album: "Private frequency is quiet",
  source: null,
  accent: "#8B908A",
  isFavorite: false,
};

export type RadioSession = {
  snapshot: RadioSnapshot;
  play(): void;
  pause(): void;
  next(): void;
  retry(): void;
  selectStation(stationId: StationId): void;
  toggleFavorite(): void;
  encore(): void;
  setSleepTimer(minutes: SleepMinutes): void;
};

export function useRadioSession(
  profile: ServerProfile | null,
  onUnauthorized: () => void,
): RadioSession {
  const [stations, setStations] = useState(demoStations);
  const [stationId, setStationId] = useState<StationId>("default");
  const [tracks, setTracks] = useState(demoTracks);
  const [trackIndex, setTrackIndex] = useState(0);
  const [encoreCount, setEncoreCount] = useState(0);
  const [sleepEndsAt, setSleepEndsAt] = useState<number | null>(null);
  const [sync, setSync] = useState<SyncState>(
    profile
      ? { kind: "loading", message: "Opening private frequency" }
      : { kind: "demo" },
  );
  const handledFinish = useRef(false);
  const recentUris = useRef<string[]>([]);
  const requestVersion = useRef(0);
  const currentTrack = tracks[trackIndex] ?? demoTracks[0]!;
  const {
    status,
    load,
    play: playerPlay,
    pause,
    clear,
    replay,
  } = useRadioPlayer(demoTracks[0]!);
  const api = useMemo(
    () => (profile ? createRadioApi(profile) : null),
    [profile],
  );

  const handleApiError = useCallback(
    (error: unknown) => {
      if (error instanceof TikLocalApiError && error.status === 401) {
        onUnauthorized();
        return;
      }
      setSync({
        kind: "offline",
        message:
          error instanceof Error
            ? error.message
            : "TikLocal Server is unavailable.",
      });
    },
    [onUnauthorized],
  );

  useEffect(() => {
    const version = ++requestVersion.current;
    recentUris.current = [];
    if (!api || !profile) {
      setStations(demoStations);
      setStationId("default");
      setTracks(demoTracks);
      setTrackIndex(0);
      setEncoreCount(0);
      setSync({ kind: "demo" });
      load(demoTracks[0]!, false);
      return;
    }

    setSync({ kind: "loading", message: "Tuning your library" });
    setTracks([emptyTrack]);
    setTrackIndex(0);
    clear();
    void loadRadioResume(profile)
      .then(async (resumed) => {
        if (version !== requestVersion.current) {
          return;
        }
        if (resumed) {
          recentUris.current = resumed.recentUris;
          setStationId(resumed.stationId);
          setTracks(resumed.tracks);
          setTrackIndex(resumed.trackIndex);
          setEncoreCount(0);
          setSync({ kind: "ready", serverName: profile.serverName });
          load(resumed.tracks[resumed.trackIndex]!, false);
          try {
            const nextStations = await api.stations();
            if (version === requestVersion.current) {
              setStations(nextStations);
            }
          } catch (error) {
            if (version === requestVersion.current) {
              handleApiError(error);
            }
          }
          return;
        }

        const [nextStations, tuned] = await Promise.all([
          api.stations(),
          api.tune("default"),
        ]);
        if (version !== requestVersion.current) {
          return;
        }
        if (!tuned.tracks.length) {
          setStations(nextStations);
          setStationId(tuned.station.id);
          setTracks([emptyTrack]);
          setTrackIndex(0);
          setEncoreCount(0);
          setSync({
            kind: "empty",
            serverName: profile.serverName,
            message: "No playable audio was found on this TikLocal Server.",
          });
          return;
        }
        setStations(nextStations);
        setStationId(tuned.station.id);
        setTracks(tuned.tracks);
        setTrackIndex(0);
        setEncoreCount(0);
        setSync({ kind: "ready", serverName: profile.serverName });
        load(tuned.tracks[0]!, false);
      })
      .catch((error) => {
        if (version === requestVersion.current) {
          handleApiError(error);
        }
      });
  }, [api, clear, handleApiError, load, profile]);

  useEffect(() => {
    if (!profile || sync.kind !== "ready") {
      return;
    }
    void saveRadioResume(profile, {
      stationId,
      tracks,
      trackIndex,
      recentUris: recentUris.current,
    }).catch(() => {
      // Playback must remain usable when the optional resume file cannot be written.
    });
  }, [profile, stationId, sync.kind, trackIndex, tracks]);

  const tuneStation = useCallback(
    async (nextStationId: StationId, shouldPlay: boolean) => {
      if (!api || !profile) {
        const nextIndex = demoStationStarts[nextStationId];
        setStationId(nextStationId);
        setTrackIndex(nextIndex);
        setEncoreCount(0);
        load(demoTracks[nextIndex]!, shouldPlay);
        return;
      }

      const version = ++requestVersion.current;
      setSync({ kind: "loading", message: "Changing frequency" });
      try {
        const tuned = await api.tune(nextStationId, recentUris.current);
        if (version !== requestVersion.current) {
          return;
        }
        if (!tuned.tracks.length) {
          setStationId(tuned.station.id);
          setTracks([emptyTrack]);
          setTrackIndex(0);
          setEncoreCount(0);
          setSync({
            kind: "empty",
            serverName: profile.serverName,
            message: "No playable audio was found on this TikLocal Server.",
          });
          clear();
          return;
        }
        setStationId(tuned.station.id);
        setTracks(tuned.tracks);
        setTrackIndex(0);
        setEncoreCount(0);
        setSync({ kind: "ready", serverName: profile.serverName });
        load(tuned.tracks[0]!, shouldPlay);
      } catch (error) {
        if (version === requestVersion.current) {
          handleApiError(error);
        }
      }
    },
    [api, clear, handleApiError, load, profile],
  );

  const sendFeedback = useCallback(
    (
      track: Track,
      event: "play" | "complete" | "replay" | "skip" | "error",
      ratio?: number,
    ) => {
      if (!api || track.uri.startsWith("demo:")) {
        return;
      }
      void api.feedback(track.uri, event, ratio).catch(() => {
        // Feedback is best-effort and must never interrupt playback.
      });
    },
    [api],
  );

  const moveNext = useCallback(
    (userInitiated: boolean) => {
      if (userInitiated) {
        const ratio = status.duration > 0 ? status.currentTime / status.duration : 0;
        sendFeedback(currentTrack, "skip", ratio);
      }
      recentUris.current = [...recentUris.current, currentTrack.uri].slice(-20);
      const nextIndex = trackIndex + 1;
      if (nextIndex < tracks.length) {
        setTrackIndex(nextIndex);
        setEncoreCount(0);
        load(tracks[nextIndex]!, true);
        return;
      }
      void tuneStation(stationId, true);
    },
    [
      currentTrack,
      load,
      sendFeedback,
      stationId,
      status.currentTime,
      status.duration,
      trackIndex,
      tracks,
      tuneStation,
    ],
  );

  useEffect(() => {
    if (!status.didJustFinish) {
      handledFinish.current = false;
      return;
    }
    if (handledFinish.current) {
      return;
    }
    handledFinish.current = true;

    if (encoreCount > 0) {
      setEncoreCount((count) => Math.max(0, count - 1));
      sendFeedback(currentTrack, "replay", 1);
      replay();
      return;
    }
    sendFeedback(currentTrack, "complete", 1);
    moveNext(false);
  }, [
    currentTrack,
    encoreCount,
    moveNext,
    replay,
    sendFeedback,
    status.didJustFinish,
  ]);

  useEffect(() => {
    if (sleepEndsAt === null) {
      return;
    }
    const remaining = sleepEndsAt - Date.now();
    if (remaining <= 0) {
      pause();
      setSleepEndsAt(null);
      return;
    }
    const timer = setTimeout(() => {
      pause();
      setSleepEndsAt(null);
    }, remaining);
    return () => clearTimeout(timer);
  }, [pause, sleepEndsAt]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", (state) => {
      if (
        state === "active" &&
        sleepEndsAt !== null &&
        sleepEndsAt <= Date.now()
      ) {
        pause();
        setSleepEndsAt(null);
      }
    });
    return () => subscription.remove();
  }, [pause, sleepEndsAt]);

  const toggleFavorite = useCallback(() => {
    const desired = !currentTrack.isFavorite;
    setTracks((current) =>
      current.map((track) =>
        track.id === currentTrack.id ? { ...track, isFavorite: desired } : track,
      ),
    );
    if (!api || currentTrack.uri.startsWith("demo:")) {
      return;
    }
    void api
      .setFavorite(currentTrack.uri, desired)
      .then((persisted) => {
        setTracks((current) =>
          current.map((track) =>
            track.id === currentTrack.id
              ? { ...track, isFavorite: persisted }
              : track,
          ),
        );
      })
      .catch((error) => {
        setTracks((current) =>
          current.map((track) =>
            track.id === currentTrack.id
              ? { ...track, isFavorite: !desired }
              : track,
          ),
        );
        handleApiError(error);
      });
  }, [api, currentTrack, handleApiError]);

  const setSleepTimer = useCallback(
    (minutes: SleepMinutes) => {
      setSleepEndsAt(
        minutes > 0 ? Date.now() + minutes * 60 * 1000 : null,
      );
    },
    [],
  );

  const retry = useCallback(() => {
    const hasQueue = tracks.some((track) => track.id !== emptyTrack.id);
    if (!api || !profile || !hasQueue) {
      void tuneStation(stationId, false);
      return;
    }

    const version = ++requestVersion.current;
    setSync({ kind: "loading", message: "Reconnecting" });
    void api
      .stations()
      .then((nextStations) => {
        if (version !== requestVersion.current) {
          return;
        }
        setStations(nextStations);
        setSync({ kind: "ready", serverName: profile.serverName });
      })
      .catch((error) => {
        if (version === requestVersion.current) {
          handleApiError(error);
        }
      });
  }, [
    api,
    handleApiError,
    profile,
    stationId,
    tracks,
    tuneStation,
  ]);
  const canPlay = sync.kind === "ready" || sync.kind === "demo";
  const station = stations.find((item) => item.id === stationId) ?? stations[0]!;
  const snapshot: RadioSnapshot = {
    station,
    stations,
    track: currentTrack,
    playback: playbackStateFrom(status),
    sync,
    currentTime: canPlay ? status.currentTime : 0,
    duration: canPlay ? status.duration : 0,
    isFavorite: currentTrack.isFavorite,
    encoreCount,
    sleepEndsAt,
  };

  return {
    snapshot,
    play: () => {
      if (!canPlay) {
        return;
      }
      sendFeedback(currentTrack, "play");
      playerPlay();
    },
    pause,
    next: () => {
      if (canPlay) {
        moveNext(true);
      }
    },
    retry,
    selectStation: (nextStationId) => {
      if (sync.kind !== "empty" && sync.kind !== "offline") {
        void tuneStation(nextStationId, status.playing);
      }
    },
    toggleFavorite: () => {
      if (canPlay) {
        toggleFavorite();
      }
    },
    encore: () => {
      if (canPlay) {
        setEncoreCount((count) => Math.min(3, count + 1));
      }
    },
    setSleepTimer: (minutes) => {
      if (canPlay) {
        setSleepTimer(minutes);
      }
    },
  };
}

function playbackStateFrom(status: {
  error: string | null;
  isBuffering: boolean;
  playing: boolean;
}): PlaybackState {
  if (status.error) {
    return { kind: "error", message: status.error };
  }
  if (status.isBuffering) {
    return { kind: "buffering" };
  }
  return status.playing ? { kind: "playing" } : { kind: "paused" };
}
