import { NativeModule, requireNativeModule } from 'expo';

declare class TikLocalStorageModule extends NativeModule<{}> {
  excludeFromBackup(uri: string): Promise<void>;
  generateVideoThumbnail(videoUri: string, outputUri: string): Promise<string>;
}

export default requireNativeModule<TikLocalStorageModule>('TikLocalStorage');
