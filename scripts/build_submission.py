"""Build the academic submission from measured, separately identified evidence."""
import csv
import hashlib
import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                               Spacer, Table, TableStyle, Image, KeepTogether,
                               FrameBreak, NextPageTemplate, Preformatted)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon

ROOT = Path(__file__).resolve().parents[1]
EVID = ROOT/'artifacts/entrega-2026-10-23'
OUT = ROOT/'output/entrega-2026-10-23'
OUT.mkdir(parents=True, exist_ok=True)
if not (EVID/'texto_informe.json').exists(): EVID=OUT/'Evidencias'
FONT = Path('C:/Windows/Fonts')
for label, name in [('TimesPE','times.ttf'), ('TimesPE-Bold','timesbd.ttf'), ('TimesPE-Italic','timesi.ttf')]:
    pdfmetrics.registerFont(TTFont(label, str(FONT/name)))
pdfmetrics.registerFontFamily('TimesPE', normal='TimesPE', bold='TimesPE-Bold', italic='TimesPE-Italic')
W,H = A4
LEFT,RIGHT,TOP,BOTTOM,GAP = 20*mm,18*mm,20*mm,20*mm,5*mm
CW = (W-LEFT-RIGHT-GAP)/2
INK=colors.HexColor('#152a3a')
GREY=colors.HexColor('#d9d9d9')
styles={
 'body':ParagraphStyle('body',fontName='TimesPE',fontSize=11,leading=12.5,
                       alignment=TA_JUSTIFY,spaceAfter=6,allowWidows=0,allowOrphans=0),
 'h1':ParagraphStyle('h1',fontName='TimesPE-Bold',fontSize=11.5,leading=13.5,
                     spaceBefore=9,spaceAfter=6,keepWithNext=True),
 'h2':ParagraphStyle('h2',fontName='TimesPE-Bold',fontSize=11,leading=12.5,
                     spaceBefore=7,spaceAfter=5,keepWithNext=True),
 'small':ParagraphStyle('small',fontName='TimesPE',fontSize=9,leading=10.5,spaceAfter=5),
 'caption':ParagraphStyle('caption',fontName='TimesPE-Italic',fontSize=9,leading=10.5,
                          spaceAfter=7,alignment=TA_LEFT),
 'cell':ParagraphStyle('cell',fontName='TimesPE',fontSize=9,leading=10.3),
 'head':ParagraphStyle('head',fontName='TimesPE-Bold',fontSize=9,leading=10.3,textColor=colors.white),
 'ref':ParagraphStyle('ref',fontName='TimesPE',fontSize=10,leading=11.5,leftIndent=12,
                      firstLineIndent=-12,spaceAfter=7,splitLongWords=True),
 'title':ParagraphStyle('title',fontName='TimesPE-Bold',fontSize=14,leading=16.5,
                        alignment=TA_CENTER,spaceAfter=7),
 'meta':ParagraphStyle('meta',fontName='TimesPE',fontSize=10,leading=12,
                       alignment=TA_CENTER,spaceAfter=5),
}
story=[]
def p(text, style='body'):
    text=str(text).replace('Hyndman y Athanasopoulos, s. f.', 'Hyndman y Athanasopoulos, 2021').replace('scikit-learn Developers, s. f.', 'Scikit-learn developers, s. f.-a').replace('La Figura 1 debe representar','La Figura 1 representa')
    return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
def add(text, style='body'):
    story.append(p(text,style))
def section(title): add(title,'h1')
def sub(title): add(title,'h2')
def table(title, headers, rows, fractions):
    add(title,'caption')
    values=[[p(v,'head') for v in headers]]+[[p(v,'cell') for v in row] for row in rows]
    t=Table(values,colWidths=[CW*f for f in fractions],repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([
      ('BACKGROUND',(0,0),(-1,0),INK),('GRID',(0,0),(-1,-1),.35,GREY),
      ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),5),
      ('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),
      ('BOTTOMPADDING',(0,0),(-1,-1),4),
      ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f2f5f7')]),
    ]))
    story.extend([t,Spacer(1,7)])
