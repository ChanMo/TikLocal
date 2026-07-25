import { beforeEach, expect, jest, test } from "@jest/globals";

import type { ServerProfile, Track } from "./model";
import {
  clearRadioResume,
  loadRadioResume,
  saveRadioResume,
} from "./radioResume";

let mockFileText: string | null = null;
const mockDelete = jest.fn(() => {
  mockFileText = null;
});
const mockWrite = jest.fn((value: string) => {
  mockFileText = value;
});
const mockCreate = jest.fn(() => {
  mockFileText = "";
});

jest.mock("expo-file-system", () => ({
  File: class {
    get exists() {
      return mockFileText !== null;
    }

    delete() {
      mockDelete();
    }

    create() {
      mockCreate();
    }

    async text() {
      if (mockFileText === null) {
        throw new Error("missing file");
      }
      return mockFileText;
    }

    write(value: string) {
      mockWrite(value);
    }
  },
  Paths: { document: "file:///documents" },
}));

const profile: ServerProfile = {
  baseUrl: "https://radio.test",
  serverName: "Studio",
  deviceId: "device-1",
  token: "secret-token",
};
const track: Track = {
  id: "track-1",
  uri: "@music/track-1.mp3",
  title: "Track One",
  artist: "Artist",
  album: "Album",
  source: {
    uri: "https://radio.test/api/v1/radio/media?uri=track-1",
    headers: { Authorization: "Bearer secret-token" },
  },
  accent: "#D9633B",
  isFavorite: false,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockFileText = null;
});

test("stores a queue without duplicating its bearer token", async () => {
  await saveRadioResume(profile, {
    stationId: "recent",
    tracks: [track],
    trackIndex: 0,
    recentUris: ["@music/previous.mp3"],
  });

  expect(mockWrite).toHaveBeenCalledTimes(1);
  expect(mockCreate).toHaveBeenCalledTimes(1);
  expect(mockFileText).not.toContain(profile.token);
  expect(mockFileText).toContain(track.uri);
  expect(mockFileText).toContain(
    "https://radio.test/api/v1/radio/media?uri=track-1",
  );
});

test("restores the same queue with the current secure token", async () => {
  await saveRadioResume(profile, {
    stationId: "favorites",
    tracks: [track],
    trackIndex: 0,
    recentUris: [],
  });

  const refreshedProfile = {
    ...profile,
    token: "refreshed-token",
  };
  await expect(loadRadioResume(refreshedProfile)).resolves.toEqual({
    stationId: "favorites",
    tracks: [
      {
        ...track,
        source: {
          uri: "https://radio.test/api/v1/radio/media?uri=track-1",
          headers: { Authorization: "Bearer refreshed-token" },
        },
      },
    ],
    trackIndex: 0,
    recentUris: [],
  });
});

test("removes stale or malformed sessions", async () => {
  await saveRadioResume(profile, {
    stationId: "default",
    tracks: [track],
    trackIndex: 0,
    recentUris: [],
  });

  await expect(
    loadRadioResume({ ...profile, deviceId: "another-device" }),
  ).resolves.toBeNull();
  expect(mockDelete).toHaveBeenCalledTimes(1);

  mockFileText = "{not-json";
  await expect(loadRadioResume(profile)).resolves.toBeNull();
  expect(mockDelete).toHaveBeenCalledTimes(2);
});

test("clears the optional queue snapshot idempotently", () => {
  clearRadioResume();
  expect(mockDelete).not.toHaveBeenCalled();

  mockFileText = "{}";
  clearRadioResume();
  expect(mockDelete).toHaveBeenCalledTimes(1);
});
