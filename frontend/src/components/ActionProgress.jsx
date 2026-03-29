import { useState, useEffect, useRef, useCallback } from "react";

/**
 * Reusable component that handles: trigger POST -> poll status -> spinner + message -> call onComplete.
 *
 * Props:
 *   endpoint   - POST endpoint to trigger the action (e.g. "/api/actions/summarize")
 *   body       - request body object
 *   onComplete - called with the final status data when action finishes successfully
 *   onError    - optional, called with error message on failure
 *   label      - display label while running (e.g. "Generating summary")
 *   buttonLabel - label for the trigger button (default: "Generate")
 *   regenerate - if true, show as a secondary "Regenerate" button
 *   disabled   - disable the trigger button
 *   autoTrigger - if true, trigger immediately on mount
 *   className  - optional extra class on wrapper
 *   children   - optional, rendered when idle (replaces default button)
 */
export default function ActionProgress({
  endpoint,
  body,
  onComplete,
  onError,
  label = "Running",
  buttonLabel = "Generate",
  regenerate = false,
  disabled = false,
  autoTrigger = false,
  className = "",
  children,
}) {
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(null); // { done, total }
  const pollTimer = useRef(null);
  const mounted = useRef(true);
  const triggered = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, []);

  // Auto-trigger on mount if requested
  useEffect(() => {
    if (autoTrigger && !triggered.current) {
      triggered.current = true;
      trigger();
    }
  }, [autoTrigger]); // eslint-disable-line react-hooks/exhaustive-deps

  const pollStatus = useCallback(async () => {
    try {
      const resp = await fetch(`${endpoint}/status`);
      const data = await resp.json();
      if (!mounted.current) return;

      setMessage(data.message || `${label}...`);
      if (data.sub_progress) {
        setProgress(data.sub_progress);
      } else if (data.total > 0) {
        setProgress({ done: data.completed || 0, total: data.total });
      }

      if (data.running) {
        pollTimer.current = setTimeout(pollStatus, 500);
      } else {
        setRunning(false);
        setProgress(null);
        if (data.error) {
          setError(data.error);
          if (onError) onError(data.error);
        } else {
          setError(null);
          setMessage("");
          if (onComplete) onComplete(data);
        }
      }
    } catch (err) {
      if (!mounted.current) return;
      setRunning(false);
      setError(String(err.message || err));
      if (onError) onError(String(err.message || err));
    }
  }, [endpoint, label, onComplete, onError]);

  async function trigger() {
    setRunning(true);
    setError(null);
    setMessage(`${label}...`);
    setProgress(null);
    try {
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const data = await resp.json();
      if (!mounted.current) return;
      if (!resp.ok) {
        throw new Error(data.detail || data.error || `HTTP ${resp.status}`);
      }
      if (data.async || data.running) {
        setMessage(data.message || `${label}...`);
        pollTimer.current = setTimeout(pollStatus, 300);
      } else {
        // Synchronous completion
        setRunning(false);
        setMessage("");
        if (data.error) {
          setError(data.error);
          if (onError) onError(data.error);
        } else {
          if (onComplete) onComplete(data);
        }
      }
    } catch (err) {
      if (!mounted.current) return;
      setRunning(false);
      setError(String(err.message || err));
      if (onError) onError(String(err.message || err));
    }
  }

  if (running) {
    return (
      <div className={`action-progress ${className}`}>
        <div className="action-progress-status">
          <span className="action-spinner">&#x27F3;</span>
          <span className="action-progress-label">{message || `${label}...`}</span>
        </div>
        {progress && progress.total > 0 && (
          <div className="progress-bar" style={{ marginTop: "0.3rem", height: "4px" }}>
            <div
              className="progress-fill"
              style={{ width: `${Math.round((progress.done / progress.total) * 100)}%` }}
            />
          </div>
        )}
      </div>
    );
  }

  if (error) {
    return (
      <div className={`action-progress ${className}`}>
        <div className="action-status error" style={{ fontSize: "0.78rem", marginBottom: "0.3rem" }}>{error}</div>
        <button className="absent-refs-btn-small" onClick={trigger} disabled={disabled}>
          Retry
        </button>
      </div>
    );
  }

  // Idle state — render children or default button
  if (children) return <>{children}</>;

  return (
    <button
      className={regenerate ? "absent-refs-btn-small" : "absent-refs-btn-small absent-refs-btn-primary"}
      disabled={disabled}
      onClick={trigger}
    >
      {buttonLabel}
    </button>
  );
}
