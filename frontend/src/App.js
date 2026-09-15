import { useState, useEffect } from "react";
import "@/App.css";
import { HashRouter, Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "@/pages/Dashboard";
import Segmentation from "@/pages/Segmentation";
import Customers from "@/pages/Customers";
import CustomerDetail from "@/pages/CustomerDetail";
import DataManagement from "@/pages/DataManagement";
import Layout from "@/components/Layout";
import { Toaster } from "@/components/ui/sonner";

function App() {
  return (
    <div className="App">
      <HashRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="segmentation" element={<Segmentation />} />
            <Route path="customers" element={<Customers />} />
            <Route path="customers/:customerId" element={<CustomerDetail />} />
            <Route path="data" element={<DataManagement />} />
          </Route>
        </Routes>
      </HashRouter>
      <Toaster position="top-right" />
    </div>
  );
}

export default App;