// SPDX-License-Identifier: AGPL-3.0-or-later
import { useState } from "react";
import { generate, importCards, DeckEntry, GenResult } from "./api";

// Niveaux de maîtrise initiaux (du neuf à l'acquis). « Neuf » = aucun amorçage,
// la carte reste neuve. Les autres préinitialisent la mémoire FSRS côté serveur.
const LEVELS: { value: string; label: string }[] = [
  { value: "neuf", label: "Neuf" },
  { value: "vu", label: "Vu" },
  { value: "correct", label: "Correct" },
  { value: "solide", label: "Solide" },
  { value: "acquis", label: "Acquis" },
];

export function CreateCards({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [pages, setPages] = useState("");
  const [phase, setPhase] = useState<"form" | "loading" | "review" | "done">("form");
  const [gen, setGen] = useState<GenResult | null>(null);
  const [decks, setDecks] = useState<DeckEntry[]>([]);
  const [annee, setAnnee] = useState("");
  const [cours, setCours] = useState("");
  const [done, setDone] = useState<{ added?: number; skipped?: number; seeded?: number }>({});
  const [prog, setProg] = useState<{ done: number; total: number } | null>(null);
  const [err, setErr] = useState("");

  async function runGenerate() {
    if (!file) return;
    setPhase("loading");
    setErr("");
    setProg(null);
    const d = await generate(file, pages.trim() || "all", (done, total) =>
      setProg({ done, total })
    );
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
    setDone({ added: d.added, skipped: d.skipped, seeded: d.seeded });
    setPhase("done");
  }

  if (phase === "loading")
    return (
      <div className="center">
        <h2>Lecture du poly…</h2>
        <p className="lead">
          Le modèle lit les pages et en extrait la structure. Ça peut prendre
          quelques minutes sur un gros poly.
        </p>
        {prog && prog.total > 0 && (
          <p className="lead">
            Lot {Math.min(prog.done + 1, prog.total)} / {prog.total}
          </p>
        )}
      </div>
    );

  if (phase === "done")
    return (
      <div className="center">
        <h2>Cartes créées ✓</h2>
        <p className="lead">
          {done.added} carte(s) ajoutée(s) à Anki
          {done.skipped ? `, ${done.skipped} ignorée(s) (doublons)` : ""}
          {done.seeded ? `, dont ${done.seeded} préinitialisée(s) à un niveau de maîtrise` : ""}.
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
          {gen?.pages ? ` · pages ${gen.pages[0]} à ${gen.pages[1]}` : ""}
        </p>
        {gen?.failed && gen.failed.length > 0 && (
          <p style={{ color: "var(--exo)" }}>
            ⚠️ {gen.failed.length} lot(s) de pages non lus (
            {gen.failed.map((b) => `${b.pages[0]} à ${b.pages[1]}`).join(", ")}
            ). Relance ces pages séparément si besoin.
          </p>
        )}
        <p className="lead">
          Vérifie le découpage en sous-decks. Renomme un <code>deck</code>, ou donne le
          <b> même</b> chemin à plusieurs parties pour les fusionner. Le <b>niveau</b>{" "}
          préinitialise ta maîtrise : laisse <b>Neuf</b> pour repartir de zéro, ou monte
          le curseur (Vu, Correct, Solide, Acquis) pour les parties que tu connais déjà,
          FSRS espacera d'autant les premières révisions.
        </p>
        <div className="card">
          <div className="meta" style={{ marginBottom: ".5rem" }}>
            Rangement (suggéré par Claude, choisis un existant ou tape un nouveau)
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
            <div style={{ display: "flex", gap: ".5rem", marginTop: ".4rem" }}>
              <input
                type="text"
                value={d.deck}
                onChange={(e) => {
                  const next = decks.slice();
                  next[i] = { ...d, deck: e.target.value };
                  setDecks(next);
                }}
                style={{ flex: 1, padding: ".5rem .6rem", borderRadius: 8, border: "1px solid var(--line-strong)", fontFamily: "ui-monospace, monospace", fontSize: ".9rem" }}
              />
              <select
                value={d.level || "neuf"}
                onChange={(e) => {
                  const next = decks.slice();
                  next[i] = { ...d, level: e.target.value };
                  setDecks(next);
                }}
                title="Niveau de maîtrise initial"
                style={{ padding: ".5rem .6rem", borderRadius: 8, border: "1px solid var(--line-strong)", background: "var(--bg)", color: "inherit" }}
              >
                {LEVELS.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>
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
        Choisis un PDF de cours. Laisse le champ pages vide pour tout le poly (il
        sera découpé automatiquement en lots), ou précise une plage pour ne
        traiter qu'un chapitre. La lecture coûte et prend un peu de temps.
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
