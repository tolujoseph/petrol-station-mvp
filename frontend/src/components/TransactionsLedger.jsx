import { CURRENCY_SYMBOL } from "../format";
import { IconPlus, IconTrash } from "./Icons";
import { TRANSACTION_TYPES } from "./transactionTypes";

export default function TransactionsLedger({ rows, disabled, onChange, onAdd, onRemove }) {
  return (
    <div className="ledger">
      <div className="ledger__head" aria-hidden="true">
        <span>Type</span><span>Product</span><span>Amount</span><span>Reference</span><span />
      </div>

      {rows.map((row, index) => {
        const isExpense = row.transaction_type === "expense";
        return (
          <div className="ledger__row" key={index} role="group" aria-label={`Transaction ${index + 1}`}>
            <div className="field">
              <label htmlFor={`tx-type-${index}`}>Type</label>
              <select id={`tx-type-${index}`} value={row.transaction_type} disabled={disabled} onChange={(event) => onChange(index, { transaction_type: event.target.value })}>
                {TRANSACTION_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor={`tx-product-${index}`}>Product</label>
              {isExpense ? (
                <div className="field__static" id={`tx-product-${index}`}>Not applicable</div>
              ) : (
                <select id={`tx-product-${index}`} value={row.product_type} disabled={disabled} onChange={(event) => onChange(index, { product_type: event.target.value })}>
                  <option value="PMS">PMS · Petrol</option>
                  <option value="AGO">AGO · Diesel</option>
                </select>
              )}
            </div>
            <div className="field">
              <label htmlFor={`tx-amount-${index}`}>Amount</label>
              <div className="money">
                <span className="money__symbol">{CURRENCY_SYMBOL}</span>
                <input id={`tx-amount-${index}`} type="number" inputMode="decimal" min="0" step="0.01" placeholder="0.00" value={row.amount} disabled={disabled} onChange={(event) => onChange(index, { amount: event.target.value })} />
              </div>
            </div>
            <div className="field">
              <label htmlFor={`tx-desc-${index}`}>Reference <span className="field__opt">optional</span></label>
              <input id={`tx-desc-${index}`} type="text" value={row.description} placeholder="Receipt no. or note" disabled={disabled} onChange={(event) => onChange(index, { description: event.target.value })} />
            </div>
            <div className="ledger__remove">
              {rows.length > 1 && (
                <button type="button" className="icon-btn icon-btn--danger" disabled={disabled} onClick={() => onRemove(index)} aria-label={`Remove transaction ${index + 1}`} title="Remove">
                  <IconTrash size={18} />
                </button>
              )}
            </div>
          </div>
        );
      })}

      <button type="button" className="btn btn--outline btn--sm ledger__add" disabled={disabled} onClick={onAdd}>
        <IconPlus size={16} /> Add transaction
      </button>
    </div>
  );
}
