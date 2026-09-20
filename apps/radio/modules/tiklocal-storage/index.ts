// Re-export the native module. On web, it will be resolved to TikLocalStorageModule.web.ts
// and on native platforms to TikLocalStorageModule.ts
export { default } from './src/TikLocalStorageModule';
