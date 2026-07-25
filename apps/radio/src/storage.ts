import * as SecureStore from "expo-secure-store";

import type { ServerProfile } from "./model";

const PROFILE_KEY = "tiklocal.radio.server-profile.v1";

export async function loadServerProfile(): Promise<ServerProfile | null> {
  const stored = await SecureStore.getItemAsync(PROFILE_KEY);
  if (!stored) {
    return null;
  }
  try {
    const profile = JSON.parse(stored) as Partial<ServerProfile>;
    if (
      typeof profile.baseUrl === "string" &&
      typeof profile.serverName === "string" &&
      typeof profile.deviceId === "string" &&
      typeof profile.token === "string"
    ) {
      return profile as ServerProfile;
    }
  } catch {
    // Invalid data is treated as disconnected and removed below.
  }
  await clearServerProfile();
  return null;
}

export async function saveServerProfile(profile: ServerProfile): Promise<void> {
  await SecureStore.setItemAsync(PROFILE_KEY, JSON.stringify(profile));
}

export async function clearServerProfile(): Promise<void> {
  await SecureStore.deleteItemAsync(PROFILE_KEY);
}
