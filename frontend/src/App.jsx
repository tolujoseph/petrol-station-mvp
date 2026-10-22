import { useEffect, useMemo, useState } from "react";
import "./App.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
const MAX_IMAGE_SIZE = 10 * 1024 * 1024;
const TRANSACTION_TYPES = [
  { value: "POS", label: "POS sales" },
  { value: "cash_bank", label: "Cash / bank sales" },
  { value: "CREDIT", label: "Credit sales" },
  { value: "expense", label: "Expense" },
  { value: "transfer", label: "Transfer" },
  { value: "shell_deposit", label: "Shell deposit" },
];

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
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
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

  const activePumpIds = useMemo(() => new Set(selectedPumpIds.map(Number)), [selectedPumpIds]);
  const activeTankIds = useMemo(() => new Set(selectedTankIds.map(Number)), [selectedTankIds]);

  async function refreshDrafts() {
    const response = await fetch(`${API_BASE_URL}/daily-entries/`, { credentials: "include" });
    const data = await readResponse(response);
    setDrafts(Array.isArray(data) ? data : []);
  }

  useEffect(() => {
    async function loadPage() {
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
        setError(err.message || "Could not load the station.");
      } finally {
        setLoading(false);
      }
    }
    loadPage();
  }, []);

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
      counts[key] = (counts[key] ?? 0) + count;
    }
    for (const tankId of selectedTankIds) {
      const key = `tank-${tankId}`;
      const count = await uploadEvidence(key, ids.tanks[tankId], "tank");
      counts[key] = (counts[key] ?? 0) + count;
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
      setPumpReadings(Object.fromEntries(savedDraft.pump_readings.map((item) => [item.pump, item.closing_reading])));
      setTankReadings(Object.fromEntries(savedDraft.tank_readings.map((item) => [item.tank, item.closing_reading])));
      setUploadedEvidence((previous) => ({
        ...previous,
        ...Object.fromEntries(savedDraft.pump_readings.map((item) => [`pump-${item.pump}`, item.evidence_count ?? 0])),
        ...Object.fromEntries(savedDraft.tank_readings.map((item) => [`tank-${item.tank}`, item.evidence_count ?? 0])),
      }));

      const evidenceCounts = await uploadAllEvidence(savedDraft);
      if (mode === "finalise") {
        const missingPump = chosenPumpIds.find((id) => (evidenceCounts[`pump-${id}`] ?? 0) < 1);
        const missingTank = chosenTankIds.find((id) => (evidenceCounts[`tank-${id}`] ?? 0) < 1);
        if (missingPump || missingTank) {
          throw new Error("Add at least one evidence photo for every selected pump and tank before submitting.");
        }
        const csrfToken = await getCsrfToken();
        const finaliseResponse = await fetch(`${API_BASE_URL}/daily-entries/${savedDraft.id}/finalise/`, {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRFToken": csrfToken },
        });
        const result = await readResponse(finaliseResponse);
        setDraft(null);
        resetForm();
        await refreshDrafts();
        setSuccess(result.message || "Daily entry submitted and reconciled successfully.");
      } else {
        await refreshDrafts();
        setDraft(null);
        resetForm();
        setSuccess("Draft saved. You can continue later from your saved drafts.");
      }
    } catch (err) {
      setError(err.message || "Could not save the daily entry.");
      if (draft) {
        try { await refreshDrafts(); } catch { /* keep the original error visible */ }
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
    const message = draft
      ? "Leave this draft? Your saved draft will be kept, and you can resume it later. Unsaved changes in this session will be lost."
      : "Cancel this entry? Any unsaved readings and selected photos will be lost.";
    if (!window.confirm(message)) return;
    setError("");
    setSuccess(draft ? "Draft kept. You can resume it from Saved drafts." : "Entry cancelled.");
    resetForm();
    refreshDrafts().catch(() => {});
  }

  async function discardDraft(draftId) {
    if (!window.confirm("Permanently discard this saved draft? Its readings and uploaded evidence will be deleted. This cannot be undone.")) return;
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
  }

  function renderEvidenceUploader(key, readingId, evidenceType) {
    const files = selectedPhotos[key] ?? [];
    const count = uploadedEvidence[key] ?? 0;
    const state = uploadStatus[key];
    return (
      <div className="evidence-section">
        <div className="evidence-heading">
          <div>
            <label className="evidence-label">📸 Reading photo evidence</label>
            <p className="evidence-help">Add a photo of the meter or dip reading.</p>
          </div>
          <span className={`evidence-indicator ${count > 0 || files.length > 0 ? "complete" : ""}`}>
            {count > 0 ? `${count} photo(s) saved` : files.length ? `${files.length} selected` : "Photo required"}
          </span>
        </div>
        <div className="evidence-choice-grid">
          <label className="evidence-choice">
            <span className="evidence-choice-icon">📷</span><span className="evidence-choice-title">Take photo</span><span className="evidence-choice-help">Use phone camera</span>
            <input type="file" accept="image/*" capture="environment" disabled={saving} onChange={(event) => { addPhotos(key, event.target.files); event.target.value = ""; }} />
          </label>
          <label className="evidence-choice">
            <span className="evidence-choice-icon">🖼️</span><span className="evidence-choice-title">Choose photos</span><span className="evidence-choice-help">From photo library</span>
            <input type="file" accept="image/*" multiple disabled={saving} onChange={(event) => { addPhotos(key, event.target.files); event.target.value = ""; }} />
          </label>
        </div>
        {files.length > 0 && <div className="photo-selection"><strong className="photo-selection-count">{files.length} photo(s) selected</strong><div className="photo-preview-grid">
          {files.map((file, index) => <div className="photo-preview" key={`${file.name}-${file.lastModified}-${index}`}>
            <img src={URL.createObjectURL(file)} alt={`Selected evidence ${index + 1}`} /><span title={file.name}>{file.name}</span>
            <button type="button" className="remove-photo-button" disabled={saving} onClick={() => removePhoto(key, index)}>Remove</button>
          </div>)}
        </div></div>}
        {state === "uploading" && <p className="evidence-status">Uploading photos...</p>}
        {state === "uploaded" && <p className="evidence-status uploaded">✓ Photos uploaded</p>}
        {state === "failed" && <p className="evidence-status failed">Upload failed. Save again to retry.</p>}
        {!readingId && <p className="evidence-help">Photos will upload when you save the entry.</p>}
      </div>
    );
  }

  const formattedRole = currentUser?.role ? currentUser.role.charAt(0).toUpperCase() + currentUser.role.slice(1) : "Loading...";

  return (
    <div className="app">
      <header className="topbar"><div className="brand"><span className="brand-icon">⛽</span><div><h1>Javeln</h1><p>Petrol Station Management</p></div></div><span className="role-badge">{formattedRole}</span></header>
      <main className="main-content">
        <section className="page-heading"><p className="eyebrow">DAILY OPERATIONS</p><h2>Daily entry</h2><p>Record the readings and transactions, attach evidence, then submit when ready.</p>
          {currentUser?.station && <div className="station-label"><span className="status-dot" />{currentUser.station}</div>}
          {currentUser && <p className="user-label">Logged in as {currentUser.username}</p>}
        </section>
        {loading && <div className="notice">Loading your station...</div>}
        {error && <div className="notice error" role="alert"><strong>Something needs attention</strong><p>{error}</p></div>}
        {success && <div className="notice success" role="status"><strong>{success}</strong></div>}

        {!loading && currentUser?.role === "manager" && !draft && drafts.length > 0 && <section className="form-card saved-drafts-card">
          <div className="section-heading"><span className="step-number">↻</span><div><h3>Saved drafts</h3><p>Resume an unfinished entry or explicitly discard it.</p></div></div>
          {drafts.map((item) => <div className="saved-draft-row" key={item.id}>
            <div><strong>{item.entry_date}</strong><p>Draft #{item.id} · {item.pump_count} pump(s), {item.tank_count} tank(s)</p></div>
            <div className="draft-actions"><button type="button" className="secondary-button" onClick={() => resumeDraft(item.id)}>Resume draft</button><button type="button" className="text-danger-button" onClick={() => discardDraft(item.id)}>Discard</button></div>
          </div>)}
        </section>}

        {!loading && currentUser?.role === "manager" && <form onSubmit={(event) => handleSave(event, "finalise")}>
          <section className="form-card"><div className="section-heading"><span className="step-number">1</span><div><h3>Entry date</h3><p>Choose the business date for this entry.</p></div></div>
            <div className="form-field"><label htmlFor="entryDate">Business date</label><input id="entryDate" type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} disabled={saving} required /></div>
            <div className="form-field notes-field"><label htmlFor="entryNotes">Notes (optional)</label><textarea id="entryNotes" value={notes} onChange={(event) => setNotes(event.target.value)} disabled={saving} rows="3" placeholder="Add any notes about today's operations" /></div>
            {draft && <p className="draft-context">Editing saved draft #{draft.id}. Changes are saved when you choose an action below.</p>}
          </section>

          <section className="form-card"><div className="section-heading"><span className="step-number">2</span><div><h3>Pump readings</h3><p>Select pumps used today, enter closing readings and attach evidence.</p></div></div>
            {pumps.length === 0 && <p className="empty-state">No active pumps are configured for this station.</p>}
            {pumps.map((pump) => { const key = `pump-${pump.id}`; const selected = activePumpIds.has(Number(pump.id)); return <div className={`reading-item ${!selected ? "equipment-not-selected" : ""}`} key={pump.id}>
              <label className="equipment-used-toggle"><input type="checkbox" checked={selected} disabled={saving} onChange={(event) => toggleEquipment("pump", pump.id, event.target.checked)} /><span className="reading-name">{pump.label}</span><span className="equipment-type">{pump.product_type}</span><span className="used-label">Used today</span></label>
              {selected && <><div className="reading-input"><label htmlFor={key}>Closing meter reading</label><input id={key} type="number" min="0" step="0.01" placeholder="Enter meter reading" value={pumpReadings[pump.id] ?? ""} onChange={(event) => updatePumpReading(pump.id, event.target.value)} disabled={saving} required /></div>{renderEvidenceUploader(key, getReadingIds(draft).pumps[pump.id], "pump")}</>}
            </div>; })}
          </section>

          <section className="form-card"><div className="section-heading"><span className="step-number">3</span><div><h3>Tank readings</h3><p>Select tanks used today, enter closing dip readings and attach evidence.</p></div></div>
            {tanks.length === 0 && <p className="empty-state">No active tanks are configured for this station.</p>}
            {tanks.map((tank) => { const key = `tank-${tank.id}`; const selected = activeTankIds.has(Number(tank.id)); return <div className={`reading-item ${!selected ? "equipment-not-selected" : ""}`} key={tank.id}>
              <label className="equipment-used-toggle"><input type="checkbox" checked={selected} disabled={saving} onChange={(event) => toggleEquipment("tank", tank.id, event.target.checked)} /><span className="reading-name">{tank.label}</span><span className="equipment-type">{tank.product_type}</span><span className="used-label">Used today</span></label>
              {selected && <><div className="reading-input"><label htmlFor={key}>Closing dip reading</label><input id={key} type="number" min="0" step="0.01" placeholder="Enter dip reading" value={tankReadings[tank.id] ?? ""} onChange={(event) => updateTankReading(tank.id, event.target.value)} disabled={saving} required /></div>{renderEvidenceUploader(key, getReadingIds(draft).tanks[tank.id], "tank")}</>}
            </div>; })}
          </section>

          <section className="form-card"><div className="section-heading"><span className="step-number">4</span><div><h3>Financial transactions</h3><p>Enter the day's recorded sales and expenses. Leave unused rows blank.</p></div></div>
            {transactions.map((item, index) => <div className="transaction-row" key={index}>
              <div className="form-field"><label htmlFor={`transaction-type-${index}`}>Transaction type</label><select id={`transaction-type-${index}`} value={item.transaction_type} disabled={saving} onChange={(event) => setTransactions((previous) => previous.map((row, rowIndex) => rowIndex === index ? { ...row, transaction_type: event.target.value } : row))}>{TRANSACTION_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}</select></div>
              {item.transaction_type !== "expense" && <div className="form-field"><label htmlFor={`transaction-product-${index}`}>Product</label><select id={`transaction-product-${index}`} value={item.product_type} disabled={saving} onChange={(event) => setTransactions((previous) => previous.map((row, rowIndex) => rowIndex === index ? { ...row, product_type: event.target.value } : row))}><option value="PMS">PMS</option><option value="AGO">AGO</option></select></div>}
              <div className="form-field"><label htmlFor={`transaction-amount-${index}`}>Amount (£)</label><input id={`transaction-amount-${index}`} type="number" min="0" step="0.01" value={item.amount} disabled={saving} onChange={(event) => setTransactions((previous) => previous.map((row, rowIndex) => rowIndex === index ? { ...row, amount: event.target.value } : row))} placeholder="0.00" /></div>
              <div className="form-field"><label htmlFor={`transaction-description-${index}`}>Description (optional)</label><input id={`transaction-description-${index}`} value={item.description} disabled={saving} onChange={(event) => setTransactions((previous) => previous.map((row, rowIndex) => rowIndex === index ? { ...row, description: event.target.value } : row))} placeholder="Reference or note" /></div>
              {transactions.length > 1 && <button type="button" className="text-danger-button remove-transaction" disabled={saving} onClick={() => setTransactions((previous) => previous.filter((_, rowIndex) => rowIndex !== index))}>Remove transaction</button>}
            </div>)}
            <button type="button" className="secondary-button add-transaction-button" disabled={saving} onClick={() => setTransactions((previous) => [...previous, emptyTransaction()])}>+ Add transaction</button>
          </section>

          <section className="form-card submit-card"><h3>{draft ? "Continue your draft" : "Finish this entry"}</h3><p>Submit finalises the entry and runs reconciliation. Saving keeps it as a draft so you can return later. Cancelling never deletes an already-saved draft.</p>
            <div className="entry-action-row">
              <button type="submit" className="primary-button" disabled={saving || !selectedPumpIds.length || !selectedTankIds.length}>{saving ? "Saving..." : "Submit entry"}</button>
              <button type="button" className="secondary-button" disabled={saving} onClick={(event) => handleSave(event, "save")}>{saving ? "Saving..." : "Save and continue later"}</button>
              <button type="button" className="cancel-button" disabled={saving} onClick={cancelEntry}>Cancel entry</button>
            </div>
          </section>
        </form>}

        {!loading && currentUser?.role === "owner" && <section className="form-card"><h3>Owner dashboard</h3><p>Daily results, discrepancy reports and station settings are the next frontend workstream.</p></section>}
        {!loading && currentUser && !["manager", "owner"].includes(currentUser.role) && <section className="notice">Your account role is not configured for this page.</section>}
      </main>
    </div>
  );
}

export default App;
