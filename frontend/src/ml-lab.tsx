import { useEffect, useState } from 'react';
import { Download, Upload, RefreshCw, Plus, ArrowRight, Database, FlaskConical } from 'lucide-react';
import { api, useLoad, useStore, Loading, ErrorBox, Modal, Pagination } from './lib';
import { Frame } from './ml';
import './ml-lab.css';

const base = '/admin/ml/lab';
const num = (v: number | null | undefined, digits = 2) => v == null ? '—' : v.toLocaleString('es-PE', { maximumFractionDigits: digits });
const actionName: Record<string, string> = { train: 'Entrenamiento', predict: 'Pronóstico', compare: 'Comparación' };
const eventName: Record<string, string> = { crear_historial: 'Historial creado', importar: 'Archivo confirmado', train: 'Entrenamiento iniciado', predict: 'Pronóstico solicitado', compare: 'Comparación solicitada', activar_version: 'Versión activada', archivar_demostracion: 'Demostración archivada' };

export function MLLaboratory() {
  const { notify } = useStore();
  const [did, setDid] = useState(''), [section, setSection] = useState('datos');
  const data = useLoad(base + (did ? `?dataset=${did}` : ''));
  const d = data.data, selected = d?.selected, versions = d?.versions || [];
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [newOpen, setNewOpen] = useState(false), [resetOpen, setResetOpen] = useState(false);
  const [name, setName] = useState(''), [frequency, setFrequency] = useState('monthly'), [source, setSource] = useState('');
  const [file, setFile] = useState<File | null>(null), [preview, setPreview] = useState<any>(null), [mapping, setMapping] = useState<Record<string, string>>({});
  const [v1, setV1] = useState(''), [v2, setV2] = useState(''), [predictionVersion, setPredictionVersion] = useState('');
  const [jid, setJid] = useState(''), [q, setQ] = useState(''), [page, setPage] = useState(1);
  const result = useLoad(jid ? `${base}/jobs/${jid}?q=${encodeURIComponent(q)}&page=${page}` : null);
  const running = d?.jobs?.some((j: any) => j.status === 'running');
  const disabled = busy || running || !!selected?.archived;
  useEffect(() => { if (selected?.id && !did) setDid(selected.id); }, [selected?.id, did]);
  useEffect(() => {
    setPreview(null); setFile(null); setMapping({}); setJid(''); setV1(''); setV2(''); setPredictionVersion(''); setError('');
  }, [did]);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(data.reload, 2500);
    return () => window.clearInterval(timer);
  }, [running, did]);
  const chosen1 = v1 || versions[0]?.id || '', chosen2 = v2 || versions[1]?.id || '';
  const chosenPrediction = predictionVersion || selected?.active_version || '';
  const label = (id: string) => versions.find((v: any) => v.id === id)?.label || id;
  const execute = async (fn: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await fn(); data.reload(); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const upload = () => execute(async () => {
    if (!file) throw new Error('Selecciona un archivo CSV o Excel.');
    const body = new FormData(); body.append('file', file); body.append('dataset', did); body.append('mapping', JSON.stringify(mapping));
    setPreview(await api(base + '/preview', { method: 'POST', body }));
  });
  const job = (action: string, ids?: string[]) => execute(async () => {
    await api(`${base}/datasets/${did}/jobs`, { method: 'POST', body: { action, versions: ids } });
    notify('Cálculo iniciado. Puedes seguir su estado en esta pantalla.');
  });
  const viewResult = (id: string) => { setJid(id); setPage(1); setQ(''); setSection('resultados'); };
  const finished = (d?.jobs || []).filter((j: any) => j.status === 'done' && j.action !== 'train');
  return <Frame title="Laboratorio y versiones" subtitle="Importa ventas, entrena cinco modelos y comprueba cómo cambia su precisión."
    action={<button className="secondary" disabled={busy} onClick={() => setNewOpen(true)}><Plus size={17}/>Nuevo historial</button>}>
    <ErrorBox message={error || data.error}/>
    {!d ? (data.error ? <button className="secondary" onClick={data.reload}>Reintentar carga</button> : <Loading/>) : <>
      <div className="ml-controlbar lab-selector">
        <label>Historial de trabajo<select aria-label="Historial de trabajo" disabled={busy || running} value={selected?.id || ''} onChange={e => setDid(e.target.value)}>
          {!d.datasets.length && <option value="">Sin historiales</option>}
          {d.datasets.map((h: any) => <option key={h.id} value={h.id}>{h.name}{h.archived ? ' · archivado' : ''} · {h.id.slice(0, 5)}</option>)}
        </select></label>
        <button className="secondary" disabled={busy || running} onClick={() => execute(async () => { const r = await api(base + '/demo', { method: 'POST' }); setDid(r.id); setSection('datos'); notify('Demostración preparada con el historial inicial.'); })}><FlaskConical size={17}/>Preparar demostración</button>
        {!!selected?.demo && <button className="secondary" disabled={disabled} onClick={() => setResetOpen(true)}><RefreshCw size={16}/>Restablecer demo</button>}
      </div>
      <div className="ml-notice"><Database size={19}/><div><b>Datos con procedencia, resultados comprobables.</b> {(!selected || selected.demo) ? <>Car Parts contiene ventas mensuales de 2,674 series anónimas (1998–2002). Es una fuente histórica externa; sus códigos no corresponden a los productos de la tienda. <a href={d.source?.source_url || 'https://zenodo.org/records/4656022'} target="_blank" rel="noreferrer">Consultar fuente y licencia CC BY 4.0</a>.</> : <>La procedencia de este historial fue declarada al crearlo: {selected.source}. Valida su origen y cobertura antes de interpretar sus resultados.</>}</div></div>
      {!selected ? <div className="ml-panel lab-empty"><h2>Empieza con un historial verificable</h2><p>Prepara la demostración para recorrer el ciclo V1 → nuevos datos → V2 → evaluación, o crea un historial con tus propios archivos.</p><p>Importar datos y calcular pronósticos no modifica pedidos ni existencias.</p></div> : <>
        <div className="ml-stats">
          {[
            ['Observaciones', num(d.stats.rows, 0), `${num(d.stats.products, 0)} series o productos`],
            ['Periodo disponible', d.stats.end || 'Sin datos', `Desde ${d.stats.start || '—'} · ${selected.frequency === 'monthly' ? 'mensual' : 'diario'}`],
            ['Valores desconocidos', num(d.stats.missing || 0, 0), 'Se conservan; no se convierten en cero'],
            ['Versión activa', selected.active_version ? label(selected.active_version) : 'Sin entrenar', 'Activa únicamente en este historial'],
          ].map(([title, value, note]) => <div className="ml-stat" key={title}><span>{title}</span><strong>{value}</strong><small>{note}</small></div>)}
        </div>
        {!!selected.archived && <div className="ml-notice">Historial archivado: sus importaciones, modelos y resultados se conservan para consulta.</div>}
        {running && <div className="ml-progress" role="status"><RefreshCw size={17} className="spin"/> Cálculo en curso. El entrenamiento puede tardar varios minutos; la pantalla actualizará el resultado.</div>}
        <div className="lab-subnav" role="group" aria-label="Secciones del laboratorio">{[['datos', '01', 'Datos e importación'], ['versiones', '02', 'Modelos y versiones'], ['resultados', '03', 'Resultados']].map(([key, step, text]) => <button key={key} className={section === key ? 'selected' : ''} aria-pressed={section === key} onClick={() => setSection(key)}><span>{step}</span>{text}</button>)}</div>

        {section === 'datos' && <>
          {!!selected.demo && <section className="ml-panel"><div className="ml-panel-title"><div><h2>Un recorrido que puedes repetir</h2><p>Carga cada archivo después de completar el paso anterior. Los CSV también se abren en Excel.</p></div><span className="ml-tag">136,374 registros originales</span></div>
            <div className="lab-stages">{[
              ['01_historial_inicial.csv', 'V1 · punto de partida', 'Ene. 1998 – dic. 2000', 'Ya cargado al preparar la demo. Entrena la primera versión.'],
              ['02_datos_nuevos.csv', 'V2 · incorporar historia', 'Ene. – sep. 2001', 'Importa estos meses y entrena otra versión.'],
              ['03_ventas_posteriores.csv', 'Evaluación · comprobar', 'Oct. 2001 – mar. 2002', 'Impórtalos después de V2 y compara ambas versiones.'],
            ].map(([fileName, title, period, description], i) => <article key={fileName}><span className="lab-stage-number">0{i + 1}</span><h3>{title}</h3><b>{period}</b><p>{description}</p><a className="secondary button small" href={`/api${base}/examples/${fileName}`}><Download size={15}/>Descargar CSV</a></article>)}</div>
          </section>}
          <section className="ml-panel"><div className="ml-panel-title"><div><h2>Importar ventas observadas</h2><p>Una fila por producto y periodo. Las compras o ventas de prueba deben identificarse como tales en la procedencia.</p></div><span className="ml-tag">CSV / XLSX · máx. 8 MB</span></div>
            <p className="lab-helper">Columnas: <code>periodo</code>, <code>sku</code>, <code>unidades</code>. Periodo: {selected.frequency === 'monthly' ? 'AAAA-MM' : 'AAAA-MM-DD'}. Unidades enteras, cero si no hubo ventas, vacío si no se conoce. Excel: una hoja, sin fórmulas.</p>
            <div className="lab-upload"><label>Archivo de ventas<input key={did} type="file" accept=".csv,.xlsx" disabled={disabled} onChange={e => { setFile(e.target.files?.[0] || null); setPreview(null); setMapping({}); }}/></label><button disabled={disabled || !file} onClick={upload}><Upload size={17}/>{busy ? 'Revisando…' : 'Revisar archivo'}</button></div>
            {preview?.needs_mapping && <div className="lab-mapping"><h3>Relaciona las columnas</h3><p>Selecciona qué columna de tu archivo corresponde a cada dato.</p><div className="lab-fields">{['periodo', 'sku', 'unidades'].map(k => <label key={k}>{k}<select value={mapping[k] || ''} onChange={e => setMapping({ ...mapping, [k]: e.target.value })}><option value="">Seleccionar columna</option>{preview.headers.map((h: string) => <option key={h} value={h}>{h}</option>)}</select></label>)}</div><button className="secondary" disabled={disabled || Object.keys(mapping).length < 3} onClick={upload}>Validar columnas</button></div>}
            {preview && !preview.needs_mapping && <div className="lab-preview"><h3>Vista previa · {file?.name}</h3><p>{num(preview.accepted, 0)} filas nuevas · {num(preview.duplicates, 0)} duplicadas omitidas · {num(preview.missing, 0)} valores desconocidos · <b>{num(preview.invalid, 0)} errores</b></p>
              {preview.errors.length > 0 && <div className="lab-errors" role="alert">{preview.errors.map((e: any, i: number) => <p key={i}>Fila {e.row}: {e.message}</p>)}</div>}
              <table className="ml-table"><thead><tr><th>Periodo</th><th>SKU / serie</th><th>Unidades observadas</th></tr></thead><tbody>{preview.preview.map((r: any) => <tr key={r.sku + r.period}><td>{r.period}</td><td>{r.sku}</td><td>{r.units == null ? 'Desconocido' : num(r.units, 0)}</td></tr>)}</tbody></table>
              <button disabled={disabled || preview.invalid > 0 || !preview.accepted} onClick={() => execute(async () => { await api(`${base}/batches/${preview.id}/confirm`, { method: 'POST' }); setPreview(null); notify('Importación confirmada. Los datos originales se conservaron.'); })}>Confirmar importación<ArrowRight size={16}/></button>
            </div>}
          </section>
          <section className="ml-panel"><h2>Trazabilidad del historial</h2><p className="lab-source">Procedencia declarada: {selected.source}</p>{d.batches.length ? <table className="ml-table"><thead><tr><th>Archivo</th><th>Periodo</th><th>Filas nuevas</th><th>Desconocidos</th></tr></thead><tbody>{d.batches.map((b: any) => <tr key={b.id}><td><b>{b.filename}</b><small title={b.summary.file_sha256}>SHA-256: {b.summary.file_sha256.slice(0, 20)}…</small></td><td>{b.summary.start} → {b.summary.end}</td><td>{num(b.summary.accepted, 0)}</td><td>{num(b.summary.missing, 0)}</td></tr>)}</tbody></table> : <p>Aún no hay importaciones confirmadas.</p>}</section>
        </>}

        {section === 'versiones' && <>
          <section className="ml-panel"><div className="ml-panel-title"><div><h2>Entrenar y conservar cada versión</h2><p>Ridge, Poisson, Random Forest, Extra Trees y Hist. Gradient Boosting compiten con el mismo corte temporal.</p></div><button disabled={disabled || !d.stats.rows} onClick={() => job('train')}><RefreshCw size={16}/>Entrenar {`V${versions.length + 1}`}</button></div>
            <p className="lab-helper">Se elige el menor MAE de validación y se reajusta con el historial disponible. Predecir utiliza un modelo guardado; no lo reentrena. V2 permanece como candidata hasta demostrar una mejora de al menos 1% frente a la activa. <a className="lab-notebook-link" href="https://colab.research.google.com/github/NEYEN111/REPUESTOS/blob/main/notebooks/RODA_ML_Datos_Reales.ipynb" target="_blank" rel="noreferrer">Abrir cuaderno completo en Colab</a></p>
            {!versions.length && <p>Importa un historial y ejecuta el primer entrenamiento.</p>}
            {versions.map((v: any) => <details className="lab-version" key={v.id} open={versions.length === 1}><summary><span><b>{v.label} · {v.report.winner}</b><small>Entrenado hasta {v.report.cutoff} · {num(v.report.refit_rows, 0)} objetivos observados</small></span><span className={`ml-tag ${selected.active_version === v.id ? 'success' : ''}`}>{selected.active_version === v.id ? 'Activa' : 'Candidata'}</span></summary>
              <p>{v.report.reason} Validación posterior a {v.report.split}. MAE expresa error absoluto medio en unidades; menor es mejor.</p>
              <div className="lab-score-bars">{v.report.candidates.map((c: any) => <div key={c.model}><span>{c.model}</span><div><i style={{ width: `${Math.max(1, c.mae / Math.max(...v.report.candidates.map((s: any) => s.mae), 1) * 100)}%` }}/></div><b>{num(c.mae, 3)}</b></div>)}</div>
              <table className="ml-table"><thead><tr><th>Modelo</th><th>MAE</th><th>RMSE</th><th>WAPE %</th><th>R²</th></tr></thead><tbody>{[...v.report.candidates, { model: 'Referencia: promedio histórico', ...v.report.validation_baseline }].map((c: any) => <tr key={c.model}><td>{c.model}{c.model === v.report.winner ? ' · elegido' : ''}</td><td>{num(c.mae, 3)}</td><td>{num(c.rmse, 3)}</td><td>{num(c.wape)}</td><td>{num(c.r2, 3)}</td></tr>)}</tbody></table>
              <p className="lab-helper"><b>{Math.min(...v.report.candidates.map((s: any) => s.mae)) < v.report.validation_baseline.mae ? 'Superó al promedio en validación.' : 'No superó al promedio en validación; uso exploratorio.'}</b> Ganar entre cinco modelos no garantiza aportar valor frente a una referencia simple ni mejorar con nuevos datos.</p>
              <details><summary>Variables y límites de esta versión</summary><p>Rezagos, media, dispersión, ventas recientes, proporción de ceros, faltantes y calendario. Se calculan exclusivamente con periodos anteriores.</p><ul>{v.report.limitations.map((s: string) => <li key={s}>{s}</li>)}</ul><p className="lab-hash">Archivo: {v.report.model_sha256}</p><a className="secondary button small" href={`/api${base}/versions/${v.id}/download`}><Download size={15}/>Descargar {v.label} · joblib</a></details>
            </details>)}
          </section>
          <div className="lab-two-panels">
            <section className="ml-panel"><h2>Calcular próximo periodo</h2><p>{selected.frequency === 'monthly' ? 'Estima el mes siguiente al último mes importado.' : 'Estima las unidades de los siete días siguientes al último día importado.'}</p><label>Modelo para predecir<select value={chosenPrediction} onChange={e => setPredictionVersion(e.target.value)}><option value="">Seleccionar versión</option>{versions.map((v: any) => <option key={v.id} value={v.id}>{v.label} · {v.report.winner}</option>)}</select></label><button disabled={disabled || !chosenPrediction} onClick={() => job('predict', [chosenPrediction])}>Calcular pronóstico<ArrowRight size={16}/></button></section>
            <section className="ml-panel"><h2>Comparar con ventas posteriores</h2><p>Ambas versiones se evalúan sobre las mismas observaciones, posteriores a sus entrenamientos.</p><div className="lab-fields">{[[chosen1, setV1, 'Versión base'], [chosen2, setV2, 'Versión candidata']].map(([v, setter, title]: any) => <label key={title}>{title}<select value={v} onChange={e => setter(e.target.value)}><option value="">Seleccionar</option>{versions.map((version: any) => <option key={version.id} value={version.id}>{version.label} · corte {version.report.cutoff}</option>)}</select></label>)}</div><button disabled={disabled || !chosen1 || !chosen2 || chosen1 === chosen2} onClick={() => job('compare', [chosen1, chosen2])}>Evaluar ambas versiones</button></section>
          </div>
        </>}

        {section === 'resultados' && <section className="ml-panel"><div className="ml-panel-title"><div><h2>Resultados guardados</h2><p>La versión y el corte quedan asociados a cada cálculo.</p></div>{jid && result.data?.items && <a className="secondary button" href={`/api${base}/jobs/${jid}/export`}><Download size={16}/>Exportar CSV</a>}</div>
          <label>Cálculo<select value={jid} onChange={e => viewResult(e.target.value)}><option value="">Seleccionar resultado</option>{finished.map((j: any) => <option key={j.id} value={j.id}>{actionName[j.action]} · {j.created_at.slice(0, 19).replace('T', ' ')} · {j.id.slice(0, 5)}</option>)}</select></label>
          {!jid ? <p>Ejecuta un pronóstico o una comparación en «Modelos y versiones».</p> : result.error ? <ErrorBox message={result.error}/> : !result.data ? <Loading/> : result.data.items ? <>
            <div className="lab-result-summary"><h3>Próximo {selected.frequency === 'monthly' ? 'mes' : 'periodo de siete días'} · corte {result.data.cutoff}</h3><p>Modelo: {label(result.data.version || selected.active_version)}. {num(result.data.excluded, 0)} series excluidas por historial insuficiente o por no estar presentes en el entrenamiento. Cantidades estimadas; no son pedidos de reposición.</p></div>
            <label>Buscar SKU o serie<input value={q} onChange={e => { setQ(e.target.value); setPage(1); }} placeholder="Ej. T125"/></label>
            <table className="ml-table"><thead><tr><th>SKU / serie</th><th>{selected.frequency === 'monthly' ? 'Mes previsto' : 'Fin del periodo previsto'}</th><th>Estimación ML</th><th>Promedio histórico</th><th>Faltantes en ventana</th></tr></thead><tbody>{result.data.items.map((r: any) => <tr key={r.sku}><td><b>{r.sku}</b></td><td>{r.period}</td><td>{num(r.prediction)}</td><td>{num(r.baseline)}</td><td>{r.missing}</td></tr>)}</tbody></table>{!result.data.items.length && <p>No hay series que coincidan con la búsqueda.</p>}<Pagination page={page} pages={Math.ceil(result.data.total / 20)} total={result.data.total} onChange={setPage}/>
          </> : <Comparison result={result.data} label={label} active={selected.active_version} disabled={disabled} activate={(id: string) => execute(async () => { await api(`${base}/datasets/${did}/activate`, { method: 'POST', body: { version: id } }); notify('Versión activada para este historial.'); })}/>}
        </section>}
        <section className="ml-panel lab-jobs"><div className="ml-panel-title"><div><h2>Actividad de cálculo</h2><p>El historial de trabajos conserva tanto resultados como errores.</p></div><button className="secondary small" onClick={data.reload} disabled={busy}><RefreshCw size={14}/>Actualizar</button></div>
          {!d.jobs.length ? <p>Aún no se han ejecutado cálculos.</p> : <table className="ml-table"><thead><tr><th>Trabajo</th><th>Estado</th><th>Resultado</th><th>Acción</th></tr></thead><tbody>{d.jobs.slice(0, 8).map((j: any) => <tr key={j.id}><td>{actionName[j.action]}<small>{j.created_at.slice(0, 19).replace('T', ' ')}</small></td><td><span className={`ml-tag ${j.status === 'done' ? 'success' : 'warning'}`}>{j.status === 'done' ? 'Completado' : j.status === 'running' ? 'En curso' : 'Revisar'}</span></td><td>{j.error || j.result?.winner || (j.status === 'running' ? 'Procesando historial y modelo…' : 'Disponible para consultar')}</td><td>{j.status === 'done' && <button className="secondary small" onClick={() => j.action === 'train' ? setSection('versiones') : viewResult(j.id)}>Ver resultado<ArrowRight size={14}/></button>}</td></tr>)}</tbody></table>}
          <details><summary>Auditoría del historial</summary>{d.activity.map((e: any) => <p key={e.id}>{e.created_at.slice(0, 19).replace('T', ' ')} · {eventName[e.action] || e.action} · usuario #{e.user_id}</p>)}</details>
        </section>
      </>}
    </>}
    {newOpen && <Modal title="Nuevo historial de ventas" onClose={() => { if (!busy) setNewOpen(false); }}><form className="lab-new" onSubmit={e => { e.preventDefault(); execute(async () => { const r = await api(base + '/datasets', { method: 'POST', body: { name, frequency, source } }); setDid(r.id); setSection('datos'); setNewOpen(false); setName(''); setSource(''); }); }}><p>Usa un historial independiente para cada fuente. Indica si procede de operaciones reales, de una fuente pública o de pruebas.</p><ErrorBox message={error}/><label>Nombre<input required maxLength={120} value={name} onChange={e => setName(e.target.value)}/></label><label>Frecuencia<select value={frequency} onChange={e => setFrequency(e.target.value)}><option value="monthly">Mensual · pronóstico del próximo mes</option><option value="daily">Diaria · pronóstico de siete días</option></select></label><label>Procedencia<textarea required maxLength={1000} value={source} onChange={e => setSource(e.target.value)} placeholder="Empresa o fuente, URL o referencia y tratamiento aplicado"/></label><button disabled={busy}>Crear historial</button></form></Modal>}
    {resetOpen && <Modal title="Restablecer la demostración" onClose={() => { if (!busy) setResetOpen(false); }}><p>Se archivará esta demostración con sus versiones y resultados. Se abrirá una nueva con el historial inicial de 1998–2000.</p><p>Los pedidos, productos y existencias de la tienda no cambian. Podrás consultar la demostración anterior en el selector de historiales.</p><ErrorBox message={error}/><button disabled={busy} onClick={() => execute(async () => { const r = await api(`${base}/datasets/${did}/reset`, { method: 'POST' }); setDid(r.id); setResetOpen(false); setSection('datos'); notify('Nueva demostración preparada. La anterior se conserva archivada.'); })}>{busy ? 'Preparando…' : 'Archivar y restablecer'}</button></Modal>}
  </Frame>;
}

function Comparison({ result: r, label, active, disabled, activate }: any) {
  if (!r.scores) return null;
  const periods = Array.from(new Set<string>(r.periods.map((p: any) => p.period)));
  const max = Math.max(1, ...r.periods.flatMap((p: any) => [p.actual, p.predicted]));
  const series = [null, ...r.scores.map((s: any) => s.version)];
  const colors = ['#253441', '#bc4828', '#357d80'];
  const x = (i: number) => 70 + i * 720 / Math.max(1, periods.length - 1), y = (v: number) => 205 - v / max * 165;
  return <div className="lab-comparison"><h3>Evaluación posterior · {r.start} → {r.end}</h3><p>{num(r.rows, 0)} observaciones comunes · {num(r.products, 0)} series. {r.protocol} Se actualizan las variables con el pasado observado, sin reentrenar los modelos.</p>
    {r.baseline.mae <= Math.min(...r.scores.map((s: any) => s.mae)) && <div className="ml-notice lab-baseline-warning"><div><b>El promedio histórico obtuvo menor error que ambas versiones.</b> Estos resultados son exploratorios. No justifican automatizar decisiones de compra con los modelos evaluados.</div></div>}
    <div className="lab-recommendation"><div><b>{r.recommended === active ? `Mantener ${label(active)}` : `Candidata recomendada: ${label(r.recommended)}`}</b><p>La candidata debe reducir el MAE al menos 1%. Esta regla no equivale a una garantía estadística de mejora futura.</p></div>{r.recommended !== active && <button disabled={disabled} onClick={() => activate(r.recommended)}>Activar {label(r.recommended)}</button>}</div>
    <table className="ml-table"><thead><tr><th>Versión / referencia</th><th>MAE</th><th>RMSE</th><th>WAPE %</th><th>Sesgo</th><th>R²</th></tr></thead><tbody>{[...r.scores, { ...r.baseline, version: 'baseline' }].map((s: any) => <tr key={s.version}><td><b>{s.version === 'baseline' ? 'Promedio histórico' : label(s.version)}</b></td><td>{num(s.mae, 3)}</td><td>{num(s.rmse, 3)}</td><td>{num(s.wape)}</td><td>{num(s.bias, 3)}</td><td>{num(s.r2, 3)}</td></tr>)}</tbody></table>
    <h3>Ventas observadas y estimadas por periodo</h3><div className="lab-chart-legend">{series.map((id, i) => <span key={id || 'actual'}><i style={{ background: colors[i] }}/>{id ? label(id) : 'Observado'}</span>)}</div>
    <svg viewBox="0 0 850 250" role="img" aria-label="Ventas agregadas por periodo, observadas y estimadas por ambas versiones. Valores en la tabla siguiente." className="lab-chart">
      {[0, .5, 1].map(t => <g key={t}><line x1="65" x2="800" y1={y(max*t)} y2={y(max*t)} stroke="#dce1e5"/><text x="58" y={y(max*t)+4} textAnchor="end">{num(max*t, 0)}</text></g>)}
      {series.map((id, i) => <polyline key={id || 'actual'} fill="none" stroke={colors[i]} strokeWidth="3" strokeDasharray={i === 2 ? '7 4' : undefined} points={periods.map((p, index) => { const row = r.periods.find((s: any) => s.period === p && (!id || s.version === id)); return `${x(index)},${y(id ? row.predicted : row.actual)}`; }).join(' ')}/>)}
      {periods.map((p, i) => <text key={p} x={x(i)} y="232" textAnchor="middle">{p}</text>)}
    </svg>
    <details><summary>Ver valores por periodo</summary><table className="ml-table"><thead><tr><th>Periodo</th><th>Versión</th><th>Observado</th><th>Estimado</th><th>MAE</th></tr></thead><tbody>{r.periods.map((p: any) => <tr key={p.version + p.period}><td>{p.period}</td><td>{label(p.version)}</td><td>{num(p.actual)}</td><td>{num(p.predicted)}</td><td>{num(p.mae, 3)}</td></tr>)}</tbody></table></details>
  </div>;
}
