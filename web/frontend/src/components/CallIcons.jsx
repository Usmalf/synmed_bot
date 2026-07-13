function IconBase({ children, className = "" }) {
  return (
    <svg
      aria-hidden="true"
      className={className || "call-control-icon"}
      fill="none"
      focusable="false"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
    >
      {children}
    </svg>
  );
}

export function PhoneIcon(props) {
  return (
    <IconBase {...props}>
      <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.4 19.4 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 2 .7 2.9a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.2-1.2a2 2 0 0 1 2.1-.5c.9.3 1.9.6 2.9.7a2 2 0 0 1 1.7 2Z" />
    </IconBase>
  );
}

export function PhoneOffIcon(props) {
  return (
    <IconBase {...props}>
      <path d="m2 2 20 20" />
      <path d="M13.4 13.4a16 16 0 0 0 2.5 1.5l1.2-1.2a2 2 0 0 1 2.1-.5c.9.3 1.8.5 2.8.7v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.4 19.4 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3c.2 0 .5 0 .7.1" />
    </IconBase>
  );
}

export function VideoIcon(props) {
  return (
    <IconBase {...props}>
      <path d="M15 10.5 21 7v10l-6-3.5V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v3.5Z" />
    </IconBase>
  );
}

export function VideoOffIcon(props) {
  return (
    <IconBase {...props}>
      <path d="m2 2 20 20" />
      <path d="M10.7 5H13a2 2 0 0 1 2 2v3.5L21 7v10l-4-2.3" />
      <path d="M3 7.8V17a2 2 0 0 0 2 2h8a2 2 0 0 0 1.7-1" />
    </IconBase>
  );
}

export function MicIcon(props) {
  return (
    <IconBase {...props}>
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <path d="M12 19v3" />
    </IconBase>
  );
}

export function MicOffIcon(props) {
  return (
    <IconBase {...props}>
      <path d="m2 2 20 20" />
      <path d="M9 9v3a3 3 0 0 0 5.1 2.1" />
      <path d="M15 9.3V5a3 3 0 0 0-5.1-2.1" />
      <path d="M19 10v2a7 7 0 0 1-.7 3" />
      <path d="M5 10v2a7 7 0 0 0 9.7 6.5" />
      <path d="M12 19v3" />
    </IconBase>
  );
}

export function SwitchCameraIcon(props) {
  return (
    <IconBase {...props}>
      <path d="M4 8h3l2-2h6l2 2h3v10H4V8Z" />
      <path d="M9.5 13a3 3 0 0 1 5-2.2" />
      <path d="m15 9.5-.5 2.8-2.6-.9" />
      <path d="M14.5 13a3 3 0 0 1-5 2.2" />
      <path d="m9 16.5.5-2.8 2.6.9" />
    </IconBase>
  );
}
