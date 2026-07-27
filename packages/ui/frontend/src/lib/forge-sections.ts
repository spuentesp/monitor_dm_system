import {
  BookOpen,
  Camera,
  ClipboardCheck,
  Compass,
  Globe2,
  LayoutDashboard,
  LayoutTemplate,
  MessageSquareText,
  Network,
  Package,
  Palette,
  Upload,
} from "lucide-react";

// ─── Forge section nav (F1-1 · target IA) ─────────────────────
// Shared between app/forge/layout.tsx (a Next Layout may not export extra
// fields) and its tests.

export type ForgeAccent = "cyan" | "purple" | "emerald";

export interface ForgeSection {
  href: string;
  label: string;
  icon: typeof Globe2;
  accent: ForgeAccent;
  /** Extra path prefixes that belong to this section (nested routes). */
  aliases?: string[];
}

export const FORGE_SECTIONS: ForgeSection[] = [
  { href: "/forge",           label: "Overview",     icon: LayoutDashboard, accent: "cyan"    },
  { href: "/forge/worlds",    label: "Worlds",       icon: Globe2,          accent: "purple"  },
  { href: "/forge/ontology",  label: "Ontology",     icon: Network,         accent: "cyan"    },
  { href: "/forge/architect", label: "Architect",    icon: Compass,         accent: "purple"  },
  { href: "/forge/ingest",    label: "Ingest Studio", icon: Upload,         accent: "cyan"    },
  { href: "/forge/packs",     label: "Packs",        icon: Package,         accent: "cyan",
    aliases: ["/forge/apply", "/forge/editor"] },
  { href: "/forge/review",    label: "Canon Review", icon: ClipboardCheck,  accent: "emerald" },
  { href: "/forge/systems",   label: "Systems",      icon: BookOpen,        accent: "purple"  },
  { href: "/forge/style",     label: "Style",        icon: Palette,         accent: "cyan"    },
  { href: "/forge/templates", label: "Templates",    icon: LayoutTemplate,  accent: "purple"  },
  { href: "/forge/prompts",   label: "Prompts",      icon: MessageSquareText, accent: "emerald" },
  { href: "/forge/snapshots", label: "Snapshots",    icon: Camera,          accent: "cyan"    },
];

export function isForgeSectionActive(section: ForgeSection, pathname: string): boolean {
  if (section.href === "/forge") return pathname === "/forge";
  if (pathname.startsWith(section.href)) return true;
  return (section.aliases ?? []).some((a) => pathname.startsWith(a));
}
