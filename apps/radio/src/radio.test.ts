import { beforeEach, expect, jest, test } from "@jest/globals";
import { act, renderHook, waitFor } from "@testing-library/react-native";

import type { ServerProfile, StationId } from "./model";
import { useRadioSession } from "./radio";
import type { RadioResume } from "./radioResume";

const mockPlayer = {
  status: {
    currentTime: 20,
    didJustFinish: false,
    duration: 100,
    error: null,
    isBuffering: false,
    playing: false,
  },
  load: jest.fn(),
  play: jest.fn(),
  pause: jest.fn(),
  clear: jest.fn(),
  replay: jest.fn(),
};

jest.mock("./player", () => ({
  useRadioPlayer: () => mockPlayer,
}));

const mockLoadRadioResume = jest.fn<
  (profile: ServerProfile) => Promise<RadioResume | null>
>();
const mockSaveRadioResume = jest.fn<
  (profile: ServerProfile, resume: RadioResume) => Promise<void>
>();

jest.mock("./radioResume", () => ({
  loadRadioResume: (profile: ServerProfile) =>
    mockLoadRadioResume(profile),
  saveRadioResume: (profile: ServerProfile, resume: RadioResume) =>
    mockSaveRadioResume(profile, resume),
}));

const profile: ServerProfile = {
  baseUrl: "https://radio.test",
  serverName: "Studio",
  deviceId: "device-1",
  token: "secret-token",
};

const stationNames: Record<StationId, string> = {
  default: "Daily Signal",
  recent: "New Air",
  favorites: "Kept Close",
};

function station(id: StationId) {
  return {
    id,
    name: stationNames[id],
    description: `${stationNames[id]} description`,
  };
}

function tunePayload(id: StationId, trackId = `${id}-track`) {
  return {
    success: true,
    data: {
      station: station(id),
      items: [
        {
          id: trackId,
          uri: `@music/${trackId}.mp3`,
          title: trackId,
          artist: "Test Artist",
          album: "Test Album",
          is_favorite: false,
          media_path: `/api/v1/radio/media?uri=${trackId}`,
        },
      ],
    },
  };
}

function stationsPayload() {
  return {
    success: true,
    data: {
      stations: [
        station("default"),
        station("recent"),
        station("favorites"),
      ],
    },
  };
}

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
}

function installFetch(
  implementation: (url: string, init?: RequestInit) => Promise<Response>,
) {
  const fetchMock = jest.fn(
    (input: RequestInfo | URL, init?: RequestInit) =>
      implementation(String(input), init),
  );
  globalThis.fetch = fetchMock as typeof fetch;
  return fetchMock;
}

beforeEach(() => {
  jest.useRealTimers();
  jest.clearAllMocks();
  mockLoadRadioResume.mockResolvedValue(null);
  mockSaveRadioResume.mockResolvedValue();
});

test("loads a protected server track and becomes ready", async () => {
  const fetchMock = installFetch(async (url) =>
    response(
      url.includes("/stations")
        ? stationsPayload()
        : tunePayload("default"),
    ),
  );
  const onUnauthorized = jest.fn();

  const { result } = await renderHook(() =>
    useRadioSession(profile, onUnauthorized),
  );

  await waitFor(() => {
    expect(result.current.snapshot.sync.kind).toBe("ready");
  });
  expect(result.current.snapshot.track.id).toBe("default-track");
  expect(result.current.snapshot.track.source).toEqual({
    uri: "https://radio.test/api/v1/radio/media?uri=default-track",
    headers: { Authorization: "Bearer secret-token" },
  });
  expect(mockPlayer.load).toHaveBeenLastCalledWith(
    expect.objectContaining({ id: "default-track" }),
    false,
  );
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(onUnauthorized).not.toHaveBeenCalled();
});

