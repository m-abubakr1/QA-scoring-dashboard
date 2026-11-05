export default function CallList({ calls, selectedId, onSelect }) {
  if (calls.length === 0) return <p className="muted">No calls yet. Start a practice call above.</p>;

  return (
    <ul className="calls">
      {calls.map((call) => (
        <li key={call.id}>
          <button className={call.id === selectedId ? "call selected" : "call"} onClick={() => onSelect(call.id)}>
            <span>
              <strong>{call.agent_name}</strong>
              <span className="muted"> #{call.id}</span>
            </span>
            {call.status === "live" ? (
              <span className="badge live">live</span>
            ) : (
              <span className="badge">{call.overall === null ? "no score" : Math.round(call.overall)}</span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
