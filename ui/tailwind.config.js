/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        void: '#07111F',
        tactical: 'rgba(11, 24, 43, 0.86)',
        cyan: {
          arc: '#4DA3FF',
          glow: 'rgba(77, 163, 255, 0.25)',
        },
        gold: {
          reactor: '#FF8A1F',
          glow: 'rgba(255, 138, 31, 0.25)',
        },
        cyber: '#1C3B62',
        ice: '#F1F7FF',
        steel: '#7D9AB8',
        crimson: '#FF3B5C',
      },
      fontFamily: {
        mono: ['Fira Code', 'JetBrains Mono', 'Courier New', 'monospace'],
        hud: ['Orbitron', 'Rajdhani', 'Inter', 'sans-serif'],
      },
      boxShadow: {
        'arc-glow': '0 0 15px rgba(77, 163, 255, 0.25)',
        'arc-glow-lg': '0 0 25px rgba(77, 163, 255, 0.4)',
        'reactor-glow': '0 0 15px rgba(255, 138, 31, 0.25)',
        'crimson-glow': '0 0 15px rgba(255, 59, 92, 0.3)',
      },
      animation: {
        'spin-slow': 'spin 12s linear infinite',
        'spin-reverse': 'spin-reverse 16s linear infinite',
        'pulse-glow': 'pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'scanline': 'scanline 8s linear infinite',
      },
      keyframes: {
        'spin-reverse': {
          '0%': { transform: 'rotate(360deg)' },
          '100%': { transform: 'rotate(0deg)' },
        },
        'pulse-glow': {
          '0%, 100%': { opacity: 0.9, filter: 'drop-shadow(0 0 8px rgba(77,163,255,0.4))' },
          '50%': { opacity: 0.5, filter: 'drop-shadow(0 0 2px rgba(77,163,255,0.1))' },
        },
        'scanline': {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(1000%)' },
        },
      },
    },
  },
  plugins: [],
}
