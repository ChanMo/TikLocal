import { beforeEach, expect, jest, test } from "@jest/globals";
import type { SQLiteDatabase } from "expo-sqlite";

import {
  importFromFiles,
  InsufficientStorageError,
  deleteLocalMedia,
  initializeLocalLibrary,
  migrateLocalLibrary,
  summarizeLocalMedia,
  type LocalMediaItem,
} from "./localLibrary";

const mockExcludeFromBackup = jest.fn<(_uri: string) => Promise<void>>();
const mockGenerateVideoThumbnail = jest.fn<
  (_videoUri: string, outputUri: string) => Promise<string>
>();
const mockGetDocumentAsync = jest.fn<() => Promise<unknown>>();
const mockExecAsync = jest.fn<(_sql: string) => Promise<void>>();
const mockGetAllAsync = jest.fn<(_sql: string) => Promise<unknown[]>>();
const mockGetFirstAsync = jest.fn<
  (_sql: string, ..._params: unknown[]) => Promise<unknown>
>();
const mockRunAsync = jest.fn<
  (_sql: string, ..._params: unknown[]) => Promise<unknown>
>();
const mockWithTransactionAsync = jest.fn<
  (task: () => Promise<void>) => Promise<void>
>();
const mockDeleteFile = jest.fn();
let mockAvailableDiskSpace = 5_000_000_000;

jest.mock("../modules/tiklocal-storage", () => ({
  __esModule: true,
  default: {
    excludeFromBackup: (uri: string) => mockExcludeFromBackup(uri),
    generateVideoThumbnail: (videoUri: string, outputUri: string) =>
      mockGenerateVideoThumbnail(videoUri, outputUri),
  },
}));

jest.mock("expo-document-picker", () => ({
  getDocumentAsync: () => mockGetDocumentAsync(),
}));

jest.mock("expo-image-picker", () => ({
  launchImageLibraryAsync: jest.fn(),
}));

jest.mock("expo-file-system", () => ({
  Directory: class MockDirectory {
    uri: string;

    constructor(_base: unknown, name: string) {
      this.uri = `file:///documents/${name}/`;
    }

    create() {}
  },
  File: class MockFile {
    exists = true;
    uri: string;

    constructor(uri: string | { uri: string }, filename?: string) {
      const base = typeof uri === "string" ? uri : uri.uri;
      this.uri = filename ? `${base}${filename}` : base;
    }

    async copy() {}

    delete() {
      mockDeleteFile(this.uri);
      this.exists = false;
    }
  },
  Paths: {
    get availableDiskSpace() {
      return mockAvailableDiskSpace;
    },
    document: "file:///documents/",
    totalDiskSpace: 10_000_000_000,
  },
}));

jest.mock("expo-sqlite", () => ({
  openDatabaseAsync: async () => mockDatabase,
}));

const mockDatabase = {
  execAsync: mockExecAsync,
  getAllAsync: mockGetAllAsync,
  getFirstAsync: mockGetFirstAsync,
  runAsync: mockRunAsync,
  withTransactionAsync: mockWithTransactionAsync,
} as unknown as SQLiteDatabase;

beforeEach(() => {
  jest.clearAllMocks();
  mockExcludeFromBackup.mockResolvedValue();
  mockGenerateVideoThumbnail.mockImplementation(async (_videoUri, outputUri) =>
    outputUri,
  );
  mockGetDocumentAsync.mockResolvedValue({ canceled: true });
  mockAvailableDiskSpace = 5_000_000_000;
  mockExecAsync.mockResolvedValue();
  mockGetAllAsync.mockResolvedValue([]);
  mockGetFirstAsync.mockResolvedValue({ user_version: 2 });
  mockRunAsync.mockResolvedValue({});
  mockWithTransactionAsync.mockImplementation(async (task) => task());
});

test("migrates an unversioned local library through schema version two", async () => {
  mockGetFirstAsync.mockResolvedValueOnce({ user_version: 0 });

  await migrateLocalLibrary(mockDatabase);

  expect(mockExecAsync).toHaveBeenNthCalledWith(1, "PRAGMA journal_mode = WAL;");
  expect(mockWithTransactionAsync).toHaveBeenCalledTimes(2);
  expect(mockExecAsync.mock.calls[1]?.[0]).toContain(
    "CREATE TABLE IF NOT EXISTS local_media",
  );
  expect(mockExecAsync.mock.calls[1]?.[0]).toContain("PRAGMA user_version = 1");
  expect(mockExecAsync.mock.calls[2]?.[0]).toContain(
    "ALTER TABLE local_media ADD COLUMN thumbnail_uri TEXT",
  );
  expect(mockExecAsync.mock.calls[2]?.[0]).toContain("PRAGMA user_version = 2");
});

