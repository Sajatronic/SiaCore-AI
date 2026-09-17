import React, { useRef, useState } from 'react'
import Papa from 'papaparse'
import { UploadCloud, FileText } from 'lucide-react'
import { api } from '../lib/supabaseClient.js'

export default function CsvUploader({ tableConfig }) {
  const [dragging, setDragging] = useState(false)
  const [status, setStatus] = useState(null) // { ok, message }
  const [busy, setBusy] = useState(false)
  const inputRef = useRef(null)

  const knownColumns = tableConfig.fields.map((f) => f.name)

  function processFile(file) {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setStatus({ ok: false, message: 'Please upload a .csv file.' })
      return
    }
    setBusy(true)
    setStatus(null)
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: async (results) => {
        // Only keep columns that exist on this table's schema, drop the rest.
        const rows = results.data.map((row) => {
          const clean = {}
          knownColumns.forEach((col) => {
            if (row[col] !== undefined && row[col] !== '') clean[col] = row[col]
          })
          return clean
        })

        if (rows.length === 0) {
          setBusy(false)
          setStatus({ ok: false, message: 'No usable rows found — check your column headers match the schema.' })
          return
        }

        const { error, data } = await api.insertRow(tableConfig.table, rows)
        setBusy(false)
        if (error) {
          setStatus({ ok: false, message: error.message })
        } else {
          setStatus({ ok: true, message: `Uploaded ${data?.length ?? rows.length} rows to ${tableConfig.label}.` })
        }
      },
      error: (err) => {
        setBusy(false)
        setStatus({ ok: false, message: err.message })
      },
    })
  }

  return (
    <div className="surface rounded-xl p-6 flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg surface-2 flex items-center justify-center shrink-0">
          <FileText size={16} className="text-royal" />
        </div>
        <div>
          <h2 className="font-display font-semibold">Bulk upload (CSV) — {tableConfig.label}</h2>
          <p className="text-secondary text-xs mt-0.5">
            Headers matching the schema fields are mapped automatically.
          </p>
        </div>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          processFile(e.dataTransfer.files?.[0])
        }}
        onClick={() => inputRef.current?.click()}
        className={`surface-2 rounded-xl border-2 border-dashed px-6 py-10 flex flex-col items-center gap-2 text-center cursor-pointer transition ${
          dragging ? 'border-royal bg-royal/5' : ''
        }`}
        style={{ borderColor: dragging ? undefined : 'var(--border)' }}
      >
        <UploadCloud size={22} className="text-secondary" />
        <p className="text-sm font-medium">{busy ? 'Uploading…' : 'Drop a CSV file, or click to browse'}</p>
        <p className="text-secondary text-xs max-w-sm">
          Expected columns: {knownColumns.join(', ')}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => processFile(e.target.files?.[0])}
        />
      </div>

      {status && (
        <p className={`text-sm ${status.ok ? 'text-teal' : 'text-magenta'}`}>{status.message}</p>
      )}
    </div>
  )
}
