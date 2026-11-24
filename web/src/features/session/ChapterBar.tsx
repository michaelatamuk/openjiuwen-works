import type { PhaseId, PhaseView } from "./types";

export type ChapterBarProps = {
  phases: PhaseView[];
  showAll: boolean;
  selectedPhase: PhaseId | null;
  currentId: PhaseId;
  onSelect: (id: PhaseId) => void;
  onShowAll: (checked: boolean) => void;
  onReset: () => void;
};

export function ChapterBar({ phases, showAll, selectedPhase, currentId, onSelect, onShowAll, onReset }: ChapterBarProps) {
  return (
    <nav className="cl-chapter-bar" aria-label="Run chapters">
      {phases.map((phase) => (
        <button
          key={phase.id}
          type="button"
          className={`cl-chapter-chip ${phase.state} ${!showAll && (selectedPhase || currentId) === phase.id ? "active" : ""}`}
          onClick={() => onSelect(phase.id)}
        >
          <span className="cl-phase-dot" aria-hidden="true" />
          {phase.label}
          <span className="cl-chapter-chip-count">{phase.items.length}</span>
        </button>
      ))}
      <label className="cl-chapter-all">
        <input
          type="checkbox"
          checked={showAll}
          onChange={(event) => onShowAll(event.target.checked)}
        />
        All chapters
      </label>
      {selectedPhase ? (
        <button type="button" className="cl-chapter-reset" onClick={onReset}>
          Back to current
        </button>
      ) : null}
    </nav>
  );
}
