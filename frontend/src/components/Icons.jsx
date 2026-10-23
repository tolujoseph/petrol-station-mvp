const base = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
  focusable: false,
};

function Icon({ size, children, ...rest }) {
  return (
    <svg {...base} {...(size ? { width: size, height: size } : {})} {...rest}>
      {children}
    </svg>
  );
}

export const IconCalendar = (p) => <Icon {...p}><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></Icon>;
export const IconPump = (p) => <Icon {...p}><path d="M5 20V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v15" /><path d="M3.5 20h13M8 8h4" /><path d="M15 9h2.5a2 2 0 0 1 2 2v5a1.5 1.5 0 0 0 3 0v-6l-2.5-2.5" /></Icon>;
export const IconTank = (p) => <Icon {...p}><ellipse cx="12" cy="6" rx="7.5" ry="2.5" /><path d="M4.5 6v12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5V6" /><path d="M4.5 12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5" /></Icon>;
export const IconLedger = (p) => <Icon {...p}><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" /><path d="M9.5 8h5M9.5 12h5" /></Icon>;
export const IconCheckSquare = (p) => <Icon {...p}><path d="M4 12.5 9 17.5 20 6.5" /></Icon>;
export const IconCamera = (p) => <Icon {...p}><path d="M4 8.5A1.5 1.5 0 0 1 5.5 7H8l1.2-2h5.6L16 7h2.5A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z" /><circle cx="12" cy="13" r="3.4" /></Icon>;
export const IconImage = (p) => <Icon {...p}><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="m4 17 5-4.5 4 3.5 2.5-2L20 17" /></Icon>;
export const IconPlus = (p) => <Icon {...p}><path d="M12 5v14M5 12h14" /></Icon>;
export const IconTrash = (p) => <Icon {...p}><path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.8 12.5h9.4L17.5 7M10 11v5M14 11v5" /></Icon>;
export const IconClose = (p) => <Icon {...p}><path d="M6 6l12 12M18 6 6 18" /></Icon>;
export const IconAlert = (p) => <Icon {...p}><path d="M12 3.5 21.5 20h-19z" /><path d="M12 10v4.5M12 17.4v.1" /></Icon>;
export const IconInfo = (p) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 7.9v.1" /></Icon>;
export const IconCheckCircle = (p) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="m8 12.3 2.7 2.7L16 9.5" /></Icon>;
export const IconDraft = (p) => <Icon {...p}><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 12h6M9 16h4" /></Icon>;
export const IconArrowRight = (p) => <Icon {...p}><path d="M5 12h14M13 6l6 6-6 6" /></Icon>;
export const IconRefresh = (p) => <Icon {...p}><path d="M20 11a8 8 0 0 0-14.4-4.2L4 9M4 4v5h5M4 13a8 8 0 0 0 14.4 4.2L20 15M20 20v-5h-5" /></Icon>;
export const IconUser = (p) => <Icon {...p}><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20c.6-3.6 3.4-5.5 7-5.5s6.4 1.9 7 5.5" /></Icon>;
export const IconLock = (p) => <Icon {...p}><rect x="5" y="10.5" width="14" height="10" rx="2" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" /></Icon>;
export const IconUnplug = (p) => <Icon {...p}><path d="M9 3v4M15 3v4M7 7h10v3.5a5 5 0 0 1-10 0z" /><path d="M12 15.5V21" /><path d="m3 3 18 18" /></Icon>;

export function BrandMark({ size = 40 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <path d="M24 2.5 43 13.5v21L24 45.5 5 34.5v-21z" fill="#F5B301" />
      <path d="M24 10c4.6 6 8.4 10.1 8.4 15a8.4 8.4 0 0 1-16.8 0C15.6 20.1 19.4 16 24 10z" fill="#0C1820" />
      <path d="M20.5 26.5a3.6 3.600 0 0 0 3.5 3.700" fill="none" stroke="#F5B301" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