test("restores a saved queue without requesting a new random tune", async () => {
  const resumedTrack = {
    id: "resumed-track",
    uri: "@music/resumed-track.mp3",
    title: "Resumed Track",
    artist: "Test Artist",
    album: "Test Album",
    source: {
      uri: "https://radio.test/api/v1/radio/media?uri=resumed-track",
      headers: { Authorization: "Bearer secret-token" },
    },
    accent: "#476F5B",
    isFavorite: false,
  };
  mockLoadRadioResume.mockResolvedValue({
    stationId: "recent",
    tracks: [resumedTrack],
    trackIndex: 0,
    recentUris: ["@music/previous-track.mp3"],
  });
  const fetchMock = installFetch(async (url) => {
    if (!url.includes("/stations")) {
      throw new Error(`unexpected request: ${url}`);
    }
    return response(stationsPayload());
  });
  const onUnauthorized = jest.fn();

  const { result } = await renderHook(() =>
    useRadioSession(profile, onUnauthorized),
  );

  await waitFor(() => {
    expect(result.current.snapshot.track.id).toBe("resumed-track");
  });
  expect(result.current.snapshot.station.id).toBe("recent");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(mockPlayer.load).toHaveBeenLastCalledWith(resumedTrack, false);
  await waitFor(() =>
    expect(mockSaveRadioResume).toHaveBeenCalledWith(
      profile,
      expect.objectContaining({
        stationId: "recent",
        tracks: [resumedTrack],
        trackIndex: 0,
      }),
    ),
  );
});

test("ignores a slower station response after a newer selection wins", async () => {
  const recentResponse = deferred<Response>();
  const favoritesResponse = deferred<Response>();
  installFetch(async (url) => {
    if (url.includes("/stations")) {
      return response(stationsPayload());
    }
    if (url.includes("station=recent")) {
      return recentResponse.promise;
    }
    if (url.includes("station=favorites")) {
      return favoritesResponse.promise;
    }
    return response(tunePayload("default"));
  });

  const onUnauthorized = jest.fn();
  const { result } = await renderHook(() =>
    useRadioSession(profile, onUnauthorized),
  );
  await waitFor(() => {
    expect(result.current.snapshot.sync.kind).toBe("ready");
  });

  await act(() => result.current.selectStation("recent"));
  await act(() => result.current.selectStation("favorites"));

  await act(async () => {
    favoritesResponse.resolve(response(tunePayload("favorites", "winner")));
    await favoritesResponse.promise;
  });
  await waitFor(() => {
    expect(result.current.snapshot.track.id).toBe("winner");
  });

  await act(async () => {
    recentResponse.resolve(response(tunePayload("recent", "stale")));
    await recentResponse.promise;
  });
  expect(result.current.snapshot.station.id).toBe("favorites");
  expect(result.current.snapshot.track.id).toBe("winner");
  expect(mockPlayer.load).not.toHaveBeenCalledWith(
    expect.objectContaining({ id: "stale" }),
    expect.any(Boolean),
  );
});

test("routes an unauthorized response to the profile owner", async () => {
  let rejectRecent = false;
  installFetch(async (url) => {
    if (url.includes("/stations")) {
      return response(stationsPayload());
    }
    if (url.includes("station=recent") && rejectRecent) {
      return response(
        {
          success: false,
          error: { code: "unauthorized", message: "Pair again" },
        },
        401,
      );
    }
    return response(tunePayload("default"));
  });
  const onUnauthorized = jest.fn();
  const { result } = await renderHook(() =>
    useRadioSession(profile, onUnauthorized),
  );
  await waitFor(() => {
    expect(result.current.snapshot.sync.kind).toBe("ready");
  });

  rejectRecent = true;
  await act(() => result.current.selectStation("recent"));

  await waitFor(() => {
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });
  expect(result.current.snapshot.sync.kind).toBe("loading");
});

