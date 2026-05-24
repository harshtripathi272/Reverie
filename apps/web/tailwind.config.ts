import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Reverie palette — drawn from the SRS section 8 spec.
        goal: "#7C3AED",
        tool: "#0EA5E9",
        memory: "#10B981",
        retry: "#F59E0B",
        failure: "#EF4444",
        reflection: "#8B5CF6",
        subagent: "#06B6D4",
        validate: "#22C55E",
        bg: "#000000",
        glass: "rgba(0, 0, 0, 0.6)",
        // Border for glass panels — barely-there rim light.
        rim: "rgba(255, 255, 255, 0.06)",
      },
      fontFamily: {
        // System UI stack; we don't ship a webfont yet.
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      backdropBlur: {
        glass: "12px",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.4s ease-out forwards",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
