import { useState } from 'react';
import { ArrowLeft, ArrowRight, BarChart3 } from 'lucide-react';
import './ml-explain.css';

const number = (value: number | null | undefined, digits = 3) => value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('es-PE', { maximumFractionDigits: digits });
const measures = {
  mae: { title: 'MAE', help: 'Error medio en unidades. Menor es mejor.' },
  rmse: { title: 'RMSE', help: 'Da más peso a los errores grandes. Menor es mejor.' },
  wape: { title: 'WAPE (%)', help: 'Error total respecto a las unidades vendidas. Puede superar 100%.' },
};
type Measure = keyof typeof measures;
const descriptions: Record<string, string> = {
  Ridge: 'Combina señales del historial y limita su peso para evitar ajustes excesivos.',
  Poisson: 'Modela cantidades no negativas a partir del historial.',
  'Random Forest': 'Promedia árboles que aprenden distintos patrones de ventas.',
  'Extra Trees': 'Combina árboles con cortes aleatorios para diversificar sus estimaciones.',
  'Hist. Gradient Boosting': 'Construye árboles sucesivos para corregir errores anteriores.',
};

function Bars({ rows, metric, chosen, onChoose }: { rows: any[]; metric: Measure; chosen?: string; onChoose?: (name: string) => void }) {
  const maximum = Math.max(.001, ...rows.map(r => Number.isFinite(r[metric]) ? r[metric] : 0));
  return <div className="explain-bars" aria-label={`Comparación por ${measures[metric].title}`}>
    {rows.map(row => <button type="button" key={row.model} className={chosen === row.model ? 'chosen' : ''}
      aria-pressed={onChoose ? chosen === row.model : undefined} disabled={!onChoose}
      onClick={() => onChoose?.(row.model)}>
      <span>{row.model}</span><span className="explain-track"><i style={{ width: `${Number.isFinite(row[metric]) ? row[metric] / maximum * 100 : 0}%` }}/></span>
      <b>{number(row[metric])}</b>
    </button>)}
  </div>;
}

