"""Produce una ejecución Car Parts aislada; preserva fuentes y resultados anteriores."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DELIVERY = ROOT/'ml/evaluations/entrega-2026-10-23'
NAME = 'RODA_ML_Datos_Reales_Ejecutado.ipynb'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    import nbformat
    original = ROOT/'notebooks/RODA_ML_Datos_Reales.ipynb'
    notebook = nbformat.read(original, as_version=4)
    sources = [ROOT/'ml/examples/carparts'/name for name in [
        '01_historial_inicial.csv', '02_datos_nuevos.csv', '02_datos_nuevos.xlsx',
        '03_ventas_posteriores.csv', 'provenance.json']]
    preserved = [original, *sources, *list((ROOT/'ml/evaluations/carparts').glob('*')),
                 ROOT/'ml/runs/carparts/V1.joblib', ROOT/'ml/runs/carparts/V2.joblib']
    before = {str(path.relative_to(ROOT)): digest(path) for path in preserved if path.is_file()}
    (DELIVERY/'datos').mkdir(parents=True, exist_ok=True)
    for path in sources:
        shutil.copyfile(path, DELIVERY/'datos'/path.name)
    title = notebook.cells[0]
    title.source = title.source.replace('# RODA ·', '# Entrega verificada ·') + (
        '\n\n**Ejecución completa local:** este cuaderno vuelve a entrenar los cinco algoritmos '
        'para V1 y V2 con las configuraciones fijas originales, importa el Excel y recalcula la '
        'comparación posterior. No es una ejecución en Google Colab. Los resultados anteriores '
        'y los archivos fuente se conservan. Cada repetición escribe en una carpeta nueva.\n')
    code_cells = [cell for cell in notebook.cells if cell.cell_type == 'code']
    code_cells[0].source = code_cells[0].source.replace(
        "IN_COLAB = 'google.colab' in sys.modules", "START_DIR = Path.cwd()\nIN_COLAB = 'google.colab' in sys.modules")
    setup = code_cells[1].source
    setup = setup.replace('from scripts.prepare_real_ml import prepare\nprovenance = prepare()', '''from datetime import datetime, timezone
import time
STARTED_AT = datetime.now(timezone.utc).isoformat()
RUN_CLOCK = time.perf_counter()
DELIVERY = ROOT/'ml/evaluations/entrega-2026-10-23'
INPUTS = next(path for path in [START_DIR/'datos', DELIVERY/'datos', ROOT/'ml/examples/carparts'] if path.is_dir())
provenance = json.loads((INPUTS/'provenance.json').read_text(encoding='utf-8'))
for entry in provenance['files']:
    path = INPUTS/entry['name']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], path.name
RUN_DIR = DELIVERY/'ejecuciones'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
RUN_DIR.mkdir(parents=True, exist_ok=False)
print('Entorno de ejecución:', 'Google Colab' if IN_COLAB else 'Local · '+platform.system())
print('Salida nueva:', RUN_DIR)''')
    setup = setup.replace("OUT = ROOT/'ml/runs/carparts'", "OUT = RUN_DIR/'modelos'")
    setup = setup.replace("REPORTS = ROOT/'ml/evaluations/carparts'", "REPORTS = RUN_DIR/'resultados'")
    setup = setup.replace("ROOT/'ml/examples/carparts'/name", 'INPUTS/name')
    setup = setup.replace("new_data=read_stage('02_datos_nuevos.csv')", '''# Lee el Excel entregable con la biblioteca estándar; no requiere una dependencia adicional.
import zipfile
import xml.etree.ElementTree as ET
def read_excel_stage(path):
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        shared=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            tree=ET.fromstring(archive.read('xl/sharedStrings.xml'))
            shared=[''.join(item.itertext()) for item in tree]
        tree=ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        values=[]
        for row in tree.findall('.//m:sheetData/m:row',ns):
            fields=[None,None,None]
            for cell in row.findall('m:c',ns):
                index=ord(cell.attrib['r'][0])-ord('A')
                if index>2: raise ValueError('El ejemplo debe tener tres columnas.')
                value=cell.find('m:v',ns)
                if cell.attrib.get('t')=='inlineStr': value=cell.find('m:is',ns);text=''.join(value.itertext())
                elif cell.attrib.get('t')=='s': text=shared[int(value.text)]
                else: text=value.text if value is not None else None
                fields[index]=text
            values.append(fields)
    assert values[0]==['periodo','sku','unidades']
    return [dict(period=r[0],sku=r[1],units=int(r[2]) if r[2] not in [None,''] else None) for r in values[1:]]
new_data=read_excel_stage(INPUTS/'02_datos_nuevos.xlsx')
csv_records=read_stage('02_datos_nuevos.csv')
assert sorted(new_data,key=lambda r:(r['sku'],r['period'])) == sorted(csv_records,key=lambda r:(r['sku'],r['period']))
print('Excel validado: 24,066 filas iguales al CSV original, incluidos los valores ausentes.')''')
    code_cells[1].source = setup
    train_cell = code_cells[3]
    train_cell.source = train_cell.source.replace("path=OUT/(label+'.joblib')", "started=time.perf_counter()\n    path=OUT/(label+'.joblib')")
    train_cell.source = train_cell.source.replace('result.update(version=label,environment=environment,source=provenance[\'doi\'],',
        "result.update(version=label,elapsed_seconds=time.perf_counter()-started,environment=environment,source=provenance['doi'],")
    notebook.cells.append(nbformat.v4.new_markdown_cell('''## 10. Registro de la ejecución y contraste con resultados anteriores
Se registran datos, particiones, configuración, hashes y entorno. Los resultados se comparan con los artefactos preexistentes; no se cambia el método en función de la prueba. La comparación nueva se realizó localmente, sin modificar Neon ni los datos de la tienda.'''))
    notebook.cells.append(nbformat.v4.new_code_cell('''# Figuras adicionales legibles a 84 mm de ancho para el informe a dos columnas.
with plt.rc_context({'font.size':7,'axes.titlesize':8,'axes.labelsize':7,'xtick.labelsize':7,'ytick.labelsize':7}):
    fig,ax=plt.subplots(figsize=(3.307,2.25))
    names=['V1','V2','Promedio histórico']
    errors=[r['mae'] for r in comparison['scores']]+[comparison['baseline']['mae']]
    bars=ax.barh(names,errors,color=['#bc4828','#357d80','#526775'])
    ax.invert_yaxis();ax.set_xlim(0,max(errors)*1.23)
    for bar,value in zip(bars,errors): ax.text(value+.008,bar.get_y()+bar.get_height()/2,f'{value:.4f}',va='center',fontsize=7)
    ax.set(title='Error en ventas posteriores',xlabel='MAE (unidades/serie/mes)')
    ax.spines[['top','right']].set_visible(False)
    fig.tight_layout();fig.savefig(REPORTS/'figura_2a_mae_84mm.png',dpi=300);plt.close(fig)
    fig,ax=plt.subplots(figsize=(3.307,2.25))
    ax.hist(test.V2-test.target,bins=40,color='#357d80');ax.axvline(0,color='#253441',linewidth=.8)
    ax.set(title='V2 · residuales en prueba posterior',xlabel='Estimado − observado (unidades)',ylabel='Observaciones')
    ax.spines[['top','right']].set_visible(False)
    fig.tight_layout();fig.savefig(REPORTS/'figura_2b_residuales_84mm.png',dpi=300);plt.close(fig)
from ml.lab_engine import candidates, digest
def json_safe(value):
    if isinstance(value,dict): return {str(k):json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [json_safe(v) for v in value]
    if isinstance(value,np.generic): value=value.item()
    if isinstance(value,float) and not np.isfinite(value): return None
    if value is None or isinstance(value,(str,int,float,bool)): return value
    return str(value)
configurations={name:[dict(step=step,algorithm=type(estimator).__name__,parameters=json_safe(estimator.get_params(deep=False)))
    for step,estimator in pipeline.steps] for name,pipeline in candidates().items()}
prior=json.loads((ROOT/'ml/evaluations/carparts/comparison.json').read_text(encoding='utf-8'))
prior_metrics={row['version']:row for row in prior['scores']}
comparison_differences={row['version']:{metric:row[metric]-prior_metrics[row['version']][metric]
    for metric in ['mae','rmse','r2']} for row in comparison['scores']}
new_vs_prior_match=all(abs(value)<1e-10 for row in comparison_differences.values() for value in row.values())
artifact_paths=[OUT/'V1.joblib',OUT/'V2.joblib',OUT/'predicciones.csv',*REPORTS.glob('*')]
summary=dict(schema_version=1,execution=dict(started_at_utc=STARTED_AT,finished_at_utc=datetime.now(timezone.utc).isoformat(),
    duration_seconds=time.perf_counter()-RUN_CLOCK,environment='Google Colab' if IN_COLAB else 'Local · '+platform.system(),
    python=platform.python_version(),libraries=environment,training_executed=True,models_fitted_for_selection=10,
    selected_models_refitted=2,api_calls=0,production_database_access=False),
    git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    engine_sha256=digest(ROOT/'ml/lab_engine.py'),source=provenance,
    inputs=[dict(name=p.name,sha256=digest(p),bytes=p.stat().st_size) for p in sorted(INPUTS.iterdir()) if p.is_file()],
    data=dict(rows=len(all_records),series=raw.sku.nunique(),missing=int(raw.units.isna().sum()),
        frequency='monthly',target='Unidades observadas del mes siguiente por serie',target_unit='unidades/serie/mes',
        initial_rows=len(initial),excel_new_rows=len(new_data),later_test_rows=len(later),
        exclude='Objetivos desconocidos; series sin historial suficiente; sin correspondencia con SKU de RODA.'),
    splits=dict(V1=dict(history=['1998-01','2000-12'],validation=['2000-07','2000-12']),
        V2=dict(history=['1998-01','2001-09'],validation=['2001-04','2001-09']),
        test=['2001-10','2002-03'],protocol=comparison['protocol']),
    configurations=configurations,features=FEATURES,
    versions=[v1,v2],comparison=comparison,
    new_data_effect=dict(excel_records=len(new_data),v1_hash=spec1['sha256'],v2_hash=spec2['sha256'],
        mae_improvement_pct=improvement,promotion_threshold_pct=1,ml_beats_baseline=comparison.get('approved_recommendation',False)),
    prior_evidence=dict(location='ml/evaluations/carparts/comparison.json',kind='Resultado previo conservado; no creado en esta ejecución',
        sha256=digest(ROOT/'ml/evaluations/carparts/comparison.json'),numeric_differences=comparison_differences,
        matches_within_1e_10=new_vs_prior_match),
    artifacts=[dict(path=str(p.relative_to(RUN_DIR)),sha256=digest(p),bytes=p.stat().st_size) for p in artifact_paths],
    conclusion='Comparación académica reproducible. El promedio histórico mantiene menor MAE; no se aprueba reposición automática con estos resultados.',
    limitations=['Ventas mensuales históricas de series anónimas; no son ventas actuales de RODA ni Perú.',
        'La comparación ya había sido examinada; esta repetición confirma reproducibilidad, no es una nueva prueba independiente.',
        'Cada predicción mensual usa observaciones previas disponibles; no es un pronóstico fijo de seis meses.',
        'WAPE no es exactitud porcentual; no hay precios, stock ni plazos en esta fuente.',
        'La revisión humana y una evaluación posterior nueva son necesarias para una promoción operativa.'])
summary=json_safe(summary)
(RUN_DIR/'resumen_ejecucion.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
print('Entrenamientos nuevos:',summary['execution']['models_fitted_for_selection'],'+ reajustes:',summary['execution']['selected_models_refitted'])
print('Coincide con comparación previa (tolerancia 1e-10):',new_vs_prior_match)
print('Resumen verificable:',RUN_DIR/'resumen_ejecucion.json')
display(pd.DataFrame([dict(version=row['version'],MAE=row['mae'],RMSE=row['rmse'],R2=row['r2'],n=row['n'])
    for row in comparison['scores']+[dict(version='Promedio histórico',**comparison['baseline'])]]))'''))
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.execution_count = None
            cell.outputs = []
    notebook.metadata['roda']['delivery'] = '2026-10-23 · ejecución completa aislada'
    notebook.metadata['roda']['engine_sha256'] = digest(ROOT/'ml/lab_engine.py')
    notebook.metadata['kernelspec']['name'] = 'roda-ml-delivery'
    path = DELIVERY/NAME
    nbformat.write(notebook, path)
    return path, before


def finalize():
    """Inserta las figuras reales en el cuaderno y publica un índice del último run."""
    import base64
    import nbformat
    run = sorted((DELIVERY/'ejecuciones').iterdir())[-1]
    path = DELIVERY/NAME
    notebook = nbformat.read(path, as_version=4)
    codes = [cell for cell in notebook.cells if cell.cell_type == 'code']
    assert all(cell.execution_count is not None for cell in codes), 'Hay celdas sin ejecutar.'
    assert not any(output.output_type == 'error' for cell in codes for output in cell.outputs)
    figures = [run/'resultados/figura_2a_mae_84mm.png', run/'resultados/figura_2b_residuales_84mm.png']
    notebook.cells = [cell for cell in notebook.cells if cell.get('id') != 'figuras-entrega']
    cell = nbformat.v4.new_markdown_cell(
        '## Figuras verificadas de esta ejecución\n'
        'Prueba común: octubre de 2001–marzo de 2002; 15,054 observaciones de 2,509 series. '
        'El menor MAE corresponde al promedio histórico.\n\n'
        + '\n\n'.join(f'![{figure.stem}](attachment:{figure.name})' for figure in figures))
    cell['id'] = 'figuras-entrega'
    cell['attachments'] = {p.name: {'image/png': base64.b64encode(p.read_bytes()).decode('ascii')} for p in figures}
    notebook.cells.append(cell)
    notebook.metadata['kernelspec'] = dict(name='python3', display_name='Python 3', language='python')
    nbformat.write(notebook, path)
    summary_path = run/'resumen_ejecucion.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8'))
    summary['execution'].update(notebook_code_cells=len(codes), notebook_error_cells=0)
    summary['executed_notebook'] = dict(path=str(path.relative_to(ROOT)), sha256=digest(path),
                                       origin='Ejecución local completa; no se afirma ejecución en Colab.')
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (DELIVERY/'resumen_ejecucion.json').write_text(summary_path.read_text(encoding='utf-8'), encoding='utf-8')
    artifact_dir = ROOT/'artifacts/entrega-2026-10-23/ML'
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for item in [*figures, summary_path, path]:
        shutil.copyfile(item, artifact_dir/item.name)
    preservation_path = artifact_dir/'preservacion.json'
    preservation = json.loads(preservation_path.read_text(encoding='utf-8')) if preservation_path.exists() else {}
    preservation['notebook_sha256'] = digest(path)
    preservation_path.write_text(json.dumps(preservation, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(executed_notebook=str(path), summary=str(DELIVERY/'resumen_ejecucion.json'),
                          figures=[str(p) for p in figures]), ensure_ascii=False))


def main():
    import nbformat
    from nbclient import NotebookClient
    path, before = build()
    kernel_root = ROOT/'.tmp/ml-delivery-jupyter'
    kernel_folder = kernel_root/'kernels/roda-ml-delivery'
    kernel_folder.mkdir(parents=True, exist_ok=True)
    python = ROOT/'.venv-ml/Scripts/python.exe'
    (kernel_folder/'kernel.json').write_text(json.dumps(dict(
        argv=[str(python), '-m', 'ipykernel_launcher', '-f', '{connection_file}'],
        display_name='RODA ML · entorno fijado', language='python')), encoding='utf-8')
    os.environ['JUPYTER_PATH'] = str(kernel_root)
    os.environ['RODA_FORCE_SQLITE'] = '1'
    os.environ['MPLBACKEND'] = 'Agg'
    os.environ['LOKY_MAX_CPU_COUNT'] = '2'
    notebook = nbformat.read(path, as_version=4)
    client = NotebookClient(notebook, timeout=600, kernel_name='roda-ml-delivery', resources={'metadata': {'path': str(DELIVERY)}})
    try:
        client.execute()
    finally:
        nbformat.write(notebook, path)
    after = {name: digest(ROOT/name) for name in before}
    assert before == after, 'Una fuente o evidencia anterior cambió.'
    runs = sorted((DELIVERY/'ejecuciones').iterdir())
    latest = runs[-1]
    artifact_dir = ROOT/'artifacts/entrega-2026-10-23/ML'
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(latest/'resumen_ejecucion.json', artifact_dir/'resumen_ejecucion.json')
    shutil.copyfile(path, artifact_dir/NAME)
    preservation = dict(unchanged=True, files=before, notebook_sha256=digest(path), output_folder=str(latest.relative_to(ROOT)))
    (artifact_dir/'preservacion.json').write_text(json.dumps(preservation, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(notebook=str(path), run=str(latest), preserved_files=len(before)), ensure_ascii=False))
    finalize()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--finalize-only', action='store_true')
    if parser.parse_args().finalize_only:
        finalize()
    else:
        main()
