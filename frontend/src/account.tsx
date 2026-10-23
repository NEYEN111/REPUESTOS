import React, { useState } from "react";
import {
  Link,
  Navigate,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  ArrowRight,
  CarFront,
  Package,
  UserRound,
  MapPin,
  FileText,
  LogOut,
  ShieldCheck,
  CheckCircle2,
  BookOpen,
  Trash2,
} from "lucide-react";
import {
  api,
  useStore,
  useLoad,
  Loading,
  ErrorBox,
  Empty,
  Field,
  Badge,
  money,
  date,
  Modal,
  Pagination,
} from "./lib";
import { Logo, Garage } from "./store";
import { UbigeoFields } from "./commerce";
export function Login() {
  const { user: currentUser, config, notify } = useStore(),
    [accountLogin, setAccountLogin] = useState(false),
    [register, setRegister] = useState(false),
    [d, setD] = useState<any>({
      email: "",
      password: "",
      name: "",
      phone: "",
      consent: false,
    }),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [params] = useSearchParams();
  const demo = config.DEMO_ACCESS_ENABLED && !accountLogin;
  const enter = (user: any) => {
    const next = params.get("next");
    const staff = ["admin", "empleado"].includes(user.role);
    const safeNext = next && next.startsWith("/") && !next.startsWith("//") && !next.includes(String.fromCharCode(92)) && !next.includes("ingresar") && (staff || !/^\/(admin|gestion)(\/|$)/.test(next));
    window.location.assign(safeNext ? next : staff ? "/gestion" : "/cuenta");
  };
  const enterDemo = async (role: "admin" | "cliente") => {
    setBusy(true);
    setError("");
    try {
      enter(await api("/auth/demo", { method: "POST", body: { role } }));
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  };
  const submit = async (e: any) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await api(register ? "/auth/register" : "/auth/login", {
        method: "POST",
        body: d,
      });
      notify(register ? "Tu cuenta está lista." : "Sesión iniciada.");
      enter(user);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  if (currentUser) return <Navigate to={["admin", "empleado"].includes(currentUser.role) ? "/gestion" : "/cuenta"} replace />;
  return (
    <div className="login-wrap">
      <div className="login-story">
        <Logo />
        <div>
          <div className="eyebrow">CADA PIEZA CUENTA</div>
          <h1>Tu auto.<br />Tu tienda.<br />Tu espacio.</h1>
          <p>Compra, consulta tus pedidos o gestiona la tienda desde tu cuenta.</p>
        </div>
        <span><ShieldCheck size={18} />Repuestos para seguir</span>
      </div>
      <div className="login-form">
        <div className="eyebrow muted">{demo ? "DEMOSTRACIÓN DEL PROYECTO" : "BIENVENIDO A TU ESPACIO"}</div>
        <h2>{demo ? "Elige tu espacio" : register ? "Crea tu cuenta" : "Qué bueno verte de nuevo"}</h2>
        <p>{demo ? "Accede sin contraseña para recorrer la tienda o revisar su gestión." : register ? "Tus próximos kilómetros empiezan aquí." : "Ingresa con tu correo y contraseña. Verás las opciones disponibles para tu cuenta."}</p>
        {demo ? <div className="demo-access" aria-busy={busy}>
          <button className="demo-access-card" disabled={busy} onClick={() => enterDemo("admin")}>
            <ShieldCheck size={26} aria-hidden="true" />
            <span><strong>Entrar como administrador</strong><small>Inventario, pronósticos y agentes</small></span>
            <ArrowRight size={20} aria-hidden="true" />
          </button>
          <button className="demo-access-card secondary" disabled={busy} onClick={() => enterDemo("cliente")}>
            <UserRound size={26} aria-hidden="true" />
            <span><strong>Entrar como cliente</strong><small>Catálogo, asistente y pedidos</small></span>
            <ArrowRight size={20} aria-hidden="true" />
          </button>
          <p className="demo-access-note" role="status">{busy ? "Abriendo tu espacio..." : "Acceso temporal para la evaluación académica. Las operaciones se guardan en las cuentas de demostración."}</p>
          <ErrorBox message={error} />
          <button className="text-link demo-account-link" disabled={busy} onClick={() => { setAccountLogin(true); setError(""); }}>Ingresar con mi cuenta</button>
        </div> : <>
        <form onSubmit={submit}>
          {register && (
            <>
              <Field
                label="Nombres y apellidos"
                required
                value={d.name}
                onChange={(e: any) => setD({ ...d, name: e.target.value })}
              />
              <Field
                label="Celular"
                required
                pattern="9[0-9]{8}"
                value={d.phone}
                onChange={(e: any) => setD({ ...d, phone: e.target.value })}
              />
            </>
          )}
          <Field
            label="Correo electrónico"
            type="email"
            required
            autoComplete="username"
            value={d.email}
            onChange={(e: any) => setD({ ...d, email: e.target.value })}
          />
          <Field
            label="Contraseña"
            type="password"
            required
            minLength={8}
            autoComplete={register ? "new-password" : "current-password"}
            value={d.password}
            onChange={(e: any) => setD({ ...d, password: e.target.value })}
          />
          {register && (
            <label className="check consent">
              <input
                type="checkbox"
                required
                checked={d.consent}
                onChange={(e) => setD({ ...d, consent: e.target.checked })}
              />
              <span>
                Acepto el tratamiento de mis datos según la{" "}
                <Link to="/privacidad">política de privacidad</Link>.
              </span>
            </label>
          )}
          <ErrorBox message={error} />
          <button disabled={busy}>
            {busy ? "Un momento..." : register ? "Crear cuenta" : "Ingresar"}
            <ArrowRight size={18} />
          </button>
        </form>
        <div className="login-switch">
            {register ? "¿Ya tienes cuenta?" : "¿Es tu primera visita?"}
            <button
              onClick={() => {
                setRegister(!register);
                setError("");
              }}
            >
              {register ? "Inicia sesión" : "Crea una cuenta"}
            </button>
          </div>
        {config.DEMO_ACCESS_ENABLED && <button className="text-link demo-account-link" onClick={() => { setAccountLogin(false); setRegister(false); setError(""); }}>Volver al acceso de demostración</button>}
        </>}
        <Link className="text-link" to="/">
          Volver a la tienda
        </Link>
      </div>
    </div>
  );
}

function AccountHistory({ load, quote = false }: any) {
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [sort, setSort] = useState("recent"),
    [page, setPage] = useState(1);
  const records = load.data || [];
  const filtered = records.filter((r: any) =>
    r.code.toLowerCase().includes(query.trim().toLowerCase()) && (!status || r.status === status)
  ).sort((a: any, b: any) => sort === "amount" ? b.total_cents - a.total_cents : sort === "oldest" ? a.id - b.id : b.id - a.id);
  const pages = Math.max(1, Math.ceil(filtered.length / 10));
  const current = Math.min(page, pages);
  return <section className="panel">
    <h2>{quote ? "Mis cotizaciones" : "Mis pedidos"}</h2>
    <div className="history-filters">
      <Field label="Buscar por código" value={query} placeholder={quote ? "COT-..." : "PED-..."} onChange={(e: any) => { setQuery(e.target.value); setPage(1); }} />
      <Field label="Estado"><select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
        <option value="">Todos los estados</option>
        {Array.from(new Set<string>(records.map((r: any) => r.status))).map(s => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}
      </select></Field>
      <Field label="Ordenar"><select value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }}>
        <option value="recent">Más recientes</option><option value="oldest">Más antiguos</option><option value="amount">Mayor importe</option>
      </select></Field>
    </div>
    {load.loading ? <Loading /> : load.error ? <ErrorBox message={load.error} /> : !filtered.length ? <Empty title={records.length ? "No hay coincidencias" : quote ? "Aún no tienes cotizaciones" : "Aún no tienes pedidos"} text={records.length ? "Prueba con otro código o estado." : "Explora el catálogo y agrega productos al carrito."} /> : <>
      <table><thead><tr><th>{quote ? "Cotización" : "Pedido"}</th><th>{quote ? "Vence" : "Fecha"}</th><th>Estado</th><th>Total</th><th /></tr></thead>
        <tbody>{filtered.slice((current - 1) * 10, current * 10).map((r: any) => <tr key={r.id}>
          <td><b>{r.code}</b></td><td>{date(quote ? r.expires_at : r.created_at)}</td><td><Badge>{r.status}</Badge></td><td>{money(r.total_cents)}</td>
          <td><Link className="table-link" to={(quote ? "/cotizacion/" : "/pedido/") + r.id}>{quote ? "Ver cotización" : "Ver pedido"}<ArrowRight size={14} /></Link></td>
        </tr>)}</tbody>
      </table>
      <Pagination page={current} pages={pages} total={filtered.length} onChange={setPage} />
    </>}
  </section>;
}

