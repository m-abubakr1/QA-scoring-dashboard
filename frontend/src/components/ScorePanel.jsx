// The score for one call: the overall number, then one bar per rubric criterion.

export default function ScorePanel({ score, error }) {
  if (!score) return <p className="muted">{error || "No score yet. It appears after a few lines."}</p>;

  return (
    <div>
      <div className="overall">
        <span className="big">{score.overall === null ? "-" : Math.round(score.overall)}</span>
        <span className="muted"> / 100 ({score.kind === "final" ? "final" : "live, so far"})</span>
      </div>
      {error && <p className="warn">{error}</p>}
      <p>{score.summary}</p>

      {score.criteria.map((c) => (
        <div key={c.id} className="criterion">
          <div className="row">
            <span>{c.name}</span>
            <span>{c.score === null ? "not seen yet" : `${c.score} / 5`}</span>
          </div>
          <div className="bar">
            <div className={"fill s" + (c.score || 0)} style={{ width: `${((c.score || 0) / 5) * 100}%` }} />
          </div>
          {c.reasoning && <div className="muted small">{c.reasoning}</div>}
          {c.evidence.map((quote) => (
            <blockquote key={quote}>{quote}</blockquote>
          ))}
        </div>
      ))}
    </div>
  );
}
