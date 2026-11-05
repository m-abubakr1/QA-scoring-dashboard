import { useEffect, useRef } from "react";
import ScorePanel from "./ScorePanel.jsx";
import Notes from "./Notes.jsx";

export default function CallView({ call, data, onNote }) {
  const bottom = useRef(null);

  // keep the newest line in view while a call is running
  useEffect(() => {
    bottom.current && bottom.current.scrollIntoView({ block: "nearest" });
  }, [data.lines.length]);

  return (
    <div className="callview">
      <h2>
        {call.agent_name} <span className="muted">call #{call.id}</span>{" "}
        {call.status === "live" && <span className="badge live">live</span>}
      </h2>

      {data.alerts.map((a) => (
        <div key={a.id} className={"alert " + a.severity}>
          <strong>{a.type.replace("_", " ")}:</strong> {a.message}
        </div>
      ))}

      <div className="columns">
        <section>
          <h3>Transcript</h3>
          <div className="transcript">
            {data.lines.map((line) => (
              <div key={line.seq} className={"line " + line.speaker}>
                <span className="who">{line.speaker}</span> {line.text}
              </div>
            ))}
            <div ref={bottom} />
          </div>
        </section>

        <section>
          <h3>Score</h3>
          <ScorePanel score={data.score} error={data.error} />
          <h3>Notes</h3>
          <Notes notes={data.notes} onAdd={onNote} />
        </section>
      </div>
    </div>
  );
}
