import React from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Home from './pages/Home.jsx'
import Overview from './pages/Overview.jsx'
import PartsStock from './pages/PartsStock.jsx'
import PartDetails from './pages/PartDetails.jsx'
import InventoryRecords from './pages/InventoryRecords.jsx'
import Distributors from './pages/Distributors.jsx'
import DistributorDetails from './pages/DistributorDetails.jsx'
import AddData from './pages/AddData.jsx'
import News from './pages/News.jsx'
import Reports from './pages/Reports.jsx'
import ReportDetails from './pages/ReportDetails.jsx'
import PcnReports from './pages/PcnReports.jsx'
import PcnReportDetails from './pages/PcnReportDetails.jsx'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/overview" element={<Overview />} />
        <Route path="/parts-stock" element={<PartsStock />} />
        <Route path="/parts-stock/:mpn" element={<PartDetails />} />
        <Route path="/inventory" element={<InventoryRecords />} />
        <Route path="/distributors" element={<Distributors />} />
        <Route path="/distributors/:code" element={<DistributorDetails />} />
        <Route path="/add-data" element={<AddData />} />
        <Route path="/news" element={<News />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/reports/:type/:id" element={<ReportDetails />} />
        <Route path="/pcn-reports" element={<PcnReports />} />
        <Route path="/pcn-reports/:id" element={<PcnReportDetails />} />
      </Routes>
    </Layout>
  )
}
