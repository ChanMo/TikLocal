import type { ServerProfile, Station, StationId, Track } from "./model";

type PairResponse = {
  server: {
    name: string;
    api_version: number;
  };
  device: {
    id: string;
    token: string;
  };
};

type TuneResponse = {
  station: Station;
  items: Array<{
    id: string;
    uri: string;
    title: string;
    artist: string;
    album: string;
    is_favorite: boolean;
    media_path: string;
  }>;
};

type ApiEnvelope<T> = {
  success: boolean;
  data?: T;
  error?: string | { code?: string; message?: string };
};

export class TikLocalApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function pairServer(input: {
  baseUrl: string;
  password: string;
  deviceName: string;
}): Promise<ServerProfile> {
  const baseUrl = normalizeServerUrl(input.baseUrl);
  const data = await request<PairResponse>(baseUrl, "/api/v1/pair", "", {
    method: "POST",
    body: JSON.stringify({
      password: input.password,
      device_name: input.deviceName,
    }),
  });
  return profileFromPairResponse(baseUrl, data);
}

export function parsePairingUri(value: string): {
  baseUrl: string;
  grant: string;
} {
  const candidate = value.trim();
  if (!candidate || candidate.length > 1200) {
    throw new TikLocalApiError(
      "Paste a valid TikLocal Server pairing link.",
      "invalid_pairing_link",
      400,
    );
  }
  let url: URL;
  try {
    url = new URL(candidate);
  } catch {
    throw new TikLocalApiError(
      "Paste a valid TikLocal Server pairing link.",
      "invalid_pairing_link",
      400,
    );
  }
  const serverValues = url.searchParams.getAll("server");
  const grantValues = url.searchParams.getAll("grant");
  const versionValues = url.searchParams.getAll("v");
  const grant = grantValues[0] || "";
  if (
    url.protocol !== "tiklocal-radio:"
    || url.hostname !== "pair"
    || (url.pathname !== "" && url.pathname !== "/")
    || serverValues.length !== 1
    || grantValues.length !== 1
    || versionValues.length !== 1
    || versionValues[0] !== "1"
    || !/^tlpg_[A-Za-z0-9_-]{43}$/.test(grant)
  ) {
    throw new TikLocalApiError(
      "This is not a supported TikLocal Server pairing link.",
      "invalid_pairing_link",
      400,
    );
  }
  try {
    return {
      baseUrl: normalizeServerUrl(serverValues[0]!),
      grant,
    };
  } catch {
    throw new TikLocalApiError(
      "This pairing link contains an invalid Server address.",
      "invalid_pairing_link",
      400,
    );
  }
}

export async function claimPairingGrant(input: {
  pairingUri: string;
  deviceName: string;
}): Promise<ServerProfile> {
  const { baseUrl, grant } = parsePairingUri(input.pairingUri);
  const data = await request<PairResponse>(
    baseUrl,
    "/api/v1/pair/claim",
    "",
    {
      method: "POST",
      body: JSON.stringify({
        grant,
        device_name: input.deviceName,
      }),
    },
  );
  return profileFromPairResponse(baseUrl, data);
}

function profileFromPairResponse(
  baseUrl: string,
  data: PairResponse,
): ServerProfile {
  if (data.server.api_version !== 1) {
    throw new TikLocalApiError(
      "This TikLocal Server uses an unsupported API version.",
      "unsupported_api",
      400,
    );
  }
  return {
    baseUrl,
    serverName: data.server.name,
    deviceId: data.device.id,
    token: data.device.token,
  };
}

export async function revokeServer(profile: ServerProfile): Promise<void> {
  await request(
    profile.baseUrl,
    "/api/v1/device",
    profile.token,
    { method: "DELETE" },
  );
}

