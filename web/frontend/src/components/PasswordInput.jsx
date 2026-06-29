import { useEffect, useRef, useState } from "react";

export default function PasswordInput({ className = "form-field__input", ...props }) {
  const [visible, setVisible] = useState(false);
  const hideTimerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (hideTimerRef.current) {
        window.clearTimeout(hideTimerRef.current);
      }
    };
  }, []);

  function previewPassword() {
    if (hideTimerRef.current) {
      window.clearTimeout(hideTimerRef.current);
    }
    setVisible(true);
    hideTimerRef.current = window.setTimeout(() => {
      setVisible(false);
      hideTimerRef.current = null;
    }, 1000);
  }

  return (
    <span className="password-input">
      <input {...props} className={className} type={visible ? "text" : "password"} />
      <button
        className="password-input__preview"
        type="button"
        onClick={previewPassword}
        aria-label="Preview password for one second"
        title="Preview password"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z" />
          <circle cx="12" cy="12" r="2.7" />
        </svg>
      </button>
    </span>
  );
}
