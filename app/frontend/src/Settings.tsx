// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from "react";
import { getSettings, saveSettings, Settings as Prefs, SecretStatus } from "./api";

const PROVIDERS = ["anthropic", "openrouter"];

function SecretRow({ label, ok, hint }: { label: string; ok: boolean; hint: string }) {
  return (
    <div className="secret-row">
      <span className="secret-name">{label}</span>
      <span className={ok ? "secret-ok" : "secret-no"}>{ok ? "✓ défini" : "✗ absent"}</span>
      <span className="muted secret-hint">{hint}</span>
    </div>
  );
}

export function Settings() {
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [secrets, setSecrets] = useState<SecretStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    getSettings()
      .then((r) => { setPrefs(r.settings); setSecrets(r.secrets); })
      .catch(() => setMsg("Backend injoignable."));
  }, []);

  function set<K extends keyof Prefs>(k: K, v: Prefs[K]) {
    if (prefs) setPrefs({ ...prefs, [k]: v });
  }

  async function save() {
    if (!prefs) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await saveSettings(prefs);
      setPrefs(r.settings);
      setSecrets(r.secrets);
      setMsg("Enregistré ✓");
    } catch {
      setMsg("Échec de l'enregistrement.");
    }
    setBusy(false);
    setTimeout(() => setMsg(""), 4000);
  }

  if (!prefs) return <p className="spin">{msg || "Chargement…"}</p>;

  return (
    <div className="settings">
      <h2>Paramètres</h2>
      <p className="lead">Préférences appliquées immédiatement, stockées dans <code>~/.config/sapio/settings.json</code>.</p>

      <label className="field">
        <span>Fournisseur</span>
        <select value={prefs.provider} onChange={(e) => set("provider", e.target.value)}>
          {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>

      <label className="field">
        <span>Modèle d'extraction</span>
        <input value={prefs.extract_model} onChange={(e) => set("extract_model", e.target.value)} />
      </label>

      <label className="field">
        <span>Modèle de notation</span>
        <input value={prefs.review_model} onChange={(e) => set("review_model", e.target.value)} />
      </label>

      <label className="field">
        <span>Résolution PDF (DPI)</span>
        <input type="number" value={prefs.dpi} onChange={(e) => set("dpi", Number(e.target.value))} />
      </label>

      <label className="field">
        <span>Chemin de la collection (.anki2)</span>
        <input value={prefs.collection} onChange={(e) => set("collection", e.target.value)}
          placeholder="ex. /home/.../collection.anki2" />
      </label>

      <div className="nav">
        <div className="nav-inner">
          {msg && <span className="muted">{msg}</span>}
          <span className="grow" />
          <button disabled={busy} onClick={save}>{busy ? "Enregistrement…" : "Enregistrer"}</button>
        </div>
      </div>

      <h3 style={{ marginTop: "2rem" }}>Secrets</h3>
      <p className="lead">
        Pour des raisons de sécurité, les clés et identifiants ne sont <strong>pas</strong> modifiables ici.
        Définis-les via variables d'environnement ou le fichier <code>.env</code>, puis relance le serveur.
      </p>
      {secrets && (
        <div className="secrets">
          <SecretRow label="Clé Anthropic" ok={secrets.anthropic} hint="ANTHROPIC_API_KEY" />
          <SecretRow label="Clé OpenRouter" ok={secrets.openrouter} hint="OPENROUTER_API_KEY" />
          <SecretRow label="Compte AnkiWeb" ok={secrets.ankiweb} hint="ANKIWEB_USERNAME / ANKIWEB_PASSWORD" />
        </div>
      )}
    </div>
  );
}