test("keeps the current track when changing station goes offline", async () => {
  let failRecent = false;
  installFetch(async (url) => {
    if (url.includes("/stations")) {
      return response(stationsPayload());
    }
    if (url.includes("station=recent") && failRecent) {
      throw new TypeError("network down");
    }
    return response(tunePayload("default", "still-playing"));
  });
  const onUnauthorized = jest.fn();
  const { result } = await renderHook(() =>
    useRadioSession(profile, onUnauthorized),
  );
  await waitFor(() => {
    expect(result.current.snapshot.track.id).toBe("still-playing");
  });

  failRecent = true;
  await act(() => result.current.selectStation("recent"));

  await waitFor(() => {
    expect(result.current.snapshot.sync.kind).toBe("offline");
  });
  expect(result.current.snapshot.track.id).toBe("still-playing");
  expect(result.current.snapshot.station.id).toBe("default");
});

test("reconnects an offline session without replacing its current queue", async () => {
  let failStationChange = false;
  const fetchMock = installFetch(async (url) => {
    if (url.includes("/stations")) {
      return response(stationsPayload());
    }
    if (url.includes("station=recent") && failStationChange) {
      throw new TypeError("network down");
    }
    return response(tunePayload("default", "keep-this-track"));
  });
  const onUnauthorized = jest.fn();
  const { result } = await renderHook(() =>
    useRadioSession(profile, onUnauthorized),
  );
  await waitFor(() => {
    expect(result.current.snapshot.track.id).toBe("keep-this-track");
  });
  const loadCount = mockPlayer.load.mock.calls.length;

  failStationChange = true;
  await act(() => result.current.selectStation("recent"));
  await waitFor(() => {
    expect(result.current.snapshot.sync.kind).toBe("offline");
  });

  failStationChange = false;
  await act(() => result.current.retry());
  await waitFor(() => {
    expect(result.current.snapshot.sync.kind).toBe("ready");
  });

  expect(result.current.snapshot.track.id).toBe("keep-this-track");
  expect(result.current.snapshot.station.id).toBe("default");
  expect(mockPlayer.load).toHaveBeenCalledTimes(loadCount);
  expect(
    fetchMock.mock.calls.filter(([url]) =>
      String(url).includes("/api/v1/radio/tune"),
    ),
  ).toHaveLength(2);
});

test("clears the player and blocks controls for an empty library", async () => {
  installFetch(async (url) => {
    if (url.includes("/stations")) {
      return response(stationsPayload());
    }
    if (url.includes("/tune")) {
      return response({
        success: true,
        data: { station: station("default"), items: [] },
      });
    }
    return response({ success: true, data: {} });
  });
  const onUnauthorized = jest.fn();
  const { result } = await renderHook(() =>
    useRadioSession(profile, onUnauthorized),
  );
  await waitFor(() => {
    expect(result.current.snapshot.sync.kind).toBe("empty");
  });
  expect(result.current.snapshot.track.id).toBe("empty-library");
  expect(mockPlayer.clear).toHaveBeenCalledTimes(1);
  const loadCalls = mockPlayer.load.mock.calls.length;

  await act(() => {
    result.current.play();
    result.current.next();
    result.current.toggleFavorite();
    result.current.encore();
    result.current.setSleepTimer(30);
  });

  expect(mockPlayer.play).not.toHaveBeenCalled();
  expect(mockPlayer.load).toHaveBeenCalledTimes(loadCalls);
  expect(result.current.snapshot.encoreCount).toBe(0);
  expect(result.current.snapshot.sleepMinutes).toBe(0);
});

test("pauses and clears the sleep timer when it expires", async () => {
  jest.useFakeTimers();
  installFetch(async () => response({ success: true, data: {} }));
  const onUnauthorized = jest.fn();
  const { result, unmount } = await renderHook(() =>
    useRadioSession(null, onUnauthorized),
  );

  await act(() => result.current.setSleepTimer(30));
  expect(result.current.snapshot.sleepMinutes).toBe(30);

  await act(() => {
    jest.advanceTimersByTime(30 * 60 * 1000);
  });
  expect(mockPlayer.pause).toHaveBeenCalledTimes(1);
  expect(result.current.snapshot.sleepMinutes).toBe(0);

  await unmount();
  jest.useRealTimers();
});
