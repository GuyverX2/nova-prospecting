import { useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

declare global {
  interface Window {
    NOVA_PLATFORM_TOKEN?: string;
    NOVA_API_URL?: string;
  }
}

const apiUrl = (window.NOVA_API_URL || import.meta.env.VITE_NOVA_API_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");

function App() {
  const [token, setToken] = useState(window.NOVA_PLATFORM_TOKEN || "");
  const [result, setResult] = useState("Supply a platform bearer token to load Nova.");

  async function loadSummary() {
    if (!token.trim()) {
      setResult("A platform bearer token is required.");
      return;
    }
    try {
      const response = await fetch(`${apiUrl}/prospecting/summary`, {
        headers: { Authorization: `Bearer ${token.trim()}` }
      });
      const body: unknown = await response.json();
      setResult(response.ok ? JSON.stringify(body, null, 2) : `Request failed (${response.status}): ${JSON.stringify(body)}`);
    } catch {
      setResult("Nova API is unavailable.");
    }
  }

  return <main>
    <p className="eyebrow">NOVA / PROSPECTING</p>
    <h1>Independent operator console.</h1>
    <p className="lede">Nova accepts a bearer token issued by the platform. It does not issue credentials or provide a login flow.</p>
    <label htmlFor="token">Platform bearer token</label>
    <textarea id="token" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Supplied by the platform host" />
    <button type="button" onClick={loadSummary}>Load tenant summary</button>
    <pre aria-live="polite">{result}</pre>
  </main>;
}

createRoot(document.getElementById("root")!).render(<App />);
