import type { Config } from "tailwindcss";

/**
 * Tailwind config for AuRIS web. Uses the same validated dark-mode palette
 * as the Streamlit dashboard so the two interfaces are visually consistent
 * (see src/auris/... references/palette.md in the dataviz skill).
 */
const config: Config = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx}",
    "./src/components/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "var(--font-inter)",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
      },
      colors: {
        surface: {
          DEFAULT: "#1a1a19",
          raised: "#242422",
          border: "#2c2c2a",
        },
        ink: {
          primary: "#ffffff",
          secondary: "#c3c2b7",
          muted: "#898781",
        },
        // Validated dark-mode categorical palette.
        series: {
          1: "#3987e5", // blue
          2: "#199e70", // aqua
          3: "#c98500", // yellow
          4: "#008300", // green
          5: "#9085e9", // violet
          6: "#e66767", // red
          7: "#d55181", // magenta
          8: "#d95926", // orange
        },
        // Status (never themed with series colors).
        status: {
          good: "#0ca30c",
          warn: "#fab219",
          crit: "#d03b3b",
        },
      },
    },
  },
  plugins: [],
};

export default config;
