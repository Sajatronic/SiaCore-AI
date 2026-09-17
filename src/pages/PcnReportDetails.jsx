import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, CalendarDays, FileText, ExternalLink, ShieldAlert } from 'lucide-react'
import { api } from '../lib/supabaseClient.js'
import RiskBadge from '../components/RiskBadge.jsx'

const first = (row, keys) => keys.map((key) => row?.[key]).find((value) => value !== undefined && value !== null && value !== '')
const label = (value) => value == null || value === '' ? '—' : String(value)
const date = (value) => value ? new Date(value).toLocaleString() : '—'
const ignored = new Set(['id', 'pcn_id', 'PCN_ID', 'pcn_number', 'PCN_Number'])

function Field({ title, value }) { return <div><div className="text-secondary text-xs uppercase tracking-wide mb-1">{title}</div><div className="font-medium break-words">{label(value)}</div></div> }
function Section({ title, icon: Icon, children }) { return <section className="surface card-hover rounded-xl p-5"><h2 className="font-display font-semibold flex items-center gap-2 mb-4"><Icon size={16} className="text-royal" />{title}</h2>{children}</section> }
function pretty(key) { return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) }

export default function PcnReportDetails() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [row, setRow] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    api.getPcnReport(decodeURIComponent(id)).then(({ data, error: requestError }) => {
      if (!active) return
      setRow(data ?? null)
      setError(requestError?.message ?? null)
      setLoading(false)
    }).catch((err) => { if (active) { setError(err?.message ?? 'Failed to load PCN report.'); setLoading(false) } })
    return () => { active = false }
  }, [id])

  const fields = useMemo(() => row ? Object.entries(row).filter(([key, value]) => !ignored.has(key) && value !== null && value !== '') : [], [row])
  const pcnId = first(row, ['id', 'pcn_id', 'PCN_ID', 'pcn_number', 'PCN_Number']) ?? id
  const manufacturer = first(row, ['manufacturer', 'Manufacturer', 'manufacturer_name', 'Manufacturer Name'])
  const mpn = first(row, ['mpn', 'MPN', 'part_number', 'Part Number'])
  const announcement = first(row, ['announcement_date', 'Announcement Date', 'announced_at'])
  const effective = first(row, ['effective_date', 'Effective Date', 'effective_at'])
  const status = first(row, ['status', 'Status', 'pcn_status', 'PCN Status'])
  const change = first(row, ['change_description', 'Change Description', 'what_changed', 'What Changed', 'description', 'Description'])
  const reason = first(row, ['reason', 'Reason', 'change_reason', 'Change Reason'])
  const source = first(row, ['source_url', 'Source URL', 'url', 'URL', 'source', 'Source'])
  const impact = first(row, ['risk_level', 'Risk Level', 'impact', 'Impact', 'risk', 'Risk'])

  return <div className="pt-6 flex flex-col gap-6 max-w-5xl mx-auto">
    <button onClick={() => navigate('/pcn-reports')} className="text-secondary hover:text-royal text-xs flex items-center gap-1 w-fit"><ArrowLeft size={13} /> Back to PCN Reports</button>
    {error && <div className="surface rounded-xl p-4 text-magenta text-sm">Couldn’t load PCN report: {error}</div>}
    {loading && <div className="surface rounded-xl p-10 text-center text-secondary">Loading PCN report…</div>}
    {!loading && !row && !error && <div className="surface rounded-xl p-10 text-center text-secondary">PCN record not found. <Link to="/pcn-reports" className="text-royal hover:underline">Back to PCN Reports</Link></div>}
    {!loading && row && <>
      <div className="surface rounded-2xl overflow-hidden"><div className="h-1.5 bg-gradient-to-r from-royal to-violet" /><div className="p-6"><div className="flex flex-wrap items-start justify-between gap-5"><div><div className="flex items-center gap-2"><FileText size={20} className="text-royal" /><h1 className="font-display text-2xl font-bold">PCN {label(pcnId)}</h1></div><p className="text-secondary text-sm mt-2">{label(manufacturer)} · {label(mpn)}</p></div>{impact && <RiskBadge level={impact} />}</div><div className="grid grid-cols-2 md:grid-cols-4 gap-5 mt-6"><Field title="Manufacturer" value={manufacturer} /><Field title="Part / MPN" value={mpn} /><Field title="Announcement Date" value={date(announcement)} /><Field title="Effective Date" value={date(effective)} /></div></div></div>
      <Section title="PCN Overview" icon={FileText}><div className="grid grid-cols-2 md:grid-cols-4 gap-5"><Field title="PCN ID" value={pcnId} /><Field title="Current Status" value={status} /><Field title="Change Type" value={first(row, ['change_type', 'Change Type'])} /><Field title="Risk / Impact" value={impact} /></div></Section>
      <Section title="Change Details" icon={CalendarDays}><div className="space-y-4"><Field title="What Changed" value={change} /><Field title="Reason for Change" value={reason} /><Field title="Affected Components / Parts" value={first(row, ['affected_parts', 'Affected Parts', 'affected_components', 'Affected Components'])} /><Field title="Previous vs. New Information" value={first(row, ['previous_new', 'Previous vs New', 'previous_information', 'new_information'])} /></div></Section>
      <Section title="Impact / Risk" icon={ShieldAlert}><div className="grid grid-cols-1 md:grid-cols-2 gap-5"><Field title="Supply-Chain Impact" value={first(row, ['supply_chain_impact', 'Supply Chain Impact'])} /><Field title="Inventory Impact" value={first(row, ['inventory_impact', 'Inventory Impact'])} /><Field title="Manufacturer Impact" value={first(row, ['manufacturer_impact', 'Manufacturer Impact'])} /><Field title="Alternative / Substitution Impact" value={first(row, ['alternative_impact', 'Alternative Impact', 'substitution_impact'])} /><Field title="Compliance Impact" value={first(row, ['compliance_impact', 'Compliance Impact'])} /><Field title="Overall Risk Assessment" value={first(row, ['risk_assessment', 'Risk Assessment', 'overall_risk']) ?? impact} /></div></Section>
      <Section title="Source / Evidence" icon={ExternalLink}><div className="grid grid-cols-1 md:grid-cols-2 gap-5"><Field title="Source" value={first(row, ['source', 'Source', 'source_name', 'Source Name'])} /><div><div className="text-secondary text-xs uppercase tracking-wide mb-1">Source URL</div>{source ? <a href={source} target="_blank" rel="noreferrer" className="text-royal hover:underline break-all inline-flex items-center gap-1">{source}<ExternalLink size={13} /></a> : '—'}</div><Field title="Related Documents / References" value={first(row, ['references', 'References', 'related_documents', 'Related Documents', 'document_url'])} /></div></Section>
      {fields.length > 0 && <Section title="Additional PCN Data" icon={FileText}><div className="grid grid-cols-2 md:grid-cols-3 gap-5">{fields.map(([key, value]) => <Field key={key} title={pretty(key)} value={typeof value === 'object' ? JSON.stringify(value) : value} />)}</div></Section>}
    </>}
  </div>
}
