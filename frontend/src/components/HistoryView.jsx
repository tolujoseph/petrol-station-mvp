import { useCallback, useEffect, useMemo, useState } from "react";
import { CURRENCY_SYMBOL, formatLongDate, formatMoney, formatShortDate } from "../format";
import { IconAlert, IconArrowRight, IconCheckCircle, IconChevronDown, IconHistory, IconRefresh, IconUnplug } from "./Icons";

const RANGES = [
  { id: "7", label: "7 days", days: 7 },
  { id: "30", label: "30 days", days: 30 },
  { id: "90", label: "90 days", days: 90 },
  { id: "all", label: "All time", days: null },
];

function isoDaysAgo(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

const num = (value) => (Number.isFinite(Number(value)) ? Number(value) : 0);
const litres = (value) => `${new Intl.NumberFormat("en-NG", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num(value))} L`;
const signed = (value, formatter) => {
  const n = num(value);
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${formatter(Math.abs(n))}`;
};
const asLitres = (n) => litres(n);
const compactMoney = (value) => `${value < 0 ? "−" : ""}${CURRENCY_SYMBOL}${new Intl.NumberFormat("en-NG", { notation: "compact", maximumFractionDigits: 2 }).format(Math.abs(value))}`;

// A day needs attention when physical stock is outside tolerance or sales are off by at least one cent.
// The backend's own discrepancy list also flags sub-cent rounding residue, so it isn't used here.
function hasVariance(item) {
  const physicalOff = item.physical_within_tolerance === false || (item.physical_within_tolerance == null && Math.abs(num(item.physical_difference)) >= 0.01);
  return physicalOff || Math.abs(num(item.financial_difference)) >= 0.01;
}

export default function HistoryView({ apiBaseUrl, onGoToEntry, canEnter }) {
  const [range, setRange] = useState("30");
  const [onlyVariance, setOnlyVariance] = useState(false);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState("");
  const [openId, setOpenId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setFailure("");
    const selected = RANGES.find((item) => item.id === range);
    const query = selected.days ? `?start_date=${isoDaysAgo(selected.days)}` : "";
    try {
      const response = await fetch(`${apiBaseUrl}/reports/daily-results/${query}`, { credentials: "include" });
      if (!response.ok) throw new Error(`Could not load history (${response.status}).`);
      const data = await response.json();
      setResults(Array.isArray(data) ? data : []);
    } catch (err) {
      setFailure(err instanceof TypeError ? "Can't reach the station server." : err.message);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, range]);

  useEffect(() => {
    load();
  }, [load]);

  const visible = useMemo(() => (onlyVariance ? results.filter(hasVariance) : results), [results, onlyVariance]);

  const totals = useMemo(() => ({
    days: results.length,
    sales: results.reduce((sum, item) => sum + num(item.actual_sales), 0),
    profit: results.reduce((sum, item) => sum + num(item.net_profit), 0),
    variance: results.filter(hasVariance).length,
  }), [results]);

  const trend = useMemo(() => [...results].slice(0, 30).reverse(), [results]);
  const maxSales = Math.max(1, ...trend.map((item) => num(item.actual_sales)));

  return (
    <>
      <div className="pagehead">
        <div>
          <p className="eyebrow">Records · Submitted entries</p>
          <h1>History</h1>
        </div>
        <div className="seg" role="group" aria-label="Date range">
          {RANGES.map((item) => (
            <button key={item.id} type="button" className={`seg__btn ${range === item.id ? "is-on" : ""}`} aria-pressed={range === item.id} onClick={() => setRange(item.id)}>{item.label}</button>
          ))}
        </div>
      </div>

      {loading && <div className="skeleton" aria-busy="true" aria-label="Loading history"><span /><span /></div>}

      {!loading && failure && (
        <section className="state-screen">
          <span className="state-screen__icon"><IconUnplug size={26} /></span>
          <h2>History unavailable</h2>
          <p>{failure}</p>
          <div className="state-screen__actions"><button type="button" className="btn btn--outline" onClick={load}><IconRefresh size={16} /> Try again</button></div>
        </section>
      )}

      {!loading && !failure && results.length === 0 && (
        <section className="state-screen">
          <span className="state-screen__icon"><IconHistory size={26} /></span>
          <h2>No submitted entries</h2>
          <p>{range === "all" ? "Entries appear here once a daily entry has been submitted and reconciled." : "Nothing was submitted in this period. Try a longer range."}</p>
          <div className="state-screen__actions">
            {range !== "all" && <button type="button" className="btn btn--outline" onClick={() => setRange("all")}>Show all time</button>}
            {canEnter && <button type="button" className="btn btn--primary" onClick={onGoToEntry}>Start a daily entry <IconArrowRight size={16} /></button>}
          </div>
        </section>
      )}

      {!loading && !failure && results.length > 0 && (
        <>
          <section className="stats" aria-label="Summary for selected period">
            <div className="stat"><span>Days recorded</span><strong>{totals.days}</strong></div>
            <div className="stat"><span>Sales recorded</span><strong title={formatMoney(totals.sales)}>{compactMoney(totals.sales)}</strong></div>
            <div className={`stat ${totals.profit < 0 ? "stat--bad" : ""}`}><span>Net profit</span><strong title={formatMoney(totals.profit)}>{compactMoney(totals.profit)}</strong></div>
            <div className={`stat ${totals.variance > 0 ? "stat--warn" : "stat--ok"}`}><span>Days with variance</span><strong>{totals.variance}</strong></div>
          </section>

          {trend.length > 1 && (
            <section className="panel trend" aria-label="Sales trend">
              <div className="panel__head">
                <p className="panel__tag">Trend · last {trend.length} entries</p>
                <h2>Daily sales</h2>
              </div>
              <div className="bars" role="img" aria-label={`Bar chart of daily sales, highest ${formatMoney(maxSales)}`}>
                {trend.map((item) => (
                  <div className="bars__col" key={item.id} title={`${formatShortDate(item.entry_date)} · ${formatMoney(num(item.actual_sales))}`}>
                    <span className={`bars__bar ${hasVariance(item) ? "is-variance" : ""}`} style={{ height: `${Math.max(4, (num(item.actual_sales) / maxSales) * 100)}%` }} />
                  </div>
                ))}
              </div>
              <div className="bars__legend"><span><i /> Balanced</span><span><i className="is-variance" /> Variance</span></div>
            </section>
          )}

          <section className="panel panel--flush" aria-label="Daily results">
            <div className="listbar">
              <div>
                <p className="panel__tag">Daily results</p>
                <h2>{visible.length} {visible.length === 1 ? "entry" : "entries"}</h2>
              </div>
              <label className="check">
                <input type="checkbox" checked={onlyVariance} onChange={(event) => setOnlyVariance(event.target.checked)} />
                <span>Variance only</span>
              </label>
            </div>

            {visible.length === 0 && <p className="empty empty--flush">No entries with variance in this period.</p>}

            <div className="results__head result__row" aria-hidden="true">
              <span>Date</span><span>Status</span><span>Pump volume</span><span>Actual sales</span><span>Net profit</span><span />
            </div>
            <ul className="results">
              {visible.map((item) => {
                const variance = hasVariance(item);
                const open = openId === item.id;
                return (
                  <li key={item.id} className={`result ${variance ? "has-variance" : ""} ${open ? "is-open" : ""}`}>
                    <button type="button" className="result__row" aria-expanded={open} onClick={() => setOpenId(open ? null : item.id)}>
                      <span className="result__date">
                        <strong>{formatShortDate(item.entry_date)}</strong>
                        <small>{new Intl.DateTimeFormat("en-GB", { weekday: "long" }).format(new Date(`${item.entry_date}T00:00:00`))}</small>
                      </span>
                      <span className={`pill ${variance ? "pill--warn" : "pill--ok"}`}>
                        {variance ? <IconAlert size={14} /> : <IconCheckCircle size={14} />}
                        {variance ? "Variance" : "Balanced"}
                      </span>
                      <span className="result__cell"><small>Pump volume</small><b>{litres(item.pump_volume)}</b></span>
                      <span className="result__cell"><small>Actual sales</small><b>{formatMoney(num(item.actual_sales))}</b></span>
                      <span className={`result__cell result__cell--profit ${num(item.net_profit) < 0 ? "is-neg" : ""}`}><small>Net profit</small><b>{formatMoney(num(item.net_profit))}</b></span>
                      <IconChevronDown size={18} className="result__chev" />
                    </button>

                    {open && (
                      <div className="result__detail">
                        <p className="result__when">{formatLongDate(item.entry_date)} · reconciled {new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" }).format(new Date(item.calculated_at))}</p>
                        <div className="detail-grid">
                          <section>
                            <h3>Fuel reconciliation</h3>
                            <dl>
                              <div><dt>Pump volume</dt><dd>{litres(item.pump_volume)}</dd></div>
                              <div><dt>Tank movement</dt><dd>{litres(item.tank_movement)}</dd></div>
                              <div className={num(item.physical_difference) !== 0 ? "diff" : ""}>
                                <dt>Physical difference</dt>
                                <dd>{signed(item.physical_difference, asLitres)}{item.physical_within_tolerance === true && " · within tolerance"}{item.physical_within_tolerance === false && " · outside tolerance"}</dd>
                              </div>
                            </dl>
                          </section>
                          <section>
                            <h3>Sales reconciliation</h3>
                            <dl>
                              <div><dt>Expected revenue</dt><dd>{formatMoney(num(item.expected_revenue))}</dd></div>
                              <div><dt>Actual sales</dt><dd>{formatMoney(num(item.actual_sales))}</dd></div>
                              <div className={num(item.financial_difference) !== 0 ? "diff" : ""}><dt>Financial difference</dt><dd>{signed(item.financial_difference, formatMoney)}</dd></div>
                            </dl>
                          </section>
                          <section>
                            <h3>Profit</h3>
                            <dl>
                              <div><dt>Fuel cost</dt><dd>{formatMoney(num(item.fuel_cost))}</dd></div>
                              <div><dt>Gross profit</dt><dd>{formatMoney(num(item.gross_profit))}</dd></div>
                              <div><dt>Expenses</dt><dd>{formatMoney(num(item.expenses))}</dd></div>
                              <div className="total"><dt>Net profit</dt><dd>{formatMoney(num(item.net_profit))}</dd></div>
                            </dl>
                          </section>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        </>
      )}
    </>
  );
}
