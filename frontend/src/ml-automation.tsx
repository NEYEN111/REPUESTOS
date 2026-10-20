import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, ArrowRight, Clock3, CheckCircle2 } from 'lucide-react';
import { api, useLoad, useStore, Loading, ErrorBox } from './lib';
import { Frame } from './ml';
import './ml-lab.css';

const endpoint = '/admin/ml/automation';
const stamp = (value?: string) => value ? new Date(value).toLocaleString('es-PE', { timeZone: 'America/Lima' }) : 'Pendiente';
const n = (value: number) => value.toLocaleString('es-PE', { maximumFractionDigits: 3 });

export function MLAutomation() {
  const data = useLoad(endpoint), { notify } = useStore();
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const s = data.data, q = s?.quality || {};
  useEffect(() => {
    const timer = window.setInterval(data.reload, 10000);
    return () => window.clearInterval(timer);
  }, []);
  const action = async (path: string, body?: any) => {
    setBusy(true); setError('');
    try {
      const response = await api(endpoint + path, { method: 'POST', body });
      notify(path === '/review' ? response.message : response.enabled ? 'Revisión automática activada.' : 'Revisión automática pausada.');
      data.reload();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  };
  const active = s?.versions.find((v: any) => v.id === s.active_version);
  return <Frame title="Actualización del modelo" subtitle="De las ventas registradas a una nueva versión, con controles antes de activarla."
    action={<button disabled={busy || !s || (!!s.lease_until && new Date(s.lease_until).getTime() > Date.now())} onClick={() => action('/review')}><RefreshCw size={17} className={busy ? 'spin' : ''}/>{busy ? 'Revisando…' : 'Revisar ahora'}</button>}>
    <ErrorBox message={error || data.error}/>
    {!s ? data.error ? <button className="secondary" onClick={data.reload}>Reintentar</button> : <Loading/> : <>
      <section className="ml-panel auto-status">
        <div><span className="ml-tag">{s.enabled ? 'Programación activa' : 'Programación pausada'}</span>
          <h2>{s.pending_job ? 'Procesando el historial' : s.candidate ? 'Candidata en observación' : active ? `${active.label} · ${active.report.winner}` : 'Preparando el primer modelo de la tienda'}</h2>
          <p role="status">{s.message}</p></div>
        <button className="secondary" disabled={busy} onClick={() => action('/settings', { enabled: !s.enabled })}>{s.enabled ? 'Pausar programación' : 'Activar programación'}</button>
      </section>
      <div className="ml-stats">
        {[
          ['Cierres consecutivos', `${q.consecutive_days || 0} / 90`, 'Mayor continuidad disponible hasta ayer'],
          ['Productos preparados', n(q.eligible || 0), `De ${q.catalog_products || 0} productos en catálogo`],
          ['Observaciones con ventas', `${q.positive_days || 0} / 30`, 'Mínimo inicial en productos preparados'],
          ['Versión activa', active?.label || 'Sin modelo aprobado', active?.report.winner || 'No se activa por cumplir una fecha'],
        ].map(([label, value, note]) => <div className="ml-stat" key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></div>)}
      </div>
      <section className="ml-panel"><div className="ml-panel-title"><div><h2>Ensayo de 90 días para la presentación</h2><p>En el laboratorio puedes crear un historial sintético diario calibrado con Car Parts, entrenar V1, cargar 30 días desde Excel, entrenar V2 y comparar con 30 días posteriores.</p></div><Link className="secondary button" to="/gestion/ml/laboratorio">Abrir laboratorio<ArrowRight size={16}/></Link></div><p className="lab-helper">El ensayo usa SKU del catálogo, pero sus ventas y fechas no son operaciones de RODA. Por eso no incrementa el contador de cierres observados que aparece arriba.</p></section>
      <section className="ml-panel">
        <div className="ml-panel-title"><div><h2>Cómo se actualiza</h2><p>El carrito registra intención. Las ventas pagadas alimentan los cierres diarios y los pronósticos.</p></div><Clock3 size={21}/></div>
        <div className="auto-steps">
          {[
            ['01', 'Acumular', 'Se sincronizan días completos. Los días sin observación permanecen desconocidos.'],
            ['02', 'Entrenar', 'Cada 30 días nuevos, cinco algoritmos compiten en tres ventanas temporales.'],
            ['03', 'Comprobar', 'Cada candidata espera 28 días posteriores. La primera se compara con el promedio histórico; las demás, también con la activa.'],
            ['04', 'Activar', 'Debe reducir al menos 1% el MAE frente al promedio histórico y, si existe, frente a la activa. Si falla, no se activa.'],
          ].map(([step, title, text]) => <article key={step}><span className="lab-stage-number">{step}</span><h3>{title}</h3><p>{text}</p></article>)}
        </div>
        <p className="lab-helper"><b>Ninguna versión se aprueba solo por la validación.</b> También debe superar al promedio histórico con ventas posteriores que no vio al entrenarse. Una nueva versión puede ser V3 sin convertirse en la activa. El MAE mide cuántas unidades se equivoca el pronóstico semanal, en promedio; un valor menor es mejor. El umbral de 1% es una regla de aprobación, no una garantía de mejora futura.</p>
        <div className="auto-schedule"><span>Última revisión<br/><b>{stamp(s.last_check)}</b></span><span>Próxima comprobación del historial<br/><b>{s.enabled ? stamp(s.next_check) : 'Programación pausada'}</b></span><span>Frecuencia de entrenamiento<br/><b>30 días nuevos completos</b></span></div>
        <p>«Revisar ahora» ejecuta los mismos controles de la programación. No adelanta fechas ni crea ventas. Si el servidor estuvo apagado, revisará lo pendiente al iniciarse.</p>
      </section>
      <section className="ml-panel">
        <div className="ml-panel-title"><div><h2>Versiones de la tienda</h2><p>Las versiones y sus errores se conservan, incluso cuando no se aprueban.</p></div>
          <Link className="secondary button" to={`/gestion/ml/laboratorio?dataset=${s.dataset}`}>Datos y pronósticos<ArrowRight size={16}/></Link></div>
        {s.prediction && <div className="lab-helper"><b>Último pronóstico: {s.prediction.count} productos · corte {s.prediction.cutoff}.</b> <Link to={`/gestion/ml/laboratorio?dataset=${s.dataset}&result=${s.prediction.id}`}>Consultar cantidades previstas y descargar CSV</Link>. La versión utilizada queda asociada al resultado.</div>}
        {!s.versions.length ? <p>Aún no hay versiones operativas. Puedes consultar la demostración histórica en el laboratorio mientras se reúne el historial de la tienda.</p> :
          s.versions.map((v: any) => <details className="lab-version" key={v.id}><summary><span><b>{v.label} · {v.report.winner}</b><small>Corte: {v.report.cutoff} · {v.report.temporal_windows || 1} ventanas de validación</small></span><span className="ml-tag">{v.id === s.active_version ? 'Activa' : v.id === s.candidate ? 'En observación' : 'Conservada'}</span></summary>
            <p>{v.report.reason} {v.report.validation_protocol}</p>
            <table className="ml-table"><thead><tr><th>Algoritmo</th><th>MAE · menor es mejor</th><th>RMSE</th><th>WAPE %</th></tr></thead><tbody>
              {[...v.report.candidates, { model: 'Promedio histórico', ...v.report.validation_baseline }].map((m: any) => <tr key={m.model}><td>{m.model}{m.model === v.report.winner && ' · elegido'}</td><td>{n(m.mae)}</td><td>{n(m.rmse)}</td><td>{m.wape == null ? 'No calculable' : n(m.wape)}</td></tr>)}
            </tbody></table>
            {v.report.windows && <details><summary>Periodos utilizados en la validación</summary><table className="ml-table"><thead><tr><th>Ventana</th><th>Entrenamiento hasta</th><th>Desde el corte</th><th>Ventas evaluadas hasta</th></tr></thead><tbody>{v.report.windows.map((w: any, i: number) => <tr key={i}><td>{i + 1}</td><td>{w.training_end}</td><td>{w.validation_start}</td><td>{w.validation_end}</td></tr>)}</tbody></table><p>Cada ventana utiliza únicamente ventas conocidas antes de pronosticar. Los objetivos semanales evaluados no se solapan.</p></details>}
            <a className="secondary button small" href={`/api/admin/ml/lab/versions/${v.id}/download`}>Descargar {v.label} · joblib</a>
          </details>)}
      </section>
      <section className="ml-panel"><div className="ml-panel-title"><div><h2>Registro de revisiones</h2><p>Fechas en hora de Lima. Los procesos automáticos quedan identificados en la auditoría.</p></div><CheckCircle2 size={20}/></div>
        {!s.history.length ? <p>Sin revisiones registradas.</p> : <table className="ml-table"><thead><tr><th>Fecha</th><th>Origen</th><th>Resultado</th></tr></thead><tbody>{s.history.map((h: any, i: number) => {
          const detail = JSON.parse(h.detail);
          return <tr key={i}><td>{stamp(h.created_at)}</td><td>{h.action === 'revision_manual' ? 'Revisión manual' : h.action === 'programacion' ? 'Configuración' : 'Sistema'}</td><td>{detail.message || detail.reason || (h.action === 'programacion' ? detail.enabled ? 'Programación activada' : 'Programación pausada' : 'Cálculo registrado')}</td></tr>;
        })}</tbody></table>}
      </section>
      <div className="ml-notice">Los pronósticos se actualizan con nuevos cierres sin necesidad de reentrenar en cada venta. Las compras y los cambios de stock siguen bajo control del administrador.</div>
    </>}
  </Frame>;
}
