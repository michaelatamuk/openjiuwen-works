import { useState } from "react";
import type { FormEvent } from "react";
import { connect } from "../../api/client";

export type SignInProps = {
  onSignedIn: () => void;
};

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function SignIn({ onSignedIn }: SignInProps) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await connect(value);
      onSignedIn();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="signin">
      <form className="signin-card" onSubmit={submit}>
        <img src="/mira.svg" alt="" width="96" height="96" />
        <h1>Connect to this daemon</h1>
        <p>
          This browser is not signed in. Paste the daemon token once and it is remembered; after a
          restart the page signs itself back in.
        </p>
        <label className="settings-field">
          <span>Token or pairing code</span>
          <input
            type="password"
            autoComplete="off"
            autoFocus
            value={value}
            disabled={busy}
            placeholder="paste the token or a five-minute pairing code"
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
        {error ? (
          <p className="signin-error" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit" className="btn" disabled={busy || !value.trim()}>
          {busy ? "Connecting..." : "Connect"}
        </button>
        <p className="settings-note">
          On the machine that runs the daemon: <code>works daemon pair --label phone</code> prints a
          five-minute code. The device list in Settings can revoke it later.
        </p>
      </form>
    </div>
  );
}
