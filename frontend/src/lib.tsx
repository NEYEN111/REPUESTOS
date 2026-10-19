import React, { createContext, useContext, useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import {
  X,
  Check,
  AlertCircle,
  LoaderCircle,
  ChevronLeft,
  ChevronRight,
  PackageOpen,
  ArrowRight,
} from "lucide-react";
export const money = (v: number = 0) =>
  "S/ " +
  (v / 100).toLocaleString("es-PE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
export const date = (v: string) =>
  !v ? '—' : new Date(v.length===10?v+'T12:00:00-05:00':v).toLocaleDateString("es-PE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "America/Lima",
  });
export async function api(path: string, options: any = {}) {
  const r = await fetch("/api" + path, {
    credentials: "include",
    ...options,
    headers:
      options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json", ...options.headers },
    body:
      options.body && !(options.body instanceof FormData)
        ? JSON.stringify(options.body)
        : options.body,
  });
  if (!r.ok) {
    let d;
    try {
      d = await r.json();
    } catch {}
    throw new Error(
      typeof d?.detail === "string"
        ? d.detail
        : "No pudimos completar la operación. Intenta nuevamente.",
    );
  }
  return r.json();
}
export function useLoad(path: string | null, deps: any[] = []) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [version, setVersion] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    if (!path) {
      setData(null);
      setLoading(false);
      return;
    }
    api(path)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [path, version, ...deps]);
  return {
    data,
    error,
    loading,
    reload: () => setVersion((v) => v + 1),
    setData,
  };
}
const Context = createContext<any>(null);
function stored(key: string, fallback: any) {
  try {
    return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
  } catch {
    return fallback;
  }
}
export function Provider({ children }: any) {
  const [config, setConfig] = useState<any>(null),
    [user, setUser] = useState<any>(null),
    [ready, setReady] = useState(false),
    [cart, setCart] = useState<any[]>(() => stored("cart", [])),
    [garage, setGarage] = useState<number[]>(() => stored("garage", [])),
    [vehicle, setVehicle] = useState<number | null>(() =>
      stored("vehicle", null),
    ),
    [vehicles, setVehicles] = useState<any[]>([]),
    [categories, setCategories] = useState<any[]>([]),
    [toast, setToast] = useState<any>(null),
    [fatal, setFatal] = useState("");
  useEffect(() => {
    Promise.all([
      api("/config"),
      api("/auth/me"),
      api("/vehicles"),
      api("/categories"),
    ])
      .then(([c, u, v, cat]) => {
        setConfig(c);
        document.title = c.name + " · Repuestos y accesorios";
        setUser(u);
        setVehicles(v);
        setCategories(cat);
        if (u)
          api("/account").then((a) => {
            setGarage(a.garage.map((v: any) => v.id));
            setVehicle(a.garage.find((v: any) => v.active)?.id || null);
          });
      })
      .catch((e) => setFatal(e.message))
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    localStorage.setItem("cart", JSON.stringify(cart));
  }, [cart]);
  useEffect(() => {
    localStorage.setItem("garage", JSON.stringify(garage));
    localStorage.setItem("vehicle", JSON.stringify(vehicle));
  }, [garage, vehicle]);
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 4500);
      return () => clearTimeout(t);
    }
  }, [toast]);
  const notify = (message: string, error = false) =>
    setToast({ message, error });
  const event = (type: string, payload: any = {}) => {
    let sid = sessionStorage.getItem("sid");
    if (!sid) {
      sid = crypto.randomUUID();
      sessionStorage.setItem("sid", sid);
    }
    api("/events", {
      method: "POST",
      body: { type, session_id: sid, vehicle_id: vehicle, ...payload },
    }).catch(() => {});
  };
  const add = (p: any, quantity = 1) => {
    if (p.available <= 0) return;
    setCart((old) => {
      const prev = old.find((i) => i.id === p.id);
      if ((prev?.quantity || 0) + quantity > p.available) {
        notify("No hay más unidades disponibles.", true);
        return old;
      }
      return prev
        ? old.map((i) =>
            i.id === p.id ? { ...i, quantity: i.quantity + quantity } : i,
          )
        : [...old, { ...p, quantity }];
    });
    event("cart_add", { product_id: p.id, payload: { quantity } });
    notify("Producto agregado al carrito.");
  };
  const saveGarage = async (ids: number[], active: number | null) => {
    if (user)
      await api("/account/garage", {
        method: "PUT",
        body: { vehicles: ids, active },
      });
    setGarage(ids);
    setVehicle(active);
  };
  if (!ready) return <Loading />;
  if (fatal)
    return (
      <div className="boot-error">
        <ErrorBox message={fatal} />
        <button onClick={() => location.reload()}>Reintentar conexión</button>
      </div>
    );
  return (
    <Context.Provider
      value={{
        config,
        setConfig,
        user,
        setUser,
        cart,
        setCart,
        garage,
        vehicle,
        vehicles,
        categories,
        notify,
        add,
        event,
        saveGarage,
      }}
    >
      {children}
      {toast && (
        <div className={"toast " + (toast.error ? "error" : "")} role="status">
          {toast.error ? <AlertCircle size={20} /> : <Check size={20} />}{" "}
          {toast.message}
          <button aria-label="Cerrar aviso" onClick={() => setToast(null)}>
            <X size={17} />
          </button>
        </div>
      )}
    </Context.Provider>
  );
}
export const useStore = () => useContext(Context);
export function Loading() {
  return (
    <div className="loading">
      <LoaderCircle className="spin" size={25} /> Cargando...
    </div>
  );
}
export function ErrorBox({ message }: any) {
  return message ? (
    <div className="error-box" role="alert">
      <AlertCircle size={18} />
      {message}
    </div>
  ) : null;
}
export function Empty({
  title = "No encontramos resultados",
  text = "Prueba cambiando los filtros de búsqueda.",
  action,
}: any) {
  return (
    <div className="empty">
      <PackageOpen size={48} strokeWidth={1} />
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
export function Badge({ children }: any) {
  return (
    <span
      className={
        "badge " +
        ([
          "pagado",
          "confirmado",
          "entregado",
          "recibida",
          "resuelta",
          "activo",
        ].includes(children)
          ? "green"
          : ["cancelado", "vencido", "rechazado", "agotado"].includes(children)
            ? "red"
            : "amber")
      }
    >
      {children}
    </span>
  );
}
export function Modal({ title, children, onClose, wide = false }: any) {
  const dialog = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const focusable = () => Array.from(dialog.current?.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]') || []).filter(el => el.getClientRects().length > 0);
    focusable()[0]?.focus();
    const f = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
      if (e.key === 'Tab') {
        const items = focusable();
        const first = items[0], last = items[items.length - 1];
        if (!first) { e.preventDefault(); dialog.current?.focus(); }
        else if (e.shiftKey && (document.activeElement === first || document.activeElement === dialog.current)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", f);
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", f);
      document.body.style.overflow = old;
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
          ref={dialog}
          tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={"modal " + (wide ? "wide" : "")}
      >
        <header>
          <h2>{title}</h2>
          <button className="icon-button" aria-label="Cerrar" onClick={onClose}>
            <X />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
export function Pagination({ page, pages, total, onChange }: any) {
  return (
    <div className="pagination">
      <span>
        {total} resultados · Página {page} de {Math.max(1, pages)}
      </span>
      <div>
        <button
          className="secondary small"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          <ChevronLeft size={16} />
          Anterior
        </button>
        <button
          className="secondary small"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Siguiente
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
export function Field({ label, children, ...props }: any) {
  return (
    <label className="field">
      <span>{label}</span>
      {children || <input {...props} />}
    </label>
  );
}
export function ProductImage({ p, ...props }: any) {
  const { categories } = useStore();
  return (
    <img
      {...props}
      src={
        props.src ||
        p.image ||
        categories.find((c: any) => c.id === p.category_id)?.image ||
        "/media/category/pastillas-de-freno.webp"
      }
      alt={props.alt || p.name}
      onError={(e) => {
        const el = e.currentTarget;
        if (!el.dataset.fallback) {
          el.dataset.fallback = "1";
          el.src =
            categories.find((c: any) => c.id === p.category_id)?.image ||
            categories.find((c: any) => c.image)?.image;
        }
      }}
    />
  );
}
export function ProductCard({ p }: any) {
  const { add, vehicle } = useStore();
  return (
    <article className="product-card">
      <Link className="product-photo" to={"/producto/" + p.id}>
        {p.old_price_cents > p.price_cents && (
          <span className="discount">
            −{Math.round((1 - p.price_cents / p.old_price_cents) * 100)}%
          </span>
        )}
          <ProductImage p={p} loading="lazy" />
      </Link>
      <div className="product-content">
        <div className="brand-line">
          {p.brand}
          <span>{p.sku}</span>
        </div>
        <Link className="product-name" to={"/producto/" + p.id}>
          {p.name}
        </Link>
        <div className="fit-label">
          {vehicle
            ? "Compatible con tu auto"
            : p.universal
              ? "Aplicación universal"
              : "Verifica la compatibilidad"}
        </div>
        <div className="product-bottom">
          <div>
            {p.old_price_cents > p.price_cents && (
              <del>{money(p.old_price_cents)}</del>
            )}
            <strong>{money(p.price_cents)}</strong>
            <small>Incluye IGV</small>
          </div>
          <button
            className="add-button"
            disabled={p.available < 1}
            onClick={() => add(p)}
            aria-label={"Agregar " + p.name}
          >
              <span>{p.available < 1 ? 'Agotado' : 'Agregar'}</span><ArrowRight size={17} />
          </button>
        </div>
        <span className={"stock " + (!p.available ? "out" : "")}>
          {p.available > 5
            ? "Disponible"
            : p.available
              ? "Últimas " + p.available + " unidades"
              : "Agotado"}
        </span>
      </div>
    </article>
  );
}
