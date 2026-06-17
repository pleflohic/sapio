// SPDX-License-Identifier: AGPL-3.0-or-later
import { useState } from "react";
import { DeckNode } from "./api";

function Node({
  node,
  depth,
  onPick,
}: {
  node: DeckNode;
  depth: number;
  onPick: (full: string) => void;
}) {
  const [open, setOpen] = useState(depth === 0); // années dépliées par défaut
  const kids = node.children.filter((c) => c.count > 0).sort((a, b) => a.name.localeCompare(b.name));
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
        <button className="deck-name-btn" disabled={node.count === 0} onClick={() => onPick(node.full)}>
          {node.name}
        </button>
        <span className={"deck-count" + (node.count === 0 ? " zero" : "")}>{node.count}</span>
      </div>
      {open && kids.map((c) => <Node key={c.full} node={c} depth={depth + 1} onPick={onPick} />)}
    </>
  );
}

export function DeckPicker({
  tree,
  onPick,
}: {
  tree: DeckNode | null;
  onPick: (full: string) => void;
}) {
  if (!tree) return <p className="spin">Chargement des decks…</p>;
  if (tree.count === 0)
    return <p className="lead">Aucune carte à réviser pour le moment 🎉</p>;
  const annees = tree.children.filter((c) => c.count > 0).sort((a, b) => a.name.localeCompare(b.name));
  return (
    <div>
      <h2>Choisis un deck à réviser</h2>
      <p className="lead">
        Déplie une année pour voir ses cours, chapitres et parties. Le nombre = cartes
        dues du jour (sous-decks inclus). Clique un nom pour réviser ce niveau.
      </p>
      <div className="deck-tree card">
        {annees.map((a) => (
          <Node key={a.full} node={a} depth={0} onPick={onPick} />
        ))}
      </div>
    </div>
  );
}
