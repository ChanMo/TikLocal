import ExpoModulesCore
import AVFoundation
import Foundation
import UIKit

public class TikLocalStorageModule: Module {
  public func definition() -> ModuleDefinition {
    Name("TikLocalStorage")

    AsyncFunction("excludeFromBackup") { (uri: String) throws in
      guard var url = URL(string: uri), url.isFileURL else {
        throw InvalidFileURLException(uri)
      }
      var values = URLResourceValues()
      values.isExcludedFromBackup = true
      try url.setResourceValues(values)
    }

    AsyncFunction("generateVideoThumbnail") { (videoUri: String, outputUri: String) throws -> String in
      guard let videoURL = URL(string: videoUri), videoURL.isFileURL else {
        throw InvalidFileURLException(videoUri)
      }
      guard let outputURL = URL(string: outputUri), outputURL.isFileURL else {
        throw InvalidFileURLException(outputUri)
      }

      let asset = AVURLAsset(url: videoURL)
      let generator = AVAssetImageGenerator(asset: asset)
      generator.appliesPreferredTrackTransform = true
      generator.maximumSize = CGSize(width: 640, height: 640)
      let image = try generator.copyCGImage(
        at: CMTime(seconds: 0.1, preferredTimescale: 600),
        actualTime: nil
      )
      guard let data = UIImage(cgImage: image).jpegData(compressionQuality: 0.82) else {
        throw ThumbnailEncodingException()
      }
      try data.write(to: outputURL, options: .atomic)
      return outputURL.absoluteString
    }
  }
}

private class ThumbnailEncodingException: Exception {
  override var reason: String {
    "Could not encode the video thumbnail."
  }
}

private class InvalidFileURLException: GenericException<String> {
  override var reason: String {
    "Expected a local file URL, received: \(param)"
  }
}