export function createRadioApi(profile: ServerProfile) {
  const sourceHeaders = profile.token
    ? { Authorization: `Bearer ${profile.token}` }
    : undefined;

  return {
    async stations(): Promise<Station[]> {
      const data = await request<{ stations: Station[] }>(
        profile.baseUrl,
        "/api/v1/radio/stations",
        profile.token,
      );
      return data.stations;
    },

    async tune(
      station: StationId,
      exclude: string[] = [],
    ): Promise<{ station: Station; tracks: Track[] }> {
      const query = new URLSearchParams({
        station,
        limit: "12",
      });
      if (exclude.length) {
        query.set("exclude", exclude.join(","));
      }
      const data = await request<TuneResponse>(
        profile.baseUrl,
        `/api/v1/radio/tune?${query.toString()}`,
        profile.token,
      );
      return {
        station: data.station,
        tracks: data.items.map((item) => ({
          id: item.id,
          uri: item.uri,
          title: item.title,
          artist: item.artist || "Unknown artist",
          album: item.album || profile.serverName,
          source: {
            uri: absoluteUrl(profile.baseUrl, item.media_path),
            headers: sourceHeaders,
          },
          isFavorite: item.is_favorite,
          accent: accentFor(item.uri),
        })),
      };
    },

    async setFavorite(uri: string, favorite: boolean): Promise<boolean> {
      const data = await request<{ is_favorite: boolean }>(
        profile.baseUrl,
        "/api/v1/radio/favorite",
        profile.token,
        {
          method: "PUT",
          body: JSON.stringify({ uri, favorite }),
        },
      );
      return data.is_favorite;
    },

    async feedback(
      uri: string,
      event: "play" | "complete" | "replay" | "skip" | "favorite" | "error",
      ratio?: number,
    ): Promise<void> {
      await request(
        profile.baseUrl,
        "/api/v1/radio/feedback",
        profile.token,
        {
          method: "POST",
          body: JSON.stringify({ uri, event, ratio }),
        },
      );
    },
  };
}

async function request<T>(
  baseUrl: string,
  path: string,
  token: string,
  init: RequestInit = {},
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12_000);
  try {
    const response = await fetch(absoluteUrl(baseUrl, path), {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    });
    const payload = (await response.json().catch(() => null)) as ApiEnvelope<T> | null;
    if (!response.ok || !payload?.success || payload.data === undefined) {
      const structuredError =
        payload?.error && typeof payload.error === "object" ? payload.error : null;
      const message =
        structuredError?.message ||
        (typeof payload?.error === "string" ? payload.error : "") ||
        `TikLocal Server returned ${response.status}`;
      throw new TikLocalApiError(
        message,
        structuredError?.code || "request_failed",
        response.status,
      );
    }
    return payload.data;
  } catch (error) {
    if (error instanceof TikLocalApiError) {
      throw error;
    }
    const message =
      error instanceof Error && error.name === "AbortError"
        ? "TikLocal Server took too long to respond."
        : "Could not reach TikLocal Server.";
    throw new TikLocalApiError(message, "network_error", 0);
  } finally {
    clearTimeout(timeout);
  }
}

export function normalizeServerUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (!trimmed) {
    throw new TikLocalApiError(
      "Enter the address shown by TikLocal Server.",
      "missing_url",
      400,
    );
  }
  const candidate = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`;
  try {
    const url = new URL(candidate);
    if (
      !["http:", "https:"].includes(url.protocol)
      || !url.hostname
      || url.username
      || url.password
      || url.search
      || url.hash
      || (url.pathname !== "" && url.pathname !== "/")
    ) {
      throw new Error("unsupported server URL");
    }
    return url.origin;
  } catch {
    throw new TikLocalApiError(
      "Enter a valid TikLocal Server address.",
      "invalid_url",
      400,
    );
  }
}

function absoluteUrl(baseUrl: string, path: string): string {
  return new URL(path, `${baseUrl}/`).toString();
}

function accentFor(value: string): string {
  const palette = ["#D9633B", "#476F5B", "#B78D42", "#57707A", "#675F82"];
  const index = [...value].reduce((total, char) => total + char.charCodeAt(0), 0);
  return palette[index % palette.length]!;
}
