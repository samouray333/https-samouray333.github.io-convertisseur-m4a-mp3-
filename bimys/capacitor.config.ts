import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.qmtech.bimys',
  appName: 'Bimys',
  webDir: 'dist',
  android: { allowMixedContent: false, backgroundColor: '#0f4c5c' },
  plugins: {
    SplashScreen: { launchShowDuration: 1200, launchAutoHide: true, backgroundColor: '#0f4c5c', androidScaleType: 'CENTER_CROP', showSpinner: false },
  },
};

export default config;
