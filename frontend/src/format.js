export const CURRENCY_SYMBOL = import.meta.env.VITE_CURRENCY_SYMBOL || "₦";

const moneyFormatter = new Intl.NumberFormat("en-NG", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatMoney(value) {
  return `${CURRENCY_SYMBOL}${moneyFormatter.format(Number.isFinite(value) ? value : 0)}`;
}

export function formatLongDate(isoDate) {
  if (!isoDate) return "No date selected";
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
}

export function formatShortDate(isoDate) {
  if (!isoDate) return "—";
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}
