// SPDX-License-Identifier: AGPL-3.0-or-later
import { useState } from "react";
import { generate, importCards, DeckEntry, GenResult } from "./api";

export function CreateCards({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [pages, setPages] = useState("");
  const [phase, setPhase] = useState<"form" | "loading" | "review" | "done">("form");
  const [gen, setGen] = useState<GenResult | null>(null);
  const [decks, setDecks] = useState<DeckEntry[]>([]);
  const [annee, setAnnee] = useState("");
  const [cours, setCours] = useState("");
  const [done, setDone] = useState<{ added?: number; skipped?: number }>({});
  const [err, setErr] = useState("");

  async function runGenerate() {
    if (!file) return;
    setPhase("loading");
    setErr("");
    const d = await generate(file, pages.trim() || "all");
    if (d.error) {
      setErr(d.error);
      setPhase("form");
      return;
    }
    setGen(d);
    setDecks(d.decks || []);
    setAnnee(d.suggestion?.annee || "");
    setCours(d.suggestion?.cours || "");
    setPhase("review");
  }

  async function runImport() {
    if (!annee.trim() || !cours.trim()) {
      setErr("Renseigne l'année et le cours.");
      return;
    }
    setErr("");
    const d = await importCards(annee.trim(), cours.trim(), decks);
    if (d.error) {
      setErr(d.error);
      return;
    }
    setDone({ added: d.added, skipped: d.skipped });
    setPhase("done");
  }

  if (phase === "loading")
    return (
      <div className="center">
        <h2>Lecture du poly…</h2>
        <p className="lead">
          Le modèle lit les pages et en extrait la structure. Ça peut prendre une minute.
        </p>
      </div>
    );

  if (phase === "done")
    return (
      <div className="center">
        <h2>Cartes créées ✓</h2>
        <p className="lead">
          {done.added} carte(s) ajoutée(s) à Anki
          {done.skipped ? `, ${done.skipped} ignorée(s) (doublons)` : ""}.
        </p>
        <p>
          <button className="ghost" onClick={() => setPhase("form")}>
            Créer d'autres cartes
          </button>{" "}
          <button onClick={onDone}>Aller réviser</button>
        </p>
      </div>
    );

  if (phase === "review")
    return (
      <div>
        <h2>Structure détectée</h2>
        <p className="lead">
          {gen?.objects} objets → <b>{gen?.cards} cartes</b>
          {gen?.by_type
            ? " · " +
              Object.entries(gen.by_type)
                .map(([t, n]) => `${n} ${t}`)
                .join(" · ")
            : ""}
          {gen?.pages ? ` · pages ${gen.pages[0]}–${gen.pages[1]}` : ""}
        </p>
        <p className="lead">
          Vérifie le découpage en sous-decks. Renomme un <code>deck</code>, ou donne le
          <b> même</b> chemin à plusieurs parties pour les fusionner.
        </p>
        <div className="card">
          <div className="meta" style={{ marginBottom: ".5rem" }}>
            Rangement (suggéré par Claude — choisis un existant ou tape un nouveau)
          </div>
          <label className="ctx-label">Année</label>
          <input
            list="annees" type="text" value={annee} placeholder="ex. Master 1"
            onChange={(e) => setAnnee(e.target.value)}
            style={{ width: "100%", padding: ".5rem .6rem", borderRadius: 8, border: "1px solid var(--line-strong)", marginBottom: ".6rem" }}
          />
          <datalist id="annees">
            {(gen?.taxonomy?.annees || []).map((a) => <option key={a} value={a} />)}
          </datalist>
          <label className="ctx-label">Cours</label>
          <input
            list="cours" type="text" value={cours} placeholder="ex. Probabilités"
            onChange={(e) => setCours(e.target.value)}
            style={{ width: "100%", padding: ".5rem .6rem", borderRadius: 8, border: "1px solid var(--line-strong)" }}
          />
          <datalist id="cours">
            {((gen?.taxonomy?.cours && gen.taxonomy.cours[annee]) ||
              Array.from(new Set(Object.values(gen?.taxonomy?.cours || {}).flat()))
            ).map((co) => <option key={co} value={co} />)}
          </datalist>
          <div className="meta" style={{ marginTop: ".6rem" }}>
            → <b>{annee || "Année"}::{cours || "Cours"}</b>::&lt;chapitre&gt;::&lt;partie&gt;
          </div>
        </div>
        {decks.map((d, i) => (
          <div key={i} className="card">
            <div className="meta">
              {d.chapitre} › {d.lecon}
            </div>
            <input
              type="text"
              value={d.deck}
              onChange={(e) => {
                const next = decks.slice();
                next[i] = { ...d, deck: e.target.value };
                setDecks(next);
              }}
              style={{ width: "100%", marginTop: ".4rem", padding: ".5rem .6rem", borderRadius: 8, border: "1px solid var(--line-strong)", fontFamily: "ui-monospace, monospace", fontSize: ".9rem" }}
            />
          </div>
        ))}
        {err && <p style={{ color: "var(--theo)" }}>{err}</p>}
        <div className="nav">
          <div className="nav-inner">
            <button className="ghost" onClick={() => setPhase("form")}>
              ← Recommencer
            </button>
            <span className="grow" />
            <button onClick={runImport}>Importer dans Anki ({decks.length} sous-decks)</button>
          </div>
        </div>
      </div>
    );

  // form
  return (
    <div>
      <h2>Créer des cartes depuis un poly</h2>
      <p className="lead">
        Choisis un PDF de cours et, idéalement, une plage de pages (un chapitre à la fois —
        la lecture coûte et prend du temps).
      </p>
      <div className="drop">
        <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        {file && <p className="muted">{file.name}</p>}
      </div>
      <div className="card">
        <label className="ctx-label">Pages (ex. « 8-17 », ou vide = tout le poly)</label>
        <input
          type="text"
          value={pages}
          placeholder="8-17"
          onChange={(e) => setPages(e.target.value)}
          style={{ width: "100%", padding: ".5rem .6rem", borderRadius: 8, border: "1px solid var(--line-strong)" }}
        />
      </div>
      {err && <p style={{ color: "var(--theo)" }}>{err}</p>}
      <div className="nav">
        <div className="nav-inner">
          <span className="grow" />
          <button disabled={!file} onClick={runGenerate}>
            Générer les cartes
          </button>
        </div>
      </div>
    </div>
  );
}
