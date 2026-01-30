/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                // Custom dark theme palette
                background: '#020617', // slate-950
                surface: '#0f172a',    // slate-900
                'surface-highlight': '#1e293b', // slate-800
                primary: '#7c3aed',    // violet-600
                'primary-hover': '#6d28d9', // violet-700
                secondary: '#c026d3',  // fuchsia-600
            },
            animation: {
                'fadeIn': 'fadeIn 0.3s ease-out forwards',
            },
            keyframes: {
                fadeIn: {
                    '0%': { opacity: '0', transform: 'translateY(10px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
            },
        },
    },
    plugins: [],
}
