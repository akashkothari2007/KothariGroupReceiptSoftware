import { useState, useEffect } from 'react'
import { API, authFetch } from '../utils/api'

function FieldInput({ field, value, onChange }) {
  if (field.type === 'select') {
    return (
      <select
        className="settings-input"
        value={value || ''}
        onChange={e => onChange(e.target.value)}
      >
        <option value="">— Select —</option>
        {(field.options || []).map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    )
  }
  return (
    <input
      className="settings-input"
      value={value || ''}
      onChange={e => onChange(e.target.value)}
      placeholder={field.placeholder}
    />
  )
}

function EditableRow({ item, fields, onSave, onDelete, readOnly }) {
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
            <FieldInput
              field={f}
              value={values[f.key]}
              onChange={v => setValues(prev => ({ ...prev, [f.key]: v }))}
            />
          ) : (
            <span className="settings-value">{f.displayFn ? f.displayFn(item) : f.displayKey ? item[f.displayKey] : item[f.key] || '—'}</span>
          )}
        </td>
      ))}
      {!readOnly && (
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
      )}
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
          <FieldInput
            field={f}
            value={values[f.key]}
            onChange={v => setValues(prev => ({ ...prev, [f.key]: v }))}
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

function SettingsTable({ title, items, fields, onCreate, onUpdate, onDelete, readOnly }) {
  return (
    <div className="settings-card">
      <h3 className="settings-card-title">{title}</h3>
      <table className="settings-table">
        <thead>
          <tr>
            {fields.map(f => <th key={f.key}>{f.label}</th>)}
            {!readOnly && <th className="settings-actions-col">Actions</th>}
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
              readOnly={readOnly}
            />
          ))}
          {!readOnly && <AddRow fields={fields} onAdd={onCreate} />}
        </tbody>
      </table>
      {items.length === 0 && (
        <div className="settings-empty">{readOnly ? 'No items.' : 'No items yet. Add one above.'}</div>
      )}
    </div>
  )
}

