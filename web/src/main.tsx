import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./styles.css";

// Apply the stored theme before first paint so the page does not flash the
// wrong surface while React boots.
const stored = localStorage.getItem("theme");
if (stored === "light" || stored === "dark") {
  document.documentElement.dataset.theme = stored;
}

const root = document.getElementById("root");
if (!root) throw new Error("#root not found");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
