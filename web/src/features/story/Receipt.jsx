function Receipt({ detail }) {
  const evidence = detail.evidence;
  const blocked = detail.task.state === "blocked";
  const files = evidence?.files_changed?.length || 0;
  const changed = blocked ? "No change released" : files ? `${files} file${files === 1 ? "" : "s"} changed` : "No change yet";
  const outcomes = evidence?.verdict?.outcomes || [];
  const must = outcomes.filter((item) => item.priority === "P0");
  const passed = must.filter((item) => item.passed).length;
  const checked = must.length
    ? passed === must.length
      ? `${passed} of ${must.length} must-pass checks passed`
      : `${must.length - passed} of ${must.length} must-pass checks failed`
    : "No checks yet";
  const note = !evidence?.verdict
    ? "No checks yet"
    : evidence.verdict.allow
      ? evidence.challenge?.allow ? "Independent review passed" : "No independent review"
      : "A must-pass check failed";
  return (
    <div className="receipt">
      <div><span>Changed</span><strong>{changed}</strong><p>{files ? (evidence.files_changed || []).join(", ") : "No diff yet."}</p></div>
      <div><span>Checked</span><strong>{checked}</strong><p>{note}</p></div>
      <div><span>Not checked</span><strong>{evidence?.not_tested?.[0] || "No gaps recorded"}</strong><p>The proof says what was not covered.</p></div>
      <div><span>Decides</span><strong>A person</strong><p>Human gates stay human.</p></div>
    </div>
  );
}

export { Receipt };