function UserManagement() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState(null)

  useEffect(() => {
    fetchUsers()
  }, [])

  const fetchUsers = async () => {
    try {
      const res = await authFetch(`${API}/users/`)
      if (res.ok) setUsers(await res.json())
    } catch {}
    setLoading(false)
  }

  const handleRoleChange = async (userId, newRole) => {
    setUpdating(userId)
    try {
      const res = await authFetch(`${API}/users/${userId}/role`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: newRole }),
      })
      if (res.ok) {
        setUsers(prev => prev.map(u => u.id === userId ? { ...u, role: newRole } : u))
      }
    } catch {}
    setUpdating(null)
  }

  if (loading) return <div className="settings-card"><div className="settings-empty">Loading users...</div></div>

  return (
    <div className="settings-card">
      <h3 className="settings-card-title">User Management</h3>
      <table className="settings-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Joined</th>
          </tr>
        </thead>
        <tbody>
          {users.map(u => (
            <tr key={u.id}>
              <td><span className="settings-value">{u.full_name || '—'}</span></td>
              <td><span className="settings-value">{u.email || '—'}</span></td>
              <td>
                <select
                  className="settings-input"
                  value={u.role}
                  onChange={e => handleRoleChange(u.id, e.target.value)}
                  disabled={updating === u.id}
                >
                  <option value="editor">Editor</option>
                  <option value="admin">Admin</option>
                </select>
              </td>
              <td><span className="settings-value">{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function SettingsTab({ companies, glCodes, expenseTypes, onRefresh, userRole }) {
  const [vendorMappings, setVendorMappings] = useState([])
  const [cityRules, setCityRules] = useState([])

  const isAdmin = userRole === 'admin'
  const readOnly = !isAdmin

  useEffect(() => {
    fetchVendorMappings()
    fetchCityRules()
  }, [])

  const fetchVendorMappings = async () => {
    try {
      const res = await authFetch(`${API}/lookups/vendor-mappings`)
      setVendorMappings(await res.json())
    } catch {}
  }

  const fetchCityRules = async () => {
    try {
      const res = await authFetch(`${API}/lookups/city-company-rules`)
      setCityRules(await res.json())
    } catch {}
  }
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

  // ── Vendor Mappings ──
  const handleCreateVendorMapping = async (values) => {
    try {
      await authFetch(`${API}/lookups/vendor-mappings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vendor_name: values.vendor_name, gl_code_id: values.gl_code_id }),
      })
      fetchVendorMappings()
    } catch {}
  }

  const handleUpdateVendorMapping = async (id, values) => {
    try {
      await authFetch(`${API}/lookups/vendor-mappings/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vendor_name: values.vendor_name, gl_code_id: values.gl_code_id }),
      })
      fetchVendorMappings()
    } catch {}
  }

  const handleDeleteVendorMapping = async (id) => {
    if (!confirm('Delete this vendor mapping?')) return
    try {
      await authFetch(`${API}/lookups/vendor-mappings/${id}`, { method: 'DELETE' })
      fetchVendorMappings()
    } catch {}
  }

  // ── City-Company Rules ──
  const handleCreateCityRule = async (values) => {
    try {
      await authFetch(`${API}/lookups/city-company-rules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ city: values.city, province: values.province || null, company_id: values.company_id }),
      })
      fetchCityRules()
    } catch {}
  }

  const handleUpdateCityRule = async (id, values) => {
    try {
      await authFetch(`${API}/lookups/city-company-rules/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ city: values.city, province: values.province || null, company_id: values.company_id }),
      })
      fetchCityRules()
    } catch {}
  }

  const handleDeleteCityRule = async (id) => {
    if (!confirm('Delete this city-company rule?')) return
    try {
      await authFetch(`${API}/lookups/city-company-rules/${id}`, { method: 'DELETE' })
      fetchCityRules()
    } catch {}
  }

  const glCodeOptions = glCodes.map(g => ({ value: g.id, label: `${g.code} — ${g.name}` }))
  const companyOptions = companies.map(c => ({ value: c.id, label: c.name }))

  return (
    <div className="settings-tab">
      {isAdmin && <UserManagement />}

      <SettingsTable
        title="Companies"
        items={companies}
        fields={[
          { key: 'name', label: 'Company Name', placeholder: 'e.g. Kothari Holdings', required: true },
        ]}
        onCreate={handleCreateCompany}
        onUpdate={handleUpdateCompany}
        onDelete={handleDeleteCompany}
        readOnly={readOnly}
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
        readOnly={readOnly}
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
        readOnly={readOnly}
      />

      <SettingsTable
        title="Vendor → GL Code Rules"
        items={vendorMappings}
        fields={[
          { key: 'vendor_name', label: 'Vendor Keyword', placeholder: 'e.g. uber, aircanada', required: true },
          { key: 'gl_code_id', label: 'GL Code', type: 'select', options: glCodeOptions, displayFn: (item) => item.gl_code ? `${item.gl_code} — ${item.gl_name}` : '—', required: true },
        ]}
        onCreate={handleCreateVendorMapping}
        onUpdate={handleUpdateVendorMapping}
        onDelete={handleDeleteVendorMapping}
        readOnly={readOnly}
      />

      <SettingsTable
        title="City → Company Rules"
        items={cityRules}
        fields={[
          { key: 'city', label: 'City', placeholder: 'e.g. Toronto', required: true },
          { key: 'province', label: 'Province', placeholder: 'e.g. ON (optional)' },
          { key: 'company_id', label: 'Company', type: 'select', options: companyOptions, displayKey: 'company_name', required: true },
        ]}
        onCreate={handleCreateCityRule}
        onUpdate={handleUpdateCityRule}
        onDelete={handleDeleteCityRule}
        readOnly={readOnly}
      />
    </div>
  )
}
