import { beforeEach, expect, jest, test } from "@jest/globals";
import * as SecureStore from "expo-secure-store";

import type {
  KnownServer,
  ServerProfile,
  StoredConnection,
} from "./model";
import {
  clearStoredConnection,
  loadStoredConnection,
  saveKnownServer,
  saveServerProfile,
} from "./storage";

jest.mock("expo-secure-store", () => ({
  deleteItemAsync: jest.fn(),
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
}));

const CONNECTION_KEY = "tiklocal.radio.connection.v2";
const LEGACY_PROFILE_KEY = "tiklocal.radio.server-profile.v1";
const profile: ServerProfile = {
  baseUrl: "https://radio.test",
  serverName: "Studio",
  deviceId: "device-1",
  token: "secret-token",
};
const knownServer: KnownServer = {
  baseUrl: "https://radio.test",
  serverName: "Studio",
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

test.each<StoredConnection>([
  { kind: "paired", profile },
  { kind: "known", server: knownServer },
])("restores a valid $kind connection", async (connection) => {
  getItem.mockResolvedValueOnce(JSON.stringify(connection));

  await expect(loadStoredConnection()).resolves.toEqual(connection);

  expect(getItem).toHaveBeenCalledWith(CONNECTION_KEY);
  expect(deleteItem).not.toHaveBeenCalled();
});

test("returns null when no connection has been stored", async () => {
  await expect(loadStoredConnection()).resolves.toBeNull();

  expect(getItem).toHaveBeenNthCalledWith(1, CONNECTION_KEY);
  expect(getItem).toHaveBeenNthCalledWith(2, LEGACY_PROFILE_KEY);
  expect(deleteItem).not.toHaveBeenCalled();
});

test.each([
  ["invalid JSON", "{not-json"],
  [
    "an incomplete paired connection",
    JSON.stringify({
      kind: "paired",
      profile: {
        baseUrl: profile.baseUrl,
        serverName: profile.serverName,
      },
    }),
  ],
])("removes %s instead of restoring it", async (_label, stored) => {
  getItem.mockResolvedValueOnce(stored);

  await expect(loadStoredConnection()).resolves.toBeNull();

  expect(deleteItem).toHaveBeenCalledWith(CONNECTION_KEY);
});

test("migrates a legacy profile into the paired connection record", async () => {
  getItem
    .mockResolvedValueOnce(null)
    .mockResolvedValueOnce(JSON.stringify(profile));

  await expect(loadStoredConnection()).resolves.toEqual({
    kind: "paired",
    profile,
  });

  expect(setItem).toHaveBeenCalledWith(
    CONNECTION_KEY,
    JSON.stringify({ kind: "paired", profile }),
  );
  expect(deleteItem).toHaveBeenCalledWith(LEGACY_PROFILE_KEY);
});

test("stores paired and remembered Server states without saving a password", async () => {
  await saveServerProfile(profile);
  await saveKnownServer(knownServer);

  expect(setItem).toHaveBeenNthCalledWith(
    1,
    CONNECTION_KEY,
    JSON.stringify({ kind: "paired", profile }),
  );
  expect(setItem).toHaveBeenNthCalledWith(
    2,
    CONNECTION_KEY,
    JSON.stringify({ kind: "known", server: knownServer }),
  );
});

test("clears current and legacy connection records", async () => {
  await clearStoredConnection();

  expect(deleteItem).toHaveBeenCalledWith(CONNECTION_KEY);
  expect(deleteItem).toHaveBeenCalledWith(LEGACY_PROFILE_KEY);
});
