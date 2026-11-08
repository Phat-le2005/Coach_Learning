"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
type Theme = "light" | "dark";
const Appearance = createContext({ theme: "light" as Theme, toggleTheme: () => {} });
const STORAGE_KEY = "edums-student-home-theme";
export function HomeAppearance({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => {
    try { const stored = localStorage.getItem(STORAGE_KEY); if (stored === "dark" || stored === "light") setTheme(stored); }
    catch { /* Preference storage is optional. */ }
  }, []);
  function toggleTheme() {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    try { localStorage.setItem(STORAGE_KEY, next); } catch { /* Session-only preference. */ }
  }
  return <Appearance.Provider value={{ theme, toggleTheme }}>{children}</Appearance.Provider>;
}
export const useHomeAppearance = () => useContext(Appearance);
