// Quick standalone check that your .env credentials actually reach Supabase.
// Run with:  node scripts/test-connection.mjs
//
// This does NOT start the frontend — it's just a fast way to confirm the
// URL/key are correct and the database is reachable before debugging the UI.

import { createClient } from '@supabase/supabase-js'
import { readFileSync, existsSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const envPath = path.join(__dirname, '..', '.env')

if (!existsSync(envPath)) {
  console.error('\n❌ No .env file found. Run: copy .env.example .env   (Windows)')
  process.exit(1)
}

// minimal .env parser (avoids adding a dotenv dependency just for this script)
const env = {}
for (const line of readFileSync(envPath, 'utf-8').split('\n')) {
  const trimmed = line.trim()
  if (!trimmed || trimmed.startsWith('#')) continue
  const [key, ...rest] = trimmed.split('=')
  env[key.trim()] = rest.join('=').trim()
}

const url = env.VITE_SUPABASE_URL
const key = env.VITE_SUPABASE_ANON_KEY

if (!url || url.includes('YOUR-PROJECT-REF') || !key || key.includes('YOUR-ANON')) {
  console.error('\n❌ .env still has placeholder values. Fill in VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.')
  process.exit(1)
}

console.log(`\nTesting connection to: ${url}`)

const supabase = createClient(url, key)

async function main() {
  // 1. Basic reachability check — auth endpoint always responds, even with no tables/rows.
  const { error: pingError } = await supabase.auth.getSession()
  if (pingError) {
    console.error('\n❌ Could not reach Supabase at all. Check VITE_SUPABASE_URL.')
    console.error(pingError.message)
    process.exit(1)
  }
  console.log('✅ Reached your Supabase project.')

  // 2. Check the anon key is valid by hitting a real table.
  const { error: tableError } = await supabase.from('parts').select('*').limit(1)
  if (tableError) {
    console.warn('\n⚠️  Reached Supabase, but querying "parts" failed:')
    console.warn('   ', tableError.message)
    console.warn('    This usually means: table name mismatch, or Row Level Security is blocking the anon role.')
  } else {
    console.log('✅ Successfully queried the "parts" table.')
  }

  // 3. Check whether the stored procedures from sql/01_stored_procedures.sql exist yet.
  const { error: rpcError } = await supabase.rpc('get_dashboard_summary')
  if (rpcError) {
    console.warn('\n⚠️  RPC function "get_dashboard_summary" not found or failed:')
    console.warn('   ', rpcError.message)
    console.warn('    Run sql/01_stored_procedures.sql in the Supabase SQL editor if you haven\'t yet.')
  } else {
    console.log('✅ Stored procedures are installed and callable.')
  }

  console.log('\nDone.\n')
}

main()
