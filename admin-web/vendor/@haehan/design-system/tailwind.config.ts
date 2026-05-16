import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        orange: {
          DEFAULT: '#F97316',
          hover:   '#EA580C',
          soft:    '#FFF7ED',
        },
        navy: {
          DEFAULT: '#1E2D4A',
          hover:   '#253661',
          soft:    '#EEF2F7',
        },
      },
      fontFamily: {
        sans: ['Pretendard', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
      },
      borderRadius: {
        sm:   '6px',
        md:   '8px',
        lg:   '12px',
      },
    },
  },
  plugins: [],
};

export default config;