export function Account() {
  const { user, setUser, notify } = useStore(),
    nav = useNavigate(),
    [tab, setTab] = useState(["admin", "empleado"].includes(user?.role) ? "perfil" : "pedidos"),
    load = useLoad(user ? "/account" : null),
    orders = useLoad(user ? "/account/orders" : null),
    quotes = useLoad(user ? "/account/quotes" : null),
    [address, setAddress] = useState<any>(null);
  if (!user)
    return (
      <div className="container page">
        <Empty
          title="Tu cuenta te espera"
          text="Inicia sesión para ver tus pedidos y vehículos."
          action={
            <Link className="button" to="/ingresar">
              Ingresar
            </Link>
          }
        />
      </div>
    );
  if (load.loading) return <Loading />;
  if (load.error) return <ErrorBox message={load.error} />;
  const a = load.data;
  const save = async (e: any) => {
    e.preventDefault();
    try {
      await api("/account", { method: "PUT", body: a });
      setUser({ ...user, name: a.name, phone: a.phone });
      notify("Tus datos se guardaron.");
    } catch (e: any) {
      notify(e.message, true);
    }
  };
  const tabs = [
    ["pedidos", "Mis pedidos", Package],
    ["cotizaciones", "Cotizaciones", FileText],
    ["garaje", "Mi garaje", CarFront],
    ["direcciones", "Direcciones", MapPin],
    ["perfil", "Perfil y facturación", UserRound],
  ];
  return (
    <div className="container page">
      <div className="page-title">
        <div>
          <div className="eyebrow muted">MI CUENTA</div>
          <h1>Hola, {user.name.split(" ")[0]}</h1>
          <p>Todo lo que necesitas, a la mano.</p>
        </div>
      </div>
      <div className="account-layout">
        <aside className="account-nav">
          {tabs.map(([key, label, Icon]: any) => (
            <button
              key={key}
              className={tab === key ? "active" : ""}
              onClick={() => setTab(key)}
            >
              <Icon size={18} />
              {label}
            </button>
          ))}
          <button
            onClick={async () => {
              await api("/auth/logout", { method: "POST" });
              setUser(null);
              nav("/");
            }}
          >
            <LogOut size={18} />
            Cerrar sesión
          </button>
        </aside>
        <div>
          {tab === "pedidos" && <AccountHistory key="orders" load={orders} />}
          {tab === "cotizaciones" && <AccountHistory key="quotes" load={quotes} quote />}
          {tab === "garaje" && (
            <div className="embedded-garage">
              <Garage />
            </div>
          )}
          {tab === "direcciones" && (
            <section className="panel">
              <div className="section-title">
                <h2>Mis direcciones</h2>
                <button
                  className="small"
                  onClick={() =>
                    setAddress({
                      label: "",
                      street: "",
                      ubigeo: "",
                      reference: "",
                    })
                  }
                >
                  Agregar dirección
                </button>
              </div>
              {a.addresses.length ? (
                a.addresses.map((d: any) => (
                  <div className="address-card" key={d.id}>
                    <MapPin />
                    <div>
                      <h3>{d.label}</h3>
                      <p>
                        {d.street}
                        <br />
                        {d.reference}
                      </p>
                    </div>
                    <button
                      className="icon-button"
                      aria-label="Eliminar dirección"
                      onClick={async () => {
                        if (confirm("¿Eliminar esta dirección?")) {
                          await api("/account/addresses/" + d.id, {
                            method: "DELETE",
                          });
                          load.reload();
                        }
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))
              ) : (
                <Empty title="Agrega tu primera dirección" />
              )}
            </section>
          )}
          {tab === "perfil" && (
            <form className="panel" onSubmit={save}>
              <h2>Perfil y facturación</h2>
              <div className="form-grid">
                <Field
                  label="Nombres y apellidos"
                  required
                  value={a.name}
                  onChange={(e: any) =>
                    load.setData({ ...a, name: e.target.value })
                  }
                />
                <Field label="Correo" value={a.email} disabled />
                <Field
                  label="Celular"
                  value={a.phone}
                  onChange={(e: any) =>
                    load.setData({ ...a, phone: e.target.value })
                  }
                />
                <Field
                  label="DNI"
                  pattern="[0-9]{8}"
                  value={a.document}
                  onChange={(e: any) =>
                    load.setData({ ...a, document: e.target.value })
                  }
                />
                <Field
                  label="RUC para facturación"
                  pattern="[0-9]{11}"
                  value={a.billing.ruc || ""}
                  onChange={(e: any) =>
                    load.setData({
                      ...a,
                      billing: { ...a.billing, ruc: e.target.value },
                    })
                  }
                />
                <Field
                  label="Razón social"
                  value={a.billing.name || ""}
                  onChange={(e: any) =>
                    load.setData({
                      ...a,
                      billing: { ...a.billing, name: e.target.value },
                    })
                  }
                />
              </div>
              <button>Guardar cambios</button>
            </form>
          )}
        </div>
      </div>
      {address && (
        <Modal title="Nueva dirección" wide onClose={() => setAddress(null)}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await api("/account/addresses", {
                  method: "POST",
                  body: address,
                });
                setAddress(null);
                load.reload();
                notify("Dirección guardada.");
              } catch (e: any) {
                notify(e.message, true);
              }
            }}
          >
            <Field
              label="Nombre de la dirección"
              placeholder="Casa, trabajo..."
              required
              value={address.label}
              onChange={(e: any) =>
                setAddress({ ...address, label: e.target.value })
              }
            />
            <Field
              label="Dirección"
              required
              value={address.street}
              onChange={(e: any) =>
                setAddress({ ...address, street: e.target.value })
              }
            />
            <UbigeoFields
              value={address.ubigeo}
              onChange={(v: string) => setAddress({ ...address, ubigeo: v })}
            />
            <Field
              label="Referencia"
              value={address.reference}
              onChange={(e: any) =>
                setAddress({ ...address, reference: e.target.value })
              }
            />
            <button>Guardar dirección</button>
          </form>
        </Modal>
      )}
    </div>
  );
}

