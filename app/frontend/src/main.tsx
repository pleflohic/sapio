// SPDX-License-Identifier: AGPL-3.0-or-later
import React from "react";
import { createRoot } from "react-dom/client";
import { MathJaxContext } from "better-react-mathjax";
import App from "./App";
import "./styles.css";

const mathjaxConfig = {
  tex: {
    inlineMath: [
      ["\\(", "\\)"],
      ["$", "$"],
    ],
    displayMath: [
      ["\\[", "\\]"],
      ["$$", "$$"],
    ],
  },
};

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MathJaxContext config={mathjaxConfig} version={3}>
      <App />
    </MathJaxContext>
  </React.StrictMode>
);
