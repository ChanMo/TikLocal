import { beforeEach, expect, jest, test } from "@jest/globals";
import {
  act,
  render,
  screen,
  userEvent,
  waitFor,
} from "@testing-library/react-native";
import {
  AppState,
  type AppStateStatus,
  Linking,
} from "react-native";

import type {
  ServerProfile,
  StoredConnection,
} from "./src/model";
import App from "./App";

jest.mock(
  "react-native-safe-area-context",
  () => require("react-native-safe-area-context/jest/mock").default,
);

type PairingProps = {
  initialPairingUri?: string;
  initialServerName?: string;
  initialUrl?: string;
  onConnect(input: { baseUrl: string; password: string }): Promise<void>;
  onClaim(input: { pairingUri: string }): Promise<void>;
  onUseDemo?(): void;
};

type RadioProps = {
  onConnectionPress(): void;
};

type ConnectionProps = {
  connection: StoredConnection | null;
  onChangeServer(): void;
  onDisconnect(): void;
  onReconnect(): void;
  onRetry(): void;
};

const mockPairServer = jest.fn<
  (input: {
    baseUrl: string;
    password: string;
    deviceName: string;
  }) => Promise<ServerProfile>
>();
const mockClaimPairingGrant = jest.fn<
  (input: {
    pairingUri: string;
    deviceName: string;
  }) => Promise<ServerProfile>
>();
const mockRevokeServer = jest.fn<
  (profile: ServerProfile) => Promise<void>
>();
const mockClearStoredConnection = jest.fn<() => Promise<void>>();
const mockLoadStoredConnection = jest.fn<
  () => Promise<StoredConnection | null>
>();
const mockSaveKnownServer = jest.fn<
  (server: { baseUrl: string; serverName?: string }) => Promise<void>
>();
const mockSaveServerProfile = jest.fn<
  (profile: ServerProfile) => Promise<void>
>();
const mockClearRadioResume = jest.fn();
const mockRetry = jest.fn();
const mockUseRadioSession = jest.fn<
  (
    profile: ServerProfile | null,
    onUnauthorized: () => void,
  ) => unknown
>();
let mockPairingProps: PairingProps | null = null;
let mockRadioProps: RadioProps | null = null;
let mockConnectionProps: ConnectionProps | null = null;
let mockUnauthorized: (() => void) | null = null;
let mockUrlListeners: Array<(event: { url: string }) => void> = [];
let mockVisibleScreen: "boot" | "pairing" | "radio" | "connection" = "boot";
const mockRemoveUrlListener = jest.fn();
const mockGetInitialURL = jest.spyOn(Linking, "getInitialURL");
const mockAddUrlListener = jest.spyOn(Linking, "addEventListener");

jest.mock("./src/api", () => ({
  claimPairingGrant: (input: {
    pairingUri: string;
    deviceName: string;
  }) => mockClaimPairingGrant(input),
  normalizeServerUrl: (value: string) =>
    jest.requireActual<typeof import("./src/api")>("./src/api")
      .normalizeServerUrl(value),
  pairServer: (input: {
    baseUrl: string;
    password: string;
    deviceName: string;
  }) => mockPairServer(input),
  parsePairingUri: (value: string) =>
    jest.requireActual<typeof import("./src/api")>("./src/api")
      .parsePairingUri(value),
  revokeServer: (profile: ServerProfile) => mockRevokeServer(profile),
}));

jest.mock("./src/storage", () => ({
  clearStoredConnection: () => mockClearStoredConnection(),
  loadStoredConnection: () => mockLoadStoredConnection(),
  saveKnownServer: (server: { baseUrl: string; serverName?: string }) =>
    mockSaveKnownServer(server),
  saveServerProfile: (profile: ServerProfile) =>
    mockSaveServerProfile(profile),
}));

jest.mock("./src/radio", () => ({
  useRadioSession: (
    profile: ServerProfile | null,
    onUnauthorized: () => void,
  ) => mockUseRadioSession(profile, onUnauthorized),
}));

jest.mock("./src/radioResume", () => ({
  clearRadioResume: () => mockClearRadioResume(),
}));

jest.mock("./src/PairingScreen", () => ({
  PairingScreen: (props: PairingProps) => {
    mockPairingProps = props;
    mockVisibleScreen = "pairing";
    return null;
  },
}));

jest.mock("./src/RadioScreen", () => ({
  RadioScreen: (props: RadioProps) => {
    mockRadioProps = props;
    mockVisibleScreen = "radio";
    return null;
  },
}));

jest.mock("./src/ConnectionScreen", () => ({
  ConnectionScreen: (props: ConnectionProps) => {
    mockConnectionProps = props;
    mockVisibleScreen = "connection";
    return null;
  },
}));

const oldProfile: ServerProfile = {
  baseUrl: "https://old-radio.test",
  serverName: "Old Studio",
  deviceId: "old-device",
  token: "old-token",
};

