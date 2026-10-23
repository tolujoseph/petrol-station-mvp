import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import ConfirmDialog from "./components/ConfirmDialog";
import HistoryView from "./components/HistoryView";
import EquipmentCard from "./components/EquipmentCard";
import EvidenceUploader from "./components/EvidenceUploader";
import {
  BrandMark,
  IconAlert,
  IconArrowRight,
  IconCheckCircle,
  IconClose,
  IconDraft,
  IconEdit,
  IconHistory,
  IconLock,
  IconRefresh,
  IconUnplug,
  IconUser,
} from "./components/Icons";
import StepRail from "./components/StepRail";
import { STEPS } from "./components/steps";
import TransactionsLedger from "./components/TransactionsLedger";
import { formatLongDate, formatMoney, formatShortDate } from "./format";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
const API_ORIGIN = API_BASE_URL.replace(/\/api\/?$/, "");
const MAX_IMAGE_SIZE = 10 * 1024 * 1024;
const SALES_TYPES = ["POS", "cash_bank", "CREDIT"];

function getToday() {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function getCookie(name) {
  const cookies = document.cookie ? document.cookie.split("; ") : [];
  for (const cookie of cookies) {
    const separator = cookie.indexOf("=");
    if (separator !== -1 && cookie.slice(0, separator) === name) {
      return decodeURIComponent(cookie.slice(separator + 1));
    }
  }
  return null;
}

async function getCsrfToken() {
  const response = await fetch(`${API_BASE_URL}/auth/csrf/`, { credentials: "include" });
  if (!response.ok) throw new Error("Could not initialise security protection.");
  const token = getCookie("csrftoken");
  if (!token) throw new Error("Security token missing. Please refresh the page.");
  return token;
}

async function readResponse(response) {
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail || data.non_field_errors?.join(" ") || JSON.stringify(data);
    const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    error.status = response.status;
    throw error;
  }
  return data;
}

function emptyTransaction() {
  return { product_type: "PMS", transaction_type: "POS", amount: "", description: "" };
}

