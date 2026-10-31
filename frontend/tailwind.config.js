/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        background: '#fafafa',
        paper: '#f5f5f5',
        ink: '#0f0f0f',
        card: '#ffffff',
        'card-hover': '#f5f5f5',
        border: '#e6e6e6',
        'border-subtle': '#efefef',
        'border-hover': '#cfcfcf',
        muted: '#6b6b6b',
      },
    },
  },
  plugins: [],
};
