import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { navy: { 950: "#060b18", 900: "#0a1124", 800: "#101a33", 700: "#1a2749" } },
    },
  },
  plugins: [],
} satisfies Config;
