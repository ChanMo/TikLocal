import { registerWebModule, NativeModule } from 'expo';

// TikLocalStorageModule is not available on the web platform.
class TikLocalStorageModule extends NativeModule<{}> {
  async excludeFromBackup(_uri: string): Promise<void> {}

  async generateVideoThumbnail(
    _videoUri: string,
    _outputUri: string,
  ): Promise<string> {
    throw new Error("Video thumbnails are unavailable on web.");
  }
}

export default registerWebModule(TikLocalStorageModule, 'TikLocalStorageModule');
