import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { ResetPasswordPage } from "./auth/ResetPasswordPage";
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
  if (window.location.pathname.match(/^\/(?:app\/)?reset-password\/?$/)) {
    return <ResetPasswordPage />;
  }
  return <App />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
