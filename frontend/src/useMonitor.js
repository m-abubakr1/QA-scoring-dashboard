import { useEffect, useReducer, useRef, useState } from "react";
import { getCall } from "./api.js";

// Everything we know about each call lives in state.data[callId]:
//   { lines, score, alerts, notes, error }
// The list of calls (for the left column) lives in state.calls.

const empty = () => ({ lines: [], score: null, alerts: [], notes: [], error: null });

const initial = { connected: false, you: null, watchers: [], calls: [], data: {} };

// Add lines we have not seen yet. Lines have a number (seq), so we can skip repeats.
function addLines(existing, incoming) {
  const seen = new Set(existing.map((l) => l.seq));
  const fresh = incoming.filter((l) => !seen.has(l.seq));
  return [...existing, ...fresh].sort((a, b) => a.seq - b.seq);
}

// A final score is better than a live one, so a late live score must not replace it.
function betterScore(current, incoming) {
  if (current && current.kind === "final" && incoming.kind === "live") return current;
  return incoming;
}

function updateCall(state, id, change) {
  const old = state.data[id] || empty();
  return { ...state, data: { ...state.data, [id]: { ...old, ...change(old) } } };
}

function reducer(state, msg) {
  switch (msg.type) {
    case "connection":
      return { ...state, connected: msg.connected };
    case "joined":
      return { ...state, you: msg.you, watchers: msg.watchers, calls: msg.calls };
    case "presence":
      return { ...state, watchers: msg.watchers };
    case "call_started":
      return { ...state, calls: [msg.call, ...state.calls.filter((c) => c.id !== msg.call.id)] };
    case "call_ended":
      return { ...state, calls: state.calls.map((c) => (c.id === msg.call.id ? msg.call : c)) };
    case "line":
      return updateCall(state, msg.call_id, (d) => ({ lines: addLines(d.lines, [msg.line]) }));
    case "score":
      return updateCall(state, msg.call_id, (d) => ({ score: betterScore(d.score, msg.score), error: null }));
    case "alert":
      return updateCall(state, msg.call_id, (d) => ({ alerts: [...d.alerts, msg.alert] }));
    case "note":
      return updateCall(state, msg.call_id, (d) => ({ notes: [...d.notes, msg.note] }));
    case "score_error":
      return updateCall(state, msg.call_id, () => ({ error: msg.message }));
    case "detail": {
      // the full call we asked for. Merge it with anything that already arrived live.
      const d = msg.detail;
      const known = state.calls.some((c) => c.id === d.id);
      const meta = { id: d.id, agent_name: d.agent_name, customer_label: d.customer_label, status: d.status,
                     started_at: d.started_at, ended_at: d.ended_at, overall: d.overall };
      state = known ? state : { ...state, calls: [...state.calls, meta] };
      return updateCall(state, d.id, (old) => ({
        lines: addLines(old.lines, d.lines),
        score: d.score ? betterScore(old.score, d.score) : old.score,
        alerts: d.alerts.length >= old.alerts.length ? d.alerts : old.alerts,
        notes: d.notes.length >= old.notes.length ? d.notes : old.notes,
      }));
    }
    default:
      return state;
  }
}

export function useMonitor(name) {
  const [state, dispatch] = useReducer(reducer, initial);
  const socket = useRef(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    let stopped = false;
    let retry;

    function connect() {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${scheme}://${location.host}/ws/monitor?name=${encodeURIComponent(name)}`);
      socket.current = ws;

      ws.onopen = () => dispatch({ type: "connection", connected: true });
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === "ping") ws.send(JSON.stringify({ type: "pong" })); // keeps the connection alive
        else if (msg.type === "rate_limited") setProblem(`Slow down, try again in ${Math.ceil(msg.retry_after)}s`);
        else if (msg.type === "error") setProblem(msg.message);
        else dispatch(msg);
      };
      ws.onclose = () => {
        dispatch({ type: "connection", connected: false });
        if (!stopped) retry = setTimeout(connect, 2000); // try again in 2 seconds
      };
    }

    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      socket.current && socket.current.close();
    };
  }, [name]);

  // Ask the server for one call's full details (used when you click a call).
  async function loadCall(id) {
    try {
      dispatch({ type: "detail", detail: await getCall(id) });
    } catch (err) {
      setProblem(err.message);
    }
  }

  function sendNote(callId, text) {
    if (socket.current && socket.current.readyState === 1) {
      socket.current.send(JSON.stringify({ type: "note", call_id: callId, text }));
    }
  }

  return { ...state, problem, clearProblem: () => setProblem(""), loadCall, sendNote };
}
