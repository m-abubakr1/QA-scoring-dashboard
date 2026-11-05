import { useEffect, useState } from "react";
import { getSamples, startSimulation } from "./api.js";
import { useMonitor } from "./useMonitor.js";
import CallList from "./components/CallList.jsx";
import CallView from "./components/CallView.jsx";
import History from "./components/History.jsx";
import ImportTranscript from "./components/ImportTranscript.jsx";

// A random name so two browser tabs look like two different supervisors.
const myName = "supervisor-" + Math.floor(Math.random() * 900 + 100);

export default function App() {
  const monitor = useMonitor(myName);
  const [tab, setTab] = useState("live");
  const [selectedId, setSelectedId] = useState(null);
  const [samples, setSamples] = useState([]);
  const [sampleId, setSampleId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getSamples()
      .then((list) => {
        setSamples(list);
        if (list.length) setSampleId(list[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  function select(id) {
    setSelectedId(id);
    setTab("live");
    monitor.loadCall(id); // fetch the lines we may have missed
  }

  async function startPractice() {
    setError("");
    try {
      const call = await startSimulation(sampleId, 1.5);
      select(call.id);
    } catch (e) {
      setError(e.message);
    }
  }

  const call = monitor.calls.find((c) => c.id === selectedId);
  const data = monitor.data[selectedId];
  const message = error || monitor.problem;

  return (
    <div className="app">
      <header>
        <h1>QA scoring dashboard</h1>
        <span className={monitor.connected ? "dot on" : "dot off"} />
        <span className="muted">
          {monitor.connected ? `connected as ${myName}` : "reconnecting..."} - watching now:{" "}
          {monitor.watchers.map((w) => w.name).join(", ") || "nobody"}
        </span>
        <nav>
          <button className={tab === "live" ? "tab active" : "tab"} onClick={() => setTab("live")}>Live</button>
          <button className={tab === "history" ? "tab active" : "tab"} onClick={() => setTab("history")}>History</button>
        </nav>
      </header>

      {message && (
        <div className="alert medium" onClick={() => { setError(""); monitor.clearProblem(); }}>
          {message} (click to dismiss)
        </div>
      )}

      <div className="layout">
        <aside>
          <h3>Practice call</h3>
          <div className="inline">
            <select value={sampleId} onChange={(e) => setSampleId(e.target.value)}>
              {samples.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
            </select>
            <button onClick={startPractice} disabled={!sampleId}>Start</button>
          </div>
          <h3>Score a transcript</h3>
          <ImportTranscript onScored={(call) => select(call.id)} onError={setError} />
          <h3>Calls</h3>
          <CallList calls={monitor.calls} selectedId={selectedId} onSelect={select} />
        </aside>

        <main>
          {tab === "history" && <History onOpen={select} />}
          {tab === "live" && call && data && (
            <CallView call={call} data={data} onNote={(text) => monitor.sendNote(call.id, text)} />
          )}
          {tab === "live" && !(call && data) && <p className="muted">Pick a call on the left, or start a practice call.</p>}
        </main>
      </div>
    </div>
  );
}
