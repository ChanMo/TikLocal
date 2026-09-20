package com.chanmo.tiklocal.storage

import android.media.MediaMetadataRetriever
import android.net.Uri
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.io.FileOutputStream

class TikLocalStorageModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("TikLocalStorage")

    AsyncFunction("excludeFromBackup") { _: String ->
      // Android app-private files are not part of iCloud Backup.
    }

    AsyncFunction("generateVideoThumbnail") { videoUri: String, outputUri: String ->
      val retriever = MediaMetadataRetriever()
      try {
        val videoPath = Uri.parse(videoUri).path
          ?: throw IllegalArgumentException("Expected a local video file URL")
        val outputPath = Uri.parse(outputUri).path
          ?: throw IllegalArgumentException("Expected a local output file URL")
        retriever.setDataSource(videoPath)
        val bitmap = retriever.getFrameAtTime(
          100_000,
          MediaMetadataRetriever.OPTION_CLOSEST_SYNC
        ) ?: throw IllegalStateException("Could not decode a video thumbnail")
        FileOutputStream(outputPath).use { stream ->
          if (!bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 82, stream)) {
            throw IllegalStateException("Could not encode a video thumbnail")
          }
        }
        outputUri
      } finally {
        retriever.release()
      }
    }
  }
}
