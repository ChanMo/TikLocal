import { beforeEach, expect, jest, test } from "@jest/globals";
import {
  render,
  screen,
  userEvent,
  waitFor,
} from "@testing-library/react-native";

import type { LocalMediaItem } from "./localLibrary";
import { LocalFlowScreen } from "./LocalFlowScreen";

const mockPause = jest.fn();
const mockPlay = jest.fn();
const mockPlayer = {
  loop: false,
  muted: true,
  pause: mockPause,
  play: mockPlay,
};

jest.mock(
  "react-native-safe-area-context",
  () => require("react-native-safe-area-context/jest/mock").default,
);

jest.mock("expo-video", () => ({
  VideoView: () => null,
  useVideoPlayer: (
    _uri: string,
    configure: (player: typeof mockPlayer) => void,
  ) => {
    configure(mockPlayer);
    return mockPlayer;
  },
}));

const video: LocalMediaItem = {
  duration: 12,
  filename: "summer-walk.mp4",
  height: 1920,
  id: "video-1",
  importedAt: 1,
  kind: "video",
  mimeType: "video/mp4",
  size: 4096,
  source: "files",
  thumbnailUri: null,
  uri: "file:///summer-walk.mp4",
  width: 1080,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockPlayer.loop = false;
  mockPlayer.muted = true;
});

test("plays the active local video, supports pause, and closes the Flow", async () => {
  const user = userEvent.setup();
  const onClose = jest.fn();

  await render(
    <LocalFlowScreen initialIndex={0} items={[video]} onClose={onClose} />,
  );

  await waitFor(() => expect(mockPlay).toHaveBeenCalled());
  expect(mockPlayer.loop).toBe(true);
  expect(mockPlayer.muted).toBe(false);
  expect(screen.getByText("1 / 1")).toBeOnTheScreen();
  expect(screen.getByText("A MEMORY ON THIS IPHONE")).toBeOnTheScreen();

  await user.press(screen.getByRole("button", { name: "Pause video" }));
  await waitFor(() => expect(mockPause).toHaveBeenCalled());
  expect(screen.getByRole("button", { name: "Play video" })).toBeOnTheScreen();

  await user.press(screen.getByRole("button", { name: "Close local Flow" }));
  expect(onClose).toHaveBeenCalledTimes(1);
});
