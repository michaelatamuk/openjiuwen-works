export type AppHeaderProps = {
  onFactory: () => void;
  onPalette: () => void;
  onSettings: () => void;
};

export function AppHeader({ onFactory, onPalette, onSettings }: AppHeaderProps) {
  return (
    <header className="appbar">
      <div className="appbar-brand">
        <span className="mark" aria-hidden="true">W</span>
        <div>
          <strong>openJiuwen Works</strong>
          <span>LOCAL FACTORY</span>
        </div>
      </div>
      <div className="appbar-actions">
        <button className="btn ghost" type="button" onClick={onFactory}>Factory</button>
        <button className="btn ghost" type="button" aria-label="Command palette" title="Command palette" onClick={onPalette}>Ctrl K</button>
        <button className="btn ghost" type="button" aria-label="Settings" title="Settings" onClick={onSettings}>Settings</button>
      </div>
    </header>
  );
}
