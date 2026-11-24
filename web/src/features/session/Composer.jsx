export function Composer({
  canAsk,
  activeMode,
  text,
  busy,
  focused,
  formRef,
  onText,
  onFocus,
  onToggleMode,
  onSubmit,
}) {
  return (
    <form className={`cl-composer ${focused ? "focused" : ""}`} ref={formRef} onSubmit={onSubmit}>
      <div className="cl-composer-row">
        {canAsk ? (
          <button
            type="button"
            className="cl-mode"
            onClick={onToggleMode}
            title={activeMode === "ask" ? "Switch to Add context" : "Switch to Ask Mira"}
          >
            {activeMode === "ask" ? "Ask" : "Note"}
          </button>
        ) : <span className="cl-mode">Note</span>}
        <textarea
          rows={1}
          value={text}
          placeholder={activeMode === "ask" ? "Ask about this run..." : "Add context to this run..."}
          onChange={(event) => onText(event.target.value)}
          onFocus={() => onFocus(true)}
          onBlur={() => onFocus(false)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) formRef.current?.requestSubmit();
          }}
        />
        <button type="submit" className="cl-send" disabled={busy || !text.trim()} aria-label={activeMode === "ask" ? "Ask Mira" : "Add context"}>
          ↑
        </button>
      </div>
      {focused || text ? (
        <div className="cl-helper">Ctrl Enter to send · advisory only, never opens a gate</div>
      ) : null}
    </form>
  );
}
