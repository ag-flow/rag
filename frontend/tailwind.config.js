/**
 * @type {import('tailwindcss').Config}
 *
 * Toutes les couleurs pointent vers la feuille de tokens
 * (src/styles/tokens.css) — enabler « Fondations CSS » 75058a6a.
 * Les palettes Tailwind historiques (slate, sky, emerald, amber, rose…) sont
 * REMAPPÉES sur les rampes de rôle : changer une rampe dans tokens.css
 * propage la couleur à tous les écrans sans autre modification.
 */

/** Rampe de rôle → objet Tailwind 50…900 composable en opacité. */
function ramp(role) {
  const steps = {};
  for (const step of [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]) {
    steps[step] = `rgb(var(--${role}-${step}) / <alpha-value>)`;
  }
  return steps;
}

const neutral = ramp("neutral");
const accent = ramp("accent");
const success = ramp("success");
const warning = ramp("warning");
const danger = ramp("danger");

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Rampes de rôle (usage recommandé pour le nouveau code).
        neutral,
        accent,
        success,
        warning,
        danger,

        // Alias des palettes Tailwind présentes dans le code existant —
        // même source de vérité, zéro écran à retoucher.
        slate: neutral,
        gray: neutral,
        zinc: neutral,
        stone: neutral,
        sky: accent,
        blue: accent,
        indigo: accent,
        violet: accent,
        emerald: success,
        green: success,
        teal: success,
        amber: warning,
        orange: warning,
        yellow: warning,
        rose: danger,
        red: danger,

        // Tokens sémantiques shadcn/ui.
        border: "rgb(var(--neutral-200) / <alpha-value>)",
        input: "rgb(var(--neutral-200) / <alpha-value>)",
        ring: "rgb(var(--accent-600) / <alpha-value>)",
        background: "rgb(var(--surface-0) / <alpha-value>)",
        foreground: "rgb(var(--neutral-900) / <alpha-value>)",
        primary: {
          DEFAULT: "rgb(var(--accent-600) / <alpha-value>)",
          foreground: "rgb(var(--surface-0) / <alpha-value>)",
        },
        secondary: {
          DEFAULT: "rgb(var(--neutral-100) / <alpha-value>)",
          foreground: "rgb(var(--neutral-900) / <alpha-value>)",
        },
        destructive: {
          DEFAULT: "rgb(var(--danger-600) / <alpha-value>)",
          foreground: "rgb(var(--surface-0) / <alpha-value>)",
        },
        muted: {
          DEFAULT: "rgb(var(--neutral-100) / <alpha-value>)",
          foreground: "rgb(var(--neutral-500) / <alpha-value>)",
        },
        popover: {
          DEFAULT: "rgb(var(--surface-0) / <alpha-value>)",
          foreground: "rgb(var(--neutral-900) / <alpha-value>)",
        },
        card: {
          DEFAULT: "rgb(var(--surface-0) / <alpha-value>)",
          foreground: "rgb(var(--neutral-900) / <alpha-value>)",
        },
      },
      fontFamily: {
        display: "var(--font-display)",
        sans: "var(--font-body)",
        mono: "var(--font-mono)",
      },
      fontSize: {
        xs: ["var(--text-xs)", { lineHeight: "var(--leading-xs)" }],
        sm: ["var(--text-sm)", { lineHeight: "var(--leading-sm)" }],
        base: ["var(--text-base)", { lineHeight: "var(--leading-base)" }],
        lg: ["var(--text-lg)", { lineHeight: "var(--leading-lg)" }],
        xl: ["var(--text-xl)", { lineHeight: "var(--leading-xl)" }],
        "2xl": ["var(--text-2xl)", { lineHeight: "var(--leading-2xl)" }],
        "3xl": ["var(--text-3xl)", { lineHeight: "var(--leading-3xl)" }],
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
      },
      boxShadow: {
        sm: "var(--shadow-1)",
        DEFAULT: "var(--shadow-1)",
        md: "var(--shadow-2)",
        lg: "var(--shadow-3)",
      },
    },
  },
  plugins: [],
};
