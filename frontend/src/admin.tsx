import React, { useEffect, useState } from "react";
import {
  Link,
  Navigate,
  useLocation,
  Outlet,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  LayoutDashboard,
  Package,
  Boxes,
  ShoppingBag,
  Truck,
  Users,
  FileText,
  MessageSquare,
  ChartNoAxesCombined,
  CarFront,
  Tags,
  Settings as SettingsIcon,
  ArrowUpRight,
  ArrowRight,
  Plus,
  Search,
  Bell,
  LogOut,
  ChevronDown,
  Download,
  Upload,
  SlidersHorizontal,
  Eye,
  Pencil,
  Trash2,
  Check,
  AlertTriangle,
  Wallet,
  TrendingUp,
  Clock3,
  ChevronLeft,
  Save,
  X,
  RotateCcw,
} from "lucide-react";
import {
  api,
  useStore,
  useLoad,
  money,
  date,
  Loading,
  ErrorBox,
  Empty,
  Modal,
  Pagination,
  Field,
  Badge,
  ProductImage,
} from "./lib";
import { Logo } from "./store";
import { Order } from "./commerce";
import { PurchaseBuilder, ReceiptPanel } from './operations';
const SECTIONS: any = {
  conteos: ["Conteos físicos", "counts", Boxes],
  auditoria: ["Auditoría de operaciones", "audit", FileText],
  productos: ["Productos", "products", Package],
  inventario: ["Inventario", "inventory", Boxes],
  movimientos: ["Kardex", "movements", RotateCcw],
  pedidos: ["Pedidos", "orders", ShoppingBag],
  compras: ["Órdenes de compra", "purchases", Truck],
  proveedores: ["Proveedores", "suppliers", Truck],
  clientes: ["Clientes", "customers", Users],
  cotizaciones: ["Cotizaciones", "quotes", FileText],
  reclamos: ["Reclamos", "complaints", MessageSquare],
  pagos: ["Pagos", "payments", Wallet],
  alertas: ["Alertas de stock", "alerts", Bell],
  vehiculos: ["Vehículos", "vehicles", CarFront],
  categorias: ["Categorías", "categories", Tags],
  marcas: ["Marcas", "brands", Tags],
};
export function AdminLayout() {
  const { user } = useStore();
  const location = useLocation();
  if (!user) return <Navigate to={"/ingresar?next=" + encodeURIComponent(location.pathname + location.search)} replace />;
  if (!["admin", "empleado"].includes(user.role)) return <div className="container page"><Empty title="Esta sección es para el equipo de la tienda" text="Tu cuenta tiene acceso a compras, pedidos y cotizaciones." action={<Link className="button" to="/cuenta">Ir a mi cuenta</Link>} /></div>;
  if (user.role !== "admin" && ["finanzas", "configuracion", "pagos", "calidad", "auditoria", "ml"].includes(location.pathname.split("/")[2])) return <div className="container page"><Empty title="Acceso exclusivo del administrador" text="Puedes continuar con los pedidos, productos e inventario desde el menú de gestión." action={<Link className="button" to="/gestion">Ir al resumen</Link>} /></div>;
  return <div className="workspace-content"><div className="admin-main"><Outlet /></div></div>;
}

