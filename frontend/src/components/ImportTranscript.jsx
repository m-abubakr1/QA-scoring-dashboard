import { useState } from "react";
import { scoreTranscript } from "../api.js";

const EXAMPLE = "Agent: Thanks for calling, this is Sam.\nCustomer: Hi, my bill looks wrong.\nAgent: Let me check that for you.";

// Paste a finished transcript, or pick a .txt or .json file, and score it.
export default function ImportTranscript({ onScored, onError }) {
  const [agent, setAgent] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  // The file is read in the browser and put in the box, so you can check it before scoring.
  async function pickFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    setText(await file.text());
    if (!agent) setAgent(file.name.replace(/\.[^.]+$/, ""));
    event.target.value = ""; // lets you pick the same file again
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const call = await scoreTranscript(agent.trim(), text);
      setText("");
      onScored(call);
    } catch (err) {
      onError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="import">
      <input value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="Agent name" maxLength={80} required />
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={EXAMPLE}
        rows={6}
        required
      />
      <div className="inline">
        <label className="filebutton">
          Choose file
          <input type="file" accept=".txt,.json,text/plain,application/json" onChange={pickFile} hidden />
        </label>
        <button disabled={busy || !agent.trim() || !text.trim()}>{busy ? "Scoring..." : "Score it"}</button>
      </div>
      <p className="muted small">Lines start with Agent: or Customer:. JSON also works.</p>
    </form>
  );
}
