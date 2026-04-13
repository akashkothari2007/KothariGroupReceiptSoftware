import { useState } from 'react'
import { API, authFetch } from '../utils/api'

function EditableRow({ item, fields, onSave, onDelete }) {
  const [editing, setEditing] = useState(false)
  const [values, setValues] = useState(item)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    await onSave(item.id, values)
    setSaving(false)
    setEditing(false)
  }

  const handleCancel = () => {
    setValues(item)
    setEditing(false)
  }

  return (
    <tr>
      {fields.map(f => (
        <td key={f.key}>
          {editing ? (
            <input
              className="settings-input"
              value={values[f.key] || ''}
              onChange={e => setValues(prev => ({ ...prev, [f.key]: e.target.value }))}
              placeholder={f.placeholder}
            />
          ) : (
            <span className="settings-value">{item[f.key] || '—'}</span>
          )}
        </td>
      ))}
      <td className="settings-actions">
        {editing ? (
          <>
            <button className="settings-btn settings-btn-save" onClick={handleSave} disabled={saving}>
              {saving ? '...' : 'Save'}
            </button>
            <button className="settings-btn settings-btn-cancel" onClick={handleCancel}>Cancel</button>
          </>
        ) : (
          <>
            <button className="settings-btn settings-btn-edit" onClick={() => setEditing(true)}>Edit</button>
            <button className="settings-btn settings-btn-delete" onClick={() => onDelete(item.id)}>Delete</button>
          </>
        )}
      </td>
    </tr>
  )
}

function AddRow({ fields, onAdd }) {
  const initial = {}
  fields.forEach(f => { initial[f.key] = '' })
  const [values, setValues] = useState(initial)
  const [adding, setAdding] = useState(false)

  const canAdd = fields.every(f => !f.required || values[f.key]?.trim())

  const handleAdd = async () => {
    setAdding(true)
    await onAdd(values)
    setValues(initial)
    setAdding(false)
  }

  return (
    <tr className="settings-add-row">
      {fields.map(f => (
        <td key={f.key}>
          <input
            className="settings-input"
            value={values[f.key]}
            onChange={e => setValues(prev => ({ ...prev, [f.key]: e.target.value }))}
            placeholder={f.placeholder}
          />
        </td>
      ))}
      <td className="settings-actions">
        <button
          className="settings-btn settings-btn-add"
          onClick={handleAdd}
          disabled={!canAdd || adding}
        >
          {adding ? '...' : '+ Add'}
        </button>
      </td>
    </tr>
  )
}

function SettingsTable({ title, items, fields, onCreate, onUpdate, onDelete }) {
  return (
    <div className="settings-card">
      <h3 className="settings-card-title">{title}</h3>
      <table className="settings-table">
        <thead>
          <tr>
            {fields.map(f => <th key={f.key}>{f.label}</th>)}
            <th className="settings-actions-col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map(item => (
            <EditableRow
              key={item.id}
              item={item}
              fields={fields}
              onSave={onUpdate}
              onDelete={onDelete}
            />
          ))}
          <AddRow fields={fields} onAdd={onCreate} />
        </tbody>
      </table>
      {items.length === 0 && (
        <div className="settings-empty">No items yet. Add one above.</div>
      )}
    </div>
  )
}

export function SettingsTab({ companies, glCodes, expenseTypes, onRefresh }) {
  const handleCreateCompany = async (values) => {
    try {
      await authFetch(`${API}/lookups/companies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: values.name }),
      })
      onRefresh()
    } catch {}
  }

  const handleUpdateCompany = async (id, values) => {
    try {
      await authFetch(`${API}/lookups/companies/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: values.name }),
      })
      onRefresh()
    } catch {}
  }

  const handleDeleteCompany = async (id) => {
    if (!confirm('Delete this company? Transactions assigned to it will become unassigned.')) return
    try {
      await authFetch(`${API}/lookups/companies/${id}`, { method: 'DELETE' })
      onRefresh()
    } catch {}
  }

  const handleCreateGlCode = async (values) => {
    try {
      await authFetch(`${API}/lookups/gl-codes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: values.code, name: values.name }),
      })
      onRefresh()
    } catch {}
  }

  const handleUpdateGlCode = async (id, values) => {
    try {
      await authFetch(`${API}/lookups/gl-codes/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: values.code, name: values.name }),
      })
      onRefresh()
    } catch {}
  }

  const handleDeleteGlCode = async (id) => {
    if (!confirm('Delete this GL code? Transactions using it will become unassigned.')) return
    try {
      await authFetch(`${API}/lookups/gl-codes/${id}`, { method: 'DELETE' })
      onRefresh()
    } catch {}
  }

  const handleCreateExpenseType = async (values) => {
    try {
      await authFetch(`${API}/lookups/expense-types`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: values.name }),
      })
      onRefresh()
    } catch {}
  }

  const handleUpdateExpenseType = async (id, values) => {
    try {
      await authFetch(`${API}/lookups/expense-types/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: values.name }),
      })
      onRefresh()
    } catch {}
  }

  const handleDeleteExpenseType = async (id) => {
    if (!confirm('Delete this expense type? Transactions using it will become unassigned.')) return
    try {
      await authFetch(`${API}/lookups/expense-types/${id}`, { method: 'DELETE' })
      onRefresh()
    } catch {}
  }

  return (
    <div className="settings-tab">
      <SettingsTable
        title="Companies"
        items={companies}
        fields={[
          { key: 'name', label: 'Company Name', placeholder: 'e.g. Kothari Holdings', required: true },
        ]}
        onCreate={handleCreateCompany}
        onUpdate={handleUpdateCompany}
        onDelete={handleDeleteCompany}
      />

      <SettingsTable
        title="GL Codes"
        items={glCodes}
        fields={[
          { key: 'code', label: 'Code', placeholder: 'e.g. 5010', required: true },
          { key: 'name', label: 'Description', placeholder: 'e.g. Travel & Entertainment', required: true },
        ]}
        onCreate={handleCreateGlCode}
        onUpdate={handleUpdateGlCode}
        onDelete={handleDeleteGlCode}
      />

      <SettingsTable
        title="Type of Expense"
        items={expenseTypes}
        fields={[
          { key: 'name', label: 'Expense Type', placeholder: 'e.g. Travel', required: true },
        ]}
        onCreate={handleCreateExpenseType}
        onUpdate={handleUpdateExpenseType}
        onDelete={handleDeleteExpenseType}
      />
    </div>
  )
}
