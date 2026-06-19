// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState, type ReactNode } from "react";
import { MathJax } from "better-react-mathjax";
import { Logo } from "./Logo";
import { CreateCards } from "./CreateCards";
import { DeckPicker } from "./DeckPicker";
import { DeckBrowser } from "./DeckBrowser";
import { Settings } from "./Settings";
import {
  getDecks,
  getCards,
  syncNow,
  transcribe,
  grade,
  commit,
  Phase,
  Trans,
  Result,
  DeckNode,
} from "./api";

function Tex({ html, inline }: { html: string; inline?: boolean }) {
  return (
    <MathJax dynamic inline={inline}>
      <span dangerouslySetInnerHTML={{ __html: html }} />
    </MathJax>
  );
}

const NOTES = ["again", "hard", "good", "easy"];

function Chip({ type, color }: { type: string; color: string }) {
  return <span className={"chip " + color}>{type}</span>;
}

function CardTop({
  type,
  color,
  importance,
  mode,
}: {
  type: string;
  color: string;
  importance?: string;
  mode?: string;
}) {
  return (
    <div className="card-top">
      <Chip type={type} color={color} />
      {importance && <span className={"imp imp-" + importance}>{importance}</span>}
      {mode && <span className="meta">{mode}</span>}
    </div>
  );
}

function Bar({ children }: { children: ReactNode }) {
  return (
    <div className="nav">
      <div className="nav-inner">{children}</div>
    </div>
  );
}

export default function App() {
  const [phases, setPhases] = useState<Phase[] | null>(null);
  const [count, setCount] = useState(0);
  const [step, setStep] = useState<"prep" | "verify" | "results" | "done">("prep");
  const [trans, setTrans] = useState<Trans[]>([]);
  const [results, setResults] = useState<Result[]>([]);
  const [sent, setSent] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [view, setView] = useState<"review" | "create" | "decks" | "settings">("review");
  const [decks, setDecks] = useState<DeckNode | null>(null);
  const [chosenDeck, setChosenDeck] = useState<string | null>(null);
  const [syncMsg, setSyncMsg] = useState("");

  useEffect(() => {
    // Synchro AnkiWeb au démarrage (best-effort), puis chargement des decks.
    syncNow()
      .catch(() => {})
      .finally(() =>
        getDecks().then(setDecks).catch(() => setErr("Backend injoignable (lance `sapio serve`)."))
      );
  }, []);

  // Retour à l'accueil (choix des decks à réviser) depuis le logo.
  function goHome() {
    setView("review");
    setChosenDeck(null);
    setStep("prep");
    setErr("");
  }

  async function doSync() {
    setSyncMsg("Synchro…");
    const r = await syncNow().catch(() => ({ error: "réseau" }));
    setSyncMsg(r.error ? r.error : "Synchronisé ✓");
    try {
      setDecks(await getDecks());
    } catch {
      /* ignore */
    }
    setTimeout(() => setSyncMsg(""), 4000);
  }

  async function pickDeck(full: string) {
    setBusy(true);
    setErr("");
    try {
      const d = await getCards(full);
      setPhases(d.phases);
      setCount(d.count);
      setChosenDeck(full);
      setStep("prep");
    } catch {
      setErr("Chargement des cartes impossible.");
    }
    setBusy(false);
  }

  async function run<T>(fn: () => Promise<T>, after: (d: T) => void, msg: string) {
    setBusy(true);
    setErr("");
    try {
      after(await fn());
    } catch {
      setErr(msg);
    }
    setBusy(false);
  }

  return (
    <>
      <header className="appbar">
        <div className="appbar-inner">
          <button className="logo-btn" onClick={goHome} aria-label="Accueil" title="Accueil">
            <Logo />
          </button>
          <nav className="tabs">
            <button className={view === "review" ? "tab on" : "tab"} onClick={() => setView("review")}>
              Réviser
            </button>
            <button className={view === "create" ? "tab on" : "tab"} onClick={() => setView("create")}>
              Créer des cartes
            </button>
            <button className={view === "decks" ? "tab on" : "tab"} onClick={() => setView("decks")}>
              Decks
            </button>
            <button className={view === "settings" ? "tab on" : "tab"} onClick={() => setView("settings")}>
              Paramètres
            </button>
          </nav>
          <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: ".5rem" }}>
            {syncMsg && <span className="muted" style={{ fontSize: ".8rem" }}>{syncMsg}</span>}
            {view === "review" && count > 0 && (
              <span className="muted" style={{ fontSize: ".8rem" }}>{count} cartes</span>
            )}
            <button className="tab" onClick={doSync} title="Synchroniser avec AnkiWeb">↻ Sync</button>
          </span>
        </div>
      </header>
      <main className="wrap">
        {view === "settings" ? (
          <Settings />
        ) : view === "create" ? (
          <CreateCards onDone={() => location.assign("/")} />
        ) : view === "decks" ? (
          <DeckBrowser />
        ) : (
          <ReviewFlow
            {...{ phases, count, step, trans, results, sent, busy, err, run, setTrans, setResults, setSent, setStep }}
            decks={decks}
            chosenDeck={chosenDeck}
            onPick={pickDeck}
            onChangeDeck={() => { setChosenDeck(null); setStep("prep"); }}
          />
        )}
      </main>
    </>
  );
}

