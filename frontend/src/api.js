// Small helpers for talking to the API. Each one returns the JSON, or throws an Error with a readable message.

async function request(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // the body was not JSON, keep the default message
    }
    throw new Error(message);
  }
  return res.json();
}

export const getCall = (id) => request(`/api/calls/${id}`);
export const getSamples = () => request("/api/samples");
export const getAgents = () => request("/api/agents");

export function getCalls({ agent, maxScore }) {
  const params = new URLSearchParams();
  if (agent) params.set("agent", agent);
  if (maxScore !== "" && maxScore !== undefined) params.set("max_score", maxScore);
  return request(`/api/calls?${params}`);
}

export const startSimulation = (sampleId, speed) =>
  request("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sample_id: sampleId, speed }),
  });

export const scoreTranscript = (agentName, text) =>
  request("/api/transcripts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_name: agentName, text }),
  });
