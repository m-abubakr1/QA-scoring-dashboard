import { useEffect, useState } from "react";
import { getAgents, getCalls } from "../api.js";

// Past calls with two filters, plus one line per agent.
export default function History({ onOpen }) {
  const [calls, setCalls] = useState([]);
  const [agents, setAgents] = useState([]);
  const [agent, setAgent] = useState("");
  const [maxScore, setMaxScore] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    getCalls({ agent, maxScore }).then(setCalls).catch((e) => setError(e.message));
  }, [agent, maxScore]);

  useEffect(() => {
    getAgents().then(setAgents).catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      {error && <p className="warn">{error}</p>}

      <h3>Agents</h3>
      <table>
        <thead>
          <tr><th>Agent</th><th>Finished calls</th><th>Average score</th><th>Compliance alerts</th></tr>
        </thead>
        <tbody>
          {agents.map((a) => (
            <tr key={a.agent_name}>
              <td>{a.agent_name}</td><td>{a.calls}</td><td>{a.average ?? "-"}</td><td>{a.compliance_alerts}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Calls</h3>
      <div className="inline">
        <select value={agent} onChange={(e) => setAgent(e.target.value)}>
          <option value="">All agents</option>
          {agents.map((a) => <option key={a.agent_name}>{a.agent_name}</option>)}
        </select>
        <input type="number" min="0" max="100" placeholder="Score at or below" value={maxScore}
               onChange={(e) => setMaxScore(e.target.value)} />
      </div>
      <table>
        <thead>
          <tr><th>#</th><th>Agent</th><th>Status</th><th>Score</th><th>Started</th></tr>
        </thead>
        <tbody>
          {calls.map((c) => (
            <tr key={c.id} className="clickable" onClick={() => onOpen(c.id)}>
              <td>{c.id}</td><td>{c.agent_name}</td><td>{c.status}</td>
              <td>{c.overall === null ? "-" : Math.round(c.overall)}</td>
              <td>{new Date(c.started_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
