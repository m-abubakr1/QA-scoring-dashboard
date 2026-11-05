import { useState } from "react";

// Notes are shared: when one supervisor adds one, everyone watching sees it.
export default function Notes({ notes, onAdd }) {
  const [text, setText] = useState("");

  function submit(event) {
    event.preventDefault();
    if (!text.trim()) return;
    onAdd(text.trim());
    setText("");
  }

  return (
    <div>
      {notes.map((n) => (
        <p key={n.id} className="note">
          <strong>{n.author}:</strong> {n.text}
        </p>
      ))}
      <form onSubmit={submit} className="inline">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a note for the team" maxLength={500} />
        <button>Add</button>
      </form>
    </div>
  );
}
