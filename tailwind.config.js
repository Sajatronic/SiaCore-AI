/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // SiaCore brand palette (from brand guide)
        navy: '#0B132B',       // Deep Navy - dark bg base
        royal: '#2563EB',      // Royal Blue - primary
        teal: '#00C2AB',       // Teal - accent / positive
        violet: '#7C3AED',     // Violet - accent / secondary
        magenta: '#D946EF',    // Magenta - accent / alert
        slate: '#64748B',      // Slate Gray - muted text/borders
        soft: '#F8FAFC',       // Soft White - light bg / dark-mode text
      },
      fontFamily: {
        display: ['Sora', 'sans-serif'],
        body: ['Outfit', 'sans-serif'],
      },
      backgroundImage: {
        'aurora-flow': 'linear-gradient(90deg, #00C2AB 0%, #2563EB 55%, #D946EF 100%)',
        'ocean-intel': 'linear-gradient(90deg, #00C2AB 0%, #2563EB 55%, #7C3AED 100%)',
        'sunset-insight': 'linear-gradient(90deg, #7C3AED 0%, #D946EF 55%, #FF8A3D 100%)',
      },
      boxShadow: {
        glow: '0 0 24px rgba(37, 99, 235, 0.35)',
      },
    },
  },
  plugins: [],
}
