import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { CommandCenter } from "@/components/command-center";
import type { AppData } from "@/lib/types";
import "@/src/styles.css";

function Bootstrap() {
  const [data, setData] = useState<AppData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/app")
      .then((response) => {
        if (!response.ok) throw new Error("FastAPI did not return application data");
        return response.json();
      })
      .then(setData)
      .catch((reason) => setError(reason.message));
  }, []);

  if (error) return <main className="boot-state"><h1>Northstar could not start</h1><p>{error}</p><code>uvicorn main:app --reload</code></main>;
  if (!data) return <main className="boot-state"><div className="boot-mark">N</div><h1>Preparing your command center…</h1><p>Loading the plan from FastAPI + SQLite.</p></main>;
  return <CommandCenter initialData={data} />;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><Bootstrap /></React.StrictMode>);
