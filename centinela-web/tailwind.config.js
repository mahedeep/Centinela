/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Azul petróleo: color de acento para acciones.
        petrol: {
          50: '#eef6f8', 100: '#d4e8ed', 200: '#a9d1db', 300: '#74b2c2',
          400: '#448ea3', 500: '#2a7288', 600: '#1d5b70', 700: '#17495a',
          800: '#123a48', 900: '#0e2d38',
        },
        // Semáforo: siempre acompañado de ícono y texto, jamás color solo.
        verdict: { ok: '#15803d', warn: '#b45309', bad: '#b91c1c' },
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
