import { useCallback, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { VakedGraph } from "@/types/graph";
import { useGraphStore } from "@/store";

const PARSE_DEBOUNCE_MS = 500;

export function useVakedc() {
  const setGraph = useGraphStore((s) => s.setGraph);
  const setFilePath = useGraphStore((s) => s.setFilePath);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const parseFile = useCallback(async (filePath: string) => {
    try {
      const json = await invoke<string>("parse_vaked", { filePath });
      const graph: VakedGraph = JSON.parse(json);
      setGraph(graph);
      setFilePath(filePath);
    } catch (err) {
      console.error("parse_vaked failed:", err);
    }
  }, [setGraph, setFilePath]);

  const parseFileDebounced = useCallback((filePath: string) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => parseFile(filePath), PARSE_DEBOUNCE_MS);
  }, [parseFile]);

  const checkFile = useCallback(async (filePath: string): Promise<string> => {
    try {
      return await invoke<string>("check_vaked_raw", { filePath });
    } catch {
      return '{"diagnostics":[]}';
    }
  }, []);

  const lowerFile = useCallback(async (filePath: string, outDir: string): Promise<string[]> => {
    return invoke<string[]>("lower_vaked", { filePath, outDir });
  }, []);

  return { parseFile, parseFileDebounced, checkFile, lowerFile };
}
