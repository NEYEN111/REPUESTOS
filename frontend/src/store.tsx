import React, { useEffect, useState } from "react";
import {
  Link,
  Outlet,
  useNavigate,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  Boxes,
  LogOut,
  CarFront,
  ShoppingCart,
  UserRound,
  Search,
  Phone,
  Truck,
  MapPin,
  ChevronDown,
  ArrowUpRight,
  ArrowRight,
  ShieldCheck,
  PackageCheck,
  SlidersHorizontal,
  Check,
  Plus,
  Trash2,
  ZoomIn,
  Grid2X2,
  X,
  ChevronRight,
  MessageCircle,
  Clock3,
} from "lucide-react";
import {
  api,
  useStore,
  useLoad,
  money,
  Loading,
  ErrorBox,
  Empty,
  ProductCard,
  ProductImage,
  Modal,
  Pagination,
} from "./lib";

import { WorkspaceShell } from "./workspace";
import { AssistantChat } from "./assistant";

export function Logo() {
  const { config } = useStore();
  return (
    <Link to="/" className="logo">
      <span className="logo-symbol">
        <i />
        <i />
        <i />
      </span>
      {config.name}
      <small>REPUESTOS & ACCESORIOS</small>
    </Link>
  );
}
export function StoreLayout() {
  const { config, cart, vehicle, vehicles, user, categories, notify } = useStore(),
    [search, setSearch] = useState(""),
    [menu, setMenu] = useState(false),
    nav = useNavigate(),
    location = useLocation();
  const active = vehicles.find((v: any) => v.id === vehicle);
  const staff = ["admin", "empleado"].includes(user?.role);
  const managing = location.pathname.startsWith("/gestion");
  useEffect(() => { setMenu(false); }, [location.pathname, location.search]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenu(false); };
    document.addEventListener('keydown', close);
    return () => document.removeEventListener('keydown', close);
  }, []);
  if (managing && staff) return <WorkspaceShell><Outlet /></WorkspaceShell>;
  return (
    <>
      <a className="skip-link" href="#store-main">Saltar al contenido</a>
      <div className="topbar">
        <div className="container">
          <span>
            <Truck size={13} />
            Envíos a todo el Perú
          </span>
          <span>{staff ? (user.role === "admin" ? "Área de trabajo · Administrador" : "Área de trabajo · Empleado") : "Compra online · Retira en tienda"}</span>
          <span>
            <Phone size={12} />
            {config.phone}
            <b className="top-divider" />
            <a
              href={"https://wa.me/" + config.whatsapp}
              target="_blank"
              rel="noreferrer"
            >
              Atención por WhatsApp <ArrowUpRight size={12} />
            </a>
          </span>
        </div>
      </div>
      <header className="store-header">
        <div className="container header-main">
          <Logo />
          <form
            className="searchbox"
            onSubmit={(e) => {
              e.preventDefault();
              nav("/catalogo?q=" + encodeURIComponent(search));
              setMenu(false);
            }}
          >
            <Search size={20} />
            <input
              aria-label="Buscar repuestos"
              placeholder="Busca por repuesto, marca o código OEM"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <button>Buscar</button>
          </form>
          {staff ? <Link className="header-action stock-shortcut" to="/gestion/inventario"><Boxes size={24} /><span><small>Control de existencias</small><b>Ver stock</b></span></Link> : <Link className="header-action" to="/garaje">
            <CarFront size={24} />
            <span>
              <small>Mi garaje</small>
              <b>
                {active
                  ? active.brand + " " + active.model
                  : "Selecciona tu auto"}
              </b>
            </span>
          </Link>}
          <Link
            className="header-action account-link"
            to={user ? "/cuenta" : "/ingresar"}
          >
            <UserRound size={23} />
            <span>
              <small>
                {user ? "Hola, " + user.name.split(" ")[0] : "Bienvenido"}
              </small>
              <b>{staff ? "Mi perfil" : "Mi cuenta"}</b>
            </span>
          </Link>
          <Link className="cart-link" to="/carrito" aria-label="Carrito">
            <ShoppingCart size={23} />
            <span>{cart.reduce((s: number, i: any) => s + i.quantity, 0)}</span>
          </Link>
          {user && <button className="icon-button header-logout" aria-label="Cerrar sesión" title="Cerrar sesión" onClick={async () => {
            try { await api("/auth/logout", { method: "POST" }); window.location.assign("/"); }
            catch (e: any) { notify(e.message, true); }
          }}><LogOut size={19} /></button>}
        </div>
        <div className="nav-wrap">
          <nav className="container main-nav">
            <button
              className={"category-toggle " + (menu ? "selected" : "")}
              aria-expanded={menu}
              aria-controls="store-categories"
              onClick={() => setMenu(!menu)}
            >
              <Grid2X2 size={17} /> Todas las categorías{" "}
              <ChevronDown size={15} />
            </button>
            {["frenos", "motor", "suspension", "filtros"].map((slug) => (
              <Link key={slug} to={"/catalogo?category=" + slug}>
                {categories.find((c: any) => c.slug === slug)?.name || slug}
              </Link>
            ))}
            <Link to="/catalogo?category=accesorios">Accesorios</Link>
            <Link to="/catalogo?offer=1" className="offer-nav">
              Ofertas del mes <ArrowUpRight size={14} />
            </Link>
            <Link to={staff ? '/gestion' : '/garaje'} className="nav-fit">
              {staff ? <Boxes size={16} /> : <ShieldCheck size={16} />}
              {staff ? 'Volver a gestión' : 'Encuentra la pieza que encaja'}
            </Link>
          </nav>
          {menu && (
            <div id="store-categories" className="mega-menu container">
              {categories
                .filter((c: any) => !c.parent_id)
                .map((c: any) => (
                  <div key={c.id}>
                    <Link
                      className="mega-title"
                      onClick={() => setMenu(false)}
                      to={"/catalogo?category=" + c.slug}
                    >
                      {c.name}
                      <ChevronRight size={14} />
                    </Link>
                    {categories
                      .filter((s: any) => s.parent_id === c.id)
                      .slice(0, 4)
                      .map((s: any) => (
                        <Link
                          key={s.id}
                          onClick={() => setMenu(false)}
                          to={"/catalogo?category=" + s.slug}
                        >
                          {s.name}
                        </Link>
                      ))}
                  </div>
                ))}
            </div>
          )}
        </div>
      </header>
      <main id="store-main">
        <Outlet />
      </main>
      {managing ? <footer className="workspace-footer"><div className="container"><span>{config.name} · Área de trabajo</span><span>Precios en soles · America/Lima</span></div></footer> : <footer>
        <div className="container footer-grid">
          <div>
            <Logo />
            <p>
              Todo para tu auto.
              <br />
              La pieza correcta, a tu alcance.
            </p>
            <span className="footer-note">
              Proyecto universitario · Compras simuladas
            </span>
          </div>
          <div>
            <h4>Compra con confianza</h4>
            <Link to="/catalogo">Catálogo completo</Link>
            <Link to="/garaje">Mi garaje</Link>
            <Link to="/cuenta">Mis pedidos</Link>
            <Link to="/carrito">Carrito y cotizaciones</Link>
          </div>
          <div>
            <h4>Estamos para ayudarte</h4>
            <p>{config.address}</p>
            <p>{config.hours}</p>
            <a
              href={"https://wa.me/" + config.whatsapp}
              target="_blank"
              rel="noreferrer"
            >
              {config.phone}
            </a>
          </div>
          <div>
            <h4>Información</h4>
            <Link to="/terminos">Términos y condiciones</Link>
            <Link to="/privacidad">Política de privacidad</Link>
            <Link to="/reclamaciones">Libro de Reclamaciones</Link>
            {staff && <Link to="/gestion">Mi área de trabajo <ArrowUpRight size={13} /></Link>}
          </div>
        </div>
        <div className="container footer-bottom">
          <span>
            © {new Date().getFullYear()} {config.name}. Hecho para seguir en
            movimiento.
          </span>
          <span className="payment-names">
            Yape <b>Plin</b> VISA <span>Transferencia</span>
          </span>
        </div>
      </footer>}
      {!managing && config.ASSISTANT_ENABLED && <AssistantChat vehicleId={active?.id} />}
    </>
  );
}

