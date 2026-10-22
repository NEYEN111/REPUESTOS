import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Provider, useStore } from "./lib";
import { StoreLayout, Home, Catalog, Product, Garage } from "./store";
import { Cart, Checkout, Order, Quote } from "./commerce";
import { Login, Account, Legal, Complaint } from "./account";
import {
  AdminLayout,
  Dashboard,
  AdminTable,
  ProductEditor,
  Finance,
  Settings,
} from "./admin";
import "./styles.css";
import "./precision.css";
import { InventoryWorkspace, ShipmentsWorkspace, DataQuality } from './operations';
import { Forecasts, ModelEvaluation, HistoryQuality } from './ml';
import { MLLaboratory } from './ml-lab';
import { MLAutomation } from './ml-automation';
import { AgentsWorkspace } from './agents';
import './ml.css';
function Entry() {
  const { user } = useStore();
  return ["admin", "empleado"].includes(user?.role) ? <Navigate to="/gestion" replace /> : <Home />;
}
function LegacyAdmin() {
  const location = useLocation();
  const path = location.pathname.replace(/^\/admin/, "/gestion");
  return <Navigate to={path === "/gestion/ingresar" ? "/ingresar" : path + location.search} replace />;
}
function Scroll() {
  const { pathname } = useLocation();
  React.useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <Provider>
      <Scroll />
      <Routes>
        <Route element={<StoreLayout />}>
          <Route index element={<Entry />} />
          <Route path="tienda" element={<Home />} />
          <Route path="catalogo" element={<Catalog />} />
          <Route path="producto/:id" element={<Product />} />
          <Route path="garaje" element={<Garage />} />
          <Route path="carrito" element={<Cart />} />
          <Route path="checkout" element={<Checkout />} />
          <Route path="pedido/:id" element={<Order />} />
          <Route path="cotizacion/:id" element={<Quote />} />
          <Route path="ingresar" element={<Login />} />
          <Route path="cuenta" element={<Account />} />
          <Route path="terminos" element={<Legal />} />
          <Route path="privacidad" element={<Legal />} />
          <Route path="reclamaciones" element={<Complaint />} />
          <Route path="admin/*" element={<LegacyAdmin />} />
          <Route path="gestion" element={<AdminLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="productos/nuevo" element={<ProductEditor />} />
            <Route path="productos/:id" element={<ProductEditor />} />
            <Route path="finanzas" element={<Finance />} />
            <Route path="configuracion" element={<Settings />} />
            <Route path="inventario" element={<InventoryWorkspace />} />
            <Route path="envios" element={<ShipmentsWorkspace />} />
            <Route path="calidad" element={<DataQuality />} />
            <Route path="ml" element={<Forecasts />} />
            <Route path="ml/modelos" element={<ModelEvaluation />} />
            <Route path="ml/calidad" element={<HistoryQuality />} />
            <Route path="ml/laboratorio" element={<MLLaboratory />} />
            <Route path="ml/actualizacion" element={<MLAutomation />} />
            <Route path="agentes" element={<AgentsWorkspace />} />
            <Route path=":section" element={<AdminTable />} />
          </Route>
          <Route path="*" element={<Legal missing />} />
        </Route>
      </Routes>
    </Provider>
  </BrowserRouter>,
);
