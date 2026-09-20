import { beforeEach, expect, jest, test } from "@jest/globals";
import {
  act,
  fireEvent,
  render,
  screen,
  userEvent,
  waitFor,
} from "@testing-library/react-native";
import { Alert } from "react-native";

import type {
  DeleteResult,
  ImportProgress,
  ImportResult,
  LocalMediaItem,
} from "./localLibrary";
import { LocalLibraryScreen } from "./LocalLibraryScreen";

const mockImportFromFiles = jest.fn<
  (_onProgress?: (progress: ImportProgress) => void) => Promise<ImportResult>
>();
const mockImportFromPhotos = jest.fn<
  (_onProgress?: (progress: ImportProgress) => void) => Promise<ImportResult>
>();
const mockListLocalMedia = jest.fn<() => Promise<LocalMediaItem[]>>();
const mockClearLocalMedia = jest.fn<() => Promise<DeleteResult>>();
const mockDeleteLocalMedia = jest.fn<
  (ids: string[]) => Promise<DeleteResult>
>();

jest.mock("./localLibrary", () => ({
  backfillVideoThumbnails: async () => undefined,
  clearLocalMedia: () => mockClearLocalMedia(),
  deleteLocalMedia: (ids: string[]) => mockDeleteLocalMedia(ids),
  getLocalStorageCapacity: () => ({
    available: 5_000_000_000,
    total: 10_000_000_000,
  }),
  importFromFiles: (onProgress?: (progress: ImportProgress) => void) =>
    mockImportFromFiles(onProgress),
  importFromPhotos: (onProgress?: (progress: ImportProgress) => void) =>
    mockImportFromPhotos(onProgress),
  InsufficientStorageError: class InsufficientStorageError extends Error {
    required: number;
    available: number;

    constructor(mockRequired: number, mockAvailable: number) {
      super("Not enough storage");
      this.required = mockRequired;
      this.available = mockAvailable;
    }
  },
  listLocalMedia: () => mockListLocalMedia(),
  summarizeLocalMedia: (items: LocalMediaItem[]) => ({
    count: items.length,
    images: items.filter((item) => item.kind === "image").length,
    videos: items.filter((item) => item.kind === "video").length,
    totalSize: items.reduce((size, item) => size + item.size, 0),
  }),
}));

const image: LocalMediaItem = {
  duration: 0,
  filename: "quiet-window.jpg",
  height: 1200,
  id: "image-1",
  importedAt: 1,
  kind: "image",
  mimeType: "image/jpeg",
  size: 2048,
  source: "photos",
  thumbnailUri: null,
  uri: "file:///quiet-window.jpg",
  width: 900,
};

beforeEach(() => {
  jest.clearAllMocks();
  mockListLocalMedia.mockReset().mockResolvedValue([]);
  mockImportFromFiles.mockReset().mockResolvedValue({ added: 0, skipped: 0 });
  mockImportFromPhotos.mockReset().mockResolvedValue({ added: 0, skipped: 0 });
  mockClearLocalMedia.mockReset().mockResolvedValue({ deleted: 1, failed: [] });
  mockDeleteLocalMedia.mockReset().mockResolvedValue({ deleted: 1, failed: [] });
  jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
});

test("imports selected Photos and refreshes the local library", async () => {
  const user = userEvent.setup();
  const onCountChange = jest.fn();
  mockListLocalMedia
    .mockResolvedValueOnce([])
    .mockResolvedValueOnce([image]);
  mockImportFromPhotos.mockResolvedValue({ added: 1, skipped: 0 });

  await render(
    <LocalLibraryScreen
      onCountChange={onCountChange}
      onOpenFlow={jest.fn()}
    />,
  );
  await waitFor(() => expect(onCountChange).toHaveBeenCalledWith(0));

  await user.press(screen.getByRole("button", { name: "Import from Photos" }));

  await waitFor(() => expect(onCountChange).toHaveBeenCalledWith(1));
  expect(mockImportFromPhotos).toHaveBeenCalledTimes(1);
  expect(Alert.alert).toHaveBeenCalledWith(
    "Ready for your Flow",
    "1 item imported.",
  );
  expect(
    screen.getByRole("button", { name: "Play local Flow with 1 item" }),
  ).toBeOnTheScreen();
  await settleVirtualizedList();
});

