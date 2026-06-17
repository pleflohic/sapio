// SPDX-License-Identifier: AGPL-3.0-or-later
export interface Card {
  numero: number;
  card_id: number;
  type: string;
  color: string;
  mode: string;
  importance: string;
  consigne: string;
  contexte: string;
  titre: string;
  lecon: string;
}
export interface Phase {
  title: string;
  cards: Card[];
}
export interface Doubt {
  passage: string;
  question: string;
}
export interface Trans {
  numero: number;
  titre: string;
  type: string;
  color: string;
  mode: string;
  traitee: boolean;
  lecture: string;
  confiance: string;
  doutes: Doubt[];
}
export interface Result {
  numero: number;
  card_id: number;
  titre: string;
  type: string;
  color: string;
  mode: string;
  graded: boolean;
  feedback: string;
  note: string;
  justification: string;
}

export interface DeckNode {
  name: string;
  full: string;
  count: number;
  children: DeckNode[];
}

export async function getDecks(): Promise<DeckNode> {
  const r = await fetch("/api/decks");
  return r.json();
}

export async function syncNow(direction?: string): Promise<{ status?: string; error?: string }> {
  const r = await fetch("/api/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(direction ? { direction } : {}),
  });
  return r.json();
}

export async function getCards(deck?: string): Promise<{ count: number; phases: Phase[] }> {
  const r = await fetch("/api/cards" + (deck ? "?deck=" + encodeURIComponent(deck) : ""));
  return r.json();
}

export async function transcribe(files: File[]): Promise<{ transcriptions: Trans[] }> {
  const fd = new FormData();
  files.forEach((f) => fd.append("photos", f));
  const r = await fetch("/api/transcribe", { method: "POST", body: fd });
  return r.json();
}

export async function grade(
  items: { numero: number; traitee: boolean; lecture: string }[]
): Promise<{ results: Result[] }> {
  const r = await fetch("/api/grade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  return r.json();
}

export interface DeckEntry {
  chapitre: string;
  lecon: string;
  deck: string;
}
export interface Taxonomy {
  annees: string[];
  cours: Record<string, string[]>;
}
export interface GenResult {
  objects?: number;
  cards?: number;
  by_type?: Record<string, number>;
  pages?: number[];
  decks?: DeckEntry[];
  suggestion?: { annee: string; cours: string };
  taxonomy?: Taxonomy;
  error?: string;
}

export async function generate(file: File, pages: string): Promise<GenResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("pages", pages);
  const r = await fetch("/api/generate", { method: "POST", body: fd });
  return r.json();
}

export async function importCards(
  annee: string,
  cours: string,
  decks: DeckEntry[]
): Promise<{ added?: number; skipped?: number; decks?: string[]; error?: string }> {
  const r = await fetch("/api/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ annee, cours, decks }),
  });
  return r.json();
}

export interface Settings {
  provider: string;
  extract_model: string;
  review_model: string;
  dpi: number;
  collection: string;
}
export interface SecretStatus {
  anthropic: boolean;
  openrouter: boolean;
  ankiweb: boolean;
}
export interface SettingsResponse {
  settings: Settings;
  secrets: SecretStatus;
}

export async function getSettings(): Promise<SettingsResponse> {
  const r = await fetch("/api/settings");
  return r.json();
}

export async function saveSettings(s: Partial<Settings>): Promise<SettingsResponse> {
  const r = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(s),
  });
  return r.json();
}

export async function commit(
  notes: { numero: number; note: string }[]
): Promise<{ sent: number }> {
  const r = await fetch("/api/commit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
  return r.json();
}
