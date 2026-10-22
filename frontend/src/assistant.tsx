import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowDown, ArrowRight, ArrowUp, CarFront, Check, ChevronDown, CircleHelp, FileText, LoaderCircle, Maximize2, MessageCircle, Minimize2, Plus, RotateCcw, Search, ShoppingBag, ShoppingCart, Square, Truck, Wrench, X } from "lucide-react";
import { api, money, ProductImage, useStore } from "./lib";
import "./assistant.css";

type Product = { id: number; name: string; sku: string; brand: string; category: string; price_cents: number; available: number; compatible: boolean | null; universal: boolean; image: string; thumb: string; oem?: string; specs?: Record<string, string | number> };
type Vehicle = { id: number; brand: string; model: string; year: number; version: string };
type Answer = { reply: string; conversation_id: string; query: string; intent: string; products: Product[]; total: number; actions: { label: string; path: string }[]; vehicle_options: Vehicle[]; vehicle: Vehicle | null; suggestions: string[]; notice: string; mode: string };
type Message = { role: "user" | "assistant"; text: string; time: number; data?: Answer };
const STORAGE = "roda-assistant-v2";
function saved() {
  try {
    const value = JSON.parse(sessionStorage.getItem(STORAGE) || "null");
    if (value && Date.now() - value.updated < 86400000 && Array.isArray(value.messages)) return value;
  } catch {}
  return { messages: [], token: null };
}
function vehicleName(v: Vehicle) { return v.brand + " " + v.model + " · " + v.year + " · " + v.version; }
function Copy({ text }: { text: string }) {
  return <div className="ra-copy">{text.split("\n").filter(Boolean).map((line, i) => <p key={i}>{line.split(/(\*\*[^*]+\*\*)/g).map((part, j) => part.startsWith("**") ? <strong key={j}>{part.slice(2, -2)}</strong> : part)}</p>)}</div>;
}

function VehiclePicker({ apply, close, saving }: { apply: (v: Vehicle) => void; close: () => void; saving: boolean }) {
  const { vehicles, vehicle } = useStore();
  const active = vehicles.find((v: Vehicle) => v.id === vehicle);
  const [brand, setBrand] = useState(active?.brand || "");
  const [model, setModel] = useState(active?.model || "");
  const [year, setYear] = useState(String(active?.year || ""));
  const [version, setVersion] = useState(active?.version || "");
  const unique = (key: keyof Vehicle, filter: (v: Vehicle) => boolean): string[] => [...new Set<string>(vehicles.filter(filter).map((v: Vehicle) => String(v[key])))];
  const selected = vehicles.find((v: Vehicle) => v.brand === brand && v.model === model && String(v.year) === year && v.version === version);
  return <div className="ra-vehicle-picker">
    <div className="ra-picker-heading"><strong>¿Qué auto tienes?</strong><button type="button" onClick={close} aria-label="Cerrar selector de auto"><X size={17} /></button></div>
    <p>La versión permite comprobar la compatibilidad registrada.</p>
    <div className="ra-vehicle-fields">
      <label>Marca<select aria-label="Marca para el asistente" value={brand} onChange={e => { setBrand(e.target.value); setModel(""); setYear(""); setVersion(""); }}><option value="">Seleccionar</option>{unique("brand", () => true).map(x => <option key={x}>{x}</option>)}</select></label>
      <label>Modelo<select aria-label="Modelo para el asistente" value={model} disabled={!brand} onChange={e => { setModel(e.target.value); setYear(""); setVersion(""); }}><option value="">Seleccionar</option>{unique("model", v => v.brand === brand).map(x => <option key={x}>{x}</option>)}</select></label>
      <label>Año<select aria-label="Año para el asistente" value={year} disabled={!model} onChange={e => { setYear(e.target.value); setVersion(""); }}><option value="">Seleccionar</option>{unique("year", v => v.brand === brand && v.model === model).map(x => <option key={x}>{x}</option>)}</select></label>
      <label>Versión<select aria-label="Versión para el asistente" value={version} disabled={!year} onChange={e => setVersion(e.target.value)}><option value="">Seleccionar</option>{unique("version", v => v.brand === brand && v.model === model && String(v.year) === year).map(x => <option key={x}>{x}</option>)}</select></label>
    </div>
    <button className="ra-primary" type="button" disabled={!selected || saving} onClick={() => selected && apply(selected)}>{saving ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />} Usar este auto</button>
  </div>;
}

