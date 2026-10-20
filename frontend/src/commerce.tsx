import React, { useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  ShoppingCart,
  Trash2,
  ArrowRight,
  ArrowLeft,
  ShieldCheck,
  FileText,
  MapPin,
  Truck,
  Check,
  Upload,
  Printer,
  Clock3,
  CheckCircle2,
  Package,
  ChevronRight,
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
  ProductImage,
  Badge,
  Field,
} from "./lib";
export function Cart() {
  const { cart, setCart, notify, vehicle, event, user } = useStore(),
    nav = useNavigate(),
    [busy, setBusy] = useState(false),
    [live, setLive] = useState<any[]>([]),
    [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    Promise.all(
      cart.map((p: any) =>
        api("/products/" + p.id + (vehicle ? "?vehicle=" + vehicle : "")),
      ),
    )
      .then((d) => {
        if (alive) setLive(d);
      })
      .catch((e) => setError(e.message));
    return () => {
      alive = false;
    };
  }, [vehicle, cart.length]);
  const total = cart.reduce(
    (s: number, p: any) =>
      s +
      (live.find((i) => i.id === p.id)?.price_cents ?? p.price_cents) *
        p.quantity,
    0,
  );
  const quote = async () => {
    setBusy(true);
    try {
      const q = await api("/quotes", {
        method: "POST",
        body: {
          items: cart.map((p: any) => ({
            product_id: p.id,
            quantity: p.quantity,
          })),
          customer_name: user?.name || "Cliente",
        },
      });
      localStorage.setItem("quote-token-" + q.id, q.token);
      nav("/cotizacion/" + q.id);
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="container page">
      <div className="breadcrumbs">
        <Link to="/">Inicio</Link>
        <ChevronRight size={12} />
        Carrito
      </div>
      <div className="page-title">
        <div>
          <h1>Tu carrito</h1>
          <p>{cart.length} productos para seguir en movimiento</p>
        </div>
        <Link to="/catalogo" className="text-link">
          <ArrowLeft size={16} />
          Seguir comprando
        </Link>
      </div>
      <ErrorBox message={error} />
      {!cart.length ? (
        <Empty
          title="Tu próximo repuesto está por aquí"
          text="Agrega productos para cotizar o realizar tu pedido."
          action={
            <Link className="button" to="/catalogo">
              Explorar catálogo
              <ArrowRight size={17} />
            </Link>
          }
        />
      ) : (
        <div className="checkout-layout">
          <div>
            <div className="cart-table panel">
              {cart.map((item: any) => {
                const p = live.find((i) => i.id === item.id) || item;
                return (
                  <div className="cart-item" key={p.id}>
                    <Link to={"/producto/" + p.id}>
                      <ProductImage p={p} />
                    </Link>
                    <div>
                      <span className="eyebrow muted">{p.brand}</span>
                      <Link className="cart-name" to={"/producto/" + p.id}>
                        {p.name}
                      </Link>
                      <small>SKU: {p.sku}</small>
                      {p.compatible === false ? (
                        <div className="text-danger">
                          No compatible con tu vehículo activo
                        </div>
                      ) : (
                        <span className="stock">
                          {p.available >= item.quantity
                            ? "Disponible"
                            : "Stock insuficiente"}
                        </span>
                      )}
                    </div>
                    <div className="quantity">
                      <button
                        aria-label="Reducir cantidad"
                        disabled={item.quantity <= 1}
                        onClick={() => {
                          setCart(
                            cart.map((i: any) =>
                              i.id === p.id
                                ? { ...i, quantity: i.quantity - 1 }
                                : i,
                            ),
                          );
                          event("cart_update", {
                            product_id: p.id,
                            payload: { quantity: item.quantity - 1 },
                          });
                        }}
                      >
                        −
                      </button>
                      <span>{item.quantity}</span>
                      <button
                        aria-label="Aumentar cantidad"
                        disabled={item.quantity >= p.available}
                        onClick={() => {
                          setCart(
                            cart.map((i: any) =>
                              i.id === p.id
                                ? { ...i, quantity: i.quantity + 1 }
                                : i,
                            ),
                          );
                          event("cart_update", {
                            product_id: p.id,
                            payload: { quantity: item.quantity + 1 },
                          });
                        }}
                      >
                        +
                      </button>
                    </div>
                    <strong>{money(p.price_cents * item.quantity)}</strong>
                    <button
                      aria-label="Eliminar producto"
                      className="icon-button"
                      onClick={() => {
                        setCart(cart.filter((i: any) => i.id !== p.id));
                        event("cart_remove", { product_id: p.id });
                      }}
                    >
                      <Trash2 size={17} />
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="info-note">
              <ShieldCheck size={22} />
              <span>
                Revisa la compatibilidad antes de comprar. Los productos se
                reservan al crear tu pedido.
              </span>
            </div>
          </div>
          <aside className="order-summary">
            <h2>Resumen de compra</h2>
            <div>
              <span>Productos</span>
              <b>{money(total)}</b>
            </div>
            <div>
              <span>Envío</span>
              <span>Se calcula al finalizar</span>
            </div>
            <hr />
            <div className="total">
              <span>Total</span>
              <strong>{money(total)}</strong>
            </div>
            <small>Incluye IGV · Precios en soles</small>
            <Link to="/checkout" className="button">
              Continuar con la compra
              <ArrowRight size={18} />
            </Link>
            <button className="secondary" disabled={busy} onClick={quote}>
              <FileText size={18} />
              {busy ? "Generando..." : "Guardar cotización"}
            </button>
            <p>
              Tu cotización es válida por 7 días.
              <br />
              Puedes imprimirla y comprar después.
            </p>
            <div className="summary-payments">
              Yape <b>Plin</b> VISA <span>Transferencia</span>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

export function UbigeoFields({ value, onChange }: any) {
  const { data } = useLoad("/ubigeo"),
    [dep, setDep] = useState(""),
    [prov, setProv] = useState("");
  useEffect(() => {
    const row = data?.find((r: any) => r.code === value);
    if (row) {
      setDep(row.department);
      setProv(row.province);
    }
  }, [data, value]);
  return (
    <div className="form-grid three">
      <Field label="Departamento">
        <select
          required
          aria-label="Departamento"
          value={dep}
          onChange={(e) => {
            setDep(e.target.value);
            setProv("");
            onChange("");
          }}
        >
          <option value="">Selecciona</option>
          {[...new Set<string>(data?.map((r: any) => r.department))].map(
            (d) => (
              <option key={d}>{d}</option>
            ),
          )}
        </select>
      </Field>
      <Field label="Provincia">
        <select
          required
          aria-label="Provincia"
          value={prov}
          onChange={(e) => {
            setProv(e.target.value);
            onChange("");
          }}
        >
          <option value="">Selecciona</option>
          {[
            ...new Set<string>(
              data
                ?.filter((r: any) => r.department === dep)
                .map((r: any) => r.province),
            ),
          ].map((d) => (
            <option key={d}>{d}</option>
          ))}
        </select>
      </Field>
      <Field label="Distrito">
        <select
          required
          aria-label="Distrito"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Selecciona</option>
          {data
            ?.filter((r: any) => r.department === dep && r.province === prov)
            .map((d: any) => (
              <option key={d.code} value={d.code}>
                {d.district}
              </option>
            ))}
        </select>
      </Field>
    </div>
  );
}

export function Checkout() {
  const { cart, setCart, user, config, notify } = useStore(),
    nav = useNavigate(),
    [params] = useSearchParams(),
    qid = params.get("quote"),
    [quoted, setQuoted] = useState<any>(null),
    [prices, setPrices] = useState<{ products: any[]; loading: boolean; error: string }>({ products: [], loading: !qid && cart.length > 0, error: '' }),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [key] = useState(() => crypto.randomUUID()),
    [d, setD] = useState<any>({
      customer_name: user?.name || "",
      email: user?.email || "",
      phone: user?.phone || "",
      document: user?.document || "",
      document_type: "boleta",
      business_name: "",
      delivery: "retiro",
      address: "",
      ubigeo: "",
      shipping_zone: config.shipping[0].name,
      payment_method: config.payments[0],
      consent: false,
    });
  const update = (k: string, v: any) => setD({ ...d, [k]: v });
  const productIds = cart.map((p: any) => p.id).join(',');
  useEffect(() => {
    if (qid) return;
    let alive = true;
    setPrices({ products: [], loading: true, error: '' });
    Promise.all(productIds ? productIds.split(',').map(id => api('/products/' + id)) : [])
      .then(products => { if (alive) setPrices({ products, loading: false, error: '' }); })
      .catch(e => { if (alive) setPrices({ products: [], loading: false, error: e.message }); });
    return () => { alive = false; };
  }, [qid, productIds]);
  useEffect(() => {
    if (qid)
      api(
        "/quotes/" +
          qid +
          "?token=" +
          encodeURIComponent(localStorage.getItem("quote-token-" + qid) || ""),
      )
        .then(setQuoted)
        .catch((e) => setError(e.message));
  }, [qid]);
  const items = qid
    ? quoted?.items?.map((i: any) => ({ ...i, id: i.product_id })) || []
    : cart.map((item: any) => ({ ...item, ...prices.products.find(p => p.id === item.id), quantity: item.quantity }));
  const subtotal = items.reduce(
      (s: number, p: any) => s + p.price_cents * p.quantity,
      0,
    ),
    shipping =
      d.delivery === "retiro"
        ? 0
        : config.shipping.find((z: any) => z.name === d.shipping_zone)?.cents ||
          0;
  const submit = async (e: any) => {
    e.preventDefault();
    setError("");
    if (!d.consent) {
      setError("Acepta los términos y la política de privacidad.");
      return;
    }
    setBusy(true);
    try {
      const o = await api("/orders", {
        method: "POST",
        body: {
          ...d,
          idempotency_key: key,
          items: items.map((p: any) => ({
            product_id: p.id,
            quantity: p.quantity,
          })),
          quote_id: qid ? +qid : undefined,
          quote_token: qid
            ? localStorage.getItem("quote-token-" + qid)
            : undefined,
        },
      });
      localStorage.setItem("order-token-" + o.id, o.token);
      if (!qid) setCart([]);
      notify("Pedido creado. Tu stock está reservado por 24 horas.");
      nav("/pedido/" + o.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  if (!qid && prices.loading) return <div className="container page"><Loading /></div>;
  if (!qid && prices.error) return <div className="container page"><ErrorBox message={prices.error} /><Link className="button" to="/carrito">Volver al carrito</Link></div>;
  return (
    <div className="container page">
      <div className="checkout-steps">
        <span className="done">
          <Check size={15} />
          Carrito
        </span>
        <i />
        <span className="active">
          2 <b>Datos y entrega</b>
        </span>
        <i />
        <span>3 Confirmación y pago</span>
      </div>
      <div className="page-title">
        <div>
          <h1>Finaliza tu pedido</h1>
          <p>Solo falta un paso para tener todo listo.</p>
        </div>
        <span className="secure-note">
          <ShieldCheck size={18} />
          Compra de demostración · Sin cobros reales
        </span>
      </div>
      {!items.length && !qid ? (
        <Empty
          title="Tu carrito está vacío"
          action={
            <Link to="/catalogo" className="button">
              Ver productos
            </Link>
          }
        />
      ) : (
        <form className="checkout-layout" onSubmit={submit}>
          <div>
            <section className="panel checkout-section">
              <h2>
                <span>01</span>Datos del cliente
              </h2>
              {!user && (
                <p className="hint">
                  ¿Ya tienes cuenta?{" "}
                  <Link to="/ingresar?next=/checkout">Inicia sesión</Link> o
                  continúa como invitado.
                </p>
              )}
              <div className="form-grid">
                <Field
                  label="Nombres y apellidos"
                  required
                  value={d.customer_name}
                  onChange={(e: any) => update("customer_name", e.target.value)}
                />
                <Field
                  label="Correo electrónico"
                  required
                  type="email"
                  value={d.email}
                  onChange={(e: any) => update("email", e.target.value)}
                />
                <Field
                  label="Celular"
                  required
                  pattern="(\+?51)?9[0-9]{8}"
                  placeholder="987654321"
                  value={d.phone}
                  onChange={(e: any) => update("phone", e.target.value)}
                />
              </div>
            </section>
            <section className="panel checkout-section">
              <h2>
                <span>02</span>¿Cómo quieres recibirlo?
              </h2>
              <div className="choice-grid">
                <label
                  className={
                    "choice " + (d.delivery === "retiro" ? "selected" : "")
                  }
                >
                  <input
                    type="radio"
                    name="delivery"
                    value="retiro"
                    checked={d.delivery === "retiro"}
                    onChange={() => update("delivery", "retiro")}
                  />
                  <MapPin />
                  <span>
                    <b>Retiro en tienda</b>
                    <small>Gratis · Surquillo, Lima</small>
                  </span>
                </label>
                <label
                  className={
                    "choice " + (d.delivery === "envio" ? "selected" : "")
                  }
                >
                  <input
                    type="radio"
                    name="delivery"
                    value="envio"
                    checked={d.delivery === "envio"}
                    onChange={() => update("delivery", "envio")}
                  />
                  <Truck />
                  <span>
                    <b>Envío a domicilio / agencia</b>
                    <small>Desde {money(config.shipping[0].cents)}</small>
                  </span>
                </label>
              </div>
              {d.delivery === "retiro" ? (
                <div className="pickup-address">
                  <MapPin size={18} />
                  <span>
                    <b>{config.address}</b>
                    <small>
                      {config.hours} · Espera la confirmación de recojo.
                    </small>
                  </span>
                </div>
              ) : (
                <>
                  <UbigeoFields
                    value={d.ubigeo}
                    onChange={(v: string) => update("ubigeo", v)}
                  />
                  <Field
                    label="Dirección y referencia"
                    required
                    value={d.address}
                    onChange={(e: any) => update("address", e.target.value)}
                  />
                  <Field label="Zona de envío">
                    <select
                      value={d.shipping_zone}
                      onChange={(e) => update("shipping_zone", e.target.value)}
                    >
                      {config.shipping.map((s: any) => (
                        <option key={s.name}>{s.name}</option>
                      ))}
                    </select>
                  </Field>
                  <p className="hint">
                    {
                      config.shipping.find(
                        (s: any) => s.name === d.shipping_zone,
                      )?.days
                    }{" "}
                    · {money(shipping)}
                  </p>
                </>
              )}
            </section>
            <section className="panel checkout-section">
              <h2>
                <span>03</span>Comprobante
              </h2>
              <div className="radio-row">
                {["boleta", "factura"].map((v) => (
                  <label className="check" key={v}>
                    <input
                      name="document_type"
                      type="radio"
                      checked={d.document_type === v}
                      onChange={() =>
                        setD({ ...d, document_type: v, document: "" })
                      }
                    />
                    {v === "boleta" ? "Boleta de venta" : "Factura"}
                  </label>
                ))}
              </div>
              <div className="form-grid">
                <Field
                  label={
                    d.document_type === "boleta"
                      ? "DNI (8 dígitos)"
                      : "RUC (11 dígitos)"
                  }
                  required
                  inputMode="numeric"
                  pattern={
                    d.document_type === "boleta" ? "[0-9]{8}" : "[0-9]{11}"
                  }
                  maxLength={d.document_type === "boleta" ? 8 : 11}
                  value={d.document}
                  onChange={(e: any) => update("document", e.target.value)}
                />
                {d.document_type === "factura" && (
                  <Field
                    label="Razón social"
                    required
                    value={d.business_name}
                    onChange={(e: any) =>
                      update("business_name", e.target.value)
                    }
                  />
                )}
              </div>
            </section>
            <section className="panel checkout-section">
              <h2>
                <span>04</span>Forma de pago
              </h2>
              <div className="payment-options">
                {config.payments.map((v: string) => (
                  <label
                    key={v}
                    className={
                      "payment-choice " +
                      (d.payment_method === v ? "selected" : "")
                    }
                  >
                    <input
                      type="radio"
                      name="payment_method"
                      checked={d.payment_method === v}
                      onChange={() => update("payment_method", v)}
                    />
                    <b>{v}</b>
                  </label>
                ))}
              </div>
              <p className="hint">
                {["Yape", "Plin", "Transferencia"].includes(d.payment_method)
                  ? "Después de crear el pedido podrás adjuntar tu constancia. Un administrador verificará el pago."
                  : "El pago será simulado y verificado por el administrador."}
              </p>
            </section>
          </div>
          <aside className="order-summary">
            <h2>Tu pedido</h2>
            {items.map((p: any) => (
              <div className="mini-item" key={p.id}>
                <span>
                  {p.quantity} × {p.name}
                </span>
                <b>{money(p.price_cents * p.quantity)}</b>
              </div>
            ))}
            <hr />
            <div>
              <span>Subtotal</span>
              <b>{money(subtotal)}</b>
            </div>
            <div>
              <span>
                {d.delivery === "retiro" ? "Retiro en tienda" : "Envío"}
              </span>
              <b>{shipping ? money(shipping) : "Gratis"}</b>
            </div>
            <div className="total">
              <span>Total</span>
              <strong>{money(subtotal + shipping)}</strong>
            </div>
            <small>Incluye IGV</small>
            <label className="check consent">
              <input
                required
                type="checkbox"
                checked={d.consent}
                onChange={(e) => update("consent", e.target.checked)}
              />
              <span>
                Acepto los{" "}
                <Link to="/terminos" target="_blank">
                  términos
                </Link>{" "}
                y el tratamiento de mis datos según la{" "}
                <Link to="/privacidad" target="_blank">
                  política de privacidad
                </Link>
                .
              </span>
            </label>
            <ErrorBox message={error} />
            <button disabled={busy || !items.length}>
              {busy ? "Creando pedido..." : "Crear pedido"}
              <ArrowRight size={18} />
            </button>
            <p>
              <Clock3 size={14} /> Reservamos tu stock por 24 horas.
            </p>
          </aside>
        </form>
      )}
    </div>
  );
}

export function Order({ orderId, admin = false, onChange }: any) {
  const { id: param } = useParams(),
    id = orderId || param,
    { config, notify } = useStore();
  const token = localStorage.getItem("order-token-" + id) || "",
    load = useLoad("/orders/" + id + "?token=" + encodeURIComponent(token)),
    [file, setFile] = useState<File | null>(null),
    [preview, setPreview] = useState(""),
    [busy, setBusy] = useState(false),
    [note, setNote] = useState(""),
    [tracking, setTracking] = useState("");
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );
  const act = async (path: string, body: any, method = "POST") => {
    setBusy(true);
    try {
      await api(path, { method, body });
      load.reload();
      onChange?.();
      notify("Pedido actualizado.");
    } catch (e: any) {
      notify(e.message, true);
    } finally {
      setBusy(false);
    }
  };
  if (load.loading) return <Loading />;
  if (load.error) return <ErrorBox message={load.error} />;
  const o = load.data;
  const upload = async () => {
    const fd = new FormData();
    if (file) fd.append("file", file);
    await act(
      "/orders/" + id + "/payment?token=" + encodeURIComponent(token),
      fd,
    );
  };
  const next: any = {
    pagado: "preparando",
    preparando: o.delivery === "retiro" ? "listo para recojo" : "enviado",
    enviado: "entregado",
    "listo para recojo": "entregado",
  };
  return (
    <div className={admin ? "order-admin" : "container page"}>
      <div className="page-title">
        <div>
          <div className="eyebrow muted">
            {admin ? "GESTIÓN DE PEDIDO" : "GRACIAS POR ELEGIR " + config.name}
          </div>
          <h1>Pedido {o.code}</h1>
          <p>
            {date(o.created_at)} · <Badge>{o.status}</Badge>
          </p>
        </div>
        <button className="secondary no-print" onClick={() => window.print()}>
          <Printer size={17} />
          Imprimir comprobante
        </button>
      </div>
      <div className="order-status-banner">
        <Package size={30} />
        <div>
          <h3>
            {o.status === "pendiente de pago"
              ? "Tu pedido está reservado"
              : o.status === "pago por verificar"
                ? "Estamos verificando tu pago"
                : o.status === "listo para recojo"
                  ? "Tu pedido está listo para recoger"
                  : o.status === "entregado"
                    ? "Pedido entregado"
                    : "Tu pedido: " + o.status}
          </h3>
          <p>
            {["pendiente de pago", "pago por verificar"].includes(o.status)
              ? "Reserva válida hasta " +
                new Date(o.expires_at).toLocaleString("es-PE", {
                  timeZone: "America/Lima",
                }) +
                " · " +
                o.payment_method
              : o.delivery === "retiro"
                ? "Retiro en tienda · " + config.address
                : "Envío · " + o.address}
            {o.shipment?.carrier ? " · Agencia: " + o.shipment.carrier : ""}
            {o.tracking ? " · Seguimiento: " + o.tracking : ""}
            {o.shipment?.expected_at && o.status !== 'entregado' ? " · Fecha prevista: " + date(o.shipment.expected_at) : ""}
          </p>
        </div>
      </div>
      <div className="checkout-layout">
        <div>
          <section className="panel">
            <h2>Productos del pedido</h2>
            {o.items.map((p: any) => (
              <div className="order-item" key={p.id}>
                <ProductImage p={p} />
                <div>
                  <b>{p.name}</b>
                  <small>
                    {p.sku} · Cantidad: {p.quantity}
                  </small>
                </div>
                <strong>{money(p.price_cents * p.quantity)}</strong>
              </div>
            ))}
          </section>
          <section className="panel">
            <h2>Seguimiento</h2>
            <div className="timeline">
              {o.history.map((h: any) => (
                <div key={h.id}>
                  <span />
                  <div>
                    <b>{h.status}</b>
                    <small>
                      {new Date(h.created_at).toLocaleString("es-PE", {
                        timeZone: "America/Lima",
                      })}
                    </small>
                    <p>{h.note}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
          <section className="panel">
            <div className="form-grid">
              <div>
                <h3>Cliente</h3>
                <p>
                  {o.customer_name}
                  <br />
                  {o.email}
                  <br />
                  {o.phone}
                </p>
              </div>
              <div>
                <h3>
                  {o.document_type === "factura"
                    ? "Factura"
                    : "Boleta de venta"}
                </h3>
                <p>
                  {o.document_type === "factura" ? "RUC" : "DNI"}: {o.document}
                  <br />
                  {o.business_name}
                </p>
              </div>
            </div>
            <p className="hint">
              Comprobante académico de demostración. Sin validez tributaria.
            </p>
          </section>
        </div>
        <aside>
          <section className="order-summary">
            <h2>Resumen del pedido</h2>
            <div>
              <span>Base imponible</span>
              <b>{money(o.base_cents)}</b>
            </div>
            <div>
              <span>IGV</span>
              <b>{money(o.tax_cents)}</b>
            </div>
            <div>
              <span>Envío (incluido)</span>
              <b>{money(o.shipping_cents)}</b>
            </div>
            <hr />
            <div className="total">
              <span>Total</span>
              <strong>{money(o.total_cents)}</strong>
            </div>
            <div>
              <span>Medio de pago</span>
              <b>{o.payment_method}</b>
            </div>
            <div>
              <span>Estado del pago</span>
              <Badge>{o.payment.status}</Badge>
            </div>
          </section>
          {o.payment.note && <div className="info-note">{o.payment.note}</div>}
          {!admin && o.status === "pendiente de pago" && (
            <section className="panel payment-upload no-print">
              <h2>Completa tu pago</h2>
              <p>Operación simulada para el proyecto académico.</p>
              {["Yape", "Plin"].includes(o.payment_method) && (
                <div className="payment-destination">
                  <b>{o.payment_method}</b>
                  <strong>{config.phone}</strong>
                  <small>{config.name} · Datos de ejemplo</small>
                </div>
              )}
              {o.payment_method === "Transferencia" && (
                <div className="info-note">{config.bank_account}</div>
              )}
              {!["Pago en tienda", "Tarjeta simulada"].includes(
                o.payment_method,
              ) && (
                <label className="upload-area">
                  <Upload size={25} />
                  <b>{file ? file.name : "Adjuntar constancia de pago"}</b>
                  <small>JPG, PNG o WebP · Máximo 8 MB</small>
                  <input
                    aria-label="Constancia de pago"
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) {
                        setFile(f);
                        setPreview(URL.createObjectURL(f));
                      }
                    }}
                  />
                </label>
              )}
              {preview && (
                <img
                  className="voucher-preview"
                  src={preview}
                  alt="Vista previa de constancia"
                />
              )}
              <button
                disabled={
                  busy ||
                  (!file &&
                    !["Pago en tienda", "Tarjeta simulada"].includes(
                      o.payment_method,
                    ))
                }
                onClick={upload}
              >
                {busy
                  ? "Enviando..."
                  : o.payment_method === "Pago en tienda"
                    ? "Solicitar pago en tienda"
                    : o.payment_method === "Tarjeta simulada"
                      ? "Simular pago con tarjeta"
                      : "Enviar para verificación"}
                <ArrowRight size={17} />
              </button>
            </section>
          )}
          {o.payment.voucher && (
            <section className="panel">
              <h3>Constancia adjunta</h3>
              <a
                href={
                  "/api/orders/" +
                  id +
                  "/voucher?token=" +
                  encodeURIComponent(token)
                }
                target="_blank"
                rel="noreferrer"
              >
                <img
                  className="voucher-preview"
                  src={
                    "/api/orders/" +
                    id +
                    "/voucher?token=" +
                    encodeURIComponent(token)
                  }
                  alt="Constancia de pago"
                />
              </a>
            </section>
          )}
          {admin && (
            <section className="panel no-print">
              <h3>Acciones del pedido</h3>
              {o.status === "pago por verificar" && (
                <>
                  <Field
                    label="Observación del pago"
                    value={note}
                    onChange={(e: any) => setNote(e.target.value)}
                  />
                  <button
                    disabled={busy}
                    onClick={() =>
                      act("/admin/orders/" + id + "/verify", {
                        accepted: true,
                        note,
                      })
                    }
                  >
                    <Check size={17} />
                    Confirmar pago
                  </button>
                  <button
                    className="danger secondary"
                    disabled={busy || !note.trim()}
                    onClick={() => {
                      if (
                        confirm(
                          "¿Rechazar este pago y solicitar una nueva constancia?",
                        )
                      )
                        act("/admin/orders/" + id + "/verify", {
                          accepted: false,
                          note,
                        });
                    }}
                  >
                    Rechazar pago
                  </button>
                </>
              )}
              {next[o.status] && (
                <Link className="button" to={"/gestion/envios?pedido=" + id}>Gestionar preparación y entrega<ArrowRight size={16}/></Link>
              )}
              {!next[o.status] && o.status !== "pago por verificar" && (
                <p className="hint">No hay cambios de estado disponibles.</p>
              )}
            </section>
          )}
          {["pendiente de pago", "pago por verificar"].includes(o.status) && (
            <button
              className="text-button danger no-print"
              disabled={busy}
              onClick={() => {
                if (
                  confirm(
                    "¿Cancelar el pedido y liberar los productos reservados?",
                  )
                )
                  act("/orders/" + id + "/cancel", { token });
              }}
            >
              Cancelar pedido
            </button>
          )}
        </aside>
      </div>
    </div>
  );
}

export function Quote() {
  const { id } = useParams(),
    { config } = useStore(),
    token = localStorage.getItem("quote-token-" + id) || "",
    load = useLoad("/quotes/" + id + "?token=" + encodeURIComponent(token));
  if (load.loading) return <Loading />;
  if (load.error) return <ErrorBox message={load.error} />;
  const q = load.data;
  return (
    <div className="container page quote-page">
      <div className="page-title">
        <div>
          <div className="eyebrow muted">{config.name} · COTIZACIÓN</div>
          <h1>{q.code}</h1>
          <p>
            Creada el {date(q.created_at)} · <Badge>{q.status}</Badge>
          </p>
        </div>
        <button className="secondary no-print" onClick={() => window.print()}>
          <Printer size={18} />
          Imprimir cotización
        </button>
      </div>
      <section className="panel">
        <div className="quote-meta">
          <div>
            <h3>{config.legal_name}</h3>
            <p>
              {config.address}
              <br />
              {config.phone}
            </p>
          </div>
          <div>
            <h3>Preparada para {q.customer_name}</h3>
            <p>
              Vigencia hasta {date(q.expires_at)}
              <br />
              Precios incluyen IGV.
            </p>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Producto / SKU</th>
              <th>Cantidad</th>
              <th>Precio unitario</th>
              <th>Importe</th>
            </tr>
          </thead>
          <tbody>
            {q.items.map((i: any) => (
              <tr key={i.id}>
                <td>
                  <b>{i.name}</b>
                  <small>{i.sku}</small>
                </td>
                <td>{i.quantity}</td>
                <td>{money(i.price_cents)}</td>
                <td>{money(i.price_cents * i.quantity)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="quote-total">
          Total cotizado <strong>{money(q.total_cents)}</strong>
        </div>
        <div className="info-note">
          <Clock3 size={20} />
          Vigencia de 7 días. El stock se verifica y reserva al convertir la
          cotización en pedido. Envío no incluido.
        </div>
      </section>
      <div className="quote-actions no-print">
        <Link className="button secondary" to="/catalogo">
          Seguir explorando
        </Link>
        {q.status === "vigente" && (
          <Link className="button" to={"/checkout?quote=" + q.id}>
            Convertir en pedido
            <ArrowRight size={18} />
          </Link>
        )}
        {q.order_id && (
          <Link className="button" to={"/pedido/" + q.order_id}>
            Ver pedido
          </Link>
        )}
      </div>
    </div>
  );
}
