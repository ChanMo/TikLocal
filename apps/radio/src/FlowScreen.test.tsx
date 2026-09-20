import { beforeEach, expect, jest, test } from "@jest/globals";
import { render, screen, userEvent, waitFor } from "@testing-library/react-native";

import type {
  ImportProgress,
  ImportResult,
  LocalMediaItem,
} from "./localLibrary";
import { FlowScreen } from "./FlowScreen";

const mockImportFromFiles = jest.fn<
  (_onProgress?: (progress: ImportProgress) => void) => Promise<ImportResult>
>();
const mockImportFromPhotos = jest.fn<
  (_onProgress?: (progress: ImportProgress) => void) => Promise<ImportResult>
>();
const mockListLocalMedia = jest.fn<() => Promise<LocalMediaItem[]>>();
let mockInitialIndex = -1;

jest.mock(
  "react-native-safe-area-context",
  () => require("react-native-safe-area-context/jest/mock").default,
);

jest.mock("./localLibrary", () => ({
  importFromFiles: (onProgress?: (progress: ImportProgress) => void) =>
    mockImportFromFiles(onProgress),
  importFromPhotos: (onProgress?: (progress: ImportProgress) => void) =>
    mockImportFromPhotos(onProgress),
  InsufficientStorageError: class InsufficientStorageError extends Error {},
  listLocalMedia: () => mockListLocalMedia(),
}));

jest.mock("./LocalFlowScreen", () => ({
  LocalFlowScreen: ({
    initialIndex,
    items,
    onShuffle,
  }: {
    initialIndex: number;
    items: LocalMediaItem[];
    onShuffle(): void;
  }) => {
    const { Pressable, Text } = require("react-native");
    mockInitialIndex = initialIndex;
    return (
      <Pressable
        accessibilityLabel="Shuffle Flow"
        accessibilityRole="button"
        onPress={onShuffle}
      >
        <Text>{`FLOW READY · ${items.length}`}</Text>
      </Pressable>
    );
  },
}));

const image: LocalMediaItem = {
  duration: 0,
  filename: "quiet-window.jpg",
  height: 1200,
  id: "image-1",
  importedAt: 2,
  kind: "image",
  mimeType: "image/jpeg",
  size: 2048,
  source: "photos",
  thumbnailUri: null,
  uri: "file:///quiet-window.jpg",
  width: 900,
};

const video: LocalMediaItem = {
  ...image,
  duration: 12,
  filename: "summer-walk.mp4",
  id: "video-1",
  kind: "video",
  mimeType: "video/mp4",
  uri: "file:///summer-walk.mp4",
};

beforeEach(() => {
  jest.clearAllMocks();
  mockInitialIndex = -1;
  mockListLocalMedia.mockReset().mockResolvedValue([]);
  mockImportFromFiles.mockReset().mockResolvedValue({ added: 0, skipped: 0 });
  mockImportFromPhotos.mockReset().mockResolvedValue({ added: 0, skipped: 0 });
});

test("starts an empty private Flow by importing from Photos", async () => {
  const user = userEvent.setup();
  const onCountChange = jest.fn();
  mockListLocalMedia
    .mockResolvedValueOnce([])
    .mockResolvedValueOnce([image]);
  mockImportFromPhotos.mockResolvedValue({ added: 1, skipped: 0 });

  await render(
    <FlowScreen
      onCountChange={onCountChange}
      refreshToken={0}
    />,
  );

  await user.press(
    await screen.findByRole("button", {
      name: "Choose photos and videos from Photos",
    }),
  );

  expect(await screen.findByText("FLOW READY · 1")).toBeOnTheScreen();
  expect(mockImportFromPhotos).toHaveBeenCalledTimes(1);
  expect(onCountChange).toHaveBeenLastCalledWith(1);
});

test("opens a requested Library item and exposes a real shuffle action", async () => {
  const user = userEvent.setup();
  mockListLocalMedia.mockResolvedValue([image, video]);

  await render(
    <FlowScreen
      onCountChange={jest.fn()}
      refreshToken={0}
      requestedItemId={video.id}
    />,
  );

  expect(await screen.findByText("FLOW READY · 2")).toBeOnTheScreen();
  expect(mockInitialIndex).toBe(1);
  await user.press(screen.getByRole("button", { name: "Shuffle Flow" }));
  await waitFor(() => expect(mockInitialIndex).toBe(0));
});
