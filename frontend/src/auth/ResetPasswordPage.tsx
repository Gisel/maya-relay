import { FormEvent, useMemo, useState } from "react";
import { ApiError, requestPasswordReset, updatePassword } from "../api";
import logoMaya from "../assets/logo-maya.jpg";

type RecoveryParams = {
  accessToken: string | null;
  refreshToken: string | null;
  code: string | null;
  type: string | null;
};

export function ResetPasswordPage() {
  const recovery = useMemo(readRecoveryParams, []);
  const hasRecoveryToken = Boolean((recovery.accessToken && recovery.refreshToken) || recovery.code);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleRequestReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setIsSubmitting(true);
    try {
      await requestPasswordReset(email);
      setSuccess("If that email is active, a reset link has been sent.");
      setEmail("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not send the reset email.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleUpdatePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setIsSubmitting(true);
    try {
      await updatePassword({
        password,
        accessToken: recovery.accessToken,
        refreshToken: recovery.refreshToken,
        code: recovery.code,
      });
      setPassword("");
      setConfirmPassword("");
      window.history.replaceState(null, "", "/reset-password");
      setSuccess("Password updated. You can sign in with the new password.");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not update the password.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="login-screen">
      <form className="login-panel" onSubmit={hasRecoveryToken ? handleUpdatePassword : handleRequestReset}>
        <div className="brand login-brand">
          <img alt="Maya Graphics and Signs" src={logoMaya} />
          <div>
            <strong>MAYA</strong>
            <span>RELAY</span>
          </div>
        </div>
        {hasRecoveryToken ? (
          <>
            <label>
              <span>New password</span>
              <input
                autoComplete="new-password"
                autoFocus
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                value={password}
              />
            </label>
            <label>
              <span>Confirm password</span>
              <input
                autoComplete="new-password"
                onChange={(event) => setConfirmPassword(event.target.value)}
                type="password"
                value={confirmPassword}
              />
            </label>
            {error && <p className="form-error">{error}</p>}
            {success && <p className="app-success">{success}</p>}
            <button className="send-button" disabled={!password || !confirmPassword || isSubmitting} type="submit">
              {isSubmitting ? "Updating..." : "Update password"}
            </button>
          </>
        ) : (
          <>
            <label>
              <span>Email</span>
              <input
                autoComplete="username"
                autoFocus
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                value={email}
              />
            </label>
            {error && <p className="form-error">{error}</p>}
            {success && <p className="app-success">{success}</p>}
            <button className="send-button" disabled={!email.trim() || isSubmitting} type="submit">
              {isSubmitting ? "Sending..." : "Send reset link"}
            </button>
          </>
        )}
        <a className="login-reset-link" href="/app">
          Back to sign in
        </a>
      </form>
    </main>
  );
}

function readRecoveryParams(): RecoveryParams {
  const query = new URLSearchParams(window.location.search);
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return {
    accessToken: hash.get("access_token") || query.get("access_token"),
    refreshToken: hash.get("refresh_token") || query.get("refresh_token"),
    code: query.get("code") || hash.get("code"),
    type: hash.get("type") || query.get("type"),
  };
}
