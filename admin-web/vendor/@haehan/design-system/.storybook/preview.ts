import type { Preview } from '@storybook/react';
import '../app/globals.css';

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    backgrounds: {
      default: 'light',
      values: [
        { name: 'light', value: '#F5F7FA' },
        { name: 'white', value: '#FFFFFF' },
        { name: 'navy', value: '#1E2D4A' },
      ],
    },
  },
};

export default preview;