test("opens the Flow at the selected media item", async () => {
  const user = userEvent.setup();
  const onOpenFlow = jest.fn();
  mockListLocalMedia.mockResolvedValue([image]);

  await render(
    <LocalLibraryScreen
      onCountChange={jest.fn()}
      onOpenFlow={onOpenFlow}
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", {
        name: "Open image, quiet-window.jpg",
      }),
    ).toBeOnTheScreen(),
  );

  await act(async () => {
    await user.press(
      screen.getByRole("button", {
        name: "Open image, quiet-window.jpg",
      }),
    );
  });

  expect(onOpenFlow).toHaveBeenCalledWith([image], 0);
  await settleVirtualizedList();
});

test("shows determinate progress while copying a multi-item import", async () => {
  const user = userEvent.setup();
  let finishImport: ((result: ImportResult) => void) | undefined;
  mockImportFromPhotos.mockImplementation((onProgress) => {
    onProgress?.({ completed: 1, filename: "second-video.mp4", total: 2 });
    return new Promise((resolve) => {
      finishImport = resolve;
    });
  });

  await render(
    <LocalLibraryScreen
      onCountChange={jest.fn()}
      onOpenFlow={jest.fn()}
    />,
  );
  await user.press(screen.getByRole("button", { name: "Import from Photos" }));

  expect(screen.getByText("second-video.mp4")).toBeOnTheScreen();
  expect(screen.getByRole("progressbar", { name: "Import progress" }))
    .toHaveAccessibilityValue({ max: 2, min: 0, now: 1 });

  await act(async () => {
    finishImport?.({ added: 2, skipped: 0 });
  });
  await settleVirtualizedList();
});

test("shows local storage and deletes a selected offline copy", async () => {
  const user = userEvent.setup();
  const onCountChange = jest.fn();
  mockListLocalMedia
    .mockResolvedValueOnce([image])
    .mockResolvedValueOnce([]);

  await render(
    <LocalLibraryScreen
      onCountChange={onCountChange}
      onOpenFlow={jest.fn()}
    />,
  );
  const tile = await screen.findByRole("button", {
    name: "Open image, quiet-window.jpg",
  });
  expect(screen.getByText("2.0 KB")).toBeOnTheScreen();

  await act(async () => {
    fireEvent(tile, "longPress");
  });
  await user.press(
    screen.getByRole("button", {
      name: "Delete 1 selected local copy",
    }),
  );

  const alertButtons = jest.mocked(Alert.alert).mock.calls.at(-1)?.[2];
  const deleteButton = alertButtons?.find((button) => button.text === "Delete");
  await act(async () => {
    deleteButton?.onPress?.();
  });

  await waitFor(() => expect(mockDeleteLocalMedia).toHaveBeenCalledWith([image.id]));
  await waitFor(() => expect(onCountChange).toHaveBeenLastCalledWith(0));
  await settleVirtualizedList();
});

test("requires destructive confirmation before clearing the library", async () => {
  const user = userEvent.setup();
  mockListLocalMedia
    .mockResolvedValueOnce([image])
    .mockResolvedValueOnce([]);

  await render(
    <LocalLibraryScreen
      onCountChange={jest.fn()}
      onOpenFlow={jest.fn()}
    />,
  );
  await user.press(
    await screen.findByRole("button", { name: "Clear local library" }),
  );

  expect(Alert.alert).toHaveBeenLastCalledWith(
    "Clear this local library?",
    "LumaFold will remove 1 offline copy using 2.0 KB. Your originals stay where they are.",
    expect.any(Array),
  );
  const alertButtons = jest.mocked(Alert.alert).mock.calls.at(-1)?.[2];
  const clearButton = alertButtons?.find(
    (button) => button.text === "Clear Library",
  );
  await act(async () => {
    clearButton?.onPress?.();
  });

  await waitFor(() => expect(mockClearLocalMedia).toHaveBeenCalledTimes(1));
  await settleVirtualizedList();
});

async function settleVirtualizedList() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 100));
  });
}
