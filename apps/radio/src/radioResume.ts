import { File, Paths } from "expo-file-system";

import type {
  ServerProfile,
  StationId,
  Track,
} from "./model";

const SESSION_FILE = new File(Paths.document, "tiklocal-radio-session-v1.json");

type StoredTrack = Omit<Track, "source"> & {
  sourceUri: string;
};

type StoredRadioResume = {
  version: 1;
  deviceId: string;
  stationId: StationId;
  tracks: StoredTrack[];
  trackIndex: number;
  recentUris: string[];
};

export type RadioResume = {
  stationId: StationId;
  tracks: Track[];
  trackIndex: number;
  recentUris: string[];
};

export async function loadRadioResume(
  profile: ServerProfile,
): Promise<RadioResume | null> {
  if (!SESSION_FILE.exists) {
    return null;
  }
  try {
    const stored = parseStoredResume(await SESSION_FILE.text());
    if (!stored || stored.deviceId !== profile.deviceId) {
      clearRadioResume();
      return null;
    }
    return {
      stationId: stored.stationId,
      tracks: stored.tracks.map(({ sourceUri, ...track }) => ({
        ...track,
        source: {
          uri: sourceUri,
          headers: { Authorization: `Bearer ${profile.token}` },
        },
      })),
      trackIndex: stored.trackIndex,
      recentUris: stored.recentUris,
    };
  } catch {
    clearRadioResume();
    return null;
  }
}

export async function saveRadioResume(
  profile: ServerProfile,
  resume: RadioResume,
): Promise<void> {
  const tracks = resume.tracks.map(toStoredTrack);
  if (
    tracks.some((track) => track === null)
    || resume.trackIndex < 0
    || resume.trackIndex >= tracks.length
  ) {
    return;
  }
  const stored: StoredRadioResume = {
    version: 1,
    deviceId: profile.deviceId,
    stationId: resume.stationId,
    tracks: tracks as StoredTrack[],
    trackIndex: resume.trackIndex,
    recentUris: resume.recentUris.slice(-20),
  };
  if (!SESSION_FILE.exists) {
    SESSION_FILE.create({ intermediates: true });
  }
  SESSION_FILE.write(JSON.stringify(stored));
}

export function clearRadioResume(): void {
  try {
    if (SESSION_FILE.exists) {
      SESSION_FILE.delete();
    }
  } catch {
    // A stale session must never block connection or playback.
  }
}

function toStoredTrack(track: Track): StoredTrack | null {
  if (
    !track.source
    || typeof track.source === "number"
    || typeof track.source.uri !== "string"
  ) {
    return null;
  }
  const { source: _source, ...stored } = track;
  return {
    ...stored,
    sourceUri: track.source.uri,
  };
}

function parseStoredResume(value: string): StoredRadioResume | null {
  try {
    const stored = JSON.parse(value) as Partial<StoredRadioResume>;
    if (
      stored.version !== 1
      || typeof stored.deviceId !== "string"
      || !isStationId(stored.stationId)
      || !Array.isArray(stored.tracks)
      || stored.tracks.length === 0
      || stored.tracks.length > 30
      || !stored.tracks.every(isStoredTrack)
      || !Number.isInteger(stored.trackIndex)
      || stored.trackIndex! < 0
      || stored.trackIndex! >= stored.tracks.length
      || !Array.isArray(stored.recentUris)
      || !stored.recentUris.every((uri) => typeof uri === "string")
    ) {
      return null;
    }
    return stored as StoredRadioResume;
  } catch {
    return null;
  }
}

function isStoredTrack(value: unknown): value is StoredTrack {
  if (!value || typeof value !== "object") {
    return false;
  }
  const track = value as Partial<StoredTrack>;
  return (
    typeof track.id === "string"
    && typeof track.uri === "string"
    && typeof track.title === "string"
    && typeof track.artist === "string"
    && typeof track.album === "string"
    && typeof track.sourceUri === "string"
    && typeof track.accent === "string"
    && typeof track.isFavorite === "boolean"
  );
}

function isStationId(value: unknown): value is StationId {
  return value === "default" || value === "recent" || value === "favorites";
}
