import { useEffect } from "react";
import { useUIStore } from "@/store";

/** Registers the ⌘K / Ctrl+K global shortcut to open the command palette. */
export function useCommandPalette() {
  const { openCommandPalette, commandPaletteOpen, closeCommandPalette } = useUIStore();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (commandPaletteOpen) {
          closeCommandPalette();
        } else {
          openCommandPalette();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [commandPaletteOpen, openCommandPalette, closeCommandPalette]);
}
