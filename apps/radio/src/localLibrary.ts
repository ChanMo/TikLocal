import * as DocumentPicker from "expo-document-picker";
import { Directory, File, Paths } from "expo-file-system";
import * as ImagePicker from "expo-image-picker";
import { openDatabaseAsync, type SQLiteDatabase } from "expo-sqlite";

import TikLocalStorage from "../modules/tiklocal-storage";

export type LocalMediaKind = "image" | "video";

export type LocalMediaItem = {
  id: string;
  kind: LocalMediaKind;
  uri: string;
  filename: string;
  mimeType: string;
  width: number;
  height: number;
  duration: number;
  size: number;
  importedAt: number;
  source: "photos" | "files";
  thumbnailUri: string | null;
};

export type ImportResult = {
  added: number;
  skipped: number;
};

export type ImportProgress = {
  completed: number;
  filename: string;
  total: number;
};

export type LocalStorageCapacity = {
  available: number;
  total: number;
};

export type DeleteResult = {
  deleted: number;
  failed: string[];
};

export type LocalLibraryStats = {
  count: number;
  images: number;
  videos: number;
  totalSize: number;
};

type ImportCandidate = Omit<
  LocalMediaItem,
  "id" | "uri" | "importedAt" | "thumbnailUri"
> & {
  originKey: string;
  sourceUri: string;
};

type LocalMediaRow = {
  id: string;
  kind: LocalMediaKind;
  uri: string;
  filename: string;
  mime_type: string;
  width: number;
  height: number;
  duration: number;
  size: number;
  imported_at: number;
  source: "photos" | "files";
  thumbnail_uri: string | null;
};

const DATABASE_NAME = "tiklocal-local-library.db";
const CURRENT_SCHEMA_VERSION = 2;
const STORAGE_RESERVE = 128 * 1024 * 1024;
const MEDIA_DIRECTORY = new Directory(Paths.document, "tiklocal-media");
const THUMBNAIL_DIRECTORY = new Directory(
  Paths.document,
  "tiklocal-thumbnails",
);
let databasePromise: Promise<SQLiteDatabase> | null = null;

export class InsufficientStorageError extends Error {
  constructor(
    readonly required: number,
    readonly available: number,
  ) {
    super("TikLocal does not have enough free space for this import.");
    this.name = "InsufficientStorageError";
  }
}

export async function initializeLocalLibrary(): Promise<void> {
  await getDatabase();
  ensureMediaDirectory();
  ensureThumbnailDirectory();
  await Promise.all([
    TikLocalStorage.excludeFromBackup(MEDIA_DIRECTORY.uri),
    TikLocalStorage.excludeFromBackup(THUMBNAIL_DIRECTORY.uri),
  ]);
}

export async function listLocalMedia(): Promise<LocalMediaItem[]> {
  const database = await getDatabase();
  const rows = await database.getAllAsync<LocalMediaRow>(
    `SELECT id, kind, uri, filename, mime_type, width, height,
            duration, size, imported_at, source, thumbnail_uri
       FROM local_media
      ORDER BY imported_at DESC, id DESC`,
  );
  const items: LocalMediaItem[] = [];
  const missingIds: string[] = [];
  for (const row of rows) {
    if (!new File(row.uri).exists) {
      if (row.thumbnail_uri) {
        try {
          const thumbnail = new File(row.thumbnail_uri);
          if (thumbnail.exists) {
            thumbnail.delete();
          }
        } catch {
          // The invalid database row can still be removed.
        }
      }
      missingIds.push(row.id);
      continue;
    }
    items.push(rowToItem(row));
  }
  if (missingIds.length > 0) {
    await database.withTransactionAsync(async () => {
      for (const id of missingIds) {
        await database.runAsync("DELETE FROM local_media WHERE id = ?", id);
      }
    });
  }
  return items;
}

export async function countLocalMedia(): Promise<number> {
  return (await listLocalMedia()).length;
}

export async function getLocalLibraryStats(): Promise<LocalLibraryStats> {
  return summarizeLocalMedia(await listLocalMedia());
}

export function getLocalStorageCapacity(): LocalStorageCapacity {
  return {
    available: Math.max(0, Paths.availableDiskSpace),
    total: Math.max(0, Paths.totalDiskSpace),
  };
}

