import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Dark backgrounds
        dark: {
          950: '#06070a',
          900: '#0a0c10',
          850: '#0d0f14',
          800: '#0f1117',
          750: '#12141b',
          700: '#161820',
          650: '#1a1d26',
          600: '#1e212b',
          500: '#252830',
          400: '#2d3040',
          300: '#3a3d4e',
        },
        // Profit green
        profit: {
          DEFAULT: '#00d084',
          light: '#33e0a0',
          dark: '#00a368',
          muted: 'rgba(0, 208, 132, 0.15)',
          border: 'rgba(0, 208, 132, 0.3)',
        },
        // Loss red
        loss: {
          DEFAULT: '#ef4444',
          light: '#f87171',
          dark: '#b91c1c',
          muted: 'rgba(239, 68, 68, 0.15)',
          border: 'rgba(239, 68, 68, 0.3)',
        },
        // Info blue
        info: {
          DEFAULT: '#3b82f6',
          light: '#60a5fa',
          dark: '#1d4ed8',
          muted: 'rgba(59, 130, 246, 0.15)',
          border: 'rgba(59, 130, 246, 0.3)',
        },
        // Warning yellow
        warning: {
          DEFAULT: '#f59e0b',
          light: '#fbbf24',
          dark: '#b45309',
          muted: 'rgba(245, 158, 11, 0.15)',
          border: 'rgba(245, 158, 11, 0.3)',
        },
        // Accent purple
        accent: {
          DEFAULT: '#8b5cf6',
          light: '#a78bfa',
          dark: '#6d28d9',
          muted: 'rgba(139, 92, 246, 0.15)',
        },
        // Text
        text: {
          primary: '#e2e8f0',
          secondary: '#94a3b8',
          muted: '#64748b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.3s ease-in-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
