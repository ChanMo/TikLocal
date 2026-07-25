import { beforeEach, expect, jest, test } from "@jest/globals";

import {
  claimPairingGrant,
  createRadioApi,
  pairServer,
  parsePairingUri,
  revokeServer,
} from "./api";
import type { ServerProfile, Station } from "./model";

const profile: ServerProfile = {
  baseUrl: "https://radio.test",
  serverName: "Studio",
  deviceId: "device-1",
  token: "secret-token",
};

const stations: Station[] = [
  {
    id: "default",
    name: "Daily Signal",
    description: "A quiet mix",
  },
  {
    id: "recent",
    name: "New Air",
    description: "Recently arrived",
  },
];

function envelope<T>(data: T) {
  return { success: true, data };
}

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
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

function pairPayload(apiVersion = 1) {
  return envelope({
    server: {
      name: "Living Room",
      api_version: apiVersion,
    },
    device: {
      id: "paired-device",
      token: "paired-token",
    },
  });
}

beforeEach(() => {
  jest.useRealTimers();
  jest.clearAllMocks();
});

test("normalizes a local address and pairs without an Authorization header", async () => {
  const fetchMock = installFetch(async () => response(pairPayload(), 201));

  await expect(
    pairServer({
      baseUrl: "  studio.local:8443/// ",
      password: "access-password",
      deviceName: "TikLocal Radio · ios",
    }),
  ).resolves.toEqual({
    baseUrl: "http://studio.local:8443",
    serverName: "Living Room",
    deviceId: "paired-device",
    token: "paired-token",
  });

  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0]!;
  expect(url).toBe("http://studio.local:8443/api/v1/pair");
  expect(init).toEqual(
    expect.objectContaining({
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        password: "access-password",
        device_name: "TikLocal Radio · ios",
      }),
    }),
  );
  expect(init?.signal).toBeInstanceOf(AbortSignal);
});

test.each([
  ["a missing address", "   ", "missing_url"],
  ["an invalid address", "http://[invalid", "invalid_url"],
  ["an address with credentials", "https://me:secret@radio.test", "invalid_url"],
  ["an address with a path", "https://radio.test/private", "invalid_url"],
])("rejects %s before making a request", async (_label, baseUrl, code) => {
  const fetchMock = installFetch(async () => response(pairPayload()));

  await expect(
    pairServer({ baseUrl, password: "", deviceName: "Radio" }),
  ).rejects.toMatchObject({
    code,
    status: 400,
  });
  expect(fetchMock).not.toHaveBeenCalled();
});

test("parses and claims a single-use pairing link", async () => {
  const grant = `tlpg_${"a".repeat(43)}`;
  const pairingUri = `tiklocal-radio://pair?server=${encodeURIComponent(
    "https://studio.local:8443",
  )}&grant=${grant}&v=1`;
  const fetchMock = installFetch(async () => response(pairPayload(), 201));

  expect(parsePairingUri(pairingUri)).toEqual({
    baseUrl: "https://studio.local:8443",
    grant,
  });
  await expect(claimPairingGrant({
    pairingUri,
    deviceName: "TikLocal Radio · ios",
  })).resolves.toEqual({
    baseUrl: "https://studio.local:8443",
    serverName: "Living Room",
    deviceId: "paired-device",
    token: "paired-token",
  });

  const [url, init] = fetchMock.mock.calls[0]!;
  expect(url).toBe("https://studio.local:8443/api/v1/pair/claim");
  expect(init).toEqual(expect.objectContaining({
    method: "POST",
    body: JSON.stringify({
      grant,
      device_name: "TikLocal Radio · ios",
    }),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  }));
});

test.each([
  ["empty", ""],
  ["wrong scheme", `https://pair?server=https://radio.test&grant=tlpg_${"a".repeat(43)}&v=1`],
  ["wrong route", `tiklocal-radio://connect?server=https://radio.test&grant=tlpg_${"a".repeat(43)}&v=1`],
  ["wrong version", `tiklocal-radio://pair?server=https://radio.test&grant=tlpg_${"a".repeat(43)}&v=2`],
  ["bad grant", "tiklocal-radio://pair?server=https://radio.test&grant=secret&v=1"],
  ["duplicate server", `tiklocal-radio://pair?server=https://one.test&server=https://two.test&grant=tlpg_${"a".repeat(43)}&v=1`],
  ["server credentials", `tiklocal-radio://pair?server=${encodeURIComponent("https://me:secret@radio.test")}&grant=tlpg_${"a".repeat(43)}&v=1`],
])("rejects a %s pairing link", (_label, pairingUri) => {
  expect(() => parsePairingUri(pairingUri)).toThrow(
    expect.objectContaining({ code: "invalid_pairing_link" }),
  );
});

test("rejects a Server with an unsupported API version", async () => {
  installFetch(async () => response(pairPayload(2), 201));

  await expect(
    pairServer({
      baseUrl: "https://radio.test",
      password: "access-password",
      deviceName: "Radio",
    }),
  ).rejects.toMatchObject({
    code: "unsupported_api",
    status: 400,
    message: "This TikLocal Server uses an unsupported API version.",
  });
});

test("revokes the current device with its Bearer token", async () => {
  const fetchMock = installFetch(async () =>
    response(envelope({ revoked: true })),
  );

  await revokeServer(profile);

  const [url, init] = fetchMock.mock.calls[0]!;
  expect(url).toBe("https://radio.test/api/v1/device");
  expect(init).toEqual(
    expect.objectContaining({
      method: "DELETE",
      headers: expect.objectContaining({
        Authorization: "Bearer secret-token",
      }),
    }),
  );
});