export async function backfillVideoThumbnails(
  items: LocalMediaItem[],
  onThumbnail: (item: LocalMediaItem) => void,
): Promise<void> {
  for (const item of items) {
    if (
      item.kind !== "video" ||
      (item.thumbnailUri && new File(item.thumbnailUri).exists)
    ) {
      continue;
    }
    try {
      onThumbnail(await generateVideoThumbnail(item));
    } catch {
      // A video remains playable when its decorative thumbnail cannot be made.
    }
  }
}

export function summarizeLocalMedia(
  items: LocalMediaItem[],
): LocalLibraryStats {
  return items.reduce<LocalLibraryStats>(
    (stats, item) => ({
      count: stats.count + 1,
      images: stats.images + (item.kind === "image" ? 1 : 0),
      videos: stats.videos + (item.kind === "video" ? 1 : 0),
      totalSize: stats.totalSize + item.size,
    }),
    { count: 0, images: 0, videos: 0, totalSize: 0 },
  );
}

export async function deleteLocalMedia(
  ids: string[],
): Promise<DeleteResult> {
  const database = await getDatabase();
  const failed: string[] = [];
  let deleted = 0;

  for (const id of new Set(ids)) {
    const row = await database.getFirstAsync<{
      thumbnail_uri: string | null;
      uri: string;
    }>(
      "SELECT uri, thumbnail_uri FROM local_media WHERE id = ?",
      id,
    );
    if (!row) {
      continue;
    }
    try {
      const file = new File(row.uri);
      if (file.exists) {
        file.delete();
      }
      if (row.thumbnail_uri) {
        try {
          const thumbnail = new File(row.thumbnail_uri);
          if (thumbnail.exists) {
            thumbnail.delete();
          }
        } catch {
          // An orphaned thumbnail must not block deletion of the actual media.
        }
      }
      await database.runAsync("DELETE FROM local_media WHERE id = ?", id);
      deleted += 1;
    } catch {
      failed.push(id);
    }
  }

  return { deleted, failed };
}

export async function clearLocalMedia(): Promise<DeleteResult> {
  const database = await getDatabase();
  const rows = await database.getAllAsync<{ id: string }>(
    "SELECT id FROM local_media",
  );
  return deleteLocalMedia(rows.map((row) => row.id));
}

export async function importFromPhotos(
  onProgress?: (progress: ImportProgress) => void,
): Promise<ImportResult> {
  const result = await ImagePicker.launchImageLibraryAsync({
    allowsMultipleSelection: true,
    mediaTypes: ["images", "videos"],
    orderedSelection: true,
    quality: 1,
    selectionLimit: 0,
  });
  if (result.canceled) {
    return { added: 0, skipped: 0 };
  }
  return importCandidates(
    result.assets.flatMap((asset) => {
      const kind = normalizeKind(asset.type, asset.mimeType, asset.fileName);
      if (!kind) {
        return [];
      }
      const filename = asset.fileName || defaultFilename(kind, asset.mimeType);
      return [{
        duration: asset.duration ?? 0,
        filename,
        height: asset.height,
        kind,
        mimeType: asset.mimeType || defaultMimeType(kind),
        originKey: `photos:${asset.assetId || filename}:${asset.fileSize || 0}`,
        size: asset.fileSize ?? 0,
        source: "photos" as const,
        sourceUri: asset.uri,
        width: asset.width,
      }];
    }),
    onProgress,
  );
}

export async function importFromFiles(
  onProgress?: (progress: ImportProgress) => void,
): Promise<ImportResult> {
  const result = await DocumentPicker.getDocumentAsync({
    copyToCacheDirectory: true,
    multiple: true,
    type: ["image/*", "video/*"],
  });
  if (result.canceled) {
    return { added: 0, skipped: 0 };
  }
  return importCandidates(
    result.assets.flatMap((asset) => {
      const kind = normalizeKind(undefined, asset.mimeType, asset.name);
      if (!kind) {
        return [];
      }
      return [{
        duration: 0,
        filename: asset.name,
        height: 0,
        kind,
        mimeType: asset.mimeType || defaultMimeType(kind),
        originKey: `files:${asset.name}:${asset.size || 0}:${asset.lastModified || 0}`,
        size: asset.size ?? 0,
        source: "files" as const,
        sourceUri: asset.uri,
        width: 0,
      }];
    }),
    onProgress,
  );
}

