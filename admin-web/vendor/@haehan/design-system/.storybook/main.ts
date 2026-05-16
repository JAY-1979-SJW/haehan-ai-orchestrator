import type { StorybookConfig } from '@storybook/react-vite';
import path from 'path';

const config: StorybookConfig = {
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: [
    '@storybook/addon-essentials',
  ],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  viteFinal: async (config) => {
    config.resolve = config.resolve ?? {};
    config.resolve.alias = {
      ...(config.resolve.alias as Record<string, string>),
      '@standard-ui': path.resolve(__dirname, '../src/standard-ui/index.ts'),
      '@standard-ui/components/tables/ConstructionPhaseTable': path.resolve(
        __dirname,
        '../src/standard-ui/components/tables/ConstructionPhaseTable.tsx'
      ),
    };
    return config;
  },
};

export default config;
