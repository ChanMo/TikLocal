import { beforeEach, expect, jest, test } from "@jest/globals";
import { act, renderHook } from "@testing-library/react-native";

import type { Track } from "./model";
import { useRadioPlayer } from "./player";

const mockPlayer = {
  clearLockScreenControls: jest.fn(),
  pause: jest.fn(),
  play: jest.fn(),
  replace: jest.fn(),
  seekTo: jest.fn<(seconds: number) => Promise<void>>()
    .mockResolvedValue(undefined),
  setActiveForLockScreen: jest.fn(),
};
const mockSetAudioModeAsync = jest.fn<(mode: unknown) => Promise<void>>()
  .mockResolvedValue(undefined);

jest.mock("expo-audio", () => ({
  setAudioModeAsync: (mode: unknown) => mockSetAudioModeAsync(mode),
  useAudioPlayer: () => mockPlayer,
  useAudioPlayerStatus: () => ({
    currentTime: 0,
    didJustFinish: false,
    duration: 0,
    error: null,
    isBuffering: false,
    playing: false,
  }),
}));

const track: Track = {
  id: "demo-track",
  uri: "demo:track",
  title: "Demo Track",
  artist: "TikLocal",
  album: "Demo",
  source: 1,
  accent: "#D9633B",
  isFavorite: false,
};

beforeEach(() => {
  jest.clearAllMocks();
});

test("deactivates playback without passing null to native replace", async () => {
  const { result } = await renderHook(() => useRadioPlayer(track));

  expect(mockPlayer.replace).toHaveBeenCalledWith(track.source);
  await act(() => result.current.clear());

  expect(mockPlayer.pause).toHaveBeenCalledTimes(1);
  expect(mockPlayer.clearLockScreenControls).toHaveBeenCalledTimes(1);
  expect(mockPlayer.replace).not.toHaveBeenCalledWith(null);
});
