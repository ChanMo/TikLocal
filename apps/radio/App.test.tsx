import { beforeEach, expect, jest, test } from "@jest/globals";
import { act, render, waitFor } from "@testing-library/react-native";
import { Linking } from "react-native";

import type { ServerProfile } from "./src/model";
import App from "./App";

jest.mock(
  "react-native-safe-area-context",
  () => require("react-native-safe-area-context/jest/mock").default,
);

type PairingProps = {
  initialPairingUri?: string;
  initialUrl?: string;
  onConnect(input: { baseUrl: string; password: string }): Promise<void>;
  onClaim(input: { pairingUri: string }): Promise<void>;
  onCancel?(): void;
  onUseDemo(): void;
};

type RadioProps = {
  onConnectionPress(): void;
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
const mockClearServerProfile = jest.fn<() => Promise<void>>();
const mockLoadServerProfile = jest.fn<
  () => Promise<ServerProfile | null>
>();
const mockSaveServerProfile = jest.fn<
  (profile: ServerProfile) => Promise<void>
>();
const mockUseRadioSession = jest.fn<
  (
    profile: ServerProfile | null,
    onUnauthorized: () => void,
  ) => unknown
>();
let mockPairingProps: PairingProps | null = null;
let mockRadioProps: RadioProps | null = null;
let mockUnauthorized: (() => void) | null = null;
let mockUrlListener: ((event: { url: string }) => void) | null = null;
let mockVisibleScreen: "boot" | "pairing" | "radio" = "boot";
const mockRemoveUrlListener = jest.fn();
const mockGetInitialURL = jest.spyOn(Linking, "getInitialURL");
const mockAddUrlListener = jest.spyOn(Linking, "addEventListener");

jest.mock("./src/api", () => ({
  claimPairingGrant: (input: {
    pairingUri: string;
    deviceName: string;
  }) => mockClaimPairingGrant(input),
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
  clearServerProfile: () => mockClearServerProfile(),
  loadServerProfile: () => mockLoadServerProfile(),
  saveServerProfile: (profile: ServerProfile) =>
    mockSaveServerProfile(profile),
}));

jest.mock("./src/radio", () => ({
  useRadioSession: (
    profile: ServerProfile | null,
    onUnauthorized: () => void,
  ) => mockUseRadioSession(profile, onUnauthorized),
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
const pairingUri = `tiklocal-radio://pair?server=${encodeURIComponent(
  "https://new-radio.test",
)}&grant=tlpg_${"a".repeat(43)}&v=1`;

beforeEach(() => {
  jest.clearAllMocks();
  mockPairingProps = null;
  mockRadioProps = null;
  mockUnauthorized = null;
  mockUrlListener = null;
  mockVisibleScreen = "boot";
  mockGetInitialURL.mockResolvedValue(null);
  mockAddUrlListener.mockImplementation((_type, listener) => {
    mockUrlListener = listener;
    return {
      remove: mockRemoveUrlListener,
    } as unknown as ReturnType<typeof Linking.addEventListener>;
  });
  mockClearServerProfile.mockResolvedValue(undefined);
  mockLoadServerProfile.mockResolvedValue(null);
  mockSaveServerProfile.mockResolvedValue(undefined);
  mockPairServer.mockResolvedValue(newProfile);
  mockClaimPairingGrant.mockResolvedValue(newProfile);
  mockRevokeServer.mockResolvedValue(undefined);
  mockUseRadioSession.mockImplementation(
    (_profile: ServerProfile | null, onUnauthorized: () => void) => {
      mockUnauthorized = onUnauthorized;
      return {};
    },
  );
});

test("opens an initial pairing deep link for explicit confirmation", async () => {
  mockLoadServerProfile.mockResolvedValue(oldProfile);
  mockGetInitialURL.mockResolvedValue(pairingUri);

  await render(<App />);
  await waitFor(() => {
    expect(mockVisibleScreen).toBe("pairing");
  });

  expect(mockPairingProps!.initialPairingUri).toBe(pairingUri);
  expect(mockPairingProps!.initialUrl).toBe(oldProfile.baseUrl);
  expect(mockClaimPairingGrant).not.toHaveBeenCalled();

  await act(() => mockPairingProps!.onClaim({ pairingUri }));
  await waitFor(() => {
    expect(mockVisibleScreen).toBe("radio");
  });
  expect(mockSaveServerProfile).toHaveBeenCalledWith(newProfile);
  expect(mockRevokeServer).toHaveBeenCalledWith(oldProfile);

  await act(() => mockRadioProps!.onConnectionPress());
  expect(mockPairingProps!.initialPairingUri).toBeUndefined();
});

test("handles a foreground pairing link and ignores unsupported URLs", async () => {
  mockLoadServerProfile.mockResolvedValue(oldProfile);
  await render(<App />);
  await waitFor(() => {
    expect(mockVisibleScreen).toBe("radio");
  });

  await act(() => mockUrlListener?.({ url: pairingUri }));
  expect(mockVisibleScreen).toBe("pairing");
  expect(mockPairingProps!.initialPairingUri).toBe(pairingUri);
  expect(mockClaimPairingGrant).not.toHaveBeenCalled();

  await act(() => mockPairingProps!.onCancel?.());
  expect(mockVisibleScreen).toBe("radio");

  await act(() => mockUrlListener?.({ url: "https://malicious.test/pair" }));
  expect(mockVisibleScreen).toBe("radio");
});

test("stores a profile claimed from a pairing link", async () => {
  await render(<App />);
  await waitFor(() => {
    expect(mockVisibleScreen).toBe("pairing");
  });

  await act(() =>
    mockPairingProps!.onClaim({
      pairingUri: "tiklocal-radio://pair?redacted",
    }),
  );

  await waitFor(() => {
    expect(mockVisibleScreen).toBe("radio");
  });
  expect(mockClaimPairingGrant).toHaveBeenCalledWith({
    pairingUri: "tiklocal-radio://pair?redacted",
    deviceName: expect.stringContaining("TikLocal Radio"),
  });
  expect(mockSaveServerProfile).toHaveBeenCalledWith(newProfile);
});

test("restores a stored server profile at startup", async () => {
  mockLoadServerProfile.mockResolvedValue(oldProfile);

  await render(<App />);

  await waitFor(() => {
    expect(mockVisibleScreen).toBe("radio");
  });
  expect(mockUseRadioSession).toHaveBeenLastCalledWith(
    oldProfile,
    expect.any(Function),
  );
  expect(mockPairingProps).toBeNull();
});

test("falls back to pairing when secure storage cannot be read", async () => {
  mockLoadServerProfile.mockRejectedValue(new Error("keychain unavailable"));

  await render(<App />);

  await waitFor(() => {
    expect(mockVisibleScreen).toBe("pairing");
  });
  expect(mockUseRadioSession).toHaveBeenLastCalledWith(
    null,
    expect.any(Function),
  );
});

test("clears the stored profile when the Radio session reports 401", async () => {
  mockLoadServerProfile.mockResolvedValue(oldProfile);
  await render(<App />);
  await waitFor(() => {
    expect(mockVisibleScreen).toBe("radio");
  });

  await act(() => mockUnauthorized?.());

  await waitFor(() => {
    expect(mockVisibleScreen).toBe("pairing");
  });
  expect(mockClearServerProfile).toHaveBeenCalledTimes(1);
  expect(mockUseRadioSession).toHaveBeenLastCalledWith(
    null,
    expect.any(Function),
  );
});

test("revokes a newly issued token when secure storage rejects it", async () => {
  const storageError = new Error("secure storage is full");
  mockSaveServerProfile.mockRejectedValue(storageError);
  await render(<App />);
  await waitFor(() => {
    expect(mockVisibleScreen).toBe("pairing");
  });

  let caught: unknown;
  await act(async () => {
    try {
      await mockPairingProps!.onConnect({
        baseUrl: "https://new-radio.test",
        password: "access-password",
      });
    } catch (error) {
      caught = error;
    }
  });

  expect(caught).toBe(storageError);
  expect(mockPairServer).toHaveBeenCalledWith({
    baseUrl: "https://new-radio.test",
    password: "access-password",
    deviceName: expect.stringContaining("TikLocal Radio"),
  });
  expect(mockRevokeServer).toHaveBeenCalledWith(newProfile);
  expect(mockVisibleScreen).toBe("pairing");
  expect(mockUseRadioSession).toHaveBeenLastCalledWith(
    null,
    expect.any(Function),
  );
});

test("stores the new profile before revoking the previous server", async () => {
  mockLoadServerProfile.mockResolvedValue(oldProfile);
  await render(<App />);
  await waitFor(() => {
    expect(mockVisibleScreen).toBe("radio");
  });

  await act(() => mockRadioProps!.onConnectionPress());
  expect(mockVisibleScreen).toBe("pairing");
  expect(mockPairingProps!.initialUrl).toBe(oldProfile.baseUrl);
  expect(mockPairingProps!.onCancel).toEqual(expect.any(Function));

  await act(() =>
    mockPairingProps!.onConnect({
      baseUrl: "https://new-radio.test",
      password: "access-password",
    }),
  );

  await waitFor(() => {
    expect(mockVisibleScreen).toBe("radio");
  });
  expect(mockSaveServerProfile).toHaveBeenCalledWith(newProfile);
  expect(mockSaveServerProfile.mock.invocationCallOrder[0]).toBeLessThan(
    mockRevokeServer.mock.invocationCallOrder[0]!,
  );
  expect(mockRevokeServer).toHaveBeenCalledWith(oldProfile);
  expect(mockUseRadioSession).toHaveBeenLastCalledWith(
    newProfile,
    expect.any(Function),
  );
});

test("disconnects locally and revokes the old token when entering Demo", async () => {
  mockLoadServerProfile.mockResolvedValue(oldProfile);
  await render(<App />);
  await waitFor(() => {
    expect(mockVisibleScreen).toBe("radio");
  });
  await act(() => mockRadioProps!.onConnectionPress());

  await act(() => mockPairingProps!.onUseDemo());

  await waitFor(() => {
    expect(mockVisibleScreen).toBe("radio");
  });
  expect(mockRevokeServer).toHaveBeenCalledWith(oldProfile);
  expect(mockClearServerProfile).toHaveBeenCalledTimes(1);
  expect(mockUseRadioSession).toHaveBeenLastCalledWith(
    null,
    expect.any(Function),
  );
});