test("migrates a version one library without rebuilding media rows", async () => {
  mockGetFirstAsync.mockResolvedValueOnce({ user_version: 1 });

  await migrateLocalLibrary(mockDatabase);

  expect(mockWithTransactionAsync).toHaveBeenCalledTimes(1);
  expect(mockExecAsync.mock.calls[1]?.[0]).toContain(
    "ALTER TABLE local_media ADD COLUMN thumbnail_uri TEXT",
  );
  expect(mockExecAsync.mock.calls[1]?.[0]).not.toContain("CREATE TABLE");
});

test("does not rerun migrations for the current schema", async () => {
  await migrateLocalLibrary(mockDatabase);

  expect(mockWithTransactionAsync).not.toHaveBeenCalled();
  expect(mockExecAsync).toHaveBeenCalledTimes(1);
});

test("rejects a database created by a newer app version", async () => {
  mockGetFirstAsync.mockResolvedValueOnce({ user_version: 3 });

  await expect(migrateLocalLibrary(mockDatabase)).rejects.toThrow(
    "newer than supported version 2",
  );
});

test("deletes the offline file before removing its database row", async () => {
  mockGetFirstAsync.mockImplementation(async (sql) =>
    sql === "PRAGMA user_version"
      ? { user_version: 1 }
      : {
          thumbnail_uri:
            "file:///documents/tiklocal-thumbnails/media-1.jpg",
          uri: "file:///documents/tiklocal-media/photo.jpg",
        },
  );

  const result = await deleteLocalMedia(["media-1"]);

  expect(result).toEqual({ deleted: 1, failed: [] });
  expect(mockDeleteFile).toHaveBeenCalledWith(
    "file:///documents/tiklocal-media/photo.jpg",
  );
  expect(mockDeleteFile).toHaveBeenCalledWith(
    "file:///documents/tiklocal-thumbnails/media-1.jpg",
  );
  expect(mockRunAsync).toHaveBeenCalledWith(
    "DELETE FROM local_media WHERE id = ?",
    "media-1",
  );
  expect(mockDeleteFile.mock.invocationCallOrder[0]!).toBeLessThan(
    mockRunAsync.mock.invocationCallOrder[0]!,
  );
});

test("summarizes media count, types, and local size", () => {
  const image = mediaItem({ id: "image", kind: "image", size: 2_000 });
  const video = mediaItem({ id: "video", kind: "video", size: 8_000 });

  expect(summarizeLocalMedia([image, video])).toEqual({
    count: 2,
    images: 1,
    videos: 1,
    totalSize: 10_000,
  });
});

test("marks the imported-media directory as excluded from device backup", async () => {
  await initializeLocalLibrary();

  expect(mockExcludeFromBackup).toHaveBeenCalledWith(
    "file:///documents/tiklocal-media/",
  );
  expect(mockExcludeFromBackup).toHaveBeenCalledWith(
    "file:///documents/tiklocal-thumbnails/",
  );
});

test("blocks an import that would consume the local safety reserve", async () => {
  mockAvailableDiskSpace = 200_000_000;
  mockGetDocumentAsync.mockResolvedValue({
    assets: [
      {
        lastModified: 1,
        mimeType: "video/mp4",
        name: "large-video.mp4",
        size: 100_000_000,
        uri: "file:///picker/large-video.mp4",
      },
    ],
    canceled: false,
  });

  await expect(importFromFiles()).rejects.toEqual(
    new InsufficientStorageError(100_000_000, 200_000_000),
  );
  expect(mockRunAsync).not.toHaveBeenCalled();
});

test("reports copy progress and stores a generated video thumbnail", async () => {
  const progress: Array<{ completed: number; filename: string; total: number }> = [];
  mockGetDocumentAsync.mockResolvedValue({
    assets: [
      {
        lastModified: 1,
        mimeType: "video/mp4",
        name: "small-video.mp4",
        size: 10_000,
        uri: "file:///picker/small-video.mp4",
      },
    ],
    canceled: false,
  });
  mockGetFirstAsync.mockResolvedValue(null);

  await expect(importFromFiles((value) => progress.push(value))).resolves.toEqual({
    added: 1,
    skipped: 0,
  });

  expect(progress).toEqual([
    { completed: 0, filename: "small-video.mp4", total: 1 },
    { completed: 1, filename: "small-video.mp4", total: 1 },
  ]);
  expect(mockGenerateVideoThumbnail).toHaveBeenCalledWith(
    expect.stringMatching(/tiklocal-media\/.*\.mp4$/),
    expect.stringMatching(/tiklocal-thumbnails\/.*\.jpg$/),
  );
  expect(mockRunAsync.mock.calls.at(-1)?.at(-1)).toEqual(
    expect.stringMatching(/tiklocal-thumbnails\/.*\.jpg$/),
  );
});

function mediaItem(
  input: Pick<LocalMediaItem, "id" | "kind" | "size">,
): LocalMediaItem {
  return {
    duration: 0,
    filename: `${input.id}.jpg`,
    height: 1,
    importedAt: 1,
    mimeType: "image/jpeg",
    source: "photos",
    thumbnailUri: null,
    uri: `file:///${input.id}.jpg`,
    width: 1,
    ...input,
  };
}
