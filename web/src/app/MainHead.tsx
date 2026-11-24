import { VIEWS } from "./routing";
import type { ViewId } from "./routing";

export type MainHeadProps = {
  /** Only presence is read; the detail view below renders the payload. */
  detail: object | null;
  view: ViewId;
  connected: boolean;
  crumb: string;
  title: string;
  subtitle: string;
  onQueue: () => void;
  onView: (view: ViewId) => void;
};

export function MainHead({
  detail,
  view,
  connected,
  crumb,
  title,
  subtitle,
  onQueue,
  onView,
}: MainHeadProps) {
  return (
    <div className="sticky-top">
      <header className="main-head">
        <div className="head-copy">
          <div className="crumb">
            <button type="button" className="crumb-link" onClick={onQueue}>Queue</button>
            {detail ? <><span className="crumb-sep">/</span>{crumb}</> : null}
          </div>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
      </header>
      {detail ? (
        <div className="view-tabs" role="tablist" aria-label="Detail view">
          {VIEWS.map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={view === id} className={`view-tab ${view === id ? "active" : ""}`} onClick={() => onView(id)}>{label}</button>
          ))}
          <span className={`cl-live ${connected ? "on" : ""}`} title={connected ? "Live updates connected" : "Reconnecting"} />
        </div>
      ) : null}
    </div>
  );
}