export function MLExplanation({ data, navigate, openReady }: { data: any; navigate: (section: string) => void; openReady: (id: string) => void }) {
  const [step, setStep] = useState(0), [versionId, setVersionId] = useState('');
  const [metric, setMetric] = useState<Measure>('mae'), [modelName, setModelName] = useState('');
  const [comparisonId, setComparisonId] = useState(''), [periodChoice, setPeriodChoice] = useState('');
  const versions = data.versions || [];
  const version = versions.find((v: any) => v.id === versionId) || versions[versions.length - 1];
  const report = version?.report;
  const comparisons = (data.jobs || []).filter((j: any) => j.action === 'compare' && j.status === 'done' && j.result?.scores);
  const readyDataset = data.datasets?.find((item: any) => !item.archived && item.id !== data.selected.id && item.version_count >= 2 && item.comparison_count > 0);
  const comparison = comparisons.find((j: any) => j.id === comparisonId) || comparisons[0];
  const result = comparison?.result;
  const label = (id: string) => versions.find((v: any) => v.id === id)?.label || 'Versión guardada';
  const candidates = report?.candidates || [];
  const selected = candidates.find((c: any) => c.model === (modelName || report?.winner));
  const referenceRows = report?.validation_references || (report?.validation_baseline ? [{ model: 'Promedio histórico', ...report.validation_baseline }] : []);
  const periods = [...new Set<string>((result?.periods || []).map((p: any) => p.period))].sort();
  const period = periods.includes(periodChoice) ? periodChoice : periods[0];
  const rows = (result?.periods || []).filter((p: any) => p.period === period);
  const chartMax = Math.max(1, ...(result?.periods || []).flatMap((p: any) => [p.actual, p.predicted]));
  const chartX = (i: number) => 60 + i * 660 / Math.max(1, periods.length - 1);
  const chartY = (v: number) => 170 - v / chartMax * 135;
  const chartSeries = result ? [{ id: '', name: 'Observado', color: '#263442' }, ...result.scores.map((s: any, i: number) => ({ id: s.version, name: label(s.version), color: i % 2 ? '#286d70' : '#a63b23' }))] : [];
  const monthly = data.selected.frequency === 'monthly';
  const zeroShare = report?.zero_target_share;
  const notes = [
    `Nuestro ML usa ventas pasadas para estimar las unidades del ${monthly ? 'mes siguiente' : 'siguiente periodo de siete días'}.`,
    report ? `Comparamos cinco modelos con el mismo protocolo temporal. ${report.winner} obtuvo el menor MAE de validación.` : 'Primero entrenamos; después medimos el error con periodos posteriores.',
    result ? 'Comparamos las versiones sobre las mismas ventas posteriores. Cargar más datos no garantiza un menor error.' : 'V1 se conserva. Con datos nuevos entrenamos V2 y luego evaluamos ambas.',
  ];
  return <div className="ml-explain">
    <header className="explain-heading"><div><span className="ml-eyebrow">RECORRIDO PARA LA EXPOSICIÓN</span><h2>El ML, paso a paso</h2></div><span className="ml-tag">{step + 1} / 3</span></header>
    <nav className="explain-steps" aria-label="Pasos de la explicación">{['Qué predice', 'Los cinco modelos', '¿Mejoró la versión?'].map((title, i) => <button key={title} aria-current={i === step ? 'step' : undefined} onClick={() => setStep(i)}><b>0{i + 1}</b>{title}</button>)}</nav>
    {step === 0 && <section className="ml-panel explain-intro">
      <h3>¿Cuántas unidades se venderán?</h3><p>Pronóstico por producto para {monthly ? 'el siguiente mes' : 'los próximos siete días'}.</p>
      <div className="explain-flow">{[['Historial', 'Fecha · SKU · unidades'], ['Entrenamiento', 'Cinco modelos compiten'], ['Predicción', 'Unidades estimadas'], ['Evaluación', 'Estimación frente a ventas']].map(([title, detail], i) => <article key={title}><span>0{i + 1}</span><h4>{title}</h4><p>{detail}</p></article>)}</div>
      <div className="explain-facts"><div><b>{number(data.stats.rows, 0)}</b><span>filas del historial</span></div><div><b>{number(data.stats.products, 0)}</b><span>productos o series</span></div><div><b>{versions.length}</b><span>versiones guardadas</span></div></div>
      <p className="explain-caption">{data.selected.scenario === 'roda-calibrated' ? 'Ensayo sintético calibrado con una fuente pública.' : data.selected.demo ? 'Fuente pública: ventas mensuales anónimas de Car Parts.' : `Procedencia declarada: ${data.selected.source}`}</p>
    </section>}
    {step === 1 && (!report ? <Empty text="Entrena V1 para ver los cinco modelos y sus métricas." action={() => navigate('versiones')} ready={readyDataset} openReady={openReady}/> : <section className="ml-panel">
      <div className="explain-controls"><label>Versión<select value={version.id} onChange={e => { setVersionId(e.target.value); setModelName(''); }}>{versions.map((v: any) => <option key={v.id} value={v.id}>{v.label} · {v.report.winner}</option>)}</select></label><label>Métrica<select value={metric} onChange={e => setMetric(e.target.value as Measure)}>{Object.entries(measures).map(([key, value]) => <option key={key} value={key}>{value.title}</option>)}</select></label></div>
      <p>{measures[metric].help} Selecciona una barra para conocer el modelo.</p>
      <div className="explain-model-layout"><Bars rows={[...candidates, ...referenceRows]} metric={metric} chosen={modelName || report.winner} onChoose={setModelName}/><aside className="explain-model-note">
        <span className="ml-eyebrow">{selected ? 'CÓMO FUNCIONA' : 'REFERENCIA'}</span><h3>{modelName || report.winner}</h3>
        <p>{descriptions[modelName || report.winner] || (modelName === 'Cero ventas (diagnóstico)' ? 'Siempre predice cero. Detecta cuánto influyen los periodos sin ventas; no es una política de reposición.' : modelName === 'Último periodo equivalente' ? 'Repite la cantidad del periodo anterior de igual duración.' : 'Proyecta el promedio de la ventana histórica de cada producto.')}</p>
        <b>Elegido: {report.winner}</b><p>Menor MAE en validación. Cambiar el gráfico no cambia el modelo guardado.</p>
      </aside></div>
      <div className="explain-verdict"><b>{Math.min(...candidates.map((c: any) => c.mae)) < report.validation_baseline.mae ? 'El modelo superó al promedio en validación.' : 'El promedio ganó en validación.'}</b><span>{number(report.validation_rows, 0)} objetivos evaluados · {report.temporal_windows || 1} ventanas temporales.</span></div>
      {zeroShare != null && <p className="explain-caption">{number(zeroShare * 100, 1)}% de los objetivos no tienen ventas. Esto puede favorecer referencias simples; no demuestra por sí solo la causa.</p>}
      {!!selected?.segments?.length && <details><summary>Error con ventas y sin ventas</summary><table className="ml-table"><thead><tr><th>Periodos</th><th>Observaciones</th><th>MAE · unidades</th></tr></thead><tbody>{selected.segments.map((s: any) => <tr key={s.segment}><td>{s.segment}</td><td>{number(s.n, 0)}</td><td>{number(s.mae)}</td></tr>)}</tbody></table></details>}
    </section>)}
    {step === 2 && (!result ? <Empty text="Compara las versiones con ventas posteriores para mostrar su evolución." action={() => navigate('versiones')} ready={readyDataset} openReady={openReady}/> : <section className="ml-panel">
      <div className="explain-controls"><label>Comparación guardada<select value={comparison.id} onChange={e => { setComparisonId(e.target.value); setPeriodChoice(''); }}>{comparisons.map((j: any) => <option key={j.id} value={j.id}>{j.created_at.slice(0, 19).replace('T', ' ')} · {j.result.scores.map((s: any) => label(s.version)).join(' / ')}</option>)}</select></label><span className="ml-tag">Prueba posterior al entrenamiento</span></div>
      {result.snapshot_rows !== data.stats.rows && <p className="explain-caption">Resultado histórico: se añadieron datos desde esta comparación.</p>}
      <Bars metric="mae" rows={[...result.scores.map((s: any) => ({ ...s, model: label(s.version) })), { ...result.baseline, model: 'Promedio histórico' }]}/>
      <p className="explain-caption">MAE en unidades · menor es mejor · {number(result.rows, 0)} observaciones comunes.</p>
      <div className="explain-verdict"><b>{result.baseline.mae <= Math.min(...result.scores.map((s: any) => s.mae)) ? 'El promedio obtuvo el menor error.' : `${label([...result.scores].sort((a: any, b: any) => a.mae - b.mae)[0].version)} obtuvo el menor error frente al promedio.`}</b><span>{result.scores.length > 1 ? `De ${label(result.scores[0].version)} a ${label(result.scores[1].version)}: el MAE ${result.scores[1].mae < result.scores[0].mae ? 'bajó' : result.scores[1].mae > result.scores[0].mae ? 'subió' : 'no cambió'} (${number(result.scores[0].mae)} → ${number(result.scores[1].mae)}).` : 'Primera versión evaluada.'}</span></div>
      {!!periods.length && <><h3>Observado frente a estimado</h3>
        <div className="explain-legend">{chartSeries.map((s: any) => <span key={s.id}><i style={{ background: s.color }}/>{s.name}</span>)}</div>
        <svg className="explain-line-chart" viewBox="0 0 760 210" role="img" aria-label="Unidades totales por periodo. Selecciona un periodo debajo para consultar los valores exactos.">
          {[0, .5, 1].map(t => <g key={t}><line x1="55" x2="730" y1={chartY(chartMax * t)} y2={chartY(chartMax * t)} stroke="#dce1e5"/><text x="48" y={chartY(chartMax * t) + 4} textAnchor="end">{number(chartMax * t, 0)}</text></g>)}
          <line x1={chartX(periods.indexOf(period))} x2={chartX(periods.indexOf(period))} y1="25" y2="175" stroke="#8999a3" strokeDasharray="3 4"/>
          {chartSeries.map((s: any, i: number) => <g key={s.id}><polyline fill="none" stroke={s.color} strokeWidth="2.5" strokeDasharray={i === 2 ? '6 4' : undefined} points={periods.map((p, index) => { const r = result.periods.find((v: any) => v.period === p && (!s.id || v.version === s.id)); return r ? `${chartX(index)},${chartY(s.id ? r.predicted : r.actual)}` : ''; }).join(' ')}/>{periods.map((p, index) => { const r = result.periods.find((v: any) => v.period === p && (!s.id || v.version === s.id)); return r ? <circle key={p} cx={chartX(index)} cy={chartY(s.id ? r.predicted : r.actual)} r={p === period ? 5 : 3} fill={s.color}><title>{`${s.name} · ${p}: ${number(s.id ? r.predicted : r.actual)}`}</title></circle> : null; })}</g>)}
          {periods.map((p, i) => i % Math.max(1, Math.ceil(periods.length / 6)) === 0 || i === periods.length - 1 ? <text key={p} x={chartX(i)} y="198" textAnchor="middle">{p}</text> : null)}
        </svg>
        <label className="explain-period">Explorar periodo<select value={period} onChange={e => setPeriodChoice(e.target.value)}>{periods.map(p => <option key={p}>{p}</option>)}</select></label><div className="explain-period-cards" aria-live="polite"><article><span>Observado</span><b>{number(rows[0]?.actual, 1)}</b><small>unidades totales</small></article>{rows.map((r: any) => <article key={r.version}><span>{label(r.version)} · estimado</span><b>{number(r.predicted, 1)}</b><small>Diferencia: {number(r.predicted - r.actual, 1)} unidades</small></article>)}</div><p className="explain-caption">Totales de los productos evaluados. El MAE se calcula por producto y periodo.</p></>}
    </section>)}
    <footer className="explain-footer"><div><span>PARA EXPLICARLO</span><p>{notes[step]}</p></div><div className="explain-navigation"><button className="secondary" aria-label="Paso anterior" disabled={step === 0} onClick={() => setStep(step - 1)}><ArrowLeft size={17}/></button><button disabled={step === 2} onClick={() => setStep(step + 1)}>Siguiente<ArrowRight size={17}/></button></div></footer>
  </div>;
}

function Empty({ text, action, ready, openReady }: { text: string; action: () => void; ready?: any; openReady: (id: string) => void }) {
  return <section className="ml-panel explain-empty"><BarChart3 size={32}/><h3>Aún no hay resultados para este paso</h3><p>{text}</p>{ready && <button onClick={() => openReady(ready.id)}>Abrir ejemplo terminado<ArrowRight size={16}/></button>}<button className="secondary" onClick={action}>Ir a modelos y versiones<ArrowRight size={16}/></button></section>;
}
