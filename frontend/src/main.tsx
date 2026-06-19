import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { PublicAssetsPage } from "./publicAssets/PublicAssetsPage";
import { PublicProofPage } from "./publicProof/PublicProofPage";
import "./styles.css";

function Root() {
  const proofMatch = window.location.pathname.match(/^\/proof\/([^/]+)\/?$/);
  if (proofMatch) {
    return <PublicProofPage token={decodeURIComponent(proofMatch[1])} />;
  }
  const assetsMatch = window.location.pathname.match(/^\/assets\/([^/]+)\/?$/);
  if (assetsMatch) {
    return <PublicAssetsPage token={decodeURIComponent(assetsMatch[1])} />;
  }
  return <App />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
