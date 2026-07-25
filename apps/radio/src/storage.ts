import * as SecureStore from "expo-secure-store";

import type {
  KnownServer,
  ServerProfile,
  StoredConnection,
} from "./model";

const CONNECTION_KEY = "tiklocal.radio.connection.v2";
const LEGACY_PROFILE_KEY = "tiklocal.radio.server-profile.v1";

export async function loadStoredConnection(): Promise<StoredConnection | null> {
  const stored = await SecureStore.getItemAsync(CONNECTION_KEY);
  if (stored) {
    const connection = parseConnection(stored);
    if (connection) {
      return connection;
    }
    await SecureStore.deleteItemAsync(CONNECTION_KEY);
    return null;
  }

  const legacy = await SecureStore.getItemAsync(LEGACY_PROFILE_KEY);
  if (!legacy) {
    return null;
  }
  const profile = parseProfile(legacy);
  if (!profile) {
    await SecureStore.deleteItemAsync(LEGACY_PROFILE_KEY);
    return null;
  }
  const connection: StoredConnection = { kind: "paired", profile };
  await SecureStore.setItemAsync(CONNECTION_KEY, JSON.stringify(connection));
  await SecureStore.deleteItemAsync(LEGACY_PROFILE_KEY);
  return connection;
}

export async function saveServerProfile(profile: ServerProfile): Promise<void> {
  const connection: StoredConnection = { kind: "paired", profile };
  await SecureStore.setItemAsync(CONNECTION_KEY, JSON.stringify(connection));
}

export async function saveKnownServer(server: KnownServer): Promise<void> {
  const connection: StoredConnection = { kind: "known", server };
  await SecureStore.setItemAsync(CONNECTION_KEY, JSON.stringify(connection));
}

export async function clearStoredConnection(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(CONNECTION_KEY),
    SecureStore.deleteItemAsync(LEGACY_PROFILE_KEY),
  ]);
}

function parseConnection(stored: string): StoredConnection | null {
  try {
    const value = JSON.parse(stored) as Partial<StoredConnection>;
    if (value.kind === "paired") {
      const profile = parseProfileValue(value.profile);
      return profile ? { kind: "paired", profile } : null;
    }
    if (value.kind === "known") {
      const server = parseKnownServer(value.server);
      return server ? { kind: "known", server } : null;
    }
  } catch {
    // Invalid data is removed by the caller.
  }
  return null;
}

function parseProfile(stored: string): ServerProfile | null {
  if (!stored) {
    return null;
  }
  try {
    return parseProfileValue(
      JSON.parse(stored) as Partial<ServerProfile>,
    );
  } catch {
    return null;
  }
}

function parseProfileValue(value: unknown): ServerProfile | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const profile = value as Partial<ServerProfile>;
  if (
    typeof profile.baseUrl === "string"
    && typeof profile.serverName === "string"
    && typeof profile.deviceId === "string"
    && typeof profile.token === "string"
  ) {
    return profile as ServerProfile;
  }
  return null;
}

function parseKnownServer(value: unknown): KnownServer | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const server = value as Partial<KnownServer>;
  if (
    typeof server.baseUrl === "string"
    && (
      server.serverName === undefined
      || typeof server.serverName === "string"
    )
  ) {
    return server as KnownServer;
  }
  return null;
}
