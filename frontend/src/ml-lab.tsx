import { useEffect, useState } from 'react';
import { Download, Upload, RefreshCw, Plus, ArrowRight, Database, FlaskConical } from 'lucide-react';
import { api, useLoad, useStore, Loading, ErrorBox, Modal, Pagination } from './lib';
import { Frame } from './ml';
import './ml-lab.css';

const base = '/admin/ml/lab';
const num = (v: number | null | undefined, digits = 2) => v == null ? '—' : v.toLocaleString('es-PE', { maximumFractionDigits: digits });
const actionName: Record<string, string> = { train: 'Entrenamiento', predict: 'Pronóstico', compare: 'Comparación' };
const eventName: Record<string, string> = { crear_historial: 'Historial creado', importar: 'Archivo confirmado', train: 'Entrenamiento iniciado', predict: 'Pronóstico solicitado', compare: 'Comparación solicitada', activar_version: 'Versión activada', archivar_demostracion: 'Demostración archivada', archivar_ensayo: 'Ensayo archivado' };

export function MLLaboratory() {
  const { notify } = useStore();
  const [did, setDid] = useState(() => new URLSearchParams(window.location.search).get('dataset') || ''), [section, setSection] = useState('datos');
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
  const managed = selected?.id === 'roda-operacion-diaria';
  const simulation = selected?.scenario === 'roda-calibrated';
  const disabled = busy || running || !!selected?.archived || managed;
  useEffect(() => { if (selected?.id && !did) setDid(selected.id); }, [selected?.id, did]);
  useEffect(() => {
    setPreview(null); setFile(null); setMapping({}); setJid(''); setV1(''); setV2(''); setPredictionVersion(''); setError('');
    const params = new URLSearchParams(window.location.search);
    if (params.get('dataset') === did && params.get('result')) {
      setJid(params.get('result')!); setSection('resultados');
    }
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
  const currentComparison = (d?.jobs || []).find((j: any) => j.action === 'compare' && j.status === 'done' && j.result?.snapshot_rows === d?.stats?.rows);
  const demoStep = !selected?.demo ? null : !versions.length
    ? { number: '01 / 05', title: 'Entrena V1 con el historial inicial', detail: 'El primer modelo se conserva como referencia. No se activa por el solo hecho de entrenarlo.', section: 'versiones', action: 'Ir a entrenamiento' }
    : !d?.stats?.end || d.stats.end < '2001-09'
    ? { number: '02 / 05', title: 'Carga nueve meses nuevos desde Excel', detail: 'Revisa las 24 066 observaciones antes de confirmar. Los vacíos significan dato desconocido.', file: '02_datos_nuevos.xlsx', action: 'Descargar Excel' }
    : versions.length < 2
    ? { number: '03 / 05', title: 'Entrena V2 con el historial ampliado', detail: 'La versión nueva queda como candidata; cargar ventas no reentrena el modelo.', section: 'versiones', action: 'Ir a entrenamiento' }
    : d.stats.end < '2002-03'
    ? { number: '04 / 05', title: 'Carga ventas posteriores a ambas versiones', detail: 'Son la prueba reservada para medir errores sobre las mismas observaciones.', file: '03_ventas_posteriores.csv', action: 'Descargar ventas posteriores' }
    : !currentComparison
    ? { number: '05 / 05', title: 'Compara V1, V2 y el promedio histórico', detail: 'La comparación debe actualizarse si añades ventas. Solo una mejora comprobada permite activar un modelo.', section: 'versiones', action: 'Ir a comparación' }
    : { number: '05 / 05', title: 'Revisa la comparación terminada', detail: 'Consulta errores, periodos observados y la decisión de aprobación.', section: 'resultados', action: 'Ver resultados' };
  const simStages = d?.simulation?.stages || [];
  const simDays = simulation && d?.stats?.start && d?.stats?.end
    ? Math.round((Date.parse(d.stats.end + 'T00:00:00Z') - Date.parse(d.stats.start + 'T00:00:00Z')) / 86400000) + 1 : 0;
  const simulationStep = !simulation || simStages.length < 3 ? null : !versions.length
    ? { number: '01 / 05', title: 'Entrena V1 con 90 días de ensayo', detail: 'Historial sintético diario calibrado con ventas mensuales públicas. El contador operativo de la tienda no cambia.', section: 'versiones', action: 'Ir a entrenamiento' }
    : d.stats.end < simStages[1].end
    ? { number: '02 / 05', title: 'Carga 30 días nuevos desde Excel', detail: 'Importa el archivo para mostrar cómo cambia el historial. Estas cantidades son de ensayo.', file: '02_datos_nuevos_30_dias.xlsx', action: 'Descargar Excel' }
    : versions.length < 2
    ? { number: '03 / 05', title: 'Entrena V2 con 30 días adicionales', detail: 'La V1 queda guardada para comparar los modelos con la misma prueba posterior.', section: 'versiones', action: 'Ir a entrenamiento' }
    : d.stats.end < simStages[2].end
    ? { number: '04 / 05', title: 'Carga 30 días posteriores reservados', detail: 'Ninguna versión ha visto este bloque al entrenarse.', file: '03_ventas_posteriores_30_dias.csv', action: 'Descargar CSV' }
    : !currentComparison
    ? { number: '05 / 05', title: 'Compara V1, V2 y el promedio histórico', detail: 'Mide el error en las mismas ventas posteriores de ensayo.', section: 'versiones', action: 'Ir a comparación' }
    : { number: '05 / 05', title: 'Revisa la comparación del ensayo', detail: 'Los resultados describen este escenario sintético; no validan la precisión en ventas reales.', section: 'resultados', action: 'Ver resultados' };
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
        <button className="secondary" disabled={busy || running} onClick={() => execute(async () => { const r = await api(base + '/simulation', { method: 'POST' }); setDid(r.id); setSection('datos'); notify('Ensayo calibrado preparado con 90 días.'); })}><Database size={17}/>Crear ensayo de 90 días</button>
        {(!!selected?.demo || simulation) && <button className="secondary" disabled={disabled} onClick={() => setResetOpen(true)}><RefreshCw size={16}/>Restablecer {simulation ? 'ensayo' : 'demo'}</button>}
      </div>
      <div className="ml-notice"><Database size={19}/><div><b>Datos con procedencia, resultados comprobables.</b> {simulation ? <>Este ensayo usa patrones mensuales de <a href={d.simulation?.source_url} target="_blank" rel="noreferrer">Car Parts (CC BY 4.0)</a>. La distribución diaria y la asociación con 120 SKU de RODA son simuladas. No representa ventas reales ni cambia el historial operativo.</> : (!selected || selected.demo) ? <>Car Parts contiene ventas mensuales de 2,674 series anónimas (1998–2002). Es una fuente histórica externa; sus códigos no corresponden a los productos de la tienda. <a href={d.source?.source_url || 'https://zenodo.org/records/4656022'} target="_blank" rel="noreferrer">Consultar fuente y licencia CC BY 4.0</a>.</> : <>La procedencia de este historial fue declarada al crearlo: {selected.source}. Valida su origen y cobertura antes de interpretar sus resultados.</>}</div></div>
      {managed && <div className="ml-notice"><div>Este historial recibe los cierres diarios automáticamente. Consulta aquí sus modelos y resultados. Para ejecutar el ciclo, abre <a href="/gestion/ml/actualizacion">Actualización automática → Revisar ahora</a>.</div></div>}
      {!selected ? <div className="ml-panel lab-empty"><h2>Empieza con un historial verificable</h2><p>Prepara la demostración para recorrer el ciclo V1 → nuevos datos → V2 → evaluación, o crea un historial con tus propios archivos.</p><p>Importar datos y calcular pronósticos no modifica pedidos ni existencias.</p></div> : <>
        <div className="ml-stats">
          {[
            ['Observaciones', num(d.stats.rows, 0), `${num(d.stats.products, 0)} series o productos`],
            ['Periodo disponible', d.stats.end || 'Sin datos', `Desde ${d.stats.start || '—'} · ${selected.frequency === 'monthly' ? 'mensual' : 'diario'}`],
            simulation ? ['Días de ensayo', `${Math.min(simDays, 90)} / 90`, `${Math.max(0, simDays - 90)} días adicionales · no cuentan como cierres reales`] : ['Valores desconocidos', num(d.stats.missing || 0, 0), 'Se conservan; no se convierten en cero'],
            ['Versión activa', selected.active_version ? label(selected.active_version) : versions.length ? 'Sin modelo aprobado' : 'Sin entrenar', 'Activa únicamente en este historial'],
          ].map(([title, value, note]) => <div className="ml-stat" key={title}><span>{title}</span><strong>{value}</strong><small>{note}</small></div>)}
        </div>
        {demoStep && !selected.archived && <section className="lab-next-step"><span>{demoStep.number}</span><div><h2>{demoStep.title}</h2><p>{demoStep.detail}</p></div>{demoStep.file ? <a className="button" href={`/api${base}/examples/${demoStep.file}`}><Download size={16}/>{demoStep.action}</a> : <button onClick={() => { setSection(demoStep.section!); if (demoStep.section === 'resultados' && currentComparison) viewResult(currentComparison.id); }}>{demoStep.action}<ArrowRight size={16}/></button>}</section>}
        {simulationStep && !selected.archived && <section className="lab-next-step"><span>{simulationStep.number}</span><div><h2>{simulationStep.title}</h2><p>{simulationStep.detail}</p></div>{simulationStep.file ? <a className="button" href={`/api${base}/simulation/examples/${simulationStep.file}`}><Download size={16}/>{simulationStep.action}</a> : <button onClick={() => { setSection(simulationStep.section!); if (simulationStep.section === 'resultados' && currentComparison) viewResult(currentComparison.id); }}>{simulationStep.action}<ArrowRight size={16}/></button>}</section>}
        {!!selected.archived && <div className="ml-notice">Historial archivado: sus importaciones, modelos y resultados se conservan para consulta.</div>}
        {running && <div className="ml-progress" role="status"><RefreshCw size={17} className="spin"/> Cálculo en curso. El entrenamiento puede tardar varios minutos; la pantalla actualizará el resultado.</div>}
        <div className="lab-subnav" role="group" aria-label="Secciones del laboratorio">{[['datos', '01', 'Datos e importación'], ['versiones', '02', 'Modelos y versiones'], ['resultados', '03', 'Resultados']].map(([key, step, text]) => <button key={key} className={section === key ? 'selected' : ''} aria-pressed={section === key} onClick={() => setSection(key)}><span>{step}</span>{text}</button>)}</div>

        {section === 'datos' && <>
          {!!selected.demo && <section className="ml-panel"><div className="ml-panel-title"><div><h2>Un recorrido que puedes repetir</h2><p>Carga cada archivo después de completar el paso anterior. Los CSV también se abren en Excel.</p></div><span className="ml-tag">136,374 registros originales</span></div>
            <div className="lab-stages">{[
              ['01_historial_inicial.csv', 'V1 · punto de partida', 'Ene. 1998 – dic. 2000', 'Ya cargado al preparar la demo. Entrena la primera versión.'],
              ['02_datos_nuevos.xlsx', 'V2 · incorporar historia', 'Ene. – sep. 2001', 'Excel editable con las mismas ventas observadas del CSV. Impórtalo y entrena otra versión.'],
              ['03_ventas_posteriores.csv', 'Evaluación · comprobar', 'Oct. 2001 – mar. 2002', 'Impórtalos después de V2 y compara ambas versiones.'],
            ].map(([fileName, title, period, description], i) => <article key={fileName}><span className="lab-stage-number">0{i + 1}</span><h3>{title}</h3><b>{period}</b><p>{description}</p><a className="secondary button small" href={`/api${base}/examples/${fileName}`}><Download size={15}/>Descargar {fileName.endsWith('.xlsx') ? 'Excel' : 'CSV'}</a></article>)}</div>
            <p className="lab-helper">Puedes modificar el Excel para ensayar el flujo. Si cambias cantidades, identifica ese archivo como prueba: los cambios ya no son observaciones originales de la fuente pública.</p>
          </section>}
          {simulation && <section className="ml-panel"><div className="ml-panel-title"><div><h2>Ensayo diario con 120 SKU de RODA</h2><p>90 días iniciales, 30 días nuevos y 30 días posteriores para evaluar. Todos los registros de esta sección son sintéticos.</p></div><span className="ml-tag">18,000 filas de ensayo</span></div>
            <div className="lab-stages">{[
              ['01_historial_90_dias.csv', 'V1 · 90 días', simStages[0], 'Ya cargado. Entrena V1 sin usar los bloques posteriores.'],
              ['02_datos_nuevos_30_dias.xlsx', 'V2 · 30 días nuevos', simStages[1], 'Carga este Excel y entrena V2.'],
              ['03_ventas_posteriores_30_dias.csv', 'Evaluación · 30 días', simStages[2], 'Carga después de V2 y compara ambos modelos.'],
            ].map(([fileName, title, stage, description]: any, i) => <article key={fileName}><span className="lab-stage-number">0{i + 1}</span><h3>{title}</h3><b>{stage?.start} – {stage?.end}</b><p>{description}</p><a className="secondary button small" href={`/api${base}/simulation/examples/${fileName}`}><Download size={15}/>Descargar {fileName.endsWith('.xlsx') ? 'Excel' : 'CSV'}</a></article>)}</div>
            <p className="lab-helper">Fuente: <a href={d.simulation?.source_url} target="_blank" rel="noreferrer">Car Parts, DOI {d.simulation?.source_doi}</a>. Las fechas, las ventas por día y el vínculo con cada SKU son generados para este ensayo. Su precisión no demuestra precisión futura en la tienda.</p>
          </section>}
          <section className="ml-panel"><div className="ml-panel-title"><div><h2>{simulation ? 'Importar datos nuevos del ensayo' : 'Importar ventas observadas'}</h2><p>Una fila por producto y periodo. Las compras o ventas de prueba deben identificarse como tales en la procedencia.</p></div><span className="ml-tag">CSV / XLSX · máx. 8 MB</span></div>
            <p className="lab-helper">Columnas: <code>periodo</code>, <code>sku</code>, <code>unidades</code>. Periodo: {selected.frequency === 'monthly' ? 'AAAA-MM' : 'AAAA-MM-DD'}. Carga solo periodos completos anteriores al actual. Unidades enteras, cero si no hubo ventas, vacío si no se conoce. Excel: una hoja, sin fórmulas.</p>
            <div className="lab-upload"><label>Archivo de ventas<input key={did} type="file" accept=".csv,.xlsx" disabled={disabled} onChange={e => { setFile(e.target.files?.[0] || null); setPreview(null); setMapping({}); }}/></label><button disabled={disabled || !file} onClick={upload}><Upload size={17}/>{busy ? 'Revisando…' : 'Revisar archivo'}</button></div>
            {preview?.needs_mapping && <div className="lab-mapping"><h3>Relaciona las columnas</h3><p>Selecciona qué columna de tu archivo corresponde a cada dato.</p><div className="lab-fields">{['periodo', 'sku', 'unidades'].map(k => <label key={k}>{k}<select value={mapping[k] || ''} onChange={e => setMapping({ ...mapping, [k]: e.target.value })}><option value="">Seleccionar columna</option>{preview.headers.map((h: string) => <option key={h} value={h}>{h}</option>)}</select></label>)}</div><button className="secondary" disabled={disabled || Object.keys(mapping).length < 3} onClick={upload}>Validar columnas</button></div>}
            {preview && !preview.needs_mapping && <div className="lab-preview"><h3>Vista previa · {file?.name}</h3><p>{num(preview.accepted, 0)} filas nuevas de {num(preview.products, 0)} productos · periodo {preview.start || '—'} a {preview.end || '—'} · {num(preview.duplicates, 0)} duplicadas omitidas · {num(preview.missing, 0)} valores desconocidos · <b>{num(preview.invalid, 0)} errores</b></p>
              {preview.errors.length > 0 && <div className="lab-errors" role="alert">{preview.errors.map((e: any, i: number) => <p key={i}>Fila {e.row}: {e.message}</p>)}</div>}
              <table className="ml-table"><thead><tr><th>Periodo</th><th>SKU / serie</th><th>Unidades observadas</th></tr></thead><tbody>{preview.preview.map((r: any) => <tr key={r.sku + r.period}><td>{r.period}</td><td>{r.sku}</td><td>{r.units == null ? 'Desconocido' : num(r.units, 0)}</td></tr>)}</tbody></table>
              <button disabled={disabled || preview.invalid > 0 || !preview.accepted} onClick={() => execute(async () => { await api(`${base}/batches/${preview.id}/confirm`, { method: 'POST' }); setPreview(null); notify('Importación confirmada. Los datos originales se conservaron.'); })}>Confirmar importación<ArrowRight size={16}/></button>
            </div>}
          </section>
          <section className="ml-panel"><h2>Trazabilidad del historial</h2><p className="lab-source">Procedencia declarada: {selected.source}</p>{d.batches.length ? <table className="ml-table"><thead><tr><th>Archivo</th><th>Periodo</th><th>Filas nuevas</th><th>Desconocidos</th></tr></thead><tbody>{d.batches.map((b: any) => <tr key={b.id}><td><b>{b.filename}</b><small title={b.summary.file_sha256}>SHA-256: {b.summary.file_sha256.slice(0, 20)}…</small></td><td>{b.summary.start} → {b.summary.end}</td><td>{num(b.summary.accepted, 0)}</td><td>{num(b.summary.missing, 0)}</td></tr>)}</tbody></table> : <p>Aún no hay importaciones confirmadas.</p>}</section>
        </>}

        {section === 'versiones' && <>
          <section className="ml-panel"><div className="ml-panel-title"><div><h2>Entrenar y conservar cada versión</h2><p>Ridge, Poisson, Random Forest, Extra Trees y Hist. Gradient Boosting compiten con el mismo corte temporal.</p></div><button disabled={disabled || !d.stats.rows || (selected.demo && d.stats.end > '2001-09') || (simulation && d.stats.end > simStages[1]?.end)} onClick={() => job('train')}><RefreshCw size={16}/>Entrenar {`V${versions.length + 1}`}</button></div>
            {selected.demo && d.stats.end > '2001-09' && <div className="ml-notice">El bloque de octubre de 2001 a marzo de 2002 se reserva para evaluar V1 y V2. Entrenar otra versión con él invalidaría esa demostración.</div>}
            {simulation && d.stats.end > simStages[1]?.end && <div className="ml-notice">Los últimos 30 días se reservan para evaluar V1 y V2. Entrenar con ellos invalidaría la prueba posterior.</div>}
            <p className="lab-helper">Se elige el menor MAE de validación y se reajusta con el historial disponible. Predecir utiliza un modelo guardado; no lo reentrena. Ninguna versión se activa hasta compararla con ventas posteriores y superar al promedio histórico por al menos 1%. <a className="lab-notebook-link" href="https://colab.research.google.com/github/NEYEN111/REPUESTOS/blob/main/notebooks/RODA_ML_Datos_Reales.ipynb" target="_blank" rel="noreferrer">Abrir cuaderno completo en Colab</a></p>
            {!versions.length && <p>Importa un historial y ejecuta el primer entrenamiento.</p>}
            {versions.map((v: any) => <details className="lab-version" key={v.id} open={versions.length === 1}><summary><span><b>{v.label} · {v.report.winner}</b><small>Entrenado hasta {v.report.cutoff} · {num(v.report.refit_rows, 0)} objetivos observados</small></span><span className={`ml-tag ${selected.active_version === v.id ? 'success' : ''}`}>{selected.active_version === v.id ? 'Activa' : 'En evaluación'}</span></summary>
              <p>{v.report.reason} Validación posterior a {v.report.split}. MAE expresa error absoluto medio en unidades; menor es mejor.</p>
              <div className="lab-score-bars">{v.report.candidates.map((c: any) => <div key={c.model}><span>{c.model}</span><div><i style={{ width: `${Math.max(1, c.mae / Math.max(...v.report.candidates.map((s: any) => s.mae), 1) * 100)}%` }}/></div><b>{num(c.mae, 3)}</b></div>)}</div>
              <table className="ml-table"><thead><tr><th>Modelo</th><th>MAE</th><th>RMSE</th><th>WAPE %</th><th>R²</th></tr></thead><tbody>{[...v.report.candidates, ...(v.report.validation_references || [{ model: 'Promedio histórico', ...v.report.validation_baseline }])].map((c: any) => <tr key={c.model}><td>{c.model}{c.model === v.report.winner ? ' · elegido' : ''}</td><td>{num(c.mae, 3)}</td><td>{num(c.rmse, 3)}</td><td>{num(c.wape)}</td><td>{num(c.r2, 3)}</td></tr>)}</tbody></table>
              <p className="lab-helper"><b>{Math.min(...v.report.candidates.map((s: any) => s.mae)) < v.report.validation_baseline.mae ? 'Superó al promedio en validación.' : 'No superó al promedio en validación; uso exploratorio.'}</b> Ganar entre cinco modelos no garantiza aportar valor frente a una referencia simple ni mejorar con nuevos datos.</p>
              {v.report.zero_target_share != null && <p className="lab-helper">{num(v.report.zero_target_share * 100)}% de los periodos de validación no tienen ventas. La referencia cero ayuda a detectar este desequilibrio; no es una política de reposición.</p>}
              {v.report.candidates.find((c: any) => c.model === v.report.winner)?.segments && <details><summary>Error del modelo elegido según las ventas observadas</summary><table className="ml-table"><thead><tr><th>Periodos</th><th>Observaciones</th><th>MAE · unidades</th><th>Sesgo · unidades</th></tr></thead><tbody>{v.report.candidates.find((c: any) => c.model === v.report.winner).segments.map((s: any) => <tr key={s.segment}><td>{s.segment}</td><td>{num(s.n, 0)}</td><td>{num(s.mae, 3)}</td><td>{num(s.bias, 3)}</td></tr>)}</tbody></table><p>Sesgo positivo: estima de más. Sesgo negativo: estima de menos.</p></details>}
              <details><summary>Variables y límites de esta versión</summary><p>Rezagos, media, dispersión, ventas recientes, proporción de ceros, faltantes y calendario. Se calculan exclusivamente con periodos anteriores. La lista siguiente identifica las variables exactas usadas en esta versión.</p><p>Variables guardadas: {v.report.features.join(", ")}.</p><ul>{v.report.limitations.map((s: string) => <li key={s}>{s}</li>)}</ul><p className="lab-hash">Archivo: {v.report.model_sha256}</p><a className="secondary button small" href={`/api${base}/versions/${v.id}/download`}><Download size={15}/>Descargar {v.label} · joblib</a></details>
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
          </> : <Comparison result={result.data} versions={versions} label={label} active={selected.active_version} disabled={disabled} currentRows={d.stats.rows} activate={(id: string) => execute(async () => { await api(`${base}/datasets/${did}/activate`, { method: 'POST', body: { version: id } }); notify('Versión activada para este historial.'); })}/>}
        </section>}
        <section className="ml-panel lab-jobs"><div className="ml-panel-title"><div><h2>Actividad de cálculo</h2><p>El historial de trabajos conserva tanto resultados como errores.</p></div><button className="secondary small" onClick={data.reload} disabled={busy}><RefreshCw size={14}/>Actualizar</button></div>
          {!d.jobs.length ? <p>Aún no se han ejecutado cálculos.</p> : <table className="ml-table"><thead><tr><th>Trabajo</th><th>Estado</th><th>Resultado</th><th>Acción</th></tr></thead><tbody>{d.jobs.slice(0, 8).map((j: any) => <tr key={j.id}><td>{actionName[j.action]}<small>{j.created_at.slice(0, 19).replace('T', ' ')}</small></td><td><span className={`ml-tag ${j.status === 'done' ? 'success' : 'warning'}`}>{j.status === 'done' ? 'Completado' : j.status === 'running' ? 'En curso' : 'Revisar'}</span></td><td>{j.error || j.result?.winner || (j.status === 'running' ? 'Procesando historial y modelo…' : 'Disponible para consultar')}</td><td>{j.status === 'done' && <button className="secondary small" onClick={() => j.action === 'train' ? setSection('versiones') : viewResult(j.id)}>Ver resultado<ArrowRight size={14}/></button>}</td></tr>)}</tbody></table>}
          <details><summary>Auditoría del historial</summary>{d.activity.map((e: any) => <p key={e.id}>{e.created_at.slice(0, 19).replace('T', ' ')} · {eventName[e.action] || e.action} · usuario #{e.user_id}</p>)}</details>
        </section>
      </>}
    </>}
    {newOpen && <Modal title="Nuevo historial de ventas" onClose={() => { if (!busy) setNewOpen(false); }}><form className="lab-new" onSubmit={e => { e.preventDefault(); execute(async () => { const r = await api(base + '/datasets', { method: 'POST', body: { name, frequency, source } }); setDid(r.id); setSection('datos'); setNewOpen(false); setName(''); setSource(''); }); }}><p>Usa un historial independiente para cada fuente. Indica si procede de operaciones reales, de una fuente pública o de pruebas.</p><ErrorBox message={error}/><label>Nombre<input required maxLength={120} value={name} onChange={e => setName(e.target.value)}/></label><label>Frecuencia<select value={frequency} onChange={e => setFrequency(e.target.value)}><option value="monthly">Mensual · pronóstico del próximo mes</option><option value="daily">Diaria · pronóstico de siete días</option></select></label><label>Procedencia<textarea required maxLength={1000} value={source} onChange={e => setSource(e.target.value)} placeholder="Empresa o fuente, URL o referencia y tratamiento aplicado"/></label><button disabled={busy}>Crear historial</button></form></Modal>}
    {resetOpen && <Modal title={simulation ? 'Restablecer el ensayo' : 'Restablecer la demostración'} onClose={() => { if (!busy) setResetOpen(false); }}><p>Se archivará este historial con sus versiones y resultados. Se abrirá uno nuevo con el bloque inicial.</p><p>Los pedidos, productos y existencias de la tienda no cambian. Podrás consultar el historial anterior en el selector.</p><ErrorBox message={error}/><button disabled={busy} onClick={() => execute(async () => { const r = await api(`${base}/datasets/${did}/${simulation ? 'reset-simulation' : 'reset'}`, { method: 'POST' }); setDid(r.id); setResetOpen(false); setSection('datos'); notify('Nuevo historial preparado. El anterior se conserva archivado.'); })}>{busy ? 'Preparando…' : 'Archivar y restablecer'}</button></Modal>}
  </Frame>;
}

function Comparison({ result: r, versions, label, active, disabled, currentRows, activate }: any) {
  if (!r.scores) return null;
  const selectedScore = r.scores.find((s: any) => s.version === r.recommended);
  const validation = versions.find((v: any) => v.id === r.recommended)?.report;
  const passesFirstGate = validation?.candidates?.length && Math.min(...validation.candidates.map((s: any) => s.mae)) < validation.validation_baseline.mae * .99;
  const current = r.snapshot_rows === currentRows;
  const approved = current && !!selectedScore && selectedScore.mae < r.baseline.mae * .99 && (!!active || !!passesFirstGate);
  const canActivate = approved && r.recommended !== active && (active ? selectedScore.mae < (r.scores.find((s: any) => s.version === active)?.mae ?? Infinity) * .99 : passesFirstGate);
  const periods = Array.from(new Set<string>(r.periods.map((p: any) => p.period)));
  const max = Math.max(1, ...r.periods.flatMap((p: any) => [p.actual, p.predicted]));
  const series = [null, ...r.scores.map((s: any) => s.version)];
  const colors = ['#253441', '#bc4828', '#357d80'];
  const x = (i: number) => 70 + i * 720 / Math.max(1, periods.length - 1), y = (v: number) => 205 - v / max * 165;
  return <div className="lab-comparison"><h3>Evaluación posterior · {r.start} → {r.end}</h3><p>{num(r.rows, 0)} observaciones comunes · {num(r.products, 0)} series. {r.protocol} Se actualizan las variables con el pasado observado, sin reentrenar los modelos.</p>
    {!current && <div className="ml-notice lab-baseline-warning"><div><b>Comparación anterior.</b> Se añadieron observaciones después de este cálculo o el resultado no conserva la revisión actual. Vuelve a evaluar ambas versiones antes de activarlas.</div></div>}
    {r.baseline.mae <= Math.min(...r.scores.map((s: any) => s.mae)) && <div className="ml-notice lab-baseline-warning"><div><b>El promedio histórico obtuvo menor error que ambas versiones.</b> Estos resultados son exploratorios. No justifican automatizar decisiones de compra con los modelos evaluados.</div></div>}
    <div className={`lab-recommendation ${!approved ? 'lab-recommendation-warning' : ''}`}><div><b>{!current ? 'Repetir la comparación' : !approved ? 'No aprobar un modelo todavía' : r.recommended === active ? `Mantener ${label(active)}` : `Candidata aprobable: ${label(r.recommended)}`}</b><p>{!current ? 'Las métricas pertenecen a una revisión anterior del historial; no permiten activar una versión.' : !approved ? 'El promedio histórico es más preciso o la mejora no alcanza el 1% en estas ventas posteriores. Conserva los modelos como evidencia y reúne nuevos datos.' : 'Para activar, la candidata debe reducir el MAE al menos 1% frente a la activa y al promedio histórico. Esta regla no garantiza una mejora futura.'}</p></div>{canActivate && <button disabled={disabled} onClick={() => activate(r.recommended)}>Activar {label(r.recommended)}</button>}</div>
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
