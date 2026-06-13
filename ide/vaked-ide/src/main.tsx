import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { SurfaceView } from "@/components/SurfaceLauncher/SurfaceView";

// Route to SurfaceView when launched as a surface launcher window
const isSurface = window.location.pathname === "/surface" ||
  window.location.search.includes("name=");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {isSurface ? <SurfaceView /> : <App />}
  </React.StrictMode>
);