export function Legal({ missing = false }: any) {
  const { config } = useStore(),
    location = useLocation(),
    privacy = location.pathname === "/privacidad";
  if (missing)
    return (
      <div className="container page">
        <Empty
          title="Esta página no está disponible"
          text="Vuelve al catálogo para encontrar tu repuesto."
          action={
            <Link to="/" className="button">
              Volver al inicio
            </Link>
          }
        />
      </div>
    );
  return (
    <div className="container page legal-page">
      <div className="eyebrow muted">INFORMACIÓN PARA EL CLIENTE</div>
      <h1>{privacy ? "Política de privacidad" : "Términos y condiciones"}</h1>
      <p className="lead">
        {config.name} es una tienda de demostración para un proyecto
        universitario. No realiza ventas, cobros ni envíos reales.
      </p>
      {privacy ? (
        <>
          <h2>Datos que guardamos</h2>
          <p>
            Nombre, correo, teléfono, direcciones, datos de comprobantes,
            vehículos, pedidos, cotizaciones y constancias de ejemplo. También
            registramos búsquedas, vistas de productos y acciones del carrito
            para analizar el funcionamiento de la tienda.
          </p>
          <h2>Uso de la información</h2>
          <p>
            Los datos se utilizan para gestionar las operaciones simuladas y
            preparar conjuntos de datos académicos. Utiliza información ficticia
            en las pruebas.
          </p>
          <h2>Almacenamiento y control</h2>
          <p>
            La aplicación guarda la información en la base de datos local de
            esta laptop. El navegador conserva el carrito y los vehículos de
            invitados. La sesión se mantiene mediante una cookie HTTP protegida
            contra acceso desde scripts.
          </p>
          <h2>Asistente de repuestos</h2>
          <p>
            El asistente utiliza el proveedor LLM configurado para interpretar tus preguntas. Envía el
            texto de la consulta, el contexto reciente y referencias públicas del
            catálogo; no consulta tus documentos, pagos ni direcciones.
            Evita escribir datos personales o claves. La conversación caduca
            después de 24 horas sin actividad y se elimina en la siguiente
            limpieza de la aplicación. Puedes borrarla antes desde
            «Nueva conversación» en el asistente.
          </p>
          <h2>Tus opciones</h2>
          <p>
            Puedes editar tu perfil, quitar vehículos y eliminar direcciones
            desde tu cuenta. Para solicitudes sobre otros datos, contacta al
            responsable del proyecto en {config.email}. Esta política es un
            texto de demostración que debe revisarse antes de cualquier uso
            público.
          </p>
        </>
      ) : (
        <>
          <h2>Catálogo y compatibilidad</h2>
          <p>
            Los precios se muestran en soles e incluyen IGV. Las marcas
            identifican referencias del mercado; el inventario, precios, códigos
            y compatibilidades fueron preparados para fines académicos. Las
            fotos son referenciales. Este catálogo no debe utilizarse para
            instalar piezas sin verificar la ficha técnica del fabricante.
          </p>
          <h2>Pedidos, pagos y reservas</h2>
          <p>
            Al crear un pedido se reserva el stock durante 24 horas. La
            confirmación administrativa del pago descuenta las unidades. La
            cancelación o el vencimiento libera la reserva. Los medios Yape,
            Plin, transferencia y tarjeta son simulados. No ingreses datos
            bancarios reales.
          </p>
          <h2>Entregas y cotizaciones</h2>
          <p>
            El retiro en tienda es gratuito y el envío muestra una tarifa según
            la zona seleccionada. Las cotizaciones duran siete días y no
            reservan stock. Al convertirlas en pedido se verifica la
            disponibilidad.
          </p>
          <h2>Comprobantes y atención</h2>
          <p>
            Las boletas y facturas imprimibles son documentos académicos sin
            validez tributaria. Los reclamos se registran localmente en el{" "}
            <Link to="/reclamaciones">Libro de Reclamaciones</Link> y pueden ser
            atendidos desde administración.
          </p>
        </>
      )}
    </div>
  );
}