function ReviewFlow(props: any) {
  const { phases, count, step, trans, results, sent, busy, err, run,
    setTrans, setResults, setSent, setStep, decks, chosenDeck, onPick, onChangeDeck } = props;
  if (!chosenDeck) {
    return (
      <>
        {err && <p style={{ color: "var(--theo)" }}>{err}</p>}
        <DeckPicker tree={decks} onPick={onPick} />
      </>
    );
  }
  return (
    <>
        {err && <p style={{ color: "var(--theo)" }}>{err}</p>}
        <button className="tab" style={{ marginBottom: ".4rem", paddingLeft: 0 }} onClick={onChangeDeck}>
          ← Changer de deck
        </button>
        {!phases ? (
          <p className="spin">Chargement…</p>
        ) : count === 0 ? (
          <p className="lead">Aucune carte due dans ce deck.</p>
        ) : step === "prep" ? (
          <Prep
            phases={phases}
            busy={busy}
            onPhotos={(f) =>
              run(() => transcribe(f), (d) => { setTrans(d.transcriptions || []); setStep("verify"); }, "Échec de la transcription.")
            }
          />
        ) : step === "verify" ? (
          <Verify
            trans={trans}
            busy={busy}
            onGrade={(items) =>
              run(() => grade(items), (d) => { setResults(d.results || []); setStep("results"); }, "Échec de la notation.")
            }
          />
        ) : step === "results" ? (
          <Results
            results={results}
            busy={busy}
            onCommit={(notes) =>
              run(() => commit(notes), (d) => { setSent(d.sent || 0); setStep("done"); }, "Échec de l'envoi.")
            }
          />
        ) : (
          <Done sent={sent} />
        )}
    </>
  );
}