test("loads stations and maps a protected tune response", async () => {
  const fetchMock = installFetch(async (url) => {
    if (url.endsWith("/stations")) {
      return response(envelope({ stations }));
    }
    return response(
      envelope({
        station: stations[1],
        items: [
          {
            id: "track-1",
            uri: "@music/one & two.mp3",
            title: "One & Two",
            artist: "",
            album: "",
            is_favorite: true,
            media_path:
              "/api/v1/radio/media?uri=%40music%2Fone%20%26%20two.mp3",
          },
        ],
      }),
    );
  });
  const api = createRadioApi(profile);

  await expect(api.stations()).resolves.toEqual(stations);
  const tuned = await api.tune("recent", [
    "@music/old one.mp3",
    "@music/old,two.mp3",
  ]);

  expect(tuned.station.id).toBe("recent");
  expect(tuned.tracks).toEqual([
    expect.objectContaining({
      id: "track-1",
      uri: "@music/one & two.mp3",
      title: "One & Two",
      artist: "Unknown artist",
      album: "Studio",
      isFavorite: true,
      source: {
        uri:
          "https://radio.test/api/v1/radio/media?uri=%40music%2Fone%20%26%20two.mp3",
        headers: { Authorization: "Bearer secret-token" },
      },
    }),
  ]);

  const tuneUrl = new URL(String(fetchMock.mock.calls[1]![0]));
  expect(tuneUrl.pathname).toBe("/api/v1/radio/tune");
  expect(tuneUrl.searchParams.get("station")).toBe("recent");
  expect(tuneUrl.searchParams.get("limit")).toBe("12");
  expect(tuneUrl.searchParams.get("exclude")).toBe(
    "@music/old one.mp3,@music/old,two.mp3",
  );
  for (const [, init] of fetchMock.mock.calls) {
    expect(init?.headers).toEqual(
      expect.objectContaining({
        Authorization: "Bearer secret-token",
      }),
    );
  }
});

test("does not attach an empty token to an unauthenticated media source", async () => {
  const publicProfile = { ...profile, deviceId: "", token: "" };
  installFetch(async () =>
    response(
      envelope({
        station: stations[0],
        items: [
          {
            id: "public-track",
            uri: "@music/public.mp3",
            title: "Public",
            artist: "Artist",
            album: "Album",
            is_favorite: false,
            media_path: "/api/v1/radio/media?uri=public",
          },
        ],
      }),
    ),
  );

  const tuned = await createRadioApi(publicProfile).tune("default");

  expect(tuned.tracks[0]!.source).toEqual({
    uri: "https://radio.test/api/v1/radio/media?uri=public",
    headers: undefined,
  });
});

test("sends idempotent favorite state and listening feedback", async () => {
  const fetchMock = installFetch(async (url) =>
    url.endsWith("/favorite")
      ? response(envelope({ is_favorite: true }))
      : response(envelope({ profile: {} })),
  );
  const api = createRadioApi(profile);

  await expect(api.setFavorite("@music/song.mp3", true)).resolves.toBe(true);
  await api.feedback("@music/song.mp3", "skip", 0.25);

  expect(fetchMock.mock.calls[0]![1]).toEqual(
    expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({
        uri: "@music/song.mp3",
        favorite: true,
      }),
    }),
  );
  expect(fetchMock.mock.calls[1]![1]).toEqual(
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        uri: "@music/song.mp3",
        event: "skip",
        ratio: 0.25,
      }),
    }),
  );
});

test("preserves a structured Server error", async () => {
  installFetch(async () =>
    response(
      {
        success: false,
        error: {
          code: "authentication_required",
          message: "Pair this device again",
        },
      },
      401,
    ),
  );

  await expect(createRadioApi(profile).stations()).rejects.toMatchObject({
    code: "authentication_required",
    status: 401,
    message: "Pair this device again",
  });
});

test("uses string and HTTP fallbacks for malformed error responses", async () => {
  const payloads: Array<Response> = [
    response({ success: false, error: "Library unavailable" }, 503),
    {
      ok: false,
      status: 502,
      json: async () => {
        throw new SyntaxError("not JSON");
      },
    } as unknown as Response,
  ];
  installFetch(async () => payloads.shift()!);
  const api = createRadioApi(profile);

  await expect(api.stations()).rejects.toMatchObject({
    code: "request_failed",
    status: 503,
    message: "Library unavailable",
  });
  await expect(api.stations()).rejects.toMatchObject({
    code: "request_failed",
    status: 502,
    message: "TikLocal Server returned 502",
  });
});

test("converts a fetch failure into a stable network error", async () => {
  installFetch(async () => {
    throw new TypeError("socket closed");
  });

  await expect(createRadioApi(profile).stations()).rejects.toEqual(
    expect.objectContaining({
      code: "network_error",
      status: 0,
      message: "Could not reach TikLocal Server.",
    }),
  );
});

test("aborts a request after twelve seconds and clears the timer", async () => {
  jest.useFakeTimers();
  installFetch(
    async (_url, init) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          const error = new Error("aborted");
          error.name = "AbortError";
          reject(error);
        });
      }),
  );

  const request = createRadioApi(profile).stations();
  jest.advanceTimersByTime(12_000);

  await expect(request).rejects.toMatchObject({
    code: "network_error",
    status: 0,
    message: "TikLocal Server took too long to respond.",
  });
  expect(jest.getTimerCount()).toBe(0);
  jest.useRealTimers();
});