function ProductResult({ product, checkedVehicle, currentVehicle, chooseVehicle, close }: { product: Product; checkedVehicle?: number; currentVehicle?: number; chooseVehicle: () => void; close: () => void }) {
  const { add, cart, notify } = useStore();
  const [p, setP] = useState(product);
  const [checked, setChecked] = useState(checkedVehicle);
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState(false);
  const inCart = cart.find((item: any) => item.id === p.id)?.quantity || 0;
  const verified = checked === currentVehicle && p.compatible !== null;
  const needsVehicle = !p.universal && !currentVehicle;
  const incompatible = verified && p.compatible === false;
  async function addProduct() {
    if (needsVehicle) { chooseVehicle(); return; }
    setBusy(true);
    try {
      const fresh = await api("/products/" + p.id + (currentVehicle ? "?vehicle=" + currentVehicle : ""));
      setP(fresh); setChecked(currentVehicle);
      if (fresh.compatible === false) throw new Error("Esta pieza no figura como compatible con tu auto. Elige otra opción.");
      if (fresh.available < quantity + inCart) throw new Error("El stock cambió o ya tienes esas unidades en el carrito. Revisa la cantidad.");
      if (add(fresh, quantity, "asistente")) { setAdded(true); window.setTimeout(() => setAdded(false), 2500); }
    } catch (e: any) { notify(e.message, true); }
    finally { setBusy(false); }
  }
  return <article className="ra-product">
    <Link to={"/producto/" + p.id} onClick={close} className="ra-product-photo"><ProductImage p={p} src={p.thumb || p.image} loading="lazy" /></Link>
    <div className="ra-product-body">
      <div className="ra-product-meta"><span>{p.brand}</span><span>{p.sku}</span></div>
      <Link to={"/producto/" + p.id} onClick={close} className="ra-product-name">{p.name}</Link>
      <span className={"ra-fit " + (incompatible ? "bad" : p.universal || (verified && p.compatible) ? "good" : "")}>
        {incompatible ? "No compatible con tu auto" : p.universal ? "Aplicación universal · verifica especificaciones" : verified && p.compatible ? "Compatible según catálogo" : "Compatibilidad por verificar"}
      </span>
      <div className="ra-product-price"><strong>{money(p.price_cents)}</strong><small>Incluye IGV</small><span>{p.available > 0 ? p.available + " disponibles" : "Sin stock"}</span></div>
      <div className="ra-product-controls">
        <label>Cant.<input aria-label={"Cantidad de " + p.sku} type="number" min={1} max={Math.max(1, Math.min(100, p.available - inCart))} value={quantity} onChange={e => setQuantity(Math.max(1, Math.min(100, Number(e.target.value) || 1)))} disabled={busy || !p.available} /></label>
        <button type="button" disabled={busy || !p.available || incompatible} onClick={addProduct}>
          {busy ? <LoaderCircle size={15} className="spin" /> : added ? <Check size={15} /> : <Plus size={15} />}
          {added ? "Agregado" : needsVehicle ? "Elegir auto" : "Agregar"}
        </button>
        {inCart > 0 && <small>{inCart} en carrito</small>}
      </div>
      {(p.oem || Object.keys(p.specs || {}).length > 0) && <details className="ra-product-details"><summary>Ver detalles</summary><dl>{p.oem && <><dt>Referencia OEM</dt><dd>{p.oem}</dd></>}{Object.entries(p.specs || {}).slice(0, 8).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl></details>}
    </div>
  </article>;
}

export function AssistantChat({ vehicleId }: { vehicleId?: number }) {
  const { config, cart, vehicles, garage, saveGarage, user, notify, event } = useStore();
  const location = useLocation(), nav = useNavigate();
  const [initial] = useState(saved);
  const [messages, setMessages] = useState<Message[]>(initial.messages);
  const [token, setToken] = useState<string | null>(initial.token);
  const [open, setOpen] = useState(false), [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [lastQuestion, setLastQuestion] = useState(""), [elapsed, setElapsed] = useState(0);
  const [chooseVehicle, setChooseVehicle] = useState(false), [savingVehicle, setSavingVehicle] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false), [resetBusy, setResetBusy] = useState(false), [quoting, setQuoting] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null), launchRef = useRef<HTMLButtonElement>(null), threadRef = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null), sending = useRef(false);
  const [showBottom, setShowBottom] = useState(false);
  const active = vehicles.find((v: Vehicle) => v.id === vehicleId);
  const productId = /^\/producto\/(\d+)$/.exec(location.pathname)?.[1];
  const lastAnswer = [...messages].reverse().find(m => m.role === "assistant")?.data;
  const count = cart.reduce((sum: number, p: any) => sum + p.quantity, 0);
  const close = () => { setOpen(false); launchRef.current?.focus(); };
  useEffect(() => {
    try { sessionStorage.setItem(STORAGE, JSON.stringify({ token, messages: messages.slice(-20), updated: Date.now() })); } catch {}
  }, [messages, token]);
  useEffect(() => { if (open && !chooseVehicle) inputRef.current?.focus(); }, [open, chooseVehicle]);
  useEffect(() => {
    const closeWithEscape = (e: KeyboardEvent) => { if (e.key === "Escape" && open) close(); };
    document.addEventListener("keydown", closeWithEscape);
    return () => document.removeEventListener("keydown", closeWithEscape);
  }, [open]);
  useEffect(() => {
    const element = threadRef.current;
    if (!element) return;
    if (!messages.length) { element.scrollTop = 0; return; }
    if (messages.at(-1)?.role === "assistant") {
      const answer = element.querySelector(".ra-message:last-child");
      if (answer && !showBottom) element.scrollTop += answer.getBoundingClientRect().top - element.getBoundingClientRect().top - 12;
    } else element.scrollTop = element.scrollHeight;
  }, [messages, busy, open]);
  useEffect(() => {
    if (!busy) { setElapsed(0); return; }
    const interval = window.setInterval(() => setElapsed(v => v + 1), 1000);
    return () => window.clearInterval(interval);
  }, [busy]);
  useEffect(() => () => controller.current?.abort(), []);

  async function send(question: string, retry = false, selectedVehicle = vehicleId) {
    if (!question.trim() || sending.current || quoting || resetBusy) return;
    sending.current = true;
    setError(""); setDraft(""); setBusy(true); setLastQuestion(question); setShowBottom(false);
    if (!retry) setMessages(current => [...current, { role: "user", text: question.trim(), time: Date.now() }]);
    controller.current = new AbortController();
    const timeout = window.setTimeout(() => controller.current?.abort(), 35000);
    try {
      const result: Answer = await api("/assistant/chat", { method: "POST", signal: controller.current.signal, body: {
        message: question.trim(), conversation_id: token, vehicle_id: selectedVehicle ?? null,
        product_id: productId ? Number(productId) : null,
        cart: cart.slice(0, 50).map((p: any) => ({ product_id: p.id, quantity: p.quantity })),
      } });
      setToken(result.conversation_id);
      setMessages(current => [...current, { role: "assistant", text: result.reply, data: result, time: Date.now() }]);
      if (result.intent === "search" && result.query) event("search", { payload: { query: result.query, source: "asistente", results: result.total } });
    } catch (e: any) {
      setError(e.name === "AbortError" ? "La consulta se detuvo. Puedes reintentarlo o buscar en el catálogo." : e.message);
    } finally {
      window.clearTimeout(timeout); sending.current = false; setBusy(false); controller.current = null;
    }
  }
  async function applyVehicle(v: Vehicle) {
    setSavingVehicle(true);
    try {
      await saveGarage([...new Set([...garage, v.id])], v.id);
      setChooseVehicle(false);
      if (messages.length) await send("Ya seleccioné mi auto", false, v.id);
    } catch (e: any) { notify(e.message, true); }
    finally { setSavingVehicle(false); }
  }
  async function reset() {
    setResetBusy(true);
    try {
      if (token) await api("/assistant/conversations/" + token, { method: "DELETE" });
      setMessages([]); setToken(null); setError(""); setDraft(""); setResetConfirm(false);
    } catch (e: any) { setError(e.message); }
    finally { setResetBusy(false); }
  }
  async function quote() {
    if (!cart.length || quoting) return;
    setQuoting(true);
    try {
      const q = await api("/quotes", { method: "POST", body: { items: cart.map((p: any) => ({ product_id: p.id, quantity: p.quantity })), customer_name: user?.name || "Cliente" } });
      localStorage.setItem("quote-token-" + q.id, q.token);
      close(); nav("/cotizacion/" + q.id); notify("Cotización guardada. Tiene vigencia de 7 días.");
    } catch (e: any) { notify(e.message, true); }
    finally { setQuoting(false); }
  }
  return <div className="roda-assistant">
    {open && <section id="roda-assistant-panel" className={"ra-panel" + (expanded ? " ra-expanded" : "")} role="dialog" aria-modal="false" aria-label="Asistente de compras">
      <header className="ra-header">
        <span className="ra-monogram"><MessageCircle size={23} /></span>
        <div className="ra-title"><strong>{config.name}<i>/</i> ASISTENTE</strong><span>Repuestos, dudas y tu próxima compra</span></div>
        <button type="button" aria-label={expanded ? "Reducir asistente" : "Ampliar asistente"} title={expanded ? "Reducir" : "Ampliar"} onClick={() => setExpanded(v => !v)}>{expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}</button>
        <button type="button" aria-label="Nueva conversación" title="Nueva conversación" disabled={busy || !messages.length} onClick={() => setResetConfirm(v => !v)}><RotateCcw size={17} /></button>
        <button type="button" aria-label="Cerrar asistente" onClick={close}><X size={20} /></button>
      </header>
      <div className="ra-context">
        <button className="ra-car" type="button" disabled={busy || savingVehicle} onClick={() => setChooseVehicle(v => !v)} aria-expanded={chooseVehicle}><CarFront size={20} /><span><small>TU AUTO</small><b>{active ? vehicleName(active) : "Seleccionar vehículo"}</b></span><ChevronDown size={15} /></button>
        <Link className="ra-cart-link" to="/carrito" onClick={close} aria-label={"Ver carrito, " + count + " unidades"}><ShoppingCart size={19} /><b>{count}</b></Link>
      </div>
      {resetConfirm && <div className="ra-confirm"><span>¿Borrar esta conversación y empezar de nuevo?</span><div><button disabled={resetBusy} onClick={reset}>{resetBusy ? "Borrando…" : "Borrar conversación"}</button><button className="ra-text-button" onClick={() => setResetConfirm(false)}>Conservar</button></div></div>}
      {chooseVehicle && <VehiclePicker apply={applyVehicle} close={() => setChooseVehicle(false)} saving={savingVehicle} />}
      {productId && <div className="ra-page-hint"><CircleHelp size={14} /> Puedes preguntarme por la pieza que estás viendo.</div>}
      <div className="ra-thread" ref={threadRef} onScroll={e => { const el = e.currentTarget; setShowBottom(el.scrollHeight - el.scrollTop - el.clientHeight > 120); }}>
        {!messages.length && <div className="ra-welcome">
          <span className="ra-eyebrow">LA PIEZA CORRECTA EMPIEZA AQUÍ</span>
          <h2>¿Qué necesita tu auto?</h2>
          <p>Cuéntame qué buscas. Revisamos las opciones y tú eliges cómo continuar.</p>
          <div className="ra-starters">
            {[
              [Search, "Encontrar un repuesto", "Por nombre, marca o código", "Busco pastillas de freno"],
              [Wrench, "Entender una falla", "Orientación para empezar", "Mi auto no arranca. ¿Qué debo revisar?"],
              [Truck, "Envíos y retiro", "Tarifas y puntos de recojo", "¿Cuánto cuesta el envío?"],
              [FileText, "Preparar una cotización", "Guarda tu selección por 7 días", "Quiero preparar una cotización"],
            ].map(([Icon, title, hint, prompt]: any) => <button key={title} type="button" onClick={() => void send(prompt)}><Icon size={19} /><span><b>{title}</b><small>{hint}</small></span><ArrowRight size={14} /></button>)}
          </div>
          <div className="ra-welcome-note"><Check size={16} /><span>Precios y stock consultados en el catálogo de {config.name}.</span></div>
        </div>}
        <div role="log" aria-live="polite" aria-relevant="additions">
          {messages.map((m, index) => <div key={index} className={"ra-message ra-" + m.role}>
            {m.role === "assistant" && <div className="ra-message-label"><span>{config.name}</span><small>{["thehive", "deepseek", "gemini"].includes(m.data?.mode) ? `Asistente · ${m.data.mode === "thehive" ? "TheHive · DeepSeek" : `${m.data.mode[0].toUpperCase()}${m.data.mode.slice(1)}`}` : "Consulta del catálogo"}</small></div>}
            <Copy text={m.text} />
            {m.data?.notice && <p className="ra-notice"><CircleHelp size={15} />{m.data.notice}</p>}
            {!!m.data?.vehicle_options?.length && <div className="ra-vehicle-options">{m.data.vehicle_options.map(v => <button type="button" key={v.id} disabled={busy || savingVehicle} onClick={() => void applyVehicle(v)}><CarFront size={16} /><span>{vehicleName(v)}</span><Check size={15} /></button>)}<button type="button" className="ra-text-button" onClick={() => setChooseVehicle(true)}>Elegir otra versión</button></div>}
            {!!m.data?.products?.length && <div className="ra-results">
              <div className="ra-results-heading"><b>{m.data.products.length} {m.data.products.length === 1 ? "opción" : "opciones"}{m.data.total > m.data.products.length ? " de " + m.data.total : ""}</b><small>Consultado a las {new Date(m.time).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}</small></div>
              {m.data.products.map(p => <ProductResult key={p.id} product={p} checkedVehicle={m.data?.vehicle?.id} currentVehicle={vehicleId} chooseVehicle={() => setChooseVehicle(true)} close={close} />)}
              <small className="ra-recheck">Revisamos el stock y la compatibilidad otra vez al agregar.</small>
            </div>}
            {!!m.data?.actions?.length && <div className="ra-actions">{m.data.actions.map(a => <Link key={a.path} to={a.path} onClick={close}>{a.label}<ArrowRight size={14} /></Link>)}</div>}
          </div>)}
        </div>
        {busy && <div className="ra-loading" role="status"><LoaderCircle size={18} className="spin" /><span>{elapsed < 8 ? "Interpretando tu consulta…" : elapsed < 17 ? "Preparando tu respuesta…" : "Está tardando un poco. La búsqueda seguirá disponible."}</span></div>}
        {error && <div className="ra-error" role="alert"><strong>No pude completar la consulta</strong><p>{error}</p><button type="button" disabled={busy} onClick={() => void send(lastQuestion, true)}><RotateCcw size={14} /> Reintentar</button><Link to="/catalogo" onClick={close}>Ir al catálogo</Link></div>}
        {!busy && !error && lastAnswer && <div className="ra-suggestions">{lastAnswer.suggestions.map(s => <button key={s} type="button" onClick={() => void send(s)}>{s}<ArrowUp size={13} /></button>)}</div>}
      </div>
      {showBottom && <div className="ra-jump-row"><button className="ra-to-bottom" type="button" onClick={() => { const el = threadRef.current; if (el) el.scrollTop = el.scrollHeight; }}><ArrowDown size={15} /> Ver el final de la respuesta</button></div>}
      {count > 0 && <div className="ra-purchase"><span><ShoppingBag size={17} /><b>{count}</b> {count === 1 ? "unidad" : "unidades"} en tu carrito</span><button type="button" disabled={quoting || busy} onClick={quote}>{quoting ? "Guardando…" : "Cotizar carrito"}</button><Link to="/carrito" onClick={close}>Revisar compra<ArrowRight size={15} /></Link></div>}
      <form className="ra-composer" onSubmit={e => { e.preventDefault(); void send(draft); }}>
        <label htmlFor="roda-assistant-input">Tu consulta</label>
        <div className="ra-input-row"><textarea id="roda-assistant-input" ref={inputRef} placeholder="Ej.: pastillas para mi Yaris, hasta S/ 200" maxLength={1200} value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(draft); } }} />
          {busy ? <button type="button" aria-label="Detener consulta" title="Detener" onClick={() => controller.current?.abort()}><Square size={16} /></button> : <button type="submit" aria-label="Enviar consulta" disabled={!draft.trim() || quoting || resetBusy}><ArrowUp size={20} /></button>}
        </div>
        <div className="ra-composer-meta"><span>Enter para enviar · Shift + Enter para otra línea</span><span>{draft.length}/1200</span></div>
      </form>
      <details className="ra-privacy"><summary>Cómo uso tus datos</summary><p>El texto de tu consulta se envía al proveedor LLM configurado. La conversación caduca tras 24 horas sin actividad y se elimina en la siguiente limpieza. Puedes borrarla con «Nueva conversación». No compartas datos personales ni de pago. <Link to="/privacidad" onClick={close}>Ver privacidad</Link>.</p></details>
    </section>}
    <button ref={launchRef} type="button" className={"ra-launch" + (open ? " ra-is-open" : "")} aria-expanded={open} aria-controls="roda-assistant-panel" onClick={() => open ? close() : setOpen(true)}>
      {open ? <X size={19} /> : <MessageCircle size={21} />}<span>{open ? "Cerrar asistente" : "Asistente de repuestos"}</span>{!open && <i aria-hidden="true" />}
    </button>
  </div>;
}