function SalesChart({ data }: any) {
  const max = Math.max(...data.map((d: any) => d.total), 1),
    width = 800,
    height = 210;
  const points = data
    .map(
      (d: any, i: number) =>
        `${40 + (i * (width - 55)) / Math.max(data.length - 1, 1)},${height - 25 - (d.total / max) * (height - 50)}`,
    )
    .join(" ");
  return (
    <div className="chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Ventas diarias del periodo"
      >
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#476f57" stopOpacity=".2" />
            <stop offset="100%" stopColor="#476f57" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((n) => (
          <g key={n}>
            <line
              x1="40"
              x2="790"
              y1={height - 25 - n * (height - 50)}
              y2={height - 25 - n * (height - 50)}
              stroke="#e6e9e5"
              strokeDasharray="4 5"
            />
            <text
              x="0"
              y={height - 21 - n * (height - 50)}
              fontSize="10"
              fill="#89928b"
            >
              {(n * max / 100000).toLocaleString("es-PE", { maximumFractionDigits: 1 })}k
            </text>
          </g>
        ))}
        <polygon
          points={`40,${height - 25} ${points} 785,${height - 25}`}
          fill="url(#area)"
        />
        <polyline
          points={points}
          fill="none"
          stroke="#315b45"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        {data.map((d: any, i: number) =>
          i % Math.ceil(data.length / 6) === 0 ? (
            <text
              key={d.date}
              x={40 + (i * 745) / Math.max(data.length - 1, 1)}
              y="208"
              fontSize="10"
              fill="#89928b"
            >
              {d.date.slice(8)}/{d.date.slice(5, 7)}
            </text>
          ) : null,
        )}
      </svg>
    </div>
  );
}
export function Dashboard() {
  const { user } = useStore(),
    load = useLoad("/admin/dashboard");
  if (load.loading) return <Loading />;
  if (load.error) return <ErrorBox message={load.error} />;
  const d = load.data;
  return (
    <>
      <div className="admin-page-title">
        <div>
          <div className="eyebrow muted">TU NEGOCIO, EN UN VISTAZO</div>
          <h1>Vista general</h1>
          <p>Esto es lo que está pasando en tu tienda.</p>
        </div>
        <div className="date-pill">
          <Clock3 size={16} />
          {new Date().toLocaleDateString("es-PE", {
            day: "numeric",
            month: "long",
            year: "numeric",
            timeZone: "America/Lima",
          })}
        </div>
      </div>
      <div className="stats-grid">
        {[
          ["Ventas de hoy", money(d.today), "Ventas confirmadas", ShoppingBag],
          ["Esta semana", money(d.week), "Desde el lunes", TrendingUp],
          ["Este mes", money(d.month), "Acumulado del mes", Wallet],
          [
            user.role === "admin" ? "Ganancia estimada" : "Pagos por verificar",
            user.role === "admin" ? money(d.profit) : d.pending,
            user.role === "admin"
              ? `${d.margin}% de margen · últimos 30 días`
              : "Pendientes de revisión",
            ChartNoAxesCombined,
          ],
        ].map(([title, value, sub, Icon]: any, i) => (
          <div className={"stat-card " + (i === 3 ? "dark" : "")} key={title}>
            <div>
              <span>{title}</span>
              <Icon size={19} />
            </div>
            <strong>{value}</strong>
            <small>{sub}</small>
          </div>
        ))}
      </div>
      <div className="dashboard-middle">
        <section className="panel chart-panel">
          <div className="section-title">
            <div>
              <h2>Evolución de ventas</h2>
              <p>Últimos 30 días · pagos confirmados</p>
            </div>
            <span className="chart-legend">
              <i />
              Ventas
            </span>
          </div>
          <div className="chart-total">
            {money(d.revenue)} <span>{d.orders} pedidos</span>
          </div>
          <SalesChart data={d.daily} />
        </section>
        <section className="panel attention-panel">
          <div className="section-title">
            <h2>Necesitan tu atención</h2>
            <span className="notification-dot" />
          </div>
          <Link
            to="/gestion/pedidos?status=pago+por+verificar"
            className="attention-item"
          >
            <span className="attention-icon purple">
              <Wallet size={21} />
            </span>
            <span>
              <b>{d.pending} pagos por verificar</b>
              <small>Revisa las constancias recibidas</small>
            </span>
            <ArrowRight size={17} />
          </Link>
          <Link to="/gestion/alertas?status=activa" className="attention-item">
            <span className="attention-icon amber-bg">
              <Boxes size={21} />
            </span>
            <span>
              <b>{d.low_stock} productos con stock bajo</b>
              <small>Planifica tu próxima reposición</small>
            </span>
            <ArrowRight size={17} />
          </Link>
          <h4>Pedidos por estado</h4>
          <div className="state-bars">
            {d.states
              .filter(
                (s: any) =>
                  !["entregado", "vencido", "cancelado"].includes(s.status),
              )
              .map((s: any) => (
                <Link key={s.status} to={"/gestion/pedidos?status=" + s.status}>
                  <span>{s.status}</span>
                  <b>{s.count}</b>
                </Link>
              ))}
          </div>
        </section>
      </div>
      <section className="panel recent-orders">
        <div className="section-title">
          <div>
            <h2>Pedidos recientes</h2>
            <p>El movimiento más reciente de tu tienda.</p>
          </div>
          <Link to="/gestion/pedidos">
            Ver todos los pedidos <ArrowUpRight size={16} />
          </Link>
        </div>
        <table>
          <thead>
            <tr>
              <th>Pedido</th>
              <th>Cliente</th>
              <th>Fecha</th>
              <th>Pago</th>
              <th>Estado</th>
              <th>Total</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {d.recent.map((o: any) => (
              <tr key={o.id}>
                <td>
                  <Link
                    className="table-link"
                    to={"/gestion/pedidos?detail=" + o.id}
                  >
                    {o.code}
                  </Link>
                </td>
                <td>{o.customer_name}</td>
                <td>{date(o.created_at)}</td>
                <td>{o.payment_method}</td>
                <td>
                  <Badge>{o.status}</Badge>
                </td>
                <td>
                  <b>{money(o.total_cents)}</b>
                </td>
                <td>
                  <Link
                    to={"/gestion/pedidos?detail=" + o.id}
                    aria-label="Ver pedido"
                  >
                    <ArrowUpRight size={16} />
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <div className="dashboard-bottom">
        <section className="panel">
          <div className="section-title">
            <h2>Productos más vendidos</h2>
            <Link to="/gestion/productos">
              Ver catálogo
              <ArrowUpRight size={15} />
            </Link>
          </div>
          {d.products?.slice().sort((a: any, b: any) => b.units - a.units).slice(0, 5).map((p: any, i: number) => (
            <div className="rank-item" key={p.id}>
              <span>{String(i + 1).padStart(2, "0")}</span>
              <div>
                <b>{p.name}</b>
                <small>{p.sku}</small>
              </div>
              <strong>
                {p.units}
                <small>unidades</small>
              </strong>
            </div>
          )) || <p>Consulta el catálogo y controla tu inventario.</p>}
        </section>
        <section className="panel">
          <div className="section-title">
            <h2>Próximas reposiciones</h2>
            <Link to="/gestion/alertas">
              Ver alertas
              <ArrowUpRight size={15} />
            </Link>
          </div>
          {d.alerts.slice(0, 5).map((a: any) => (
            <div className="stock-alert" key={a.id}>
              <span className="stock-number">{a.available}</span>
              <div>
                <b>{a.sku}</b>
                <p>{a.message}</p>
              </div>
              <Link to={"/gestion/compras?product=" + a.product_id}>
                Reponer
                <Plus size={13} />
              </Link>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}

const COLUMNS: any = {
  counts: [["created_at","Fecha"],["sku","SKU"],["expected","Registrado"],["counted","Contado"],["difference","Diferencia"],["reason","Motivo"],["user_name","Responsable"]],
  audit: [["created_at","Fecha"],["entity","Área"],["entity_id","Registro"],["action","Acción"],["user_name","Responsable"],["actor","Actor"]],
  products: [
    ["name", "Producto"],
    ["sku", "SKU"],
    ["brand", "Marca"],
    ["price_cents", "Precio"],
    ["stock", "Stock"],
    ["active", "Estado"],
  ],
  inventory: [
    ["sku", "SKU"],
    ["name", "Producto"],
    ["stock", "Físico"],
    ["reserved", "Reservado"],
    ["available", "Disponible"],
    ["minimum", "Mínimo"],
  ],
  movements: [
    ["created_at", "Fecha"],
    ["sku", "SKU"],
    ["kind", "Movimiento"],
    ["quantity", "Cantidad"],
    ["reserved_delta", "Reserva"],
    ["balance", "Saldo"],
    ["reason", "Motivo"],
    ["user_name", "Responsable"],
    ["actor", "Actor"],
  ],
  orders: [
    ["code", "Pedido"],
    ["customer_name", "Cliente"],
    ["created_at", "Fecha"],
    ["payment_method", "Pago"],
    ["status", "Estado"],
    ["total_cents", "Total"],
  ],
  purchases: [
    ["code", "Orden"],
    ["supplier", "Proveedor"],
    ["created_at", "Fecha"],
    ["expected_at", "Recepción prevista"],
    ["status", "Estado"],
    ["total_cents", "Total"],
  ],
  suppliers: [
    ["name", "Proveedor"],
    ["ruc", "RUC"],
    ["contact", "Contacto"],
    ["email", "Correo"],
    ["phone", "Teléfono"],
  ],
  customers: [
    ["name", "Cliente"],
    ["email", "Correo"],
    ["phone", "Celular"],
    ["document", "Documento"],
    ["created_at", "Registro"],
  ],
  quotes: [
    ["code", "Cotización"],
    ["customer_name", "Cliente"],
    ["created_at", "Creada"],
    ["expires_at", "Vence"],
    ["status", "Estado"],
    ["total_cents", "Total"],
  ],
  complaints: [
    ["code", "Código"],
    ["name", "Cliente"],
    ["type", "Tipo"],
    ["detail", "Detalle"],
    ["status", "Estado"],
    ["created_at", "Fecha"],
  ],
  payments: [
    ["code", "Pedido"],
    ["customer_name", "Cliente"],
    ["method", "Medio"],
    ["amount_cents", "Importe"],
    ["status", "Estado"],
    ["created_at", "Fecha"],
  ],
  alerts: [
    ["sku", "SKU"],
    ["name", "Producto"],
    ["available", "Disponible"],
    ["minimum", "Mínimo"],
    ["status", "Estado"],
  ],
  vehicles: [
    ["brand", "Marca"],
    ["model", "Modelo"],
    ["year", "Año"],
    ["version", "Versión"],
    ["tipo_vehiculo", "Tipo"],
  ],
  categories: [
    ["name", "Nombre"],
    ["slug", "Identificador"],
    ["parent_id", "Categoría padre"],
  ],
  brands: [["name", "Marca"]],
};
const STATUS: any = {
  products: ["activo", "oculto"],
  orders: [
    "pendiente de pago",
    "pago por verificar",
    "pagado",
    "preparando",
    "enviado",
    "listo para recojo",
    "entregado",
    "cancelado",
    "vencido",
  ],
  purchases: ["pendiente", "parcial", "recibida", "cancelada"],
  complaints: ["pendiente", "en atención", "resuelta"],
  payments: ["pendiente", "por verificar", "confirmado", "rechazado"],
  quotes: ["vigente", "convertida", "vencida"],
  alerts: ["activa", "resuelta"],
};
export function AdminTable() {
  const { section = "productos" } = useParams(),
    meta = SECTIONS[section],
    nav = useNavigate(),
    { notify, categories } = useStore(),
    [params, setParams] = useSearchParams(),
    [q, setQ] = useState(""),
    [page, setPage] = useState(1),
    [startDate, setStartDate] = useState(''),
    [endDate, setEndDate] = useState(''),
    [sort, setSort] = useState(""),
    [direction, setDirection] = useState("desc"),
    [modal, setModal] = useState<any>(null),
    [edit, setEdit] = useState<any>(null);
  const entity = meta?.[1] || "products",
    status = params.get("status") || "",
    detail = params.get("detail");
  const query = new URLSearchParams({
    q,
    page: String(page),
    sort,
    direction,
    limit: "15",
    status,
    start: startDate,
    end: endDate,
  });
  if (entity === "movements" && params.get("product"))
    query.set("product_id", params.get("product")!);
  const load = useLoad(
    entity === "products"
      ? "/admin/products?" + query
      : "/admin/list/" + entity + "?" + query,
  );
  useEffect(() => {
    setQ("");
    setPage(1);
    setSort("");
    setModal(null);
    setEdit(null);
    setStartDate('');
    setEndDate('');
  }, [section]);
  useEffect(() => {
    if (detail) setModal({ type: entity === 'purchases' ? 'purchaseDetail' : "order", id: +detail });
  }, [detail, entity]);
  const close = () => {
    setModal(null);
    setEdit(null);
    if (detail) {
      const p = new URLSearchParams(params);
      p.delete("detail");
      setParams(p);
    }
  };
  const action = async (path: string, body?: any, method = "POST") => {
    try {
      await api(path, { method, body });
      notify("Cambios guardados.");
      load.reload();
      close();
    } catch (e: any) {
      notify(e.message, true);
    }
  };
  if (!meta) return <Empty title="Sección no encontrada" />;
  const create = () => {
    if (entity === "products") nav("/gestion/productos/nuevo");
    else if (entity === "purchases")
      setModal({ type: "purchase", product_id: params.get("product") });
    else
      setEdit(
        entity === "suppliers"
          ? { name: "", ruc: "", email: "", phone: "", contact: "", active: 1 }
          : entity === "vehicles"
            ? {
                brand: "",
                model: "",
                year: 2024,
                version: "",
                tipo_vehiculo: "auto",
              }
            : entity === "categories"
              ? { name: "", slug: "", parent_id: null, image: "" }
              : { name: "" },
      );
  };
  const rowAction = (r: any) => {
    if (entity === "products") nav("/gestion/productos/" + r.id);
    else if (["orders", "payments"].includes(entity))
      setModal({ type: "order", id: r.order_id || r.id });
    else if (entity === "inventory") setModal({ type: "adjust", row: r });
    else if (entity === "purchases")
      setModal({ type: "purchaseDetail", id: r.id });
    else if (entity === "quotes") window.open("/cotizacion/" + r.id, "_blank");
    else if (entity === "alerts") nav("/gestion/compras?product=" + r.product_id);
    else if (entity === "complaints") setEdit({ ...r });
    else if (["suppliers", "vehicles", "categories", "brands"].includes(entity))
      setEdit({ ...r });
    else setModal({ type: "record", row: r });
  };
  return (
    <>
      <div className="admin-page-title">
        <div>
          <div className="eyebrow muted">GESTIÓN DE LA TIENDA</div>
          <h1>{meta[0]}</h1>
          <p>
            {entity === "products"
              ? "Organiza tu catálogo y mantén cada referencia al día."
              : entity === "inventory"
                ? "Controla existencias, reservas y movimientos de tus productos."
                : entity === "orders"
                  ? "Gestiona cada pedido, desde el pago hasta la entrega."
                  : "Consulta y administra los registros de tu tienda."}
          </p>
        </div>
        <div className="button-row">
          {entity === "inventory" && (
            <Link className="button secondary small" to="/gestion/movimientos">
              <RotateCcw size={16} />
              Ver kardex
            </Link>
          )}
          {entity === "products" && (
            <>
              <a
                className="button secondary small"
                href="/api/admin/export/products"
              >
                <Download size={16} />
                Exportar CSV
              </a>
              <label className="button secondary small file-button">
                <Upload size={16} />
                Importar
                <input
                  type="file"
                  accept=".csv"
                  onChange={async (e) => {
                    if (e.target.files?.[0]) {
                      const fd = new FormData();
                      fd.append("file", e.target.files[0]);
                      try {
                        const r = await api("/admin/import/products", {
                          method: "POST",
                          body: fd,
                        });
                        notify(r.imported + " productos importados.");
                        if (r.errors.length)
                          setModal({ type: "import", errors: r.errors });
                        load.reload();
                      } catch (e: any) {
                        notify(e.message, true);
                      }
                    }
                  }}
                />
              </label>
            </>
          )}
          {[
            "products",
            "purchases",
            "suppliers",
            "vehicles",
            "categories",
            "brands",
          ].includes(entity) && (
            <button className="small" onClick={create}>
              <Plus size={17} />
              {entity === "products"
                ? "Nuevo producto"
                : entity === "purchases"
                  ? "Nueva compra"
                  : "Agregar registro"}
            </button>
          )}
        </div>
      </div>
      {entity === "purchases" && params.get("product") && (
        <div className="info-note">
          <Boxes size={20} />
          Crea una orden de compra para reponer el producto seleccionado.
          <button className="small" onClick={create}>
            Crear orden
          </button>
        </div>
      )}
      <section className="panel table-panel">
        <div className="table-toolbar">
          <div className="table-search">
            <Search size={17} />
            <input
              aria-label="Buscar registros"
              placeholder={"Buscar " + meta[0].toLowerCase() + "..."}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div>
            {['orders','purchases','movements','audit','counts','payments'].includes(entity) && <>
              <input className="table-date" type="date" aria-label="Desde" title="Desde" value={startDate} max={endDate||undefined} onChange={e=>{setStartDate(e.target.value);setPage(1);}} />
              <input className="table-date" type="date" aria-label="Hasta" title="Hasta" value={endDate} min={startDate||undefined} onChange={e=>{setEndDate(e.target.value);setPage(1);}} />
            </>}
            {STATUS[entity] && (
              <select
                aria-label="Filtrar por estado"
                value={status}
                onChange={(e) => {
                  setParams(e.target.value ? { status: e.target.value } : {});
                  setPage(1);
                }}
              >
                <option value="">Todos los estados</option>
                {STATUS[entity].map((s: string) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            )}
            <span>{load.data?.total ?? 0} registros</span>
          </div>
        </div>
        {load.loading ? (
          <Loading />
        ) : load.error ? (
          <ErrorBox message={load.error} />
        ) : load.data?.items.length ? (
          <>
            <table className="admin-table">
              <thead>
                <tr>
                  {COLUMNS[entity].map(([key, label]: any) => (
                    <th key={key}>
                      <button
                        onClick={() => {
                          setSort(key);
                          setDirection(direction === "asc" ? "desc" : "asc");
                        }}
                      >
                        {label}
                        <ChevronDown size={12} />
                      </button>
                    </th>
                  ))}
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {load.data.items.map((r: any) => (
                  <tr key={r.id}>
                    {COLUMNS[entity].map(([key]: any) => (
                      <td key={key}>
                        {key.endsWith("_cents") ? (
                          <b>{money(r[key])}</b>
                        ) : key === "status" ? (
                          <Badge>{r[key]}</Badge>
                        ) : key === "active" ? (
                          <Badge>{r[key] ? "activo" : "oculto"}</Badge>
                        ) : key.endsWith("_at") ? (
                          date(r[key])
                        ) : key === "name" && entity === "products" ? (
                          <div className="table-product">
                            <ProductImage p={r} />
                            <div>
                              <b>{r.name}</b>
                              <small>{r.category}</small>
                            </div>
                          </div>
                        ) : key === "available" ? (
                          <b
                            className={
                              r.available <= r.minimum ? "text-danger" : ""
                            }
                          >
                            {r[key]}
                          </b>
                        ) : (
                          <span
                            className={
                              ["detail", "reason", "name"].includes(key)
                                ? "clamp-cell"
                                : ""
                            }
                          >
                            {r[key] ?? "—"}
                          </span>
                        )}
                      </td>
                    ))}
                    <td>
                      <div className="row-actions">
                        <button
                          className="icon-button"
                          aria-label={
                            entity === "inventory"
                              ? "Ajustar stock"
                              : "Ver o editar registro"
                          }
                          onClick={() => rowAction(r)}
                        >
                          {[
                            "products",
                            "brands",
                            "suppliers",
                            "categories",
                            "vehicles",
                            "inventory",
                          ].includes(entity) ? (
                            <Pencil size={16} />
                          ) : (
                            <Eye size={16} />
                          )}
                        </button>
                        {entity === "products" && r.active === 1 && (
                          <button
                            className="icon-button danger"
                            aria-label="Ocultar producto"
                            onClick={() => {
                              if (
                                confirm(
                                  "¿Ocultar este producto de la tienda? Podrás activarlo al editar.",
                                )
                              )
                                action(
                                  "/admin/products/" + r.id,
                                  undefined,
                                  "DELETE",
                                );
                            }}
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                        {entity === "inventory" && (
                          <Link
                            aria-label="Ver movimientos"
                            to={"/gestion/movimientos?product=" + r.id}
                          >
                            <RotateCcw size={16} />
                          </Link>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination {...load.data} page={page} onChange={setPage} />
          </>
        ) : (
          <Empty />
        )}
      </section>
      {modal && (
        <Modal
          title={
            modal.type === "order"
              ? "Detalle del pedido"
              : modal.type === "adjust"
                ? "Movimiento de inventario"
                : modal.type === "purchase"
                  ? "Nueva orden de compra"
                  : modal.type === "purchaseDetail"
                    ? "Detalle de compra"
                    : modal.type === "import"
                      ? "Resultado de importación"
                      : "Detalle del registro"
          }
          wide={["order", "purchase", "purchaseDetail"].includes(modal.type)}
          onClose={close}
        >
          {modal.type === "order" ? (
            <Order orderId={modal.id} admin onChange={load.reload} />
          ) : modal.type === "adjust" ? (
            <InventoryForm
              row={modal.row}
              onSave={(d: any) => action("/admin/inventory", d)}
            />
          ) : modal.type === "purchase" ? (
            <PurchaseBuilder
              productId={modal.product_id}
              onDone={() => { load.reload(); close(); }}
            />
          ) : modal.type === "purchaseDetail" ? (
            <ReceiptPanel
              id={modal.id}
              onDone={() => { load.reload(); close(); }}
            />
          ) : modal.type === "import" ? (
            <div>
              {modal.errors.map((r: any) => (
                <p key={r.row}>
                  Fila {r.row}: {r.error}
                </p>
              ))}
            </div>
          ) : (
            <dl>
              {Object.entries(modal.row).map(([k, v]) => (
                <React.Fragment key={k}>
                  <dt>
                    {(
                      {
                        id: "Código",
                        name: "Nombre",
                        email: "Correo",
                        phone: "Celular",
                        document: "Documento",
                        created_at: "Fecha",
                        sku: "SKU",
                        kind: "Movimiento",
                        quantity: "Cantidad",
                        reserved_delta: "Cambio en reserva",
                        balance: "Saldo",
                        reason: "Motivo",
                        user_name: "Responsable",
                        actor: "Actor",
                        product_id: "Producto",
                        order_id: "Pedido",
                        user_id: "Usuario",
                        expected: "Saldo registrado",
                        counted: "Unidades contadas",
                        difference: "Diferencia",
                        entity: "Área",
                        entity_id: "Registro",
                        action: "Acción",
                        detail: "Detalle de la operación",
                        reserved_balance: "Saldo reservado",
                      } as any
                    )[k] || k}
                  </dt>
                  <dd>{String(v)}</dd>
                </React.Fragment>
              ))}
            </dl>
          )}
        </Modal>
      )}
      {edit && (
        <Modal
          title={edit.id ? "Editar registro" : "Nuevo registro"}
          wide={entity === "complaints"}
          onClose={close}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              action("/admin/manage/" + entity, edit);
            }}
          >
            {entity === "complaints" ? (
              <>
                <div className="form-grid">
                  <div>
                    <h3>{edit.name}</h3>
                    <p>
                      {edit.email}
                      <br />
                      {edit.phone}
                      <br />
                      {edit.document}
                    </p>
                  </div>
                  <div>
                    <h3>
                      {edit.type} {edit.code}
                    </h3>
                    <p>{edit.detail}</p>
                    <b>Solicitud</b>
                    <p>{edit.request}</p>
                  </div>
                </div>
                <Field label="Estado">
                  <select
                    value={edit.status}
                    onChange={(e) =>
                      setEdit({ ...edit, status: e.target.value })
                    }
                  >
                    {STATUS.complaints.map((s: string) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Respuesta">
                  <textarea
                    rows={4}
                    value={edit.response}
                    onChange={(e) =>
                      setEdit({ ...edit, response: e.target.value })
                    }
                  />
                </Field>
              </>
            ) : (
              Object.entries(edit)
                .filter(([k]) => !["id", "created_at", "image"].includes(k))
                .map(([k, v]) =>
                  k === "parent_id" ? (
                    <Field key={k} label="Categoría padre">
                      <select
                        value={String(v || "")}
                        onChange={(e) =>
                          setEdit({
                            ...edit,
                            [k]: e.target.value ? +e.target.value : null,
                          })
                        }
                      >
                        <option value="">Categoría principal</option>
                        {categories
                          .filter((c: any) => !c.parent_id && c.id !== edit.id)
                          .map((c: any) => (
                            <option value={c.id} key={c.id}>
                              {c.name}
                            </option>
                          ))}
                      </select>
                    </Field>
                  ) : (
                    <Field
                      key={k}
                      label={
                        (
                          {
                            name: "Nombre",
                            ruc: "RUC",
                            email: "Correo",
                            phone: "Teléfono",
                            contact: "Contacto",
                            active: "Activo (1 sí / 0 no)",
                            brand: "Marca",
                            model: "Modelo",
                            year: "Año",
                            version: "Versión",
                            tipo_vehiculo: "Tipo de vehículo",
                            slug: "Identificador URL",
                          } as any
                        )[k] || k
                      }
                      required={k !== "contact"}
                      type={
                        ["year", "active"].includes(k)
                          ? "number"
                          : k === "email"
                            ? "email"
                            : "text"
                      }
                      value={String(v ?? "")}
                      onChange={(e: any) =>
                        setEdit({
                          ...edit,
                          [k]: ["year", "active"].includes(k)
                            ? +e.target.value
                            : e.target.value,
                        })
                      }
                    />
                  ),
                )
            )}
            <div className="modal-actions">
              <button className="secondary" type="button" onClick={close}>
                Cancelar
              </button>
              <button>
                <Save size={17} />
                Guardar cambios
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

function InventoryForm({ row, onSave }: any) {
  const [d, setD] = useState({
    product_id: row.id,
    kind: "ajuste",
    quantity: 1,
    reason: "",
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave(d);
      }}
    >
      <h3>{row.name}</h3>
      <div className="inventory-numbers">
        <span>
          Físico <b>{row.stock}</b>
        </span>
        <span>
          Reservado <b>{row.reserved}</b>
        </span>
        <span>
          Disponible <b>{row.available}</b>
        </span>
      </div>
      <Field label="Tipo de movimiento">
        <select
          value={d.kind}
          onChange={(e) =>
            setD({
              ...d,
              kind: e.target.value,
              quantity: e.target.value === "merma" ? -1 : 1,
            })
          }
        >
          <option value="ajuste">Ajuste de inventario</option>
          <option value="merma">Merma / daño</option>
          <option value="ingreso">Ingreso extraordinario</option>
        </select>
      </Field>
      <Field
        label="Cantidad (negativa para retirar)"
        type="number"
        required
        value={d.quantity}
        onChange={(e: any) => setD({ ...d, quantity: +e.target.value })}
      />
      <Field label="Motivo del movimiento">
        <textarea
          required
          rows={3}
          value={d.reason}
          onChange={(e) => setD({ ...d, reason: e.target.value })}
        />
      </Field>
      <p className="hint">
        El cambio se registrará en el kardex con tu usuario.
      </p>
      <button>Registrar movimiento</button>
    </form>
  );
}
export function ProductEditor() {
  const { id } = useParams(),
    { categories, vehicles, notify } = useStore(),
    brands = useLoad("/brands"),
    nav = useNavigate(),
    [d, setD] = useState<any>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [files, setFiles] = useState<File[]>([]),
    [previews, setPreviews] = useState<string[]>([]),
    [v, setV] = useState<any>({
      brand: "Toyota",
      model: "Yaris",
      year_from: 2012,
      year_to: 2024,
      version: "",
    });
  useEffect(() => {
    if (id)
      api("/admin/products/" + id)
        .then(setD)
        .catch((e) => setError(e.message));
    else
      setD({
        sku: "",
        name: "",
        brand_id: "",
        category_id: "",
        price_cents: 0,
        cost_cents: 0,
        old_price_cents: 0,
        minimum: 5,
        active: 1,
        featured: 0,
        universal: 0,
        oem: "",
        description: "",
        specs: {},
        compatibility: [],
        images: [],
      });
  }, [id]);
  useEffect(() => () => previews.forEach(URL.revokeObjectURL), [previews]);
  if (!d) return error ? <ErrorBox message={error} /> : <Loading />;
  const change = (k: string, value: any) => setD({ ...d, [k]: value });
  const save = async (e: any) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api("/admin/products" + (id ? "/" + id : ""), {
        method: id ? "PUT" : "POST",
        body: { ...d, brand_id: +d.brand_id, category_id: +d.category_id },
      });
      if (files.length) {
        const fd = new FormData();
        files.forEach((f) => fd.append("files", f));
        await api("/admin/products/" + r.id + "/images", {
          method: "POST",
          body: fd,
        });
      }
      notify("Producto guardado.");
      nav("/gestion/productos");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={save}>
      <div className="admin-page-title">
        <div>
          <Link className="text-link" to="/gestion/productos">
            <ChevronLeft size={15} />
            Productos
          </Link>
          <h1>{id ? "Editar producto" : "Nuevo producto"}</h1>
          <p>Información comercial, técnica y compatibilidad.</p>
        </div>
        <div className="button-row">
          <Link className="button secondary" to="/gestion/productos">
            Cancelar
          </Link>
          <button disabled={busy}>
            <Save size={18} />
            {busy ? "Guardando..." : "Guardar producto"}
          </button>
        </div>
      </div>
      <ErrorBox message={error} />
      <div className="editor-layout">
        <div>
          <section className="panel">
            <h2>Información del producto</h2>
            <Field
              label="Nombre del producto"
              required
              value={d.name}
              onChange={(e: any) => change("name", e.target.value)}
            />
            <div className="form-grid">
              <Field
                label="SKU"
                pattern="[A-Za-z0-9_-]+"
                title="Letras, números, guiones y guiones bajos"
                required
                value={d.sku}
                onChange={(e: any) => change("sku", e.target.value)}
              />
              <Field
                label="Código fabricante / OEM (si está confirmado)"
                value={d.oem}
                onChange={(e: any) => change("oem", e.target.value)}
              />
              <Field label="Marca">
                <select
                  required
                  value={d.brand_id}
                  onChange={(e) => change("brand_id", +e.target.value)}
                >
                  <option value="">Selecciona marca</option>
                  {brands.data?.map((b: any) => (
                    <option value={b.id} key={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Subcategoría">
                <select
                  required
                  value={d.category_id}
                  onChange={(e) => change("category_id", +e.target.value)}
                >
                  <option value="">Selecciona categoría</option>
                  {categories
                    .filter((c: any) => c.parent_id)
                    .map((c: any) => (
                      <option value={c.id} key={c.id}>
                        {
                          categories.find((p: any) => p.id === c.parent_id)
                            ?.name
                        }{" "}
                        / {c.name}
                      </option>
                    ))}
                </select>
              </Field>
            </div>
            <Field label="Descripción">
              <textarea
                rows={4}
                value={d.description}
                onChange={(e) => change("description", e.target.value)}
              />
            </Field>
          </section>
          <section className="panel">
            <div className="section-title">
              <h2>Especificaciones</h2>
              <button
                type="button"
                className="small secondary"
                onClick={() =>
                  change("specs", {
                    ...d.specs,
                    ["Característica " + (Object.keys(d.specs).length + 1)]: "",
                  })
                }
              >
                <Plus size={15} />
                Agregar
              </button>
            </div>
            {Object.entries(d.specs).map(([k, value], i) => (
              <div className="spec-editor" key={i}>
                <input
                  aria-label="Característica"
                  value={k}
                  onChange={(e) => {
                    const entries = Object.entries(d.specs);
                    entries[i][0] = e.target.value;
                    change("specs", Object.fromEntries(entries));
                  }}
                />
                <input
                  aria-label="Valor"
                  value={String(value)}
                  onChange={(e) =>
                    change("specs", { ...d.specs, [k]: e.target.value })
                  }
                />
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Quitar característica"
                  onClick={() =>
                    change(
                      "specs",
                      Object.fromEntries(
                        Object.entries(d.specs).filter(([key]) => key !== k),
                      ),
                    )
                  }
                >
                  <X size={16} />
                </button>
              </div>
            ))}
          </section>
          <section className="panel">
            <h2>Compatibilidad</h2>
            <label className="check">
              <input
                type="checkbox"
                checked={!!d.universal}
                onChange={(e) => change("universal", +e.target.checked)}
              />
              Producto de aplicación universal
            </label>
            {!d.universal && (
              <>
                <div className="compat-editor">
                  <select
                    aria-label="Marca compatible"
                    value={v.brand}
                    onChange={(e) =>
                      setV({
                        ...v,
                        brand: e.target.value,
                        model: "",
                        version: "",
                      })
                    }
                  >
                    {[
                      ...new Set<string>(vehicles.map((r: any) => r.brand)),
                    ].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                  <select
                    aria-label="Modelo compatible"
                    value={v.model}
                    onChange={(e) => setV({ ...v, model: e.target.value })}
                  >
                    <option value="">Modelo</option>
                    {[
                      ...new Set<string>(
                        vehicles
                          .filter((r: any) => r.brand === v.brand)
                          .map((r: any) => r.model),
                      ),
                    ].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                  <input
                    aria-label="Desde año"
                    type="number"
                    min="1950"
                    max="2030"
                    value={v.year_from}
                    onChange={(e) => setV({ ...v, year_from: +e.target.value })}
                  />
                  <input
                    aria-label="Hasta año"
                    type="number"
                    min={v.year_from}
                    max="2030"
                    value={v.year_to}
                    onChange={(e) => setV({ ...v, year_to: +e.target.value })}
                  />
                  <button
                    className="secondary"
                    type="button"
                    disabled={!v.model}
                    onClick={() =>
                      change("compatibility", [...d.compatibility, { ...v }])
                    }
                  >
                    <Plus size={17} />
                  </button>
                </div>
                <p className="hint">
                  Selecciona marca y modelo, luego agrega un rango de años. Se
                  incluyen las versiones del modelo.
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>Vehículo</th>
                      <th>Años</th>
                      <th>Versión</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {d.compatibility.map((c: any, i: number) => (
                      <tr key={i}>
                        <td>
                          {c.brand} {c.model}
                        </td>
                        <td>
                          {c.year_from}–{c.year_to}
                        </td>
                        <td>{c.version || "Todas"}</td>
                        <td>
                          <button
                            type="button"
                            aria-label="Quitar compatibilidad"
                            className="icon-button"
                            onClick={() =>
                              change(
                                "compatibility",
                                d.compatibility.filter(
                                  (_: any, n: number) => i !== n,
                                ),
                              )
                            }
                          >
                            <Trash2 size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </section>
        </div>
        <aside>
          <section className="panel">
            <h2>Precio e inventario</h2>
            {[
              ["price_cents", "Precio de venta S/"],
              ["cost_cents", "Costo de compra S/"],
              ["old_price_cents", "Precio anterior S/ (0 sin oferta)"],
            ].map(([key, label]) => (
              <Field
                key={key}
                label={label}
                type="number"
                step=".01"
                min={key === "price_cents" ? ".01" : "0"}
                required
                value={d[key] / 100}
                onChange={(e: any) =>
                  change(key, Math.round(+e.target.value * 100))
                }
              />
            ))}
            <p className="hint">Precios y costos incluyen IGV.</p>
            <Field
              label="Stock mínimo"
              type="number"
              min="0"
              required
              value={d.minimum}
              onChange={(e: any) => change("minimum", +e.target.value)}
            />
            {id && (
              <div className="info-note">
                Stock físico: {d.stock} · Reservado: {d.reserved}
                <br />
                Los ajustes se registran en Inventario.
              </div>
            )}
            <label className="check">
              <input
                type="checkbox"
                checked={!!d.active}
                onChange={(e) => change("active", +e.target.checked)}
              />
              Visible en la tienda
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={!!d.featured}
                onChange={(e) => change("featured", +e.target.checked)}
              />
              Producto destacado
            </label>
          </section>
          <section className="panel">
            <h2>Imágenes del producto</h2>
            <div className="image-editor">
              {d.images.map((im: any) => (
                <div key={im.id}>
                  <img src={im.thumb} alt="Foto del producto" />
                  <div>
                    <button
                      type="button"
                      className="text-button"
                      onClick={async () => {
                        try {
                          await api("/admin/images/" + im.id + "/primary", {
                            method: "PUT",
                          });
                          change(
                            "images",
                            d.images.map((r: any) => ({
                              ...r,
                              is_primary: +(r.id === im.id),
                            })),
                          );
                          notify("Imagen principal actualizada.");
                        } catch (e: any) {
                          notify(e.message, true);
                        }
                      }}
                    >
                      {im.is_primary ? "Principal" : "Hacer principal"}
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label="Eliminar imagen"
                      onClick={async () => {
                        if (confirm("¿Quitar esta imagen del producto?")) {
                          await api("/admin/images/" + im.id, {
                            method: "DELETE",
                          });
                          change(
                            "images",
                            d.images.filter((r: any) => r.id !== im.id),
                          );
                        }
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
              {previews.map((p) => (
                <img key={p} src={p} alt="Nueva imagen" />
              ))}
            </div>
            <label className="upload-area">
              <Upload size={24} />
              <b>Agregar fotografías</b>
              <small>JPG, PNG, WebP · Hasta 10 imágenes</small>
              <input
                aria-label="Imágenes del producto"
                type="file"
                multiple
                accept="image/png,image/jpeg,image/webp"
                onChange={(e) => {
                  const f = Array.from(e.target.files || []);
                  setFiles(f);
                  setPreviews(f.map(URL.createObjectURL));
                }}
              />
            </label>
          </section>
        </aside>
      </div>
    </form>
  );
}

export function Finance() {
  const today = new Date().toLocaleDateString("en-CA", {
      timeZone: "America/Lima",
    }),
    [start, setStart] = useState(today.slice(0, 7) + "-01"),
    [end, setEnd] = useState(today),
    [tab, setTab] = useState("products"),
    [q, setQ] = useState(""),
    [page, setPage] = useState(1),
    [sort, setSort] = useState("revenue"),
    load = useLoad("/admin/reports?start=" + start + "&end=" + end);
  const d = load.data,
    records = (d?.[tab] || [])
      .filter((p: any) => p.name.toLowerCase().includes(q.toLowerCase()))
      .sort((a: any, b: any) => b[sort] - a[sort]);
  return (
    <>
      <div className="admin-page-title">
        <div>
          <div className="eyebrow muted">RESULTADOS DEL NEGOCIO</div>
          <h1>Finanzas</h1>
          <p>Ventas confirmadas, costos y ganancia estimada del periodo.</p>
        </div>
        <a
          className="button secondary small"
          href={"/api/admin/export/finance?start=" + start + "&end=" + end}
        >
          <Download size={17} />
          Exportar CSV
        </a>
      </div>
      <div className="report-filters">
        <Field
          label="Desde"
          type="date"
          max={end}
          value={start}
          onChange={(e: any) => setStart(e.target.value)}
        />
        <Field
          label="Hasta"
          type="date"
          min={start}
          value={end}
          onChange={(e: any) => setEnd(e.target.value)}
        />
        <span>Pagos confirmados en el periodo seleccionado</span>
      </div>
      {load.loading ? (
        <Loading />
      ) : load.error ? (
        <ErrorBox message={load.error} />
      ) : (
        <>
          <div className="stats-grid">
            {[
              ["Ingresos", d.revenue],
              ["Costo de mercadería", d.cost],
              ["Ganancia estimada", d.profit],
              ["IGV de ventas", d.tax],
            ].map(([name, value]: any) => (
              <div className="stat-card" key={name}>
                <span>{name}</span>
                <strong>{money(value)}</strong>
                <small>
                  {name === "Ganancia estimada"
                    ? d.margin + "% de margen"
                    : "Periodo seleccionado"}
                </small>
              </div>
            ))}
          </div>
          <section className="panel">
            <div className="section-title">
              <h2>Ventas del periodo</h2>
              <span>{d.orders} pedidos confirmados</span>
            </div>
            <SalesChart data={d.daily} />
          </section>
          <section className="panel table-panel">
            <div className="table-toolbar">
              <div className="tabs">
                {[
                  ["products", "Por producto"],
                  ["categories", "Por categoría"],
                ].map(([v, t]) => (
                  <button
                    key={v}
                    className={tab === v ? "active" : ""}
                    onClick={() => {
                      setTab(v);
                      setPage(1);
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <div className="table-search">
                <Search size={16} />
                <input
                  aria-label="Buscar resultado"
                  placeholder="Buscar..."
                  value={q}
                  onChange={(e) => {
                    setQ(e.target.value);
                    setPage(1);
                  }}
                />
              </div>
            </div>
            <table>
              <thead>
                <tr>
                  <th>{tab === "products" ? "Producto" : "Categoría"}</th>
                  {tab === "products" && <th>Unidades</th>}
                  {[
                    ["revenue", "Ventas"],
                    ["cost", "Costo"],
                    ["profit", "Ganancia estimada"],
                  ].map(([k, l]) => (
                    <th key={k}>
                      <button className="table-sort" onClick={() => setSort(k)}>
                        {l}
                        <ChevronDown size={12} />
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {records.slice((page - 1) * 15, page * 15).map((r: any) => (
                  <tr key={r.id || r.name}>
                    <td>
                      {r.name}
                      {r.sku && <small>{r.sku}</small>}
                    </td>
                    {tab === "products" && <td>{r.units}</td>}
                    <td>{money(r.revenue)}</td>
                    <td>{money(r.cost)}</td>
                    <td>
                      <b className="text-green">{money(r.profit)}</b>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!records.length && <Empty />}
            <Pagination
              page={page}
              pages={Math.ceil(records.length / 15)}
              total={records.length}
              onChange={setPage}
            />
          </section>
          <p className="hint">
            Ganancia comercial estimada sin IGV sobre mercadería vendida;
            excluye gastos operativos y transporte. Los costos se conservan por
            cada venta.
          </p>
        </>
      )}
    </>
  );
}

export function Settings() {
  const { config, setConfig, user, notify } = useStore(),
    [d, setD] = useState<any>(config),
    [busy, setBusy] = useState(false);
  if (user.role !== "admin")
    return <ErrorBox message="Acceso exclusivo del administrador." />;
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          const c = await api("/admin/config", { method: "PUT", body: d });
          setConfig(c);
          notify("Configuración guardada.");
        } catch (e: any) {
          notify(e.message, true);
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="admin-page-title">
        <div>
          <h1>Configuración</h1>
          <p>Datos de la tienda, entregas y medios de pago.</p>
        </div>
        <button disabled={busy}>
          <Save size={17} />
          {busy ? "Guardando..." : "Guardar cambios"}
        </button>
      </div>
      <div className="editor-layout">
        <section className="panel">
          <h2>Datos de la tienda</h2>
          <div className="form-grid">
            {[
              ["name", "Nombre comercial"],
              ["legal_name", "Razón social"],
              ["ruc", "RUC"],
              ["phone", "Teléfono"],
              ["whatsapp", "WhatsApp (código país y número)"],
              ["email", "Correo"],
              ["address", "Dirección"],
              ["hours", "Horario"],
              ["bank_account", "Cuenta bancaria de ejemplo"],
            ].map(([key, label]) => (
              <Field
                key={key}
                label={label}
                required
                value={d[key]}
                onChange={(e: any) => setD({ ...d, [key]: e.target.value })}
              />
            ))}
          </div>
          <h2>Tarifas de envío</h2>
          {d.shipping.map((z: any, i: number) => (
            <div className="shipping-editor" key={i}>
              <Field
                label="Zona"
                required
                value={z.name}
                onChange={(e: any) =>
                  setD({
                    ...d,
                    shipping: d.shipping.map((s: any, n: number) =>
                      i === n ? { ...s, name: e.target.value } : s,
                    ),
                  })
                }
              />
              <Field
                label="Tarifa S/"
                type="number"
                step=".01"
                min="0"
                required
                value={z.cents / 100}
                onChange={(e: any) =>
                  setD({
                    ...d,
                    shipping: d.shipping.map((s: any, n: number) =>
                      i === n
                        ? { ...s, cents: Math.round(+e.target.value * 100) }
                        : s,
                    ),
                  })
                }
              />
              <Field
                label="Plazo estimado"
                required
                value={z.days}
                onChange={(e: any) =>
                  setD({
                    ...d,
                    shipping: d.shipping.map((s: any, n: number) =>
                      i === n ? { ...s, days: e.target.value } : s,
                    ),
                  })
                }
              />
            </div>
          ))}
          <button
            type="button"
            className="secondary small"
            onClick={() =>
              setD({
                ...d,
                shipping: [
                  ...d.shipping,
                  { name: "Nueva zona", cents: 0, days: "2–3 días" },
                ],
              })
            }
          >
            <Plus size={16} />
            Agregar zona
          </button>
        </section>
        <aside>
          <section className="panel">
            <h2>Impuestos</h2>
            <Field
              label="IGV (%)"
              type="number"
              min="0"
              max="30"
              required
              value={d.igv_percent}
              onChange={(e: any) =>
                setD({ ...d, igv_percent: +e.target.value })
              }
            />
            <p className="hint">
              Los precios del catálogo incluyen el impuesto.
            </p>
          </section>
          <section className="panel">
            <h2>Métodos de pago</h2>
            {[
              "Yape",
              "Plin",
              "Transferencia",
              "Tarjeta simulada",
              "Pago en tienda",
            ].map((p) => (
              <label className="check" key={p}>
                <input
                  type="checkbox"
                  checked={d.payments.includes(p)}
                  onChange={(e) =>
                    setD({
                      ...d,
                      payments: e.target.checked
                        ? [...d.payments, p]
                        : d.payments.filter((v: string) => v !== p),
                    })
                  }
                />
                {p}
              </label>
            ))}
            <div className="info-note">
              Todos los pagos son simulados. No se realizan cobros reales.
            </div>
          </section>
        </aside>
      </div>
    </form>
  );
}
