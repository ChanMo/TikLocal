export type AudioSource =
  | number
  | null
  | {
      uri: string;
      headers?: Record<string, string>;
    };

export type StationId = "default" | "recent" | "favorites";

export type Station = {
  id: StationId;
  name: string;
  description: string;
};

export type Track = {
  id: string;
  uri: string;
  title: string;
  artist: string;
  album: string;
  source: AudioSource;
  accent: string;
  isFavorite: boolean;
};

export type SleepMinutes = 0 | 30 | 60 | 120;

export type ServerProfile = {
  baseUrl: string;
  serverName: string;
  deviceId: string;
  token: string;
};

export type KnownServer = {
  baseUrl: string;
  serverName?: string;
};

export type StoredConnection =
  | { kind: "paired"; profile: ServerProfile }
  | { kind: "known"; server: KnownServer };

export type PlaybackState =
  | { kind: "paused" }
  | { kind: "buffering" }
  | { kind: "playing" }
  | { kind: "error"; message: string };

export type SyncState =
  | { kind: "demo" }
  | { kind: "loading"; message: string }
  | { kind: "ready"; serverName: string }
  | { kind: "empty"; serverName: string; message: string }
  | { kind: "offline"; message: string };

export type RadioSnapshot = {
  station: Station;
  stations: Station[];
  track: Track;
  playback: PlaybackState;
  sync: SyncState;
  currentTime: number;
  duration: number;
  isFavorite: boolean;
  encoreCount: number;
  sleepEndsAt: number | null;
};