function App() {
  const [entryDate, setEntryDate] = useState(getToday());
  const [currentUser, setCurrentUser] = useState(null);
  const [pumps, setPumps] = useState([]);
  const [tanks, setTanks] = useState([]);
  const [selectedPumpIds, setSelectedPumpIds] = useState([]);
  const [selectedTankIds, setSelectedTankIds] = useState([]);
  const [pumpReadings, setPumpReadings] = useState({});
  const [tankReadings, setTankReadings] = useState({});
  const [transactions, setTransactions] = useState([emptyTransaction()]);
  const [selectedPhotos, setSelectedPhotos] = useState({});
  const [uploadStatus, setUploadStatus] = useState({});
  const [uploadedEvidence, setUploadedEvidence] = useState({});
  const [drafts, setDrafts] = useState([]);
  const [draft, setDraft] = useState(null);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [fatal, setFatal] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [activeStep, setActiveStep] = useState(STEPS[0].id);
  const bannerRef = useRef(null);
  const [view, setView] = useState(() => (window.location.hash === "#/history" ? "history" : "entry"));

  useEffect(() => {
    const onHashChange = () => setView(window.location.hash === "#/history" ? "history" : "entry");
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  function goTo(next) {
    window.location.hash = next === "history" ? "#/history" : "#/";
    window.scrollTo({ top: 0 });
  }

  const activePumpIds = useMemo(() => new Set(selectedPumpIds.map(Number)), [selectedPumpIds]);
  const activeTankIds = useMemo(() => new Set(selectedTankIds.map(Number)), [selectedTankIds]);

  async function refreshDrafts() {
    const response = await fetch(`${API_BASE_URL}/daily-entries/`, { credentials: "include" });
    const data = await readResponse(response);
    setDrafts(Array.isArray(data) ? data : []);
  }

  const loadPage = useCallback(async () => {
      setLoading(true);
      setFatal(null);
      try {
        const csrfResponse = await fetch(`${API_BASE_URL}/auth/csrf/`, { credentials: "include" });
        if (!csrfResponse.ok) throw new Error("Could not initialise security protection.");

        const userResponse = await fetch(`${API_BASE_URL}/auth/me/`, { credentials: "include" });
        const userData = await readResponse(userResponse);
        setCurrentUser(userData);

        const equipmentResponse = await fetch(`${API_BASE_URL}/station/equipment/`, { credentials: "include" });
        const equipmentData = await readResponse(equipmentResponse);
        const activePumps = (equipmentData.pumps ?? []).filter((pump) => pump.active);
        const activeTanks = (equipmentData.tanks ?? []).filter((tank) => tank.active);
        setPumps(activePumps);
        setTanks(activeTanks);
        setSelectedPumpIds(activePumps.map((pump) => pump.id));
        setSelectedTankIds(activeTanks.map((tank) => tank.id));
        setPumpReadings(Object.fromEntries(activePumps.map((pump) => [pump.id, ""])));
        setTankReadings(Object.fromEntries(activeTanks.map((tank) => [tank.id, ""])));
        if (userData.role === "manager") await refreshDrafts();
      } catch (err) {
        const unauthenticated = err.status === 401 || err.status === 403;
        const unreachable = err instanceof TypeError;
        setFatal({
          kind: unauthenticated ? "auth" : unreachable ? "network" : "other",
          message: err.message || "Could not load the station.",
        });
      } finally {
        setLoading(false);
      }
  }, []);

  useEffect(() => {
    loadPage();
  }, [loadPage]);

  function resetForm() {
    setEntryDate(getToday());
    setDraft(null);
    setNotes("");
    setSelectedPumpIds(pumps.map((pump) => pump.id));
    setSelectedTankIds(tanks.map((tank) => tank.id));
    setPumpReadings(Object.fromEntries(pumps.map((pump) => [pump.id, ""])));
    setTankReadings(Object.fromEntries(tanks.map((tank) => [tank.id, ""])));
    setTransactions([emptyTransaction()]);
    setSelectedPhotos({});
    setUploadStatus({});
    setUploadedEvidence({});
  }

  function updatePumpReading(id, value) {
    setPumpReadings((previous) => ({ ...previous, [id]: value }));
  }
  function updateTankReading(id, value) {
    setTankReadings((previous) => ({ ...previous, [id]: value }));
  }
  function toggleEquipment(type, id, checked) {
    const setter = type === "pump" ? setSelectedPumpIds : setSelectedTankIds;
    const readingsSetter = type === "pump" ? setPumpReadings : setTankReadings;
    const photoKey = `${type}-${id}`;
    setter((previous) => checked ? [...previous, id] : previous.filter((item) => item !== id));
    if (!checked) {
      readingsSetter((previous) => ({ ...previous, [id]: "" }));
      setSelectedPhotos((previous) => ({ ...previous, [photoKey]: [] }));
      setUploadedEvidence((previous) => ({ ...previous, [photoKey]: 0 }));
    }
  }

  function addPhotos(key, fileList) {
    const files = Array.from(fileList ?? []);
    if (!files.length) return;
    if (files.some((file) => !file.type.startsWith("image/"))) {
      setError("Please choose image files only.");
      return;
    }
    if (files.some((file) => file.size > MAX_IMAGE_SIZE)) {
      setError("Each photo must be 10 MB or smaller.");
      return;
    }
    setError("");
    setSuccess("");
    setSelectedPhotos((previous) => ({ ...previous, [key]: [...(previous[key] ?? []), ...files] }));
  }

  function removePhoto(key, indexToRemove) {
    setSelectedPhotos((previous) => ({
      ...previous,
      [key]: (previous[key] ?? []).filter((_, index) => index !== indexToRemove),
    }));
  }

  function getReadingIds(activeDraft) {
    return {
      pumps: Object.fromEntries((activeDraft?.pump_readings ?? []).map((item) => [item.pump, item.id])),
      tanks: Object.fromEntries((activeDraft?.tank_readings ?? []).map((item) => [item.tank, item.id])),
    };
  }

  async function uploadEvidence(key, readingId, evidenceType) {
    const files = selectedPhotos[key] ?? [];
    if (!readingId || files.length === 0) return 0;
    setUploadStatus((previous) => ({ ...previous, [key]: "uploading" }));
    try {
      const csrfToken = await getCsrfToken();
      const formData = new FormData();
      files.forEach((file) => formData.append("images", file));
      const endpoint = evidenceType === "pump"
        ? `${API_BASE_URL}/readings/pumps/${readingId}/evidence/`
        : `${API_BASE_URL}/readings/tanks/${readingId}/evidence/`;
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRFToken": csrfToken },
        body: formData,
      });
      const result = await readResponse(response);
      const uploadedCount = result.uploaded_count ?? files.length;
      setUploadedEvidence((previous) => ({ ...previous, [key]: (previous[key] ?? 0) + uploadedCount }));
      setSelectedPhotos((previous) => ({ ...previous, [key]: [] }));
      setUploadStatus((previous) => ({ ...previous, [key]: "uploaded" }));
      return uploadedCount;
    } catch (err) {
      setUploadStatus((previous) => ({ ...previous, [key]: "failed" }));
      throw new Error(`Photo upload failed for ${key}. ${err.message}`);
    }
  }


  async function uploadAllEvidence(activeDraft) {
    const ids = getReadingIds(activeDraft);
    const counts = { ...uploadedEvidence };

    for (const pumpId of selectedPumpIds) {
      const key = `pump-${pumpId}`;
      const count = await uploadEvidence(key, ids.pumps[pumpId], "pump");
      if (count > 0) {
        counts[key] = (counts[key] ?? 0) + count;
      }
    }

    for (const tankId of selectedTankIds) {
      const key = `tank-${tankId}`;
      const count = await uploadEvidence(key, ids.tanks[tankId], "tank");
      if (count > 0) {
        counts[key] = (counts[key] ?? 0) + count;
      }
    }

    setUploadedEvidence(counts);
    return counts;
  }


  function buildPayload() {
    const chosenPumps = pumps.filter((pump) => activePumpIds.has(Number(pump.id)));
    const chosenTanks = tanks.filter((tank) => activeTankIds.has(Number(tank.id)));
    const validReading = (value) => String(value ?? "").trim() !== "" && Number.isFinite(Number(value)) && Number(value) >= 0;
    if (!entryDate) throw new Error("Please select the business date.");
    if (!chosenPumps.length || !chosenTanks.length) throw new Error("Select at least one pump and one tank used today.");
    if (!chosenPumps.every((pump) => validReading(pumpReadings[pump.id]))) throw new Error("Enter a valid closing reading for every selected pump.");
    if (!chosenTanks.every((tank) => validReading(tankReadings[tank.id]))) throw new Error("Enter a valid closing reading for every selected tank.");

    const financialTransactions = transactions
      .filter((item) => String(item.amount).trim() !== "")
      .map((item) => {
        if (!Number.isFinite(Number(item.amount)) || Number(item.amount) < 0) {
          throw new Error("Transaction amounts must be valid non-negative numbers.");
        }
        return {
          product_type: item.transaction_type === "expense" ? "" : item.product_type,
          transaction_type: item.transaction_type,
          amount: Number(item.amount).toFixed(2),
          description: item.description.trim(),
        };
      });

    return {
      entry_date: entryDate,
      notes,
      pump_readings: chosenPumps.map((pump) => ({ pump: pump.id, closing_reading: Number(pumpReadings[pump.id]).toFixed(2) })),
      tank_readings: chosenTanks.map((tank) => ({ tank: tank.id, closing_reading: Number(tankReadings[tank.id]).toFixed(2) })),
      financial_transactions: financialTransactions,
    };
  }

  async function persistDraft(payload) {
    const csrfToken = await getCsrfToken();
    const response = await fetch(
      draft ? `${API_BASE_URL}/daily-entries/${draft.id}/` : `${API_BASE_URL}/daily-entries/`,
      {
        method: draft ? "PATCH" : "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify(payload),
      },
    );
    const saved = await readResponse(response);
    if (draft) return saved;
    const detailResponse = await fetch(`${API_BASE_URL}/daily-entries/${saved.id}/`, { credentials: "include" });
    return readResponse(detailResponse);
  }


  async function handleSave(event, mode) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setSaving(true);

    try {
      const payload = buildPayload();
      const savedDraft = await persistDraft(payload);

      setDraft(savedDraft);
      setEntryDate(savedDraft.entry_date);
      setNotes(savedDraft.notes ?? "");

      const chosenPumpIds = savedDraft.pump_readings.map((item) => item.pump);
      const chosenTankIds = savedDraft.tank_readings.map((item) => item.tank);

      setSelectedPumpIds(chosenPumpIds);
      setSelectedTankIds(chosenTankIds);

      setPumpReadings(
        Object.fromEntries(
          savedDraft.pump_readings.map((item) => [
            item.pump,
            item.closing_reading,
          ]),
        ),
      );

      setTankReadings(
        Object.fromEntries(
          savedDraft.tank_readings.map((item) => [
            item.tank,
            item.closing_reading,
          ]),
        ),
      );

      setUploadedEvidence((previous) => ({
        ...previous,
        ...Object.fromEntries(
          savedDraft.pump_readings.map((item) => [
            `pump-${item.pump}`,
            item.evidence_count ?? 0,
          ]),
        ),
        ...Object.fromEntries(
          savedDraft.tank_readings.map((item) => [
            `tank-${item.tank}`,
            item.evidence_count ?? 0,
          ]),
        ),
      }));

      // Photos remain supported, but are not required for submission.
      await uploadAllEvidence(savedDraft);

      if (mode === "finalise") {
        const csrfToken = await getCsrfToken();

        const finaliseResponse = await fetch(
          `${API_BASE_URL}/daily-entries/${savedDraft.id}/finalise/`,
          {
            method: "POST",
            credentials: "include",
            headers: { "X-CSRFToken": csrfToken },
          },
        );

        const result = await readResponse(finaliseResponse);

        setDraft(null);
        resetForm();
        await refreshDrafts();

        setSuccess(
          result.message || "Daily entry submitted and reconciled successfully.",
        );
      } else {
        await refreshDrafts();
        setDraft(null);
        resetForm();

        setSuccess(
          "Draft saved. You can continue later from your saved drafts.",
        );
      }
    } catch (err) {
      setError(err.message || "Could not save the daily entry.");

      if (draft) {
        try {
          await refreshDrafts();
        } catch {
          // Keep the original error visible.
        }
      }
    } finally {
      setSaving(false);
    }
  }

  async function resumeDraft(draftId) {
    setError("");
    setSuccess("");
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/daily-entries/${draftId}/`, { credentials: "include" });
      const detail = await readResponse(response);
      setDraft(detail);
      setEntryDate(detail.entry_date);
      setNotes(detail.notes ?? "");
      setSelectedPumpIds(detail.pump_readings.map((item) => item.pump));
      setSelectedTankIds(detail.tank_readings.map((item) => item.tank));
      setPumpReadings(Object.fromEntries(detail.pump_readings.map((item) => [item.pump, item.closing_reading])));
      setTankReadings(Object.fromEntries(detail.tank_readings.map((item) => [item.tank, item.closing_reading])));
      setTransactions(detail.financial_transactions.length ? detail.financial_transactions.map((item) => ({
        product_type: item.product_type || "PMS",
        transaction_type: item.transaction_type,
        amount: item.amount,
        description: item.description || "",
      })) : [emptyTransaction()]);
      setSelectedPhotos({});
      setUploadStatus({});
      setUploadedEvidence({
        ...Object.fromEntries(detail.pump_readings.map((item) => [`pump-${item.pump}`, item.evidence_count ?? 0])),
        ...Object.fromEntries(detail.tank_readings.map((item) => [`tank-${item.tank}`, item.evidence_count ?? 0])),
      });
    } catch (err) {
      setError(err.message || "Could not reopen this draft.");
    } finally {
      setLoading(false);
    }
  }


  function cancelEntry() {
    setDialog({
      tone: "neutral",
      title: draft ? "Leave this draft?" : "Cancel this entry?",
      body: draft
        ? "Your saved draft is kept and you can resume it later. Changes made since your last save will be lost."
        : "Unsaved readings and selected photos will be lost.",
      confirmLabel: draft ? "Leave draft" : "Cancel entry",
      cancelLabel: "Keep editing",
      onConfirm: () => {
        setError("");
        setSuccess(draft ? "Draft kept. Resume it from Saved drafts." : "Entry cancelled.");
        resetForm();
        refreshDrafts().catch(() => {});
      },
    });
  }

  function discardDraft(draftId) {
    setDialog({
      tone: "danger",
      title: "Discard this draft permanently?",
      body: "Its readings and uploaded evidence will be deleted. This cannot be undone.",
      confirmLabel: "Discard draft",
      cancelLabel: "Keep draft",
      onConfirm: async () => {
        setError("");
        setSuccess("");
        try {
          const csrfToken = await getCsrfToken();
          const response = await fetch(`${API_BASE_URL}/daily-entries/${draftId}/`, {
            method: "DELETE",
            credentials: "include",
            headers: { "X-CSRFToken": csrfToken },
          });
          await readResponse(response);
          if (draft?.id === draftId) resetForm();
          await refreshDrafts();
          setSuccess("Draft discarded.");
        } catch (err) {
          setError(err.message || "Could not discard the draft.");
        }
      },
    });
  }

  function updateTransaction(index, patch) {
    setTransactions((previous) => previous.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)));
  }

  // ---- derived progress ----
  const validReading = (value) => String(value ?? "").trim() !== "" && Number.isFinite(Number(value)) && Number(value) >= 0;
  const pumpsEntered = selectedPumpIds.filter((id) => validReading(pumpReadings[id])).length;
  const tanksEntered = selectedTankIds.filter((id) => validReading(tankReadings[id])).length;
  const pumpsDone = selectedPumpIds.length > 0 && pumpsEntered === selectedPumpIds.length;
  const tanksDone = selectedTankIds.length > 0 && tanksEntered === selectedTankIds.length;
  const totals = useMemo(() => {
    const sum = (predicate) => transactions.reduce((acc, row) => (predicate(row) && Number.isFinite(Number(row.amount)) ? acc + Number(row.amount || 0) : acc), 0);
    return {
      sales: sum((row) => SALES_TYPES.includes(row.transaction_type)),
      expenses: sum((row) => row.transaction_type === "expense"),
      count: transactions.filter((row) => String(row.amount).trim() !== "").length,
    };
  }, [transactions]);
  const ready = Boolean(entryDate) && pumpsDone && tanksDone;
  const photoCount = Object.values(uploadedEvidence).reduce((a, b) => a + b, 0) + Object.values(selectedPhotos).reduce((a, b) => a + b.length, 0);
  const done = {
    "step-date": Boolean(entryDate),
    "step-pumps": pumpsDone,
    "step-tanks": tanksDone,
    "step-ledger": totals.count > 0,
    "step-submit": ready,
  };
  const completed = Object.values(done).filter(Boolean).length;
  const isManager = !loading && !fatal && currentUser?.role === "manager" && view === "entry";

  // scroll-spy for the step tracker
  useEffect(() => {
    if (!isManager) return undefined;
    const sections = STEPS.map((step) => document.getElementById(step.id)).filter(Boolean);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveStep(visible[0].target.id);
      },
      { rootMargin: "-20% 0px -60% 0px" },
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [isManager, draft]);

  useEffect(() => {
    if ((error || success) && bannerRef.current) bannerRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [error, success]);

  function jumpTo(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const initials = (currentUser?.username || "?").slice(0, 2).toUpperCase();
  const roleLabel = currentUser?.role ? currentUser.role.charAt(0).toUpperCase() + currentUser.role.slice(1) : "";

  function renderEvidence(key, readingId) {
    return (
      <EvidenceUploader
        files={selectedPhotos[key] ?? []}
        savedCount={uploadedEvidence[key] ?? 0}
        status={uploadStatus[key]}
        hasReading={Boolean(readingId)}
        disabled={saving}
        onAdd={(fileList) => addPhotos(key, fileList)}
        onRemove={(index) => removePhoto(key, index)}
      />
    );
  }

  function renderStateScreen() {
    if (!fatal) return null;
    const screens = {
      auth: {
        icon: <IconLock size={26} />,
        title: "Sign in to continue",
        body: "This workspace uses your station session. Sign in with your station account, then return here and reload.",
        action: <a className="btn btn--primary" href={`${API_ORIGIN}/admin/login/`} target="_blank" rel="noreferrer">Open sign-in <IconArrowRight size={16} /></a>,
      },
      network: {
        icon: <IconUnplug size={26} />,
        title: "Can't reach the station server",
        body: `The app couldn't connect to ${API_BASE_URL}. Check that the backend is running and that this address is correct.`,
      },
      other: {
        icon: <IconAlert size={26} />,
        title: "Something went wrong",
        body: fatal.message,
      },
    };
    const screen = screens[fatal.kind];
    return (
      <section className="state-screen">
        <span className="state-screen__icon">{screen.icon}</span>
        <h2>{screen.title}</h2>
        <p>{screen.body}</p>
        <div className="state-screen__actions">
          {screen.action}
          <button type="button" className="btn btn--outline" onClick={loadPage}><IconRefresh size={16} /> Try again</button>
        </div>
      </section>
    );
  }

  return (
    <div className="shell">
      <aside className="rail">
        <div className="rail__brand">
          <BrandMark size={38} />
          <div>
            <p className="rail__name">Javeln</p>
            <p className="rail__sub">Forecourt Operations</p>
          </div>
        </div>

        {currentUser && !fatal && (
          <nav className="rail__nav" aria-label="Main">
            <button type="button" className={`navlink ${view === "entry" ? "is-active" : ""}`} aria-current={view === "entry" ? "page" : undefined} onClick={() => goTo("entry")}><IconEdit size={18} /> Daily entry</button>
            <button type="button" className={`navlink ${view === "history" ? "is-active" : ""}`} aria-current={view === "history" ? "page" : undefined} onClick={() => goTo("history")}><IconHistory size={18} /> History</button>
          </nav>
        )}

        {isManager && (
          <>
            <div className="rail__block">
              <p className="rail__kicker">Station</p>
              <p className="rail__station">{currentUser.station || "Unassigned"}</p>
            </div>

            <div className="rail__block">
              <div className="rail__kicker-row">
                <p className="rail__kicker">Entry progress</p>
                <p className="rail__count">{completed}/{STEPS.length}</p>
              </div>
              <div className="meter" role="progressbar" aria-valuemin={0} aria-valuemax={STEPS.length} aria-valuenow={completed} aria-label="Entry progress">
                <span className="meter__fill" style={{ width: `${(completed / STEPS.length) * 100}%` }} />
              </div>
              <StepRail activeId={activeStep} done={done} onJump={jumpTo} />
            </div>

            <div className="rail__block rail__block--summary">
              <p className="rail__kicker">Shift summary</p>
              <dl className="summary">
                <div><dt>Pumps recorded</dt><dd>{pumpsEntered}<span>/{selectedPumpIds.length}</span></dd></div>
                <div><dt>Tanks recorded</dt><dd>{tanksEntered}<span>/{selectedTankIds.length}</span></dd></div>
                <div><dt>Evidence photos</dt><dd>{photoCount}</dd></div>
                <div className="summary__money"><dt>Sales logged</dt><dd>{formatMoney(totals.sales)}</dd></div>
                <div className="summary__money"><dt>Expenses</dt><dd>{formatMoney(totals.expenses)}</dd></div>
              </dl>
            </div>
          </>
        )}

        <div className="rail__spacer" />
        <div className="rail__user">
          <span className="avatar">{currentUser ? initials : <IconUser size={16} />}</span>
          <div>
            <p className="rail__username">{currentUser?.username ?? (loading ? "Connecting…" : "Signed out")}</p>
            <p className="rail__role">{roleLabel || "—"}</p>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="mobilebar">
          <BrandMark size={30} />
          <div className="mobilebar__text">
            <strong>Javeln</strong>
            <span>{currentUser?.station || "Forecourt Operations"}</span>
          </div>
          {isManager && <span className="mobilebar__progress">{completed}/{STEPS.length}</span>}
          {currentUser && !fatal && (
            <nav className="mobilenav" aria-label="Main">
              <button type="button" className={view === "entry" ? "is-active" : ""} onClick={() => goTo("entry")}><IconEdit size={16} /> Daily entry</button>
              <button type="button" className={view === "history" ? "is-active" : ""} onClick={() => goTo("history")}><IconHistory size={16} /> History</button>
            </nav>
          )}
        </header>

        <main className="main">
          {view === "history" && !loading && !fatal && currentUser ? (
            <HistoryView apiBaseUrl={API_BASE_URL} canEnter={currentUser.role === "manager"} onGoToEntry={() => goTo("entry")} />
          ) : (
          <>
          <div className="pagehead">
            <div>
              <p className="eyebrow">{view === "history" ? "Records · Submitted entries" : "Daily operations · End-of-day close"}</p>
              <h1>{view === "history" ? "History" : "Daily entry"}</h1>
            </div>
            {isManager && (
              <div className={`entrystate ${draft ? "entrystate--draft" : ""}`}>
                <span className="entrystate__dot" />
                {draft ? `Editing draft #${draft.id}` : "New entry"}
              </div>
            )}
          </div>

          <div ref={bannerRef} className="banners" aria-live="polite">
            {error && (
              <div className="banner banner--error" role="alert">
                <IconAlert size={20} />
                <div><strong>Needs attention</strong><p>{error}</p></div>
                <button type="button" className="icon-btn" onClick={() => setError("")} aria-label="Dismiss"><IconClose size={16} /></button>
              </div>
            )}
            {success && (
              <div className="banner banner--success" role="status">
                <IconCheckCircle size={20} />
                <div><strong>{success}</strong></div>
                <button type="button" className="icon-btn" onClick={() => setSuccess("")} aria-label="Dismiss"><IconClose size={16} /></button>
              </div>
            )}
          </div>

          {loading && (
            <div className="skeleton" aria-busy="true" aria-label="Loading your station">
              <span /><span /><span />
            </div>
          )}

          {renderStateScreen()}

          {isManager && drafts.length > 0 && !draft && (
            <section className="panel panel--drafts" aria-labelledby="drafts-title">
              <div className="panel__head">
                <p className="panel__tag">Resume</p>
                <h2 id="drafts-title">Saved drafts</h2>
                <p className="panel__lede">Pick up an unfinished entry, or discard it for good.</p>
              </div>
              <ul className="drafts">
                {drafts.map((item) => (
                  <li className="drafts__row" key={item.id}>
                    <span className="drafts__icon"><IconDraft size={20} /></span>
                    <div className="drafts__meta">
                      <strong>{formatShortDate(item.entry_date)}</strong>
                      <span>Draft #{item.id} · {item.pump_count} pump{item.pump_count === 1 ? "" : "s"} · {item.tank_count} tank{item.tank_count === 1 ? "" : "s"}</span>
                    </div>
                    <div className="drafts__actions">
                      <button type="button" className="btn btn--secondary btn--sm" onClick={() => resumeDraft(item.id)}>Resume</button>
                      <button type="button" className="btn btn--text-danger btn--sm" onClick={() => discardDraft(item.id)}>Discard</button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {isManager && (
            <form onSubmit={(event) => handleSave(event, "finalise")} noValidate={false}>
              <section className="panel" id="step-date" aria-labelledby="date-title">
                <div className="panel__head">
                  <p className="panel__tag">Section 01</p>
                  <h2 id="date-title">Business date</h2>
                  <p className="panel__lede">The trading day this entry closes out.</p>
                </div>
                <div className="date-grid">
                  <div className="field">
                    <label htmlFor="entryDate">Business date</label>
                    <input id="entryDate" type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} disabled={saving} required />
                    <p className="field__help">{formatLongDate(entryDate)}</p>
                  </div>
                  <div className="field">
                    <label htmlFor="entryNotes">Shift notes <span className="field__opt">optional</span></label>
                    <textarea id="entryNotes" value={notes} onChange={(event) => setNotes(event.target.value)} disabled={saving} rows="3" placeholder="Deliveries, outages, incidents or anything the owner should know" />
                  </div>
                </div>
              </section>

              <section className="panel" id="step-pumps" aria-labelledby="pumps-title">
                <div className="panel__head">
                  <p className="panel__tag">Section 02 · {pumpsEntered}/{selectedPumpIds.length} recorded</p>
                  <h2 id="pumps-title">Pump meters</h2>
                  <p className="panel__lede">Switch on each pump used today, then record its closing meter reading.</p>
                </div>
                {pumps.length === 0 && <p className="empty">No active pumps are configured for this station.</p>}
                <div className="units">
                  {pumps.map((pump) => {
                    const key = `pump-${pump.id}`;
                    return (
                      <EquipmentCard key={pump.id} type="pump" item={pump} selected={activePumpIds.has(Number(pump.id))} value={pumpReadings[pump.id]} disabled={saving} onToggle={(checked) => toggleEquipment("pump", pump.id, checked)} onChange={(value) => updatePumpReading(pump.id, value)}>
                        {renderEvidence(key, getReadingIds(draft).pumps[pump.id])}
                      </EquipmentCard>
                    );
                  })}
                </div>
              </section>

              <section className="panel" id="step-tanks" aria-labelledby="tanks-title">
                <div className="panel__head">
                  <p className="panel__tag">Section 03 · {tanksEntered}/{selectedTankIds.length} recorded</p>
                  <h2 id="tanks-title">Tank dips</h2>
                  <p className="panel__lede">Switch on each tank in use and record its closing dip reading.</p>
                </div>
                {tanks.length === 0 && <p className="empty">No active tanks are configured for this station.</p>}
                <div className="units">
                  {tanks.map((tank) => {
                    const key = `tank-${tank.id}`;
                    return (
                      <EquipmentCard key={tank.id} type="tank" item={tank} selected={activeTankIds.has(Number(tank.id))} value={tankReadings[tank.id]} disabled={saving} onToggle={(checked) => toggleEquipment("tank", tank.id, checked)} onChange={(value) => updateTankReading(tank.id, value)}>
                        {renderEvidence(key, getReadingIds(draft).tanks[tank.id])}
                      </EquipmentCard>
                    );
                  })}
                </div>
              </section>

              <section className="panel" id="step-ledger" aria-labelledby="ledger-title">
                <div className="panel__head">
                  <p className="panel__tag">Section 04</p>
                  <h2 id="ledger-title">Transactions</h2>
                  <p className="panel__lede">Record the day's sales and expenses. Rows left without an amount are ignored.</p>
                </div>
                <TransactionsLedger
                  rows={transactions}
                  disabled={saving}
                  onChange={updateTransaction}
                  onAdd={() => setTransactions((previous) => [...previous, emptyTransaction()])}
                  onRemove={(index) => setTransactions((previous) => previous.filter((_, rowIndex) => rowIndex !== index))}
                />
                <div className="ledger-total">
                  <div><span>Sales logged</span><strong>{formatMoney(totals.sales)}</strong></div>
                  <div><span>Expenses</span><strong>{formatMoney(totals.expenses)}</strong></div>
                </div>
              </section>

              <section className="panel panel--submit" id="step-submit" aria-labelledby="submit-title">
                <div className="hazard" aria-hidden="true" />
                <div className="submit">
                  <div className="submit__copy">
                    <p className="panel__tag">Section 05</p>
                    <h2 id="submit-title">{draft ? "Continue your draft" : "Review & submit"}</h2>
                    <p className="panel__lede">Submitting finalises the entry and runs reconciliation. Saving keeps it as a draft to finish later.</p>
                    <ul className="checks">
                      <li className={entryDate ? "ok" : ""}>Business date set</li>
                      <li className={pumpsDone ? "ok" : ""}>Pump readings · {pumpsEntered}/{selectedPumpIds.length}</li>
                      <li className={tanksDone ? "ok" : ""}>Tank readings · {tanksEntered}/{selectedTankIds.length}</li>
                      <li className={photoCount > 0 ? "ok" : ""}>Evidence photos · {photoCount}</li>
                    </ul>
                  </div>
                  <div className="submit__actions">
                    <button type="submit" className="btn btn--primary btn--lg" disabled={saving || !selectedPumpIds.length || !selectedTankIds.length}>{saving ? "Working…" : "Submit entry"}{!saving && <IconArrowRight size={18} />}</button>
                    <button type="button" className="btn btn--secondary" disabled={saving} onClick={(event) => handleSave(event, "save")}>{saving ? "Working…" : "Save and continue later"}</button>
                    <button type="button" className="btn btn--ghost" disabled={saving} onClick={cancelEntry}>Cancel entry</button>
                  </div>
                </div>
              </section>
            </form>
          )}

          {!loading && !fatal && currentUser?.role === "owner" && (
            <section className="panel">
              <div className="panel__head">
                <p className="panel__tag">Owner</p>
                <h2>Owner dashboard</h2>
                <p className="panel__lede">Daily results, discrepancy reports and station settings are the next frontend workstream.</p>
              </div>
            </section>
          )}
          {!loading && !fatal && currentUser && !["manager", "owner"].includes(currentUser.role) && (
            <section className="state-screen">
              <span className="state-screen__icon"><IconLock size={26} /></span>
              <h2>No access configured</h2>
              <p>Your account ({currentUser.username}) has no manager or owner role. Ask an administrator to assign one.</p>
            </section>
          )}
          </>
          )}
        </main>
      </div>

      <ConfirmDialog dialog={dialog} onClose={() => setDialog(null)} />
    </div>
  );
}

export default App;
