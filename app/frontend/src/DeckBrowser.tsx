// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from "react";
import { getDeckTree, DeckStatNode } from "./api";

function Node({ node, depth }: { node: DeckStatNode; depth: number }) {
  const [open, setOpen] = useState(depth === 0); // années dépliées par défaut
  const kids = node.children
    .filter((c) => c.total > 0)
    .sort((a, b) => a.name.localeCompare(b.name));
  const hasKids = kids.length > 0;
  return (
    <>
      <div className="deck-row" style={{ paddingLeft: 0.5 + depth * 1.1 + "rem" }}>
        {hasKids ? (
          <button className="chev" onClick={() => setOpen(!open)} aria-label="déplier">
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="chev-spacer" />
        )}
        <span className="deck-name">{node.name}</span>
        {node.due > 0 && <span className="deck-due">{node.due} dus</span>}
        <span className={"deck-count" + (node.total === 0 ? " zero" : "")}>{node.total}</span>
      </div>
      {open && kids.map((c) => <Node key={c.full} node={c} depth={depth + 1} />)}
    </>
  );
}

export function DeckBrowser() {
  const [tree, setTree] = useState<DeckStatNode | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    getDeckTree()
      .then(setTree)
      .catch(() => setErr("Chargement des decks impossible."));
  }, []);

  if (err) return <p style={{ color: "var(--theo)" }}>{err}</p>;
  if (!tree) return <p className="spin">Chargement des decks…</p>;
  const annees = tree.children
    .filter((c) => c.total > 0)
    .sort((a, b) => a.name.localeCompare(b.name));
  if (annees.length === 0) return <p className="lead">Aucun deck pour le moment.</p>;
  return (
    <div>
      <h2>Tes decks</h2>
      <p className="lead">
        Toute ta hiérarchie Année › Cours › Chapitre › Partie. Le compteur sombre = nombre
        total de cartes (sous-decks inclus), le badge ambré = cartes dues aujourd'hui.
      </p>
      <div className="deck-tree card">
        {annees.map((a) => (
          <Node key={a.full} node={a} depth={0} />
        ))}
      </div>
    </div>
  );
}