async function importCandidates(
  candidates: ImportCandidate[],
  onProgress?: (progress: ImportProgress) => void,
): Promise<ImportResult> {
  const database = await getDatabase();
  ensureMediaDirectory();
  ensureThumbnailDirectory();
  assertEnoughStorage(
    candidates.reduce((size, candidate) => size + candidate.size, 0),
  );
  let added = 0;
  let skipped = 0;

  for (const [index, candidate] of candidates.entries()) {
    onProgress?.({
      completed: index,
      filename: candidate.filename,
      total: candidates.length,
    });
    const duplicate = await database.getFirstAsync<{ id: string }>(
      "SELECT id FROM local_media WHERE origin_key = ?",
      candidate.originKey,
    );
    if (duplicate) {
      skipped += 1;
      onProgress?.({
        completed: index + 1,
        filename: candidate.filename,
        total: candidates.length,
      });
      continue;
    }

    assertEnoughStorage(candidate.size);

    const id = createMediaId();
    const storedFilename = `${id}${fileExtension(candidate.filename, candidate.mimeType)}`;
    const destination = new File(MEDIA_DIRECTORY, storedFilename);
    let thumbnailUri: string | null = null;
    try {
      await new File(candidate.sourceUri).copy(destination);
      await TikLocalStorage.excludeFromBackup(destination.uri);
      if (candidate.kind === "video") {
        thumbnailUri = await createThumbnailFile(id, destination.uri).catch(
          () => null,
        );
      }
      await database.runAsync(
        `INSERT INTO local_media (
           id, origin_key, kind, uri, filename, mime_type, width, height,
           duration, size, imported_at, source, thumbnail_uri
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        id,
        candidate.originKey,
        candidate.kind,
        destination.uri,
        candidate.filename,
        candidate.mimeType,
        candidate.width,
        candidate.height,
        candidate.duration,
        candidate.size,
        Date.now(),
        candidate.source,
        thumbnailUri,
      );
      added += 1;
      onProgress?.({
        completed: index + 1,
        filename: candidate.filename,
        total: candidates.length,
      });
    } catch (error) {
      if (destination.exists) {
        destination.delete();
      }
      if (thumbnailUri) {
        const thumbnail = new File(thumbnailUri);
        if (thumbnail.exists) {
          thumbnail.delete();
        }
      }
      throw error;
    }
  }
  return { added, skipped };
}

async function getDatabase(): Promise<SQLiteDatabase> {
  if (!databasePromise) {
    databasePromise = openDatabaseAsync(DATABASE_NAME).then(async (database) => {
      await migrateLocalLibrary(database);
      return database;
    });
  }
  return databasePromise;
}

export async function migrateLocalLibrary(
  database: SQLiteDatabase,
): Promise<void> {
  await database.execAsync("PRAGMA journal_mode = WAL;");
  const row = await database.getFirstAsync<{ user_version: number }>(
    "PRAGMA user_version",
  );
  let version = row?.user_version ?? 0;
  if (version > CURRENT_SCHEMA_VERSION) {
    throw new Error(
      `Local library schema ${version} is newer than supported version ${CURRENT_SCHEMA_VERSION}.`,
    );
  }
  if (version < 1) {
    await database.withTransactionAsync(async () => {
      await database.execAsync(`
        CREATE TABLE IF NOT EXISTS local_media (
          id TEXT PRIMARY KEY NOT NULL,
          origin_key TEXT NOT NULL UNIQUE,
          kind TEXT NOT NULL CHECK (kind IN ('image', 'video')),
          uri TEXT NOT NULL UNIQUE,
          filename TEXT NOT NULL,
          mime_type TEXT NOT NULL,
          width INTEGER NOT NULL DEFAULT 0,
          height INTEGER NOT NULL DEFAULT 0,
          duration REAL NOT NULL DEFAULT 0,
          size INTEGER NOT NULL DEFAULT 0,
          imported_at INTEGER NOT NULL,
          source TEXT NOT NULL CHECK (source IN ('photos', 'files'))
        );
        CREATE INDEX IF NOT EXISTS local_media_imported_at
          ON local_media(imported_at DESC);
        PRAGMA user_version = 1;
      `);
    });
    version = 1;
  }
  if (version < 2) {
    await database.withTransactionAsync(async () => {
      await database.execAsync(`
        ALTER TABLE local_media ADD COLUMN thumbnail_uri TEXT;
        PRAGMA user_version = 2;
      `);
    });
  }
}

function ensureMediaDirectory() {
  MEDIA_DIRECTORY.create({ idempotent: true, intermediates: true });
}

function ensureThumbnailDirectory() {
  THUMBNAIL_DIRECTORY.create({ idempotent: true, intermediates: true });
}

function assertEnoughStorage(required: number) {
  const available = Paths.availableDiskSpace;
  if (
    required > 0 &&
    Number.isFinite(available) &&
    available > 0 &&
    required > Math.max(0, available - STORAGE_RESERVE)
  ) {
    throw new InsufficientStorageError(required, available);
  }
}

async function generateVideoThumbnail(
  item: LocalMediaItem,
): Promise<LocalMediaItem> {
  const thumbnailUri = await createThumbnailFile(item.id, item.uri);
  const database = await getDatabase();
  await database.runAsync(
    "UPDATE local_media SET thumbnail_uri = ? WHERE id = ?",
    thumbnailUri,
    item.id,
  );
  return { ...item, thumbnailUri };
}

async function createThumbnailFile(id: string, videoUri: string) {
  ensureThumbnailDirectory();
  const thumbnail = new File(THUMBNAIL_DIRECTORY, `${id}.jpg`);
  if (thumbnail.exists) {
    thumbnail.delete();
  }
  try {
    await TikLocalStorage.generateVideoThumbnail(videoUri, thumbnail.uri);
    await TikLocalStorage.excludeFromBackup(thumbnail.uri);
    return thumbnail.uri;
  } catch (error) {
    if (thumbnail.exists) {
      thumbnail.delete();
    }
    throw error;
  }
}

function normalizeKind(
  type?: string | null,
  mimeType?: string | null,
  filename?: string | null,
): LocalMediaKind | null {
  if (type === "image" || type === "video") {
    return type;
  }
  if (mimeType?.startsWith("image/")) {
    return "image";
  }
  if (mimeType?.startsWith("video/")) {
    return "video";
  }
  const extension = filename?.toLowerCase().split(".").pop() || "";
  if (["jpg", "jpeg", "png", "heic", "heif", "webp", "gif"].includes(extension)) {
    return "image";
  }
  if (["mp4", "mov", "m4v"].includes(extension)) {
    return "video";
  }
  return null;
}

function fileExtension(filename: string, mimeType: string): string {
  const match = filename.match(/\.[A-Za-z0-9]{1,8}$/);
  if (match) {
    return match[0].toLowerCase();
  }
  const subtype = mimeType.split("/")[1]?.split(";")[0];
  if (subtype && /^[A-Za-z0-9]{1,8}$/.test(subtype)) {
    return `.${subtype.toLowerCase().replace("quicktime", "mov")}`;
  }
  return "";
}

function defaultFilename(kind: LocalMediaKind, mimeType?: string | null) {
  return `Imported ${kind}${fileExtension("", mimeType || defaultMimeType(kind))}`;
}

function defaultMimeType(kind: LocalMediaKind) {
  return kind === "image" ? "image/jpeg" : "video/mp4";
}

function createMediaId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function rowToItem(row: LocalMediaRow): LocalMediaItem {
  return {
    duration: row.duration,
    filename: row.filename,
    height: row.height,
    id: row.id,
    importedAt: row.imported_at,
    kind: row.kind,
    mimeType: row.mime_type,
    size: row.size,
    source: row.source,
    thumbnailUri:
      row.thumbnail_uri && new File(row.thumbnail_uri).exists
        ? row.thumbnail_uri
        : null,
    uri: row.uri,
    width: row.width,
  };
}