export function VehicleSelector({ onDone, compact = false }: any) {
  const { vehicles, garage, saveGarage, notify, vehicle } = useStore();
  const active = vehicles.find((v: any) => v.id === vehicle);
  const [brand, setBrand] = useState(active?.brand || ""),
    [model, setModel] = useState(active?.model || ""),
    [year, setYear] = useState(active?.year?.toString() || ""),
    [version, setVersion] = useState(active?.version || ""),
    [busy, setBusy] = useState(false);
  const unique = (field: string, filter: (v: any) => boolean) => [
    ...new Set<string>(
      vehicles.filter(filter).map((v: any) => String(v[field])),
    ),
  ];
  const submit = async (e: any) => {
    e.preventDefault();
    const v = vehicles.find(
      (v: any) =>
        v.brand === brand &&
        v.model === model &&
        v.year === +year &&
        v.version === version,
    );
    if (!v) return;
    setBusy(true);
    try {
      await saveGarage([...new Set([...garage, v.id])], v.id);
      notify("Tu vehículo está seleccionado.");
      onDone?.();
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className={"vehicle-selector " + (compact ? "compact" : "")}
      onSubmit={submit}
    >
      <label>
        <span>01 · Marca</span>
        <select
          aria-label="Marca del auto"
          required
          value={brand}
          onChange={(e) => {
            setBrand(e.target.value);
            setModel("");
            setYear("");
            setVersion("");
          }}
        >
          <option value="">Selecciona marca</option>
          {unique("brand", () => true).map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <label>
        <span>02 · Modelo</span>
        <select
          aria-label="Modelo del auto"
          required
          disabled={!brand}
          value={model}
          onChange={(e) => {
            setModel(e.target.value);
            setYear("");
            setVersion("");
          }}
        >
          <option value="">Selecciona modelo</option>
          {unique("model", (v) => v.brand === brand).map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <label>
        <span>03 · Año</span>
        <select
          aria-label="Año del auto"
          required
          disabled={!model}
          value={year}
          onChange={(e) => {
            setYear(e.target.value);
            setVersion("");
          }}
        >
          <option value="">Selecciona año</option>
          {unique("year", (v) => v.brand === brand && v.model === model).map(
            (s) => (
              <option key={s}>{s}</option>
            ),
          )}
        </select>
      </label>
      <label>
        <span>04 · Versión</span>
        <select
          aria-label="Versión del auto"
          required
          disabled={!year}
          value={version}
          onChange={(e) => setVersion(e.target.value)}
        >
          <option value="">Selecciona versión</option>
          {unique(
            "version",
            (v) => v.brand === brand && v.model === model && v.year === +year,
          ).map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <button disabled={busy || !version}>
        {busy ? "Guardando..." : "Encontrar repuestos"}
        <ArrowRight size={18} />
      </button>
    </form>
  );
}

export function Home() {
  const { categories, vehicle, config } = useStore(),
    nav = useNavigate();
  const popular = useLoad(
    "/products?limit=5" + (vehicle ? "&vehicle=" + vehicle : ""),
  );
  const cats = [
    "frenos",
    "suspension",
    "filtros",
    "motor",
    "encendido",
    "electrico",
  ];
  const selected = cats
    .map((s) => categories.find((c: any) => c.slug === s))
    .filter(Boolean);
  if (selected.length < 6)
    categories
      .filter((c: any) => !c.parent_id && !selected.includes(c))
      .slice(0, 6 - selected.length)
      .forEach((c: any) => selected.push(c));
  return (
    <>
      <section className="hero">
        <div className="hero-image" />
        <div className="hero-shade" />
        <div className="container hero-inner">
          <div className="hero-copy">
            <div className="eyebrow">
              <span /> REPUESTOS Y ACCESORIOS / PERÚ
            </div>
            <h1>
              La pieza correcta.
              <br />
              <em>El camino sigue.</em>
            </h1>
            <p>
              Busca por repuesto, marca o modelo de auto.
              <br />
              Compra online o prepara tu cotización.
            </p>
            <Link to="/catalogo" className="button lime">
              Explorar repuestos
              <ArrowUpRight size={19} />
            </Link>
            <div className="hero-meta">
              <span>Marcas que conoces.</span>
              <span>La compatibilidad que necesitas.</span>
            </div>
          </div>
          <div className="hero-caption">
            <span>CADA PIEZA CUENTA.</span>
            <b>MOTOR · FRENOS · SUSPENSIÓN · ACCESORIOS</b>
          </div>
          <div className="hero-page">
            <b>PERÚ</b>
            <i />
            ENVIOS NACIONALES
          </div>
        </div>
      </section>
      <div className="container">
        <section className="garage-strip">
          <div className="garage-heading">
            <span className="car-tile">
              <CarFront size={28} />
            </span>
            <div>
              <h2>Primero, tu auto.</h2>
              <p>Te mostramos las piezas que le corresponden.</p>
            </div>
            <Link to="/garaje">
              Ir a mi garaje <ArrowUpRight size={14} />
            </Link>
          </div>
          <VehicleSelector onDone={() => nav("/catalogo")} />
        </section>
        <div className="benefits">
          <div>
            <ShieldCheck />
            <span>
              <b>Compatibilidad a la vista</b>
              <small>Compra la pieza correcta</small>
            </span>
          </div>
          <div>
            <Truck />
            <span>
              <b>Envíos a todo el Perú</b>
              <small>A tu casa o por agencia</small>
            </span>
          </div>
          <div>
            <MapPin />
            <span>
              <b>Retiro en tienda gratis</b>
              <small>Compra online, recoge en Lima</small>
            </span>
          </div>
          <div>
            <MessageCircle />
            <span>
              <b>Atención personalizada</b>
              <small>Te ayudamos por WhatsApp</small>
            </span>
          </div>
        </div>
        <section className="home-section">
          <div className="section-title">
            <div>
              <div className="eyebrow muted">TODO LO QUE TU AUTO NECESITA</div>
              <h2>Encuentra tu repuesto</h2>
            </div>
            <Link to="/catalogo">
              Ver todas las categorías <ArrowRight size={18} />
            </Link>
          </div>
          <div className="category-grid">
            {selected.map((c: any) => (
              <Link
                key={c.id}
                to={"/catalogo?category=" + c.slug}
                className="category-card"
              >
                <img src={c.image} alt={c.name} loading="lazy" />
                <div>
                  <h3>{c.name}</h3>
                  <small>{c.count} productos</small>
                </div>
                <ArrowUpRight size={18} />
              </Link>
            ))}
          </div>
        </section>
        <section className="home-section">
          <div className="section-title">
            <div>
              <div className="eyebrow muted">
                MANTENIMIENTO SIN COMPLICACIONES
              </div>
              <h2>
                {vehicle
                  ? "Elegidos para tu auto"
                  : "Los esenciales de tu auto"}
              </h2>
            </div>
            <Link to="/catalogo?offer=1">
              Ver ofertas <ArrowRight size={18} />
            </Link>
          </div>
          {popular.loading ? (
            <Loading />
          ) : popular.error ? (
            <ErrorBox message={popular.error} />
          ) : (
            <div className="product-grid five">
              {popular.data?.items.map((p: any) => (
                <ProductCard key={p.id} p={p} />
              ))}
            </div>
          )}
        </section>
        <section className="service-banner">
          <div>
            <span className="eyebrow">CUIDA LO QUE TE MUEVE</span>
            <h2>
              Un buen mantenimiento
              <br />
              empieza con buenas piezas.
            </h2>
            <Link className="button lime" to="/catalogo?category=filtros">
              Prepara tu próximo cambio
              <ArrowUpRight size={18} />
            </Link>
          </div>
          <div className="service-image">
            <img
              src={categories.find((c: any) => c.slug === "filtros")?.image}
              alt="Filtros para mantenimiento"
            />
          </div>
          <div className="service-detail">
            <PackageCheck size={32} />
            <b>Todo en un solo lugar</b>
            <p>
              Filtros, aceites, bujías y más.
              <br />
              Arma tu cotización en minutos.
            </p>
          </div>
        </section>
        <div className="brands-row">
          <span>MARCAS QUE NOS MUEVEN</span>
          {["BOSCH", "DENSO", "brembo", "NGK", "KYB", "MANN FILTER"].map(
            (b) => (
              <b key={b}>{b}</b>
            ),
          )}
        </div>
      </div>
    </>
  );
}

export function Catalog() {
  const { categories, vehicle, vehicles, event } = useStore(),
    [params, setParams] = useSearchParams(),
    [garageModal, setGarageModal] = useState(false);
  const q = params.get("q") || "",
    category = params.get("category") || "",
    page = +(params.get("page") || 1);
  const active = vehicles.find((v: any) => v.id === vehicle);
  const query = new URLSearchParams(params);
  query.set("limit", "12");
  if (vehicle) query.set("vehicle", vehicle);
  const list = useLoad("/products?" + query),
    brands = useLoad("/brands");
  const selected = categories.find((c: any) => c.slug === category);
  const parent = selected?.parent_id
    ? categories.find((c: any) => c.id === selected.parent_id)
    : selected;
  const set = (key: string, value: string) => {
    const p = new URLSearchParams(params);
    value ? p.set(key, value) : p.delete(key);
    if (key !== "page") p.delete("page");
    setParams(p);
  };
  useEffect(() => {
    if (q) event("search", { payload: { query: q } });
  }, [q]);
  return (
    <div className="container page">
      <div className="breadcrumbs">
        <Link to="/">Inicio</Link>
        <ChevronRight size={12} />
        Catálogo
        {selected && (
          <>
            <ChevronRight size={12} />
            {selected.name}
          </>
        )}
      </div>
      <div className="catalog-heading">
        <div>
          <div className="eyebrow muted">REPUESTOS & ACCESORIOS</div>
          <h1>
            {q
              ? "Resultados para “" + q + "”"
              : selected?.name ||
                (params.get("offer") ? "Ofertas del mes" : "Todo para tu auto")}
          </h1>
          <p>{list.data?.total ?? "…"} productos para seguir en movimiento</p>
        </div>
        <button className="vehicle-mini" onClick={() => setGarageModal(true)}>
          <CarFront size={28} />
          <span>
            <small>
              {active ? "Tu auto seleccionado" : "Encuentra piezas compatibles"}
            </small>
            <b>
              {active
                ? `${active.brand} ${active.model} ${active.year}`
                : "Selecciona tu vehículo"}
            </b>
          </span>
          <ChevronDown size={17} />
        </button>
      </div>
      <div className="catalog-layout">
        <aside className="filters">
          <h3>
            <SlidersHorizontal size={17} />
            Filtrar productos{" "}
            <button onClick={() => setParams({})}>Limpiar</button>
          </h3>
          <section>
            <h4>Categorías</h4>
            {parent && (
              <Link className="filter-back" to="/catalogo">
                Todas las categorías
              </Link>
            )}
            {categories
              .filter((c: any) =>
                parent ? c.parent_id === parent.id : !c.parent_id,
              )
              .map((c: any) => (
                <button
                  key={c.id}
                  className={
                    "category-filter " + (category === c.slug ? "active" : "")
                  }
                  onClick={() => set("category", c.slug)}
                >
                  {c.name}
                  <span>{c.count}</span>
                </button>
              ))}
          </section>
          <section>
            <h4>Marca del repuesto</h4>
            <select
              aria-label="Filtrar por marca"
              value={params.get("brand") || ""}
              onChange={(e) => set("brand", e.target.value)}
            >
              <option value="">Todas las marcas</option>
              {brands.data?.map((b: any) => (
                <option key={b.id}>{b.name}</option>
              ))}
            </select>
          </section>
          <section>
            <h4>Precio máximo</h4>
            <select
              aria-label="Precio máximo"
              value={params.get("max_price") || ""}
              onChange={(e) => set("max_price", e.target.value)}
            >
              <option value="">Sin límite</option>
              <option value="10000">Hasta S/ 100</option>
              <option value="25000">Hasta S/ 250</option>
              <option value="50000">Hasta S/ 500</option>
              <option value="100000">Hasta S/ 1,000</option>
            </select>
          </section>
          <section>
            <h4>Disponibilidad</h4>
            <label className="check">
              <input
                type="checkbox"
                checked={params.get("in_stock") === "true"}
                onChange={(e) =>
                  set("in_stock", e.target.checked ? "true" : "")
                }
              />
              Solo con stock
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={!!params.get("offer")}
                onChange={(e) => set("offer", e.target.checked ? "true" : "")}
              />
              Productos en oferta
            </label>
          </section>
          <div className="filter-help">
            <MessageCircle size={25} />
            <h4>¿Buscas una pieza?</h4>
            <p>Ten a la mano el modelo y año de tu auto.</p>
            <Link to="/garaje">
              Revisar mi garaje <ArrowUpRight size={14} />
            </Link>
          </div>
        </aside>
        <section>
          <div className="list-toolbar">
            <span>
              {active ? (
                <>
                  <Check size={15} /> Compatibles con {active.brand}{" "}
                  {active.model}
                </>
              ) : (
                "Encuentra el repuesto que necesitas"
              )}
            </span>
            <label>
              Ordenar por{" "}
              <select
                aria-label="Ordenar productos"
                value={params.get("sort") || "recommended"}
                onChange={(e) => set("sort", e.target.value)}
              >
                <option value="recommended">Recomendados</option>
                <option value="price_asc">Menor precio</option>
                <option value="price_desc">Mayor precio</option>
                <option value="name">Nombre A–Z</option>
              </select>
            </label>
          </div>
          {list.loading ? (
            <Loading />
          ) : list.error ? (
            <ErrorBox message={list.error} />
          ) : list.data?.items.length ? (
            <>
              <div className="product-grid">
                {list.data.items.map((p: any) => (
                  <ProductCard p={p} key={p.id} />
                ))}
              </div>
              <Pagination
                {...list.data}
                onChange={(n: number) => {
                  set("page", String(n));
                  window.scrollTo(0, 200);
                }}
              />
            </>
          ) : (
            <Empty
              action={
                <button onClick={() => setParams({})}>Quitar filtros</button>
              }
            />
          )}
        </section>
      </div>
      {garageModal && (
        <Modal
          title="Selecciona tu auto"
          wide
          onClose={() => setGarageModal(false)}
        >
          <VehicleSelector onDone={() => setGarageModal(false)} />
        </Modal>
      )}
    </div>
  );
}

export function Product() {
  const { id } = useParams(),
    { vehicle, vehicles, add, event, config } = useStore(),
    load = useLoad("/products/" + id + (vehicle ? "?vehicle=" + vehicle : "")),
    [qty, setQty] = useState(1),
    [image, setImage] = useState(""),
    [zoom, setZoom] = useState(false),
    [tab, setTab] = useState("Especificaciones"),
    [select, setSelect] = useState(false);
  const related = useLoad(
    "/products?limit=5" +
      (load.data ? "&category=" + load.data.category_slug : "") +
      (vehicle ? "&vehicle=" + vehicle : ""),
  );
  useEffect(() => {
    setQty(1);
    setImage("");
    event("product_view", { product_id: +id! });
  }, [id]);
  if (load.loading) return <Loading />;
  if (load.error)
    return (
      <div className="container page">
        <ErrorBox message={load.error} />
      </div>
    );
  const p = load.data,
    active = vehicles.find((v: any) => v.id === vehicle);
  return (
    <div className="container page">
      <div className="breadcrumbs">
        <Link to="/">Inicio</Link>
        <ChevronRight size={12} />
        <Link to={"/catalogo?category=" + p.category_slug}>{p.category}</Link>
        <ChevronRight size={12} />
        {p.brand}
      </div>
      <div className="product-detail">
        <div className="gallery">
          <button className="gallery-main" onClick={() => setZoom(true)}>
            <ProductImage p={p} src={image || p.image} />
            <span>
              <ZoomIn size={17} />
              Ampliar imagen
            </span>
          </button>
          <div className="thumbnails">
            {p.images.map((i: any) => (
              <button key={i.id} onClick={() => setImage(i.url)}>
                <img src={i.thumb} alt="Vista del producto" />
              </button>
            ))}
          </div>
          <small>Fotografía referencial del tipo de pieza.</small>
        </div>
        <div className="product-info">
          <span className="product-brand">{p.brand}</span>
          <h1>{p.name}</h1>
          <div className="sku-line">
            SKU: {p.sku}
            <span>{p.oem ? 'Código fabricante / OEM: ' + p.oem : 'Referencia interna: ' + (p.specs?.['Referencia interna'] || p.sku)}</span>
          </div>
          <button
            onClick={() => setSelect(true)}
            className={
              "compatibility-box " +
              (p.compatible === false ? "incompatible" : "")
            }
          >
            <CarFront size={24} />
            <span>
              <b>
                {p.compatible === true
                  ? `Compatible con tu ${active?.brand} ${active?.model} ${active?.year}`
                  : p.compatible === false
                    ? "No compatible con tu auto"
                    : "Selecciona tu auto para verificar compatibilidad"}
              </b>
              <small>
                {p.universal
                  ? "Producto de aplicación universal"
                  : "Cambiar o seleccionar vehículo"}
              </small>
            </span>
            <ChevronRight size={17} />
          </button>
          {p.quality?.compatibility_source === 'seed_simulado' && <p className="hint catalog-application-note">Aplicación del catálogo académico. Confirma versión y referencia técnica antes de instalar.</p>}
          <div className="detail-price">
            {p.old_price_cents > p.price_cents && (
              <del>{money(p.old_price_cents)}</del>
            )}
            <strong>{money(p.price_cents)}</strong>
            <small>{p.specs?.['Presentación'] || 'Precio por presentación'} · Incluye IGV</small>
          </div>
          <div className={"stock " + (!p.available ? "out" : "")}>
            {p.available > 5
              ? "En stock · Disponible para despacho"
              : p.available
                ? `Últimas ${p.available} unidades`
                : "Agotado temporalmente"}
          </div>
          <div className="purchase-row">
            <div className="quantity">
              <button
                onClick={() => setQty(Math.max(1, qty - 1))}
                aria-label="Reducir cantidad"
              >
                −
              </button>
              <input
                aria-label="Cantidad"
                type="number"
                min="1"
                max={p.available}
                value={qty}
                onChange={(e) =>
                  setQty(Math.min(p.available, Math.max(1, +e.target.value)))
                }
              />
              <button
                aria-label="Aumentar cantidad"
                onClick={() => setQty(Math.min(p.available, qty + 1))}
              >
                +
              </button>
            </div>
            <button disabled={!p.available} onClick={() => add(p, qty)}>
              <ShoppingCart size={18} />
              Agregar al carrito
            </button>
          </div>
          <a
            className="button secondary whatsapp"
            href={`https://wa.me/${config.whatsapp}?text=${encodeURIComponent("Hola, consulto por " + p.name + " · SKU " + p.sku)}`}
            target="_blank"
            rel="noreferrer"
          >
            <MessageCircle size={18} />
            Consultar por WhatsApp
          </a>
          <div className="delivery-options">
            <div>
              <Truck size={20} />
              <span>
                <b>Envío a todo el Perú</b>
                <small>Tarifa y plazo al finalizar tu compra.</small>
              </span>
            </div>
            <div>
              <MapPin size={20} />
              <span>
                <b>Retiro en tienda gratis</b>
                <small>{config.address}</small>
              </span>
            </div>
          </div>
        </div>
      </div>
      <div className="detail-tabs">
        {["Especificaciones", "Compatibilidad", "Descripción"].map((t) => (
          <button
            key={t}
            className={t === tab ? "active" : ""}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>
      <section className="detail-tab-content">
        {tab === "Especificaciones" ? (
          <div className="spec-grid">
            {Object.entries(p.specs).map(([k, v]) => (
              <div key={k}>
                <span>{k}</span>
                <b>{String(v)}</b>
              </div>
            ))}
          </div>
        ) : tab === "Compatibilidad" ? (
          p.universal ? (
            <p>
              Este producto es de aplicación universal. Revisa las medidas y
              especificaciones.
            </p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Marca</th>
                  <th>Modelo</th>
                  <th>Años</th>
                  <th>Versión</th>
                </tr>
              </thead>
              <tbody>
                {p.compatibility.map((c: any) => (
                  <tr key={c.id}>
                    <td>{c.brand}</td>
                    <td>{c.model}</td>
                    <td>
                      {c.year_from}–{c.year_to}
                    </td>
                    <td>{c.version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        ) : (
          <p>{p.description}</p>
        )}
      </section>
      <section className="home-section">
        <div className="section-title">
          <h2>También para tu auto</h2>
          <Link to={"/catalogo?category=" + p.category_slug}>
            Ver categoría <ArrowRight size={17} />
          </Link>
        </div>
        <div className="product-grid five">
          {related.data?.items
            .filter((r: any) => r.id !== p.id)
            .slice(0, 5)
            .map((r: any) => (
              <ProductCard p={r} key={r.id} />
            ))}
        </div>
      </section>
      {zoom && (
        <Modal title={p.name} wide onClose={() => setZoom(false)}>
          <ProductImage p={p} src={image || p.image} className="zoom-image" />
        </Modal>
      )}
      {select && (
        <Modal
          title="Verificar compatibilidad"
          wide
          onClose={() => setSelect(false)}
        >
          <VehicleSelector onDone={() => setSelect(false)} />
        </Modal>
      )}
    </div>
  );
}

export function Garage() {
  const { garage, vehicle, vehicles, saveGarage, notify, user } = useStore();
  return (
    <div className="container page">
      <div className="page-title">
        <div>
          <div className="eyebrow muted">LA PIEZA CORRECTA EMPIEZA AQUÍ</div>
          <h1>Mi garaje</h1>
          <p>Guarda tus autos y elige cuál usar para buscar repuestos.</p>
        </div>
        <CarFront size={48} strokeWidth={1.1} />
      </div>
      <div className="panel">
        <h3>Agregar un vehículo</h3>
        <VehicleSelector />
        {!user && (
          <p className="hint">
            Tus vehículos se guardan en este navegador.{" "}
            <Link to="/ingresar">Inicia sesión</Link> para guardarlos en tu
            cuenta.
          </p>
        )}
      </div>
      <div className="garage-cards">
        {garage
          .map((id: number) => vehicles.find((v: any) => v.id === id))
          .filter(Boolean)
          .map((v: any) => (
            <div
              key={v.id}
              className={"garage-card " + (v.id === vehicle ? "active" : "")}
            >
              <CarFront size={48} strokeWidth={1} />
              <div>
                <span className="eyebrow muted">{v.brand}</span>
                <h2>
                  {v.model} {v.year}
                </h2>
                <p>{v.version}</p>
                <button
                  className={v.id === vehicle ? "secondary" : "primary"}
                  onClick={() =>
                    saveGarage(garage, v.id).catch((e: any) =>
                      notify(e.message, true),
                    )
                  }
                >
                  {v.id === vehicle ? (
                    <>
                      <Check size={16} />
                      Vehículo activo
                    </>
                  ) : (
                    "Usar este vehículo"
                  )}
                </button>
              </div>
              <button
                aria-label="Eliminar vehículo"
                className="icon-button"
                onClick={() => {
                  if (confirm("¿Quitar este auto de tu garaje?"))
                    saveGarage(
                      garage.filter((n: number) => n !== v.id),
                      vehicle === v.id ? null : vehicle,
                    ).catch((e: any) => notify(e.message, true));
                }}
              >
                <Trash2 size={17} />
              </button>
            </div>
          ))}
      </div>
      {!garage.length && (
        <Empty
          title="Tu garaje está listo para tu primer auto"
          text="Selecciona la marca, modelo, año y versión arriba."
        />
      )}
      {vehicle && (
        <button
          className="text-button"
          onClick={() => saveGarage(garage, null)}
        >
          Explorar catálogo sin filtrar por vehículo
        </button>
      )}
    </div>
  );
}