def arrow(d,x1,y1,x2,y2):
    d.add(Line(x1,y1,x2,y2,strokeColor=INK,strokeWidth=.7))
    if abs(y2-y1)>abs(x2-x1):
        s=1 if y2>y1 else -1
        d.add(Polygon([x2,y2,x2-2.5,y2-s*5,x2+2.5,y2-s*5],fillColor=INK,strokeColor=INK))
    else:
        s=1 if x2>x1 else -1
        d.add(Polygon([x2,y2,x2-s*5,y2-2.5,x2-s*5,y2+2.5],fillColor=INK,strokeColor=INK))
def box(d,x,y,w,h,lines):
    d.add(Rect(x,y,w,h,fillColor=colors.HexColor('#f4f6f7'),strokeColor=INK,strokeWidth=.65))
    for i,line in enumerate(lines):
        d.add(String(x+w/2,y+h/2+(len(lines)-1)*5-i*10,line,fontName='TimesPE',fontSize=8.5,textAnchor='middle'))
def architecture():
    d=Drawing(CW,243)
    box(d,54,211,130,27,['Usuario en navegador','sesión y rol'])
    box(d,25,150,CW-50,43,['Render','React y TypeScript','FastAPI y servicios de negocio'])
    arrow(d,CW/2,211,CW/2,193)
    box(d,0,79,73,47,['Neon','PostgreSQL','auditoría y estado'])
    box(d,83,79,73,47,['Runtime ML','joblib y hashes','proceso separado'])
    box(d,166,79,CW-166,47,['TheHive','DeepSeek','API externa'])
    for x in (36,119,202): arrow(d,x,150,x,126)
    box(d,25,11,CW-50,44,['Orquestación en el backend','herramientas autorizadas','aprobación humana para compras'])
    for x in (36,119,202): arrow(d,x,79,x,55)
    return d
def flow():
    d=Drawing(CW,253)
    stages=[('Orquestador','elige tareas'),('Calidad e inventario','datos y necesidad'),
            ('Compras y finanzas','alternativas y presupuesto'),('Auditor','contrasta expediente'),
            ('Administrador','aprueba o rechaza'),('Servicio transaccional','crea orden y auditoría')]
    for i,lines in enumerate(stages):
        y=218-i*40
        box(d,35,y,CW-70,30,lines)
        if i<5:arrow(d,CW/2,y,CW/2,y-10)
    d.add(String(2,4,'Demanda y pedidos participan si la tarea los requiere.',fontName='TimesPE-Italic',fontSize=8))
    return d
def fig(d,title):
    story.append(KeepTogether([d,p(title,'caption')]))
def image(path,title):
    from PIL import Image as PILImage
    path=Path(path)
    if path.exists():
        w,h=PILImage.open(path).size
        fig(Image(str(path),width=CW,height=CW*h/w),title)
