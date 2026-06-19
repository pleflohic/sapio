// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from "react";
import { MathJax } from "better-react-mathjax";
import { getDeckTree, getDeckCards, DeckStatNode, DeckCard } from "./api";

function Tex({ html, inline }: { html: string; inline?: boolean }) {
  return (
    <MathJax dynamic inline={inline}>
      <span dangerouslySetInnerHTML={{ __html: html }} />
    </MathJax>
  );
}

function Node({
  node,
  depth,
  onOpen,
}: {
  node: DeckStatNode;
  depth: number;
  onOpen: (full: string) => void;
}) {
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
        <button className="deck-name-btn" onClick={() => onOpen(node.full)}>
          {node.name}
        </button>
        <span className="deck-count">{node.total}</span>
      </div>
      {open && kids.map((c) => <Node key={c.full} node={c} depth={depth + 1} onOpen={onOpen} />)}
    </>
  );
}

function CardList({ deck, onBack }: { deck: string; onBack: () => void }) {
  const [cards, setCards] = useState<DeckCard[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    getDeckCards(deck)
      .then((d) => setCards(d.cards))
      .catch(() => setErr("Chargement des cartes impossible."));
  }, [deck]);

  return (
    <div>
      <button className="tab" style={{ marginBottom: ".4rem", paddingLeft: 0 }} onClick={onBack}>
        ← Tous les decks
      </button>
      <h2>{deck.split("::").pop()}</h2>
      {err && <p style={{ color: "var(--theo)" }}>{err}</p>}
      {!cards ? (
        <p className="spin">Chargement…</p>
      ) : cards.length === 0 ? (
        <p className="lead">Aucune carte dans ce deck.</p>
      ) : (
        <>
          <p className="lead">{cards.length} carte(s), question et réponse attendue.</p>
          {cards.map((c, i) => (
            <div key={i} className="card">
              <div className="card-top">
                <span className={"chip " + c.color}>{c.type}</span>
                {c.importance && <span className={"imp imp-" + c.importance}>{c.importance}</span>}
                {c.mode && <span className="meta">{c.mode}</span>}
              </div>
              <div className="consigne"><Tex html={c.consigne} inline /></div>
              {c.contexte && (
                <div className="ctx">
                  <div className="ctx-label">Énoncé de référence</div>
                  <Tex html={c.contexte} />
                </div>
              )}
              <div className="ctx">
                <div className="ctx-label">Réponse attendue</div>
                <Tex html={c.attendu} />
              </div>
              <div className="src"><Tex html={c.titre} inline /> · {c.lecon}</div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

export function DeckBrowser() {
  const [tree, setTree] = useState<DeckStatNode | null>(null);
  const [err, setErr] = useState("");
  const [openDeck, setOpenDeck] = useState<string | null>(null);

  useEffect(() => {
    getDeckTree()
      .then(setTree)
      .catch(() => setErr("Chargement des decks impossible."));
  }, []);

  if (openDeck) return <CardList deck={openDeck} onBack={() => setOpenDeck(null)} />;
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
        Toute ta hiérarchie Année › Cours › Chapitre › Partie. Le compteur = nombre total de
        cartes (sous-decks inclus). Clique un deck pour voir toutes ses cartes.
      </p>
      <div className="deck-tree card">
        {annees.map((a) => (
          <Node key={a.full} node={a} depth={0} onOpen={setOpenDeck} />
        ))}
      </div>
    </div>
  );
}
