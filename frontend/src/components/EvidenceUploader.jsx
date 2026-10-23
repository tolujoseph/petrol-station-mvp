import { useEffect, useMemo } from "react";
import { IconCamera, IconCheckCircle, IconClose, IconImage } from "./Icons";

function PhotoThumb({ file, disabled, onRemove }) {
  const url = useMemo(() => URL.createObjectURL(file), [file]);

  useEffect(() => () => URL.revokeObjectURL(url), [url]);

  return (
    <li className="thumb">
      {url && <img src={url} alt={`Selected evidence ${file.name}`} />}
      <button type="button" className="thumb__remove" disabled={disabled} onClick={onRemove} aria-label={`Remove ${file.name}`}>
        <IconClose size={14} />
      </button>
    </li>
  );
}

export default function EvidenceUploader({ files, savedCount, status, hasReading, disabled, onAdd, onRemove }) {
  const pickHandler = (event) => {
    onAdd(event.target.files);
    event.target.value = "";
  };

  return (
    <div className="evidence">
      <div className="evidence__head">
        <span className="evidence__title">Photo evidence</span>
        {savedCount > 0 ? (
          <span className="tag tag--ok"><IconCheckCircle size={14} />{savedCount} saved</span>
        ) : files.length > 0 ? (
          <span className="tag tag--info">{files.length} ready to upload</span>
        ) : (
          <span className="tag">None yet</span>
        )}
      </div>

      <div className="evidence__row">
        <label className={`btn btn--outline btn--sm ${disabled ? "is-disabled" : ""}`}>
          <IconCamera size={16} /> Take photo
          <input type="file" accept="image/*" capture="environment" disabled={disabled} onChange={pickHandler} />
        </label>
        <label className={`btn btn--outline btn--sm ${disabled ? "is-disabled" : ""}`}>
          <IconImage size={16} /> Choose from library
          <input type="file" accept="image/*" multiple disabled={disabled} onChange={pickHandler} />
        </label>
        <span className="evidence__hint">Meter or dip-stick, clearly legible.</span>
      </div>

      {files.length > 0 && (
        <ul className="thumbs">
          {files.map((file, index) => (
            <PhotoThumb key={`${file.name}-${file.lastModified}-${index}`} file={file} disabled={disabled} onRemove={() => onRemove(index)} />
          ))}
        </ul>
      )}

      <div aria-live="polite">
        {status === "uploading" && <p className="evidence__status">Uploading photos…</p>}
        {status === "uploaded" && <p className="evidence__status evidence__status--ok">Photos uploaded.</p>}
        {status === "failed" && <p className="evidence__status evidence__status--bad">Upload failed. Save again to retry.</p>}
        {!hasReading && files.length > 0 && <p className="evidence__status">Photos upload when you save or submit.</p>}
      </div>
    </div>
  );
}
