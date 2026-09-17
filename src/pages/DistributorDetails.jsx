import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { api } from '../lib/supabaseClient.js'
import RiskBadge from '../components/RiskBadge.jsx'

function Field({ label, value, full = false }) {
  return (
    <div className={full ? 'col-span-2 sm:col-span-3 lg:col-span-4' : ''}>
      <div className="text-secondary text-xs uppercase tracking-wide mb-1">{label}</div>
      <div className="font-medium">{value ?? '—'}</div>
    </div>
  )
}

export default function DistributorDetails() {
  const { code } = useParams()
  const navigate = useNavigate()
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    api.getDistributorDetails(code).then(({ data, error }) => {
      if (!active) return
      if (error) setError(error.message)
      else {
        setError(null)
        setDetail(data?.[0] ?? data ?? null)
      }
      setLoading(false)
    })
    return () => {
      active = false
    }
  }, [code])

  return (
    <div className="pt-6 flex flex-col gap-6">
      <div>
        <button
          onClick={() => navigate('/distributors')}
          className="text-secondary hover:text-royal text-xs flex items-center gap-1 mb-2 transition"
        >
          <ArrowLeft size={13} /> Back to Distributors
        </button>
        <h1 className="font-display text-2xl font-bold">{loading ? code : detail?.d_name ?? code}</h1>
        <p className="text-secondary text-sm">Full distributor record, live from Supabase.</p>
      </div>

      {error && <div className="surface rounded-xl p-4 text-magenta text-sm">{error}</div>}

      {!loading && !detail && !error && (
        <div className="surface rounded-xl p-10 text-center text-secondary text-sm">
          No record found for distributor code <span className="font-medium">{code}</span>.
        </div>
      )}

      {(loading || detail) && (
        <>
          <div className="surface card-hover rounded-xl p-6">
            <h2 className="font-display font-semibold mb-4">Basic Information</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-4 text-sm">
              <Field label="Distributor Name" value={detail?.d_name} />
              <Field label="Type" value={detail?.d_type} />
              <Field label="Country" value={detail?.d_country} />
              <Field label="Headquarters" value={detail?.d_headquarters} />
              <Field label="Website" value={detail?.d_website} />
              <Field label="Status" value={detail?.d_status} />
              <Field label="Distributor Code" value={detail?.d_code} />
              <Field label="Authorized" value={detail?.d_authorized} />
            </div>
          </div>

          <div className="surface card-hover rounded-xl p-6">
            <h2 className="font-display font-semibold mb-4">Relationship & Performance</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-4 text-sm">
              <Field label="Dealt With" value={detail?.dealt_with} />
              <Field label="Relationship Tier" value={detail?.relationship_tier} />
              <Field label="Vetting Status" value={detail?.vetting_status} />
              <Field label="Years in Relationship" value={detail?.years_relationship} />
              <Field label="Total Orders Placed" value={detail?.total_orders_placed?.toLocaleString?.() ?? detail?.total_orders_placed} />
              <Field label="On-Time Delivery Rate" value={detail?.on_time_delivery_rate != null ? `${detail.on_time_delivery_rate}%` : null} />
              <Field label="Quality Issues (12m)" value={detail?.quality_issues_12m} />
              <Field label="Company Founded" value={detail?.company_founded_year} />
              <div>
                <div className="text-secondary text-xs uppercase tracking-wide mb-1">Relationship Risk</div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{detail?.relationship_risk_score ?? '—'}</span>
                  <RiskBadge level={detail?.relationship_risk_level} />
                </div>
              </div>
            </div>
          </div>

          <div className="surface card-hover rounded-xl p-6">
            <h2 className="font-display font-semibold mb-4">Verification & Notes</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-4 text-sm">
              <Field label="Public Profile Strength" value={detail?.public_profile_strength} />
              <Field label="Data Source" value={detail?.data_source} />
              <Field label="Verification Status" value={detail?.verification_status} />
              <Field
                label="Last Updated"
                value={detail?.last_modified_date ? new Date(detail.last_modified_date).toLocaleString() : null}
              />
              <Field label="Research Notes" value={detail?.research_notes} full />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