export function Complaint() {
  const { config } = useStore(),
    [d, setD] = useState<any>({
      name: "",
      email: "",
      document: "",
      phone: "",
      type: "Reclamo",
      order_code: "",
      detail: "",
      request: "",
      consent: false,
    }),
    [result, setResult] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  if (result)
    return (
      <div className="container page">
        <div className="success-block">
          <CheckCircle2 size={52} />
          <h1>Recibimos tu {d.type.toLowerCase()}</h1>
          <p>
            Código de registro: <b>{result}</b>
          </p>
          <p>
            Tu solicitud quedó guardada y será visible para el administrador del
            proyecto.
          </p>
          <button onClick={() => window.print()}>Imprimir constancia</button>
        </div>
      </div>
    );
  return (
    <div className="container page legal-page">
      <div className="eyebrow muted">TE ESCUCHAMOS</div>
      <h1>Libro de Reclamaciones</h1>
      <p>
        {config.legal_name}
        <br />
        {config.address}
      </p>
      <form
        className="panel"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const r = await api("/complaints", { method: "POST", body: d });
            setResult(r.code);
          } catch (e: any) {
            setError(e.message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2>Datos del consumidor</h2>
        <div className="form-grid">
          {[
            ["name", "Nombres y apellidos"],
            ["email", "Correo electrónico"],
            ["document", "DNI / RUC"],
            ["phone", "Celular"],
          ].map(([k, label]) => (
            <Field
              key={k}
              label={label}
              type={k === "email" ? "email" : "text"}
              required
              value={d[k]}
              onChange={(e: any) => setD({ ...d, [k]: e.target.value })}
            />
          ))}
        </div>
        <h2>Detalle de tu solicitud</h2>
        <div className="form-grid">
          <Field label="Tipo">
            <select
              value={d.type}
              onChange={(e) => setD({ ...d, type: e.target.value })}
            >
              <option>Reclamo</option>
              <option>Queja</option>
            </select>
          </Field>
          <Field
            label="Código de pedido (opcional)"
            value={d.order_code}
            onChange={(e: any) => setD({ ...d, order_code: e.target.value })}
          />
        </div>
        <Field label="¿Qué ocurrió?">
          <textarea
            required
            rows={4}
            value={d.detail}
            onChange={(e) => setD({ ...d, detail: e.target.value })}
          />
        </Field>
        <Field label="¿Qué solución solicitas?">
          <textarea
            required
            rows={3}
            value={d.request}
            onChange={(e) => setD({ ...d, request: e.target.value })}
          />
        </Field>
        <label className="check consent">
          <input
            required
            type="checkbox"
            checked={d.consent}
            onChange={(e) => setD({ ...d, consent: e.target.checked })}
          />
          <span>
            Autorizo el tratamiento de mis datos para atender esta solicitud
            según la <Link to="/privacidad">política de privacidad</Link>.
          </span>
        </label>
        <ErrorBox message={error} />
        <button disabled={busy}>
          {busy ? "Registrando..." : "Registrar solicitud"}
          <ArrowRight size={17} />
        </button>
      </form>
    </div>
  );
}
