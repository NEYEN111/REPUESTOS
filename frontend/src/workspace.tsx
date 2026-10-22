import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { LayoutDashboard, Boxes, Package, ShoppingBag, Truck, ChevronDown, ArrowUpRight, Bell, RotateCcw, Users, FileText, MessageSquare, Wallet, ChartNoAxesCombined, CarFront, Tags, Settings } from "lucide-react";
import { api, useStore } from "./lib";
import { LogOut, Store, Network } from "lucide-react";

const primary = [
  ["", "Resumen", LayoutDashboard],
  ["inventario", "Inventario y stock", Boxes],
  ["productos", "Productos", Package],
  ["pedidos", "Pedidos", ShoppingBag],
  ["compras", "Compras", Truck],
  ["envios", "Envíos y recojos", Truck],
] as const;

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const { user, config, notify } = useStore();
  const { pathname } = useLocation();
  const groups = [
    ...(user.role === 'admin' ? [{ name: 'Análisis predictivo', links: [['ml', 'Pronósticos', ChartNoAxesCombined], ['ml/modelos', 'Modelos y evaluación', FileText], ['ml/calidad', 'Calidad del historial', Boxes], ['ml/laboratorio', 'Laboratorio y versiones', ChartNoAxesCombined], ['ml/actualizacion', 'Actualización automática', RotateCcw]] }] : []),
    { name: 'Almacén', links: [['alertas', 'Alertas de stock', Bell], ['movimientos', 'Kardex', RotateCcw], ['conteos', 'Conteos físicos', Boxes], ['proveedores', 'Proveedores', Truck]] },
    { name: 'Clientes', links: [['clientes', 'Clientes', Users], ['cotizaciones', 'Cotizaciones', FileText], ['reclamos', 'Reclamos', MessageSquare]] },
    { name: 'Catálogos', links: [['vehiculos', 'Vehículos', CarFront], ['categorias', 'Categorías', Tags], ['marcas', 'Marcas', Package]] },
    ...(user.role === 'admin' ? [{ name: 'Administración', links: [['pagos', 'Pagos', Wallet], ['finanzas', 'Finanzas', ChartNoAxesCombined], ['calidad', 'Calidad de datos', FileText], ['auditoria', 'Auditoría', FileText], ['configuracion', 'Configuración', Settings]] }] : []),
  ];
  const section = pathname === '/gestion/agentes' ? 'Agentes' : String([...primary, ...groups.flatMap(g => g.links)].find(([path]) => pathname === '/gestion' + (path ? '/' + path : '') || (path === 'productos' && pathname.startsWith('/gestion/productos/')))?.[1] || 'Área de trabajo');
  return <div className="management-shell">
    <a className="skip-link" href="#workspace-main">Saltar al contenido</a>
    <aside className="management-sidebar">
      <Link className="management-brand" to="/gestion"><span>{config.name}<i>/</i></span><small>ÁREA DE TRABAJO</small></Link>
      <nav aria-label="Gestión de la tienda">
        <p className="nav-group-label">OPERACIONES</p>
        {primary.map(([path, label, Icon]) => <NavLink key={path} to={'/gestion' + (path ? '/' + path : '')} end={!path}><Icon size={18} aria-hidden="true" />{label}</NavLink>)}
        {user.role==='admin'&&<NavLink to="/gestion/agentes"><Network size={18} aria-hidden="true"/>Agentes</NavLink>}
        {groups.map(g => <details key={g.name + pathname} open={g.links.some(([path]) => pathname === '/gestion/' + path)}><summary>{g.name}<ChevronDown size={15} aria-hidden="true" /></summary>{g.links.map(([path, label, Icon]: any) => <NavLink key={path} end to={'/gestion/' + path}><Icon size={16} aria-hidden="true" />{label}</NavLink>)}</details>)}
      </nav>
      <Link className="management-store-link" to="/tienda"><Store size={18} />Ir a la tienda<ArrowUpRight size={16} /></Link>
    </aside>
    <div className="management-body">
      <header className="management-header"><div><span>Área de trabajo</span><ChevronDown size={12} className="management-chevron"/><b>{section}</b></div><div className="management-user"><span className="user-avatar">{user.name.slice(0, 1)}</span><Link to="/cuenta"><b>{user.name}</b><small>{user.role === 'admin' ? 'Administrador' : 'Empleado'}</small></Link><button className="icon-button" aria-label="Cerrar sesión" onClick={async () => { try { await api('/auth/logout', {method:'POST'}); window.location.assign('/'); } catch(e:any) { notify(e.message,true); } }}><LogOut size={18}/></button></div></header>
      <main id="workspace-main">{children}</main>
      <footer className="management-footer"><span>{config.name} · Gestión de la tienda</span><span>Soles (PEN) · America/Lima</span></footer>
    </div>
  </div>;
}

