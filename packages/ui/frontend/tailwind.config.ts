import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        neon: {
          cyan: "#00d4ff",
          purple: "#a855f7",
          emerald: "#10b981",
          amber: "#f59e0b",
          red: "#ef4444",
        },
        bg: {
          deep: "#05050a",
          panel: "#0a0a14",
          card: "#0d0d1e",
          hover: "#111128",
        },
        border: {
          DEFAULT: "rgba(0, 212, 255, 0.12)",
          dim: "rgba(255, 255, 255, 0.06)",
          purple: "rgba(168, 85, 247, 0.2)",
          emerald: "rgba(16, 185, 129, 0.2)",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "ui-monospace", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s ease-in-out infinite",
        "glow-pulse": "glow-pulse 2s ease-in-out infinite",
        "scan": "scan 8s linear infinite",
        "fade-in": "fade-in 0.3s ease-out",
        "slide-in": "slide-in 0.25s ease-out",
        "dot-blink": "dot-blink 1.4s ease-in-out infinite",
      },
      keyframes: {
        "glow-pulse": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.4" },
        },
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in": {
          "0%": { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "dot-blink": {
          "0%, 80%, 100%": { opacity: "0" },
          "40%": { opacity: "1" },
        },
      },
      boxShadow: {
        "cyan-glow": "0 0 20px rgba(0, 212, 255, 0.15), 0 0 60px rgba(0, 212, 255, 0.04)",
        "cyan-glow-lg": "0 0 40px rgba(0, 212, 255, 0.2), 0 0 80px rgba(0, 212, 255, 0.06)",
        "purple-glow": "0 0 20px rgba(168, 85, 247, 0.15), 0 0 60px rgba(168, 85, 247, 0.04)",
        "emerald-glow": "0 0 20px rgba(16, 185, 129, 0.15)",
        "card": "0 4px 24px rgba(0, 0, 0, 0.4), 0 1px 0 rgba(255,255,255,0.03) inset",
      },
      backdropBlur: {
        xs: "2px",
      },
      opacity: {
        "2": "0.02",
        "3": "0.03",
        "4": "0.04",
        "6": "0.06",
        "7": "0.07",
        "8": "0.08",
        "12": "0.12",
      },
    },
  },
  plugins: [],
};

export default config;
