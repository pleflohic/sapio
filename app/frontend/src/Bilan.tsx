// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from "react";
import { getBilan, Bilan as BilanData } from "./api";

const NOTE_LABELS: { key: "again" | "hard" | "good" | "easy"; label: string }[] = [
  { key: "again", label: "Again" },
  { key: "hard", label: "Hard" },
  { key: "good", label: "Good" },
  { key: "easy", label: "Easy" },
];

export function Bilan() {
  const [data, setData] = useState<BilanData | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    getBilan()
      .then(setData)
      .catch(() => setErr("Chargement du bilan impossible."));
  }, []);

  if (err) return <p style={{ color: "var(--theo)" }}>{err}</p>;
  if (!data) return <p className="spin">Chargement du bilan…</p>;
  if (data.total === 0)
    return (
      <div>
        <h2>Bilan</h2>
        <p className="lead">Aucune révision évaluée pour le moment.</p>
      </div>
    );

  return (
    <div>
      <h2>Bilan</h2>
      <p className="lead">
        {data.date} · {data.total} restitution(s) évaluée(s)
      </p>

      <h3>Vue d'ensemble</h3>
      <div className="notes" style={{ marginTop: "0.2rem" }}>
        {NOTE_LABELS.map((n) => (
          <span key={n.key} className={"bilan-pill pill-" + n.key}>
            {n.label} : {data.overview[n.key]}
          </span>
        ))}
      </div>

      <h3 style={{ marginTop: "1.4rem" }}>Par leçon</h3>
      <div className="card" style={{ padding: "0.4rem 0.6rem", overflowX: "auto" }}>
        <table className="bilan-table">
          <thead>
            <tr>
              <th>Leçon</th>
              <th>A</th>
              <th>H</th>
              <th>G</th>
              <th>E</th>
            </tr>
          </thead>
          <tbody>
            {data.par_lecon.map((l, i) => (
              <tr key={i}>
                <td>{l.lecon}</td>
                <td>{l.again}</td>
                <td>{l.hard}</td>
                <td>{l.good}</td>
                <td>{l.easy}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 style={{ marginTop: "1.4rem" }}>À retravailler</h3>
      <p className="muted" style={{ marginTop: "-0.4rem", fontSize: "0.86rem" }}>
        Cartes dont la dernière restitution est Again ou Hard.
      </p>
      {data.fragiles.length === 0 ? (
        <p className="lead">Aucun point fragile.</p>
      ) : (
        <div className="card" style={{ padding: "0.4rem 0.6rem", overflowX: "auto" }}>
          <table className="bilan-table">
            <thead>
              <tr>
                <th>Titre</th>
                <th>Mode</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {data.fragiles.map((f, i) => (
                <tr key={i}>
                  <td>{f.titre}</td>
                  <td>{f.mode}</td>
                  <td className={"note-" + f.note}>{f.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