function Prep({ phases, busy, onPhotos }: { phases: Phase[]; busy: boolean; onPhotos: (f: File[]) => void }) {
  const [i, setI] = useState(0);
  const [files, setFiles] = useState<File[]>([]);
  const [urls, setUrls] = useState<string[]>([]);
  const steps = phases.length + 1;
  const onCapture = i === phases.length;

  // Aperçus : un object URL par photo, révoqués quand la liste change.
  useEffect(() => {
    const u = files.map((f) => URL.createObjectURL(f));
    setUrls(u);
    return () => u.forEach((x) => URL.revokeObjectURL(x));
  }, [files]);

  return (
    <div>
      <div className="dots">
        {Array.from({ length: steps }).map((_, k) => (
          <span key={k} className={"dot " + (k === i ? "active" : k < i ? "done" : "")} />
        ))}
      </div>
      {!onCapture ? (
        <>
          <h2>{phases[i].title}</h2>
          <p className="lead">Rédige chaque réponse sur papier en notant son numéro.</p>
          {phases[i].cards.map((c) => (
            <div key={c.numero} className="card">
              <CardTop type={c.type} color={c.color} importance={c.importance} />
              <div className="consigne">
                <span className="num">{c.numero}</span>
                <Tex html={c.consigne} inline />
              </div>
              {c.contexte && (
                <div className="ctx">
                  <div className="ctx-label">Énoncé de référence</div>
                  <Tex html={c.contexte} />
                </div>
              )}
              <div className="src"><Tex html={c.titre} inline /> · {c.lecon}</div>
            </div>
          ))}
        </>
      ) : (
        <>
          <h2>Photo de ta copie</h2>
          <p className="lead">
            Tout rédigé ? Ajoute une ou plusieurs photos de l'ensemble, depuis l'appareil
            ou la galerie. Tu peux en ajouter autant que nécessaire.
          </p>
          <div className="drop">
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={(e) => {
                const picked = Array.from(e.target.files || []);
                if (picked.length) setFiles((prev) => [...prev, ...picked]);
                e.target.value = ""; // permet de réajouter / reprendre une photo
              }}
            />
            <p className="muted">Appareil photo ou galerie.</p>
          </div>
          {files.length > 0 && (
            <div className="photos">
              {files.map((f, k) => (
                <div key={k} className="photo-item">
                  <img src={urls[k]} alt={`photo ${k + 1}`} />
                  <button
                    type="button"
                    aria-label="retirer"
                    onClick={() => setFiles(files.filter((_, j) => j !== k))}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
      <Bar>
        <button className="ghost" disabled={i === 0} onClick={() => setI(i - 1)}>← Précédent</button>
        <span className="grow" />
        {!onCapture ? (
          <button onClick={() => setI(i + 1)}>Suivant →</button>
        ) : (
          <button disabled={busy || files.length === 0} onClick={() => onPhotos(files)}>
            {busy ? "Lecture…" : "Lire ma copie"}
          </button>
        )}
      </Bar>
    </div>
  );
}

function Verify({ trans, busy, onGrade }: { trans: Trans[]; busy: boolean; onGrade: (items: { numero: number; traitee: boolean; lecture: string }[]) => void }) {
  const [edits, setEdits] = useState<Record<number, string>>(
    Object.fromEntries(trans.map((t) => [t.numero, t.lecture]))
  );
  return (
    <div>
      <h2>Vérifie ce que j'ai lu</h2>
      <p className="lead">Corrige une transcription si la lecture est fausse, puis lance la notation.</p>
      {trans.map((t) => (
        <div key={t.numero} className="card">
          <CardTop type={t.type} color={t.color} mode={t.mode} />
          <div className="consigne"><span className="num">{t.numero}</span><Tex html={t.titre} inline /></div>
          {!t.traitee ? (
            <p className="muted">Non traitée, laissée intacte.</p>
          ) : (
            <>
              <p className={"conf-" + t.confiance}>
                lecture : {t.confiance}{t.confiance === "haute" ? " ✓ probablement OK" : ""}
              </p>
              {t.doutes.map((d, k) => (
                <p key={k} className="doute">⚠️ {d.passage} · {d.question}</p>
              ))}
              <textarea
                value={edits[t.numero] ?? ""}
                onChange={(e) => setEdits({ ...edits, [t.numero]: e.target.value })}
              />
              <div className="preview"><Tex html={edits[t.numero] ?? ""} /></div>
            </>
          )}
        </div>
      ))}
      <Bar>
        <span className="grow" />
        <button disabled={busy} onClick={() => onGrade(trans.map((t) => ({ numero: t.numero, traitee: t.traitee, lecture: edits[t.numero] ?? t.lecture })))}>
          {busy ? "Notation…" : "Valider la lecture et noter"}
        </button>
      </Bar>
    </div>
  );
}

function Results({ results, busy, onCommit }: { results: Result[]; busy: boolean; onCommit: (notes: { numero: number; note: string }[]) => void }) {
  const graded = results.filter((r) => r.graded);
  const [notes, setNotes] = useState<Record<number, string>>(
    Object.fromEntries(graded.map((r) => [r.numero, r.note]))
  );
  return (
    <div>
      <h2>Résultats</h2>
      <p className="lead">Le feedback et la note proposée par carte. Ajuste la note si besoin.</p>
      <p className="muted" style={{ marginTop: "-0.7rem", marginBottom: "1.1rem", fontSize: "0.88rem" }}>
        L'IA évalue la justesse de ta réponse, pas l'effort qu'elle t'a coûté. Si une carte
        t'a demandé peu ou pas d'effort, passe-la en « easy » toi-même.
      </p>
      {results.map((r) => {
        const sel = notes[r.numero] || r.note;
        return (
          <div key={r.numero} className="card">
            <CardTop type={r.type} color={r.color} mode={r.mode} />
            <div className="consigne"><span className="num">{r.numero}</span><Tex html={r.titre} inline /></div>
            {!r.graded ? (
              <p className="muted">Non traitée, laissée intacte.</p>
            ) : (
              <>
                <div className="feedback"><Tex html={r.feedback} /></div>
                <div className="notes">
                  {NOTES.map((n) => (
                    <label key={n} className={sel === n ? "sel-" + n : ""}>
                      <input type="radio" name={"note_" + r.numero} checked={sel === n}
                        onChange={() => setNotes({ ...notes, [r.numero]: n })} />
                      {n}
                    </label>
                  ))}
                </div>
                {r.justification && <div className="justif"><Tex html={r.justification} /></div>}
              </>
            )}
          </div>
        );
      })}
      <Bar>
        <span className="grow" />
        <button disabled={busy} onClick={() => onCommit(graded.map((r) => ({ numero: r.numero, note: notes[r.numero] || r.note })))}>
          {busy ? "Envoi…" : "Valider la session"}
        </button>
      </Bar>
    </div>
  );
}

function Done({ sent }: { sent: number }) {
  return (
    <div className="center">
      <h2>Session validée ✓</h2>
      <p className="lead">{sent} carte(s) envoyée(s) à Anki, FSRS replanifie.</p>
      <p><a className="btn" href="/api/bilan.pdf" target="_blank" rel="noreferrer">Voir le bilan PDF</a></p>
      <p><a href="/">↺ Retour aux cartes du jour</a></p>
    </div>
  );
}