const newProfile: ServerProfile = {
  baseUrl: "https://new-radio.test",
  serverName: "New Studio",
  deviceId: "new-device",
  token: "new-token",
};
const oldConnection: StoredConnection = {
  kind: "paired",
  profile: oldProfile,
};
const pairingUri = `tiklocal-radio://pair?server=${encodeURIComponent(
  "https://new-radio.test",
)}&grant=tlpg_${"a".repeat(43)}&v=1`;

beforeEach(() => {
  jest.clearAllMocks();
  mockPairingProps = null;
  mockRadioProps = null;
  mockConnectionProps = null;
  mockUnauthorized = null;
  mockUrlListeners = [];
  mockVisibleScreen = "boot";
  mockGetInitialURL.mockResolvedValue(null);
  mockAddUrlListener.mockImplementation((_type, listener) => {
    mockUrlListeners.push(listener);
    return {
      remove: mockRemoveUrlListener,
    } as unknown as ReturnType<typeof Linking.addEventListener>;
  });
  mockClearStoredConnection.mockResolvedValue(undefined);
  mockLoadStoredConnection.mockResolvedValue(null);
  mockSaveKnownServer.mockResolvedValue(undefined);
  mockSaveServerProfile.mockResolvedValue(undefined);
  mockPairServer.mockResolvedValue(newProfile);
  mockClaimPairingGrant.mockResolvedValue(newProfile);
  mockRevokeServer.mockResolvedValue(undefined);
  mockClearRadioResume.mockReturnValue(undefined);
  mockUseRadioSession.mockImplementation(
    (profile: ServerProfile | null, onUnauthorized: () => void) => {
      mockUnauthorized = onUnauthorized;
      return {
        snapshot: {
          sync: profile
            ? { kind: "ready", serverName: profile.serverName }
            : { kind: "demo" },
        },
        retry: mockRetry,
      };
    },
  );
});

test("opens an initial pairing deep link while preserving the current Server", async () => {
  const user = userEvent.setup();
  mockLoadStoredConnection.mockResolvedValue(oldConnection);
  mockGetInitialURL.mockResolvedValue(pairingUri);

  await render(<App />);
  await waitFor(() => expect(mockVisibleScreen).toBe("pairing"));

  expect(mockPairingProps!.initialPairingUri).toBe(pairingUri);
  expect(mockPairingProps!.initialServerName).toBe("Old Studio");
  expect(mockPairingProps!.initialUrl).toBe(oldProfile.baseUrl);
  expect(mockClaimPairingGrant).not.toHaveBeenCalled();

  await user.press(
    screen.getByRole("button", { name: "Cancel changing Server" }),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Cancel changing Server" }),
    ).not.toBeOnTheScreen(),
  );
  expect(mockSaveServerProfile).not.toHaveBeenCalled();
  expect(mockRevokeServer).not.toHaveBeenCalled();
});

test("handles a foreground pairing link and ignores unsupported URLs", async () => {
  mockLoadStoredConnection.mockResolvedValue(oldConnection);
  await render(<App />);
  await waitFor(() => expect(mockVisibleScreen).toBe("radio"));

  await act(() => {
    mockUrlListeners.forEach((listener) => listener({ url: pairingUri }));
  });
  await waitFor(() =>
    expect(mockPairingProps?.initialPairingUri).toBe(pairingUri),
  );

  await act(() => mockPairingProps!.onClaim({ pairingUri }));
  await waitFor(() => expect(mockVisibleScreen).toBe("radio"));

  await act(() => {
    mockUrlListeners.forEach((listener) =>
      listener({ url: "https://malicious.test/pair" }),
    );
  });
  expect(mockVisibleScreen).toBe("radio");
});

test("restores a paired Server directly into Radio", async () => {
  mockLoadStoredConnection.mockResolvedValue(oldConnection);

  await render(<App />);

  await waitFor(() => expect(mockVisibleScreen).toBe("radio"));
  expect(mockUseRadioSession).toHaveBeenLastCalledWith(
    oldProfile,
    expect.any(Function),
  );
  expect(mockPairingProps).toBeNull();
});

test("does not retune when the app leaves and returns to active state", async () => {
  const listeners: Array<(state: AppStateStatus) => void> = [];
  const appStateListener = jest
    .spyOn(AppState, "addEventListener")
    .mockImplementation((_type, listener) => {
      listeners.push(listener);
      return { remove: jest.fn() };
    });
  mockLoadStoredConnection.mockResolvedValue(oldConnection);

  await render(<App />);
  await waitFor(() => expect(mockVisibleScreen).toBe("radio"));
  await act(() => {
    listeners.forEach((listener) => listener("inactive"));
    listeners.forEach((listener) => listener("active"));
    listeners.forEach((listener) => listener("background"));
    listeners.forEach((listener) => listener("active"));
  });

  expect(mockRetry).not.toHaveBeenCalled();
  appStateListener.mockRestore();
});

test("restores a known Server into a focused reauthorization flow", async () => {
  mockLoadStoredConnection.mockResolvedValue({
    kind: "known",
    server: {
      baseUrl: oldProfile.baseUrl,
      serverName: oldProfile.serverName,
    },
  });

  await render(<App />);

  await waitFor(() => expect(mockVisibleScreen).toBe("pairing"));
  expect(mockPairingProps!.initialServerName).toBe("Old Studio");
  expect(mockPairingProps!.initialUrl).toBe(oldProfile.baseUrl);
  expect(mockUseRadioSession).toHaveBeenLastCalledWith(
    null,
    expect.any(Function),
  );
});

