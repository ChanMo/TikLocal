import { beforeEach, expect, jest, test } from "@jest/globals";
import * as SecureStore from "expo-secure-store";

import type { ServerProfile } from "./model";
import {
  clearServerProfile,
  loadServerProfile,
  saveServerProfile,
} from "./storage";

jest.mock("expo-secure-store", () => ({
  deleteItemAsync: jest.fn(),
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
}));

const PROFILE_KEY = "tiklocal.radio.server-profile.v1";
const profile: ServerProfile = {
  baseUrl: "https://radio.test",
  serverName: "Studio",
  deviceId: "device-1",
  token: "secret-token",
};
const getItem = jest.mocked(SecureStore.getItemAsync);
const setItem = jest.mocked(SecureStore.setItemAsync);
const deleteItem = jest.mocked(SecureStore.deleteItemAsync);

beforeEach(() => {
  jest.clearAllMocks();
  getItem.mockResolvedValue(null);
  setItem.mockResolvedValue();
  deleteItem.mockResolvedValue();
});

test("returns a complete stored profile without rewriting it", async () => {
  getItem.mockResolvedValue(JSON.stringify(profile));

  await expect(loadServerProfile()).resolves.toEqual(profile);

  expect(getItem).toHaveBeenCalledWith(PROFILE_KEY);
  expect(deleteItem).not.toHaveBeenCalled();
});

test("returns null when no profile has been stored", async () => {
  await expect(loadServerProfile()).resolves.toBeNull();

  expect(deleteItem).not.toHaveBeenCalled();
});

test.each([
  ["invalid JSON", "{not-json"],
  [
    "an incomplete profile",
    JSON.stringify({
      baseUrl: profile.baseUrl,
      serverName: profile.serverName,
      deviceId: profile.deviceId,
    }),
  ],
])("removes %s instead of restoring it", async (_label, stored) => {
  getItem.mockResolvedValue(stored);

  await expect(loadServerProfile()).resolves.toBeNull();

  expect(deleteItem).toHaveBeenCalledWith(PROFILE_KEY);
});

test("uses one JSON entry for save and clear", async () => {
  await saveServerProfile(profile);
  await clearServerProfile();

  expect(setItem).toHaveBeenCalledWith(PROFILE_KEY, JSON.stringify(profile));
  expect(deleteItem).toHaveBeenCalledWith(PROFILE_KEY);
});