def load(path, default=None):
    path=Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def build():
    data=load(EVID/'texto_informe.json')
    if not data: raise RuntimeError('Falta la fuente revisada del informe.')
    data['titulo']='Reposición asistida de repuestos mediante aprendizaje automático y coordinación multiagente en la nube'
    sections={s['id']:s for s in data['secciones']}
    def paragraphs(prefix):
        chosen=[s for key,s in sections.items() if key==prefix or key.startswith(prefix+'.')]
        for s in chosen:
            if prefix in ('1','2.1'): sub(s['id']+' '+s['titulo'])
            for text in s['parrafos']: add(text)
    add(data['titulo'],'title')
    add('Equipo del proyecto RODA · Ingeniería de Sistemas','meta')
    add('Informe técnico · 23 de octubre de 2026 · America/Lima','meta')
    story.append(FrameBreak())
    section('Resumen')
    add(data['resumen'])
    add('Palabras clave: '+ '; '.join(data['palabras_clave']),'small')
    section('1 Introducción')
    paragraphs('1')
    sub('Objetivos verificables')
    for i,text in enumerate(data['objetivos'],1):add(f'{i}. {text}')
    section('2 Materiales y métodos')
    paragraphs('2.1')
    sub('2.2 Arquitectura y controles cloud')
    add('La Figura 1 muestra el recorrido entre interfaz, servicios, persistencia y componentes inteligentes. El modelo predictivo y el LLM tienen contratos distintos. El primero calcula cantidades; el segundo interpreta consultas y devuelve decisiones estructuradas que el servidor valida.')
    fig(architecture(),'Figura 1. Arquitectura del prototipo desplegado. Fuente: elaboración propia a partir del código y render.yaml.')
    paragraphs('2.2')
    add('La persistencia externa se apoya en la separación de cómputo y almacenamiento de Neon (Neon, s. f.). La ejecución de evaluación registró Python 3.12.10, scikit-learn 1.7.2, numpy 2.2.6, pandas 2.2.3 y joblib 1.5.1. Los contratos de datos y las dependencias fijadas permiten repetir los cálculos con esas versiones.','small')
    sub('2.3 Datos y modelo predictivo')
    paragraphs('2.3')
    add('V1 utilizó enero de 1998 a diciembre de 2000 y validó julio a diciembre de 2000. V2 amplió el historial hasta septiembre de 2001 y validó abril a septiembre de 2001. La prueba reservó octubre de 2001 a marzo de 2002. Cada origen mensual requiere una ventana de doce meses con al menos ocho cantidades conocidas; los objetivos desconocidos no se imputan.','small')
    add('La Tabla 1 define la unidad de observación, los predictores y el tratamiento de valores desconocidos. La Tabla 2 detalla la configuración que se mantuvo fija durante la comparación.','small')
    table('Tabla 1. Variables del experimento mensual Car Parts', ['Variable','Definición y tratamiento'],[
      ('sku y periodo','Clave de serie anónima y mes AAAA-MM; identifican filas y cortes. El SKU no entra como predictor numérico.'),
      ('unidades','Conteo mensual observado. Cero significa ausencia de ventas; vacío significa desconocido. Objetivo: unidades del mes siguiente.'),
      ('lag1, lag2, lag3, lag6, lag12','Cantidades observadas a 1, 2, 3, 6 y 12 meses antes del origen. Nulos de entrada se imputan con la media dentro del pipeline.'),
      ('mean, std, recent','Media y desviación de la ventana de 12 meses; media de los últimos 3. Unidad: unidades por serie y mes.'),
      ('zero_share, missing','Proporción de ceros entre datos observados y número de faltantes en la ventana. Sin confundir desconocidos con cero.'),
      ('month_sin y month_cos','Codificación cíclica del mes previsto. Valores adimensionales calculados con el calendario.')
    ],[.33,.67])
    table('Tabla 2. Configuración común de los cinco candidatos', ['Algoritmo','Configuración fijada'],[
      ('Ridge','Media, indicador de faltantes, StandardScaler; alpha=10.'),
      ('Poisson','Media, indicador, escalado; alpha=0.1; max_iter=500.'),
      ('Random Forest','60 árboles, profundidad 10, mínimo 5 por hoja; n_jobs=2; semilla 42.'),
      ('Extra Trees','60 árboles, profundidad 10, mínimo 5 por hoja; n_jobs=2; semilla 42.'),
      ('Hist Gradient Boosting','150 iteraciones, 31 hojas, regularización L2=1; semilla 42; imputación con media.')
    ],[.40,.60])
    add('Los doce predictores y los hiperparámetros corresponden al laboratorio mensual, no al motor diario de referencia ni al conjunto extendido experimental. Todos los candidatos incluyen imputación con media e indicadores de faltantes. La selección usa el menor MAE de validación; el ganador se reajusta con los objetivos conocidos hasta el corte. Las estimaciones negativas se recortan a cero. El artefacto conserva variables, frecuencia, fecha, series admitidas y hash SHA-256.')
    add('MAE, RMSE y R² describen errores de regresión con propiedades distintas; la métrica principal permanece fijada antes de la prueba (Scikit-learn developers, s. f.-b). No se cambia el criterio después de observar qué alternativa gana.','small')
    sub('2.4 Agentes y supervisión humana')
    paragraphs('2.4')
    roles=load(EVID/'arquitectura-agentes.json')['roles']
    for role in roles:
        add(role['rol'],'h2')
        add(f"Objetivo: {role['objetivo']} Entrada: {role['entrada']} Herramienta autorizada: {', '.join(role['herramientas'])}. Salida: {role['salida']} Límite: {role['limite']} Aceptación: {role['aceptacion']}")
    sub('2.5 Protocolo de evaluación')
    paragraphs('2.5')
    add('El estudio nuevo fijó dos repeticiones por escenario y modalidad, límite de 360 s por análisis y controles de presupuesto, vigencia y ausencia de compras automáticas. Para las ocho preguntas del asistente se fijó un límite de 30 s por caso y se verificó información de la base, respuesta del proveedor y ausencia de costos privados.','small')
    add('Las pruebas automáticas de permisos, integridad y recuperación utilizan SQLite temporal y respuestas controladas; se separan de las llamadas reales del estudio del proveedor. El criterio funcional exige satisfacer todos los controles del caso. El tiempo se mide de inicio a término, incluyendo proveedor. Los percentiles de una muestra pequeña no se interpretan como garantía de servicio.')
    add('El 23 de octubre se repitieron 41 pruebas de agentes en 13.137 s y 11 del asistente en 1.555 s; todas finalizaron correctamente. Cubrieron rechazo por rol, aprobación atómica e idempotente, stock cambiado, JSON inválido, recuperación acotada y ausencia de costos privados en respuestas al cliente. Estos tiempos corresponden a pruebas locales con proveedor aislado, no a latencia del LLM real. Los archivos pruebas-agentes.txt y pruebas-asistente.txt conservan nombres, resultado y duración.','small')
    section('3 Resultados y discusión técnica')
    sub('3.1 Evaluación temporal del aprendizaje automático')
    run_summary=load(ROOT/'ml/evaluations/entrega-2026-10-23/resumen_ejecucion.json',{})
    # Fresh runs are selected only by their recorded completion, never by a better test score.
    runs=ROOT/'ml/evaluations/entrega-2026-10-23/ejecuciones'
    finished=[q/'resultados' for q in sorted(runs.glob('*')) if (q/'resultados/comparison.json').is_file()]
    run=finished[-1] if finished else ROOT/'ml/evaluations/carparts'
    comparison=load(run/'comparison.json')
    v1=load(run/'V1.json');v2=load(run/'V2.json')
    add(f"La Tabla 3 compara las mismas {comparison['rows']:,} observaciones posteriores de {comparison['products']:,} series, entre {comparison['start']} y {comparison['end']}. El avance temporal incorpora únicamente ventas ya observadas antes de cada mes. No constituye una predicción fija de seis meses realizada de una sola vez.")
    scores=comparison['scores']+[dict(version='Promedio',**comparison['baseline'])]
    table('Tabla 3. Prueba temporal común y referencia histórica', ['Método','MAE','RMSE','R²'],
       [(r['version'],f"{r['mae']:.4f}",f"{r['rmse']:.4f}",f"{r['r2']:.4f}") for r in scores],[.31,.23,.23,.23])
    add(f"V1 eligió {v1['winner']} y V2 eligió {v2['winner']} usando sus validaciones respectivas. El menor MAE de prueba corresponde a {min(scores,key=lambda r:r['mae'])['version']}. Un cálculo válido o un modelo ganador entre cinco candidatos no equivalen a superar una referencia simple. MAE se expresa en unidades por serie y mes; WAPE no es un porcentaje de exactitud.")
    add('El 79.53% de los objetivos de prueba son cero. Predecir siempre cero obtiene MAE 0.3867, inferior a los métodos de la Tabla 3, pero omite todas las ventas positivas. Se conserva como diagnóstico de dispersión, no como política de reposición. El promedio es la referencia operativa predefinida; que los modelos tampoco superen esta referencia exige mantenerlos como exploratorios.','small')
    plot=EVID/'ML/figura_2a_mae_84mm.png'
    if not plot.is_file():plot=ROOT/'ml/evaluations/carparts/03_evolucion_versiones.png'
    add('La Figura 2 representa el MAE de las dos versiones y de la referencia sobre la misma prueba temporal.','small')
    image(plot,'Figura 2. Error de predicción y comparación de versiones. Menor MAE es mejor. Fuente: evaluación temporal reproducible.')
    add('La ejecución completa del 23 de octubre duró 469.53 s localmente: 11 celdas sin error, diez ajustes para seleccionar cinco candidatos por versión y dos reajustes finales. La lectura del Excel verificó 24,066 filas contra el CSV original, incluidos los faltantes. MAE, RMSE y R² reprodujeron exactamente los resultados anteriores. Se comprobó la preservación SHA-256 de 17 archivos originales. El cuaderno ejecutado conserva estas salidas; no se atribuye su ejecución a Colab ni a Render.')
    sub('3.2 Comparación de modalidades y coordinación')
    agent=load(ROOT/'ml/evaluations/agents/entrega-2026-10-23.json',{})
    results=agent.get('results',[])
    if results:
        bymode=defaultdict(list)
        for r in results:bymode[r['mode']].append(r)
        add('La Tabla 4 presenta cada ejecución del equipo. Debajo se resumen las mismas pruebas con reglas y con un solo agente.','small')
        table('Tabla 4. Casos del equipo multiagente y resultado observado', ['Caso y rep.','Estado','Tiempo s','Solicitudes'],[
          (r['case']+' '+str(r['repetition']),'Cumple' if r['passed'] else 'Falla',f"{r['seconds']:.2f}",str(r['provider_attempts'])) for r in results if r['mode']=='multiagente'
        ],[.34,.23,.21,.22])
        for mode,rows in bymode.items():
            add(f"{mode}: {sum(bool(r['passed']) for r in rows)}/{len(rows)} cumplen; tiempo medio {mean(r['seconds'] for r in rows):.2f} s; {sum(r['provider_attempts'] for r in rows)} solicitudes al proveedor.",'small')
        add('Resultado esperado: presupuesto, propuesta dentro del límite; ofertas, selección válida; vencidas, bloqueo sin compras. Cada fila se identifica por caso y repetición en agents/entrega-2026-10-23.json, dentro de los anexos. Se conservan entrada, criterios, resultado, proveedor, fecha, versión y evidencia. Los tokens desconocidos de intentos fallidos no se contabilizan como gratuitos.','small')
        add(f"La comparación nueva contiene {len(results)} ejecuciones. Los casos prueban presupuesto, alternativas de proveedor y vigencia de ofertas. Las tres modalidades comparten servicios y controles Python. El denominador incluye fallos de formato y errores del proveedor, sin descartarlos. Los tiempos y tokens completos se incluyen en el archivo de evidencia.")
    else:
        add('La comparación nueva no finalizó al cerrar esta edición. La evidencia previa contiene tres casos con una repetición por modalidad; las tres modalidades superaron 3/3. Este resultado no prueba superioridad del equipo, que añadió llamadas y latencia.')
    add('La Figura 3 explica qué se coordina: una necesidad de inventario, alternativas de compra, restricciones y revisión. Los agentes utilizan el mismo proveedor LLM con contextos y herramientas diferentes; no son ocho modelos entrenados independientemente. Las decisiones observables y las herramientas se registran, sin publicar razonamiento interno del proveedor.')
    fig(flow(),'Figura 3. Coordinación para preparar una compra supervisada. Fuente: orquestador y servicios del prototipo.')
    add('En la demostración aislada de Render del 22 de octubre, los cinco casos de control se completaron. El caso de presupuesto propuso S/ 40.00 dentro de un límite de S/ 50.00 y conservó la aprobación humana. La exportación registra ocho llamadas del equipo. Esta prueba usa datos académicos temporales y no representa una compra comercial ni demuestra ahorro operativo real.')
    add('El siguiente fragmento adapta las llamadas del comparador a los servicios compartidos; la creación de una compra permanece en otra operación autenticada.','small')
    code_style=ParagraphStyle('code',fontName='Courier',fontSize=8,leading=10)
    story.append(Preformatted("stock = data.candidates(5)\nstate['plan'] = data.purchase_plan(\n    stock, 'costo', budget, True)\nstate['audit'] = data.audit_result(\n    run, state)",code_style))
    sub('3.3 Evaluación del asistente de la tienda')
    llm=load(ROOT/'ml/evaluations/agents/llm-entrega-2026-10-23.json',{})
    llm_results=llm.get('results',llm.get('cases',[]))
    if llm_results:
        add('La Tabla 5 presenta los ocho casos del asistente, su cumplimiento y la latencia observada con el proveedor real.','small')
        table('Tabla 5. Consultas del asistente y controles observados', ['Caso','Resultado','Tiempo s'],[
          (r.get('case',r.get('id','')), 'Cumple' if r.get('passed') else 'No cumple',str(r.get('seconds','—'))) for r in llm_results
        ],[.56,.26,.18])
        add(f"Se registraron {len(llm_results)} casos, de los cuales {sum(bool(r.get('passed')) for r in llm_results)} cumplieron los criterios definidos. La evaluación conserva solicitudes, verificaciones y proveedor efectivo sin claves. El catálogo es un conjunto de prueba aislado; el servicio no inventa ventas ni modifica el stock para responder consultas.")
    else:
        add('La evaluación nueva del asistente se conserva como pendiente si no finaliza. La prueba desplegada del 22 de octubre verificó precio, disponibilidad y compatibilidad de una pieza Bosch con Toyota Yaris. Las cuatro preguntas de la sustentación aislada fueron respondidas por el proveedor. Esta muestra acotada no garantiza ausencia general de alucinaciones.')
    sub('3.4 Evidencia del despliegue')
    cloud=load(EVID/'render.json',{'checks':[]})
    add('La Tabla 6 separa consultas y pruebas completadas en Render de los pasos que no finalizaron en la instancia gratuita.','small')
    table('Tabla 6. Recorrido comprobado en el sistema desplegado', ['Prueba','Estado y alcance'],[
      (r['name'],r['result']) for r in cloud.get('checks',[])
    ] or [('V1 e importación Excel','Verificados el 22 de octubre; 120,330 registros y V1 restaurados tras un despliegue.'),
          ('Predicción guardada','2,509 resultados válidos exportados el 22 de octubre; CSV con versión y hashes.'),
          ('V2 y evaluación cloud','Intento del 23 de octubre, resultado pendiente de consolidación.')],[.35,.65])
    add('La disponibilidad depende del plan y de la API externa. Render Free puede suspender la instancia por inactividad y su disco es efímero (Render, s. f.). El prototipo persiste el laboratorio y sus modelos en Neon y los restaura al iniciar. Esta recuperación no equivale a garantizar un planificador activo durante toda la jornada.')
    add('La prueba de V2 del 23 de octubre no llegó a una versión guardada en Render: el historial informó un reinicio del servidor. Por ello, no se ejecutó allí la comparación posterior. No se infiere la causa exacta del reinicio sin registros suficientes. La evidencia reproducible local cierra el ciclo completo; para una exposición cloud, el entrenamiento grande debe ejecutarse fuera de la instancia gratuita o en un entorno cuya capacidad se verifique antes.')
    sub('3.5 Interpretación y limitaciones')
    paragraphs('3.3')
    add('La comparación nueva del 23 de octubre amplió a dos repeticiones por caso y modalidad: reglas 6/6, agente único 4/6 y equipo 6/6. El agente único agotó reintentos de formato en los dos casos de presupuesto; el equipo recuperó tres salidas JSON inválidas y completó los casos. La muestra comparte tres escenarios fijos, por lo que la diferencia observada es exploratoria y no demuestra superioridad estadística. El uso de llamadas, latencia y tokens debe valorarse junto con la revisión especializada.')
    add('Los fallos del agente único se registraron como ProviderUnavailable después de tres errores de decodificación JSON en cada caso. No se confirmó truncamiento ni una causa única del formato recibido; el estudio conserva el fallo observable sin atribuirlo a una causa no demostrada.','small')
    section('4 Conclusiones')
    for i,text in enumerate(data['conclusiones']):
        if i==2:text='La coordinación de ocho roles produjo propuestas auditadas y mantuvo supervisión humana. En la comparación nueva, el equipo cumplió 6/6 ejecuciones, las reglas 6/6 y el agente único 4/6; este último presentó dos fallos de formato del proveedor. Los ocho casos del asistente cumplieron sus controles. Los resultados respaldan la integración bajo los escenarios ensayados, pero el mayor tiempo y número de llamadas impiden atribuir una ventaja general al equipo.'
        add(text)
    section('Referencias')
    refs=[
      'Godahewa, R., Bergmeir, C., Webb, G., Hyndman, R., y Montero-Manso, P. (2020). Car Parts Dataset (with Missing Values) (versión 2) [Conjunto de datos]. Zenodo. https://doi.org/10.5281/zenodo.4656022',
      'Godahewa, R., Bergmeir, C., Webb, G. I., Hyndman, R. J., y Montero-Manso, P. (2021). Monash Time Series Forecasting Archive. arXiv. https://doi.org/10.48550/arXiv.2105.06643',
      'Hyndman, R. J., y Athanasopoulos, G. (2021). Forecasting: Principles and Practice (3.ª ed.). OTexts. https://otexts.com/fpp3/toolbox.html',
      'Neon. (s. f.). Architecture overview. Recuperado el 23 de octubre de 2026 de https://neon.com/docs/introduction/architecture-overview',
      'Render. (s. f.). Deploy for Free. Recuperado el 23 de octubre de 2026 de https://render.com/docs/free',
      'Scikit-learn developers. (s. f.-a). Common pitfalls and recommended practices. Recuperado el 23 de octubre de 2026 de https://scikit-learn.org/stable/common_pitfalls.html',
      'Scikit-learn developers. (s. f.-b). Metrics and scoring. Recuperado el 23 de octubre de 2026 de https://scikit-learn.org/stable/modules/model_evaluation.html',
      'Wu, Q., Bansal, G., Zhang, J., Wu, Y., Li, B., Zhu, E., Jiang, L., Zhang, X., Zhang, S., Liu, J., Awadallah, A. H., White, R. W., Burger, D., y Wang, C. (2023). AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation. arXiv. https://doi.org/10.48550/arXiv.2308.08155',
    ]
    for ref in refs:add(ref,'ref')
    section('Anexo A Acceso y reproducción')
    add('Sistema: https://roda-repuestos.onrender.com\nRepositorio: https://github.com/NEYEN111/REPUESTOS\nColab: https://colab.research.google.com/github/NEYEN111/REPUESTOS/blob/main/notebooks/RODA_ML_Datos_Reales.ipynb','small')
    add('El paquete adjunto incluye el cuaderno ejecutado, insumos CSV y Excel, modelos joblib de la evaluación, resultados JSON y archivos de pruebas. El archivo README indica dependencias, comandos y variables requeridas. Los identificadores de ejecución y hashes se conservan en los artefactos. Las credenciales de acceso se entregan por separado al docente; no se publican claves API en el informe.')
    add('Recorrido de exposición: mostrar la fuente y los cortes; abrir V1; importar el Excel; ejecutar o consultar V2; incorporar ventas posteriores; comparar con la referencia; abrir el expediente de agentes; explicar una corrección y el control del Auditor; consultar precio o compatibilidad en el asistente. Una función que no complete la prueba en Render se identifica en la Tabla 6 y se demuestra por separado con evidencia local.')
    add('Identificación académica: sustituir Equipo del proyecto RODA por los nombres de los integrantes y agregar universidad, curso y docente antes de entregar. Estos datos personales no se han inferido.','small')
    def footer(c,doc):
        c.setFont('TimesPE',8);c.setFillColor(colors.HexColor('#555555'))
        c.drawString(LEFT,12*mm,'RODA · Reposición asistida de inventario')
        c.drawRightString(W-RIGHT,12*mm,str(doc.page))
    doc=BaseDocTemplate(str(OUT/'Informe_RODA.pdf'),pagesize=A4,leftMargin=LEFT,rightMargin=RIGHT,
                        topMargin=TOP,bottomMargin=BOTTOM,title=data['titulo'],author='Equipo del proyecto RODA')
    frames=[Frame(LEFT,BOTTOM,CW,H-TOP-BOTTOM,id='left',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0),
            Frame(LEFT+CW+GAP,BOTTOM,CW,H-TOP-BOTTOM,id='right',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)]
    title_height=32*mm
    first=[Frame(LEFT,H-TOP-title_height,W-LEFT-RIGHT,title_height,id='title',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0),
           Frame(LEFT,BOTTOM,CW,H-TOP-BOTTOM-title_height,id='left',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0),
           Frame(LEFT+CW+GAP,BOTTOM,CW,H-TOP-BOTTOM-title_height,id='right',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)]
    doc.addPageTemplates([PageTemplate(id='first',frames=first,onPage=footer,autoNextPageTemplate='regular'),
                          PageTemplate(id='regular',frames=frames,onPage=footer)])
    doc.build(story)
    print(OUT/'Informe_RODA.pdf')

if __name__=='__main__':build()