test("keeps the Server identity when the device key becomes unauthorized", async () => {
  mockLoadStoredConnection.mockResolvedValue(oldConnection);
  await render(<App />);
  await waitFor(() => expect(mockVisibleScreen).toBe("radio"));

  await act(() => mockUnauthorized?.());

  await waitFor(() => expect(mockVisibleScreen).toBe("pairing"));
  expect(mockSaveKnownServer).toHaveBeenCalledWith({
    baseUrl: oldProfile.baseUrl,
    serverName: oldProfile.serverName,
  });
  expect(mockClearStoredConnection).not.toHaveBeenCalled();
  expect(mockPairingProps!.initialUrl).toBe(oldProfile.baseUrl);
  expect(mockUseRadioSession).toHaveBeenLastCalledWith(
    null,
    expect.any(Function),
  );
});

test("remembers a manual address even when secure profile storage later fails", async () => {
  const storageError = new Error("secure storage is full");
  mockSaveServerProfile.mockRejectedValue(storageError);
  await render(<App />);
  await waitFor(() => expect(mockVisibleScreen).toBe("pairing"));

  let caught: unknown;
  await act(async () => {
    try {
      await mockPairingProps!.onConnect({
        baseUrl: "new-radio.test",
        password: "access-password",
      });
    } catch (error) {
      caught = error;
    }
  });

  expect(caught).toBe(storageError);
  expect(mockSaveKnownServer).toHaveBeenCalledWith({
    baseUrl: "http://new-radio.test",
    serverName: undefined,
  });
  expect(mockPairServer).toHaveBeenCalledWith({
    baseUrl: "http://new-radio.test",
    password: "access-password",
    deviceName: expect.stringContaining("TikLocal Radio"),
  });
  expect(mockRevokeServer).toHaveBeenCalledWith(newProfile);
  expect(mockVisibleScreen).toBe("pairing");
});

test("keeps the old connection until a replacement is stored", async () => {
  const user = userEvent.setup();
  mockLoadStoredConnection.mockResolvedValue(oldConnection);
  await render(<App />);
  await waitFor(() => expect(mockVisibleScreen).toBe("radio"));

  await act(() => mockRadioProps!.onConnectionPress());
  await waitFor(() => expect(mockVisibleScreen).toBe("connection"));
  await act(() => mockConnectionProps!.onChangeServer());
  await waitFor(() => expect(mockVisibleScreen).toBe("pairing"));

  await user.press(
    screen.getByRole("button", { name: "Cancel changing Server" }),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("button", { name: "Cancel changing Server" }),
    ).not.toBeOnTheScreen(),
  );
  expect(mockSaveServerProfile).not.toHaveBeenCalled();
  expect(mockRevokeServer).not.toHaveBeenCalled();

  await act(() => mockConnectionProps!.onChangeServer());
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Cancel changing Server" }),
    ).toBeOnTheScreen(),
  );

  await act(() =>
    mockPairingProps!.onConnect({
      baseUrl: "https://new-radio.test",
      password: "access-password",
    }),
  );

  await waitFor(() => expect(mockVisibleScreen).toBe("radio"));
  expect(mockSaveKnownServer).not.toHaveBeenCalled();
  expect(mockSaveServerProfile.mock.invocationCallOrder[0]).toBeLessThan(
    mockRevokeServer.mock.invocationCallOrder[0]!,
  );
  expect(mockRevokeServer).toHaveBeenCalledWith(oldProfile);
});

test("forgets a Server only after the explicit disconnect action", async () => {
  mockLoadStoredConnection.mockResolvedValue(oldConnection);
  await render(<App />);
  await waitFor(() => expect(mockVisibleScreen).toBe("radio"));
  await act(() => mockRadioProps!.onConnectionPress());
  await waitFor(() => expect(mockVisibleScreen).toBe("connection"));

  await act(() => mockConnectionProps!.onDisconnect());

  await waitFor(() => expect(mockVisibleScreen).toBe("pairing"));
  expect(mockRevokeServer).toHaveBeenCalledWith(oldProfile);
  expect(mockClearStoredConnection).toHaveBeenCalledTimes(1);
  expect(mockClearRadioResume).toHaveBeenCalledTimes(1);
  expect(mockUseRadioSession).toHaveBeenLastCalledWith(
    null,
    expect.any(Function),
  );
});

test("enters Demo without creating or clearing a Server record", async () => {
  await render(<App />);
  await waitFor(() => expect(mockVisibleScreen).toBe("pairing"));

  await act(() => mockPairingProps!.onUseDemo?.());

  await waitFor(() => expect(mockVisibleScreen).toBe("radio"));
  expect(mockSaveKnownServer).not.toHaveBeenCalled();
  expect(mockClearStoredConnection).not.toHaveBeenCalled();
});
