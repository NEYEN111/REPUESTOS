"""Build the academic submission from measured, separately identified evidence."""
import csv
import hashlib
import json
import re
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
                               FrameBreak, NextPageTemplate, Preformatted, PageBreak)
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
FW = W-LEFT-RIGHT
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
    text=text.replace('\u2011','-').replace('\u2013','-').replace('\u2014','-')
    encoded=escape(str(text)).replace('\n','<br/>')
    encoded=re.sub(r'https?://[^\s<]+',lambda m:f'<link href="{m.group(0)}" color="#174b70">{m.group(0)}</link>',encoded)
    return Paragraph(encoded,styles[style])
def add(text, style='body'):
    story.append(p(text,style))
def section(title): add(title,'h1')
def sub(title): add(title,'h2')
def table(title, headers, rows, fractions, width=CW, source=None):
    values=[[p(v,'head') for v in headers]]+[[p(v,'cell') for v in row] for row in rows]
    t=Table(values,colWidths=[width*f for f in fractions],repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([
      ('BACKGROUND',(0,0),(-1,0),INK),('GRID',(0,0),(-1,-1),.35,GREY),
      ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),5),
      ('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),
      ('BOTTOMPADDING',(0,0),(-1,-1),4),
      ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f2f5f7')]),
    ]))
    elements=[p(title,'caption'),t,Spacer(1,7)]
    if len(rows)<=4 and width==CW:story.append(KeepTogether(elements))
    else:story.extend(elements)
    if source:add('Fuente: '+source,'small')
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
def image(path,title,width=CW):
    from PIL import Image as PILImage
    path=Path(path)
    if path.exists():
        w,h=PILImage.open(path).size
        fig(Image(str(path),width=width,height=width*h/w),title)

def wide_page():
    story.extend([NextPageTemplate('wide'),PageBreak()])

def web_crop(source,name,rectangle):
    """Crop a verified screenshot without changing or reconstructing its contents."""
    from PIL import Image as PILImage
    target=OUT/'Evidencias'/'Detalles_web'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    with PILImage.open(EVID/source) as original:original.crop(rectangle).save(target)
    return target
def load(path, default=None):
    path=Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def build():
    data=load(EVID/'texto_informe.json')
    demo=load(EVID/'render-demo.json',{})
    recovery=load(EVID/'render-provider-recovery.json',{})
    demo_image=EVID/'render-demo.jpg'
    demo_included=bool(demo and demo_image.is_file())
    if not data: raise RuntimeError('Falta la fuente revisada del informe.')
    data['titulo']='Reposición asistida de repuestos mediante aprendizaje automático y coordinación multiagente en la nube'
    data['resumen']=data['resumen'].replace('obtuvo MAE de 0,541','obtuvo un error absoluto medio de 0,541').replace('V1 y V2 obtuvieron 0,575 y 0,571','las versiones inicial y actualizada obtuvieron 0,575 y 0,571')
    sections={s['id']:s for s in data['secciones']}
    def paragraphs(prefix):
        chosen=[s for key,s in sections.items() if key==prefix or key.startswith(prefix+'.')]
        for s in chosen:
            if prefix in ('1','2.1'): sub(s['id']+' '+s['titulo'])
            for text in s['parrafos']:
                if s['id']=='2.2' and text.startswith('El acceso a las rutas de agentes exige'):
                    text=text.replace('El acceso a las rutas de agentes exige','En la configuración protegida, el acceso a las rutas de agentes exige',1)
                add(text)
    add(data['titulo'],'title')
    add('Equipo del proyecto RODA · Ingeniería de Sistemas','meta')
    add('Informe técnico · 23 de octubre de 2026 · America/Lima','meta')
    story.append(FrameBreak())
    section('Resumen')
    add(data['resumen'])
    add('Palabras clave: '+ '; '.join(data['palabras_clave']),'small')
    section('1 Introducción')
    paragraphs('1')
    add('La comparación de antecedentes se resume en la Tabla 7 del anexo B: se distinguen propósito, datos, técnica, evaluación, resultado y limitación. El vacío atendido es unir evidencia predictiva, restricciones transaccionales y revisión administrativa en un expediente reproducible, sin atribuir al prototipo resultados de los trabajos citados.','small')
    add('Los roles utilizan un modelo de lenguaje de gran tamaño (LLM) y se orientan a un objetivo acotado: consultan herramientas autorizadas, interpretan observaciones y eligen una decisión tipada. Su autonomía reside en delegar, seleccionar alternativas y pedir correcciones; el servidor conserva la autoridad de validar y escribir. El aprendizaje automático (ML) calcula cantidades mediante un contrato separado.')
    sub('Objetivos verificables')
    for i,text in enumerate(data['objetivos'],1):add(f'{i}. {text}')
    section('2 Materiales y métodos')
    paragraphs('2.1')
    sub('2.2 Arquitectura y controles cloud')
    add('La Figura 1 muestra el recorrido entre interfaz, servicios, persistencia y componentes inteligentes. El modelo predictivo y el LLM tienen contratos distintos. El primero calcula cantidades; el segundo interpreta consultas y devuelve decisiones estructuradas que el servidor valida.')
    fig(architecture(),'Figura 1. Arquitectura del prototipo desplegado. Fuente: elaboración propia a partir del código y render.yaml.')
    paragraphs('2.2')
    add('La persistencia externa se apoya en la separación de cómputo y almacenamiento de Neon (Neon, s. f.). La ejecución de evaluación registró Python 3.12.10, scikit-learn 1.7.2, numpy 2.2.6, pandas 2.2.3 y joblib 1.5.1. Los contratos de datos y las dependencias fijadas permiten repetir los cálculos con esas versiones.','small')
    add('requirements.txt fija FastAPI 0.135.1 y Uvicorn 0.41.0. El archivo de bloqueo del frontend registra React 19.3.0, TypeScript 5.9.3 y Vite 6.4.4. La configuración utiliza DATABASE_URL, LLM_PROVIDER, THEHIVE_API_KEY, THEHIVE_MODEL, ASSISTANT_ENABLED y SEED_PASSWORD; DEMO_ACCESS_ENABLED controla el acceso temporal de exposición. Solo se publican sus nombres.','small')
    sub('2.3 Datos y modelo predictivo')
    paragraphs('2.3')
    add('V1 utilizó enero de 1998 a diciembre de 2000 y validó julio a diciembre de 2000. V2 amplió el historial hasta septiembre de 2001 y validó abril a septiembre de 2001. La prueba reservó octubre de 2001 a marzo de 2002. Cada origen mensual requiere una ventana de doce meses con al menos ocho cantidades conocidas; los objetivos desconocidos no se imputan.','small')
    add('La Tabla 1 define la unidad de observación, los predictores y el tratamiento de valores desconocidos. La Tabla 2 detalla la configuración que se mantuvo fija durante la comparación.','small')
    table('Tabla 1. Variables del experimento mensual Car Parts', ['Variable','Definición y tratamiento'],[
      ('sku y periodo','Clave de serie anónima y mes AAAA-MM; identifican filas y cortes. El SKU no entra como predictor numérico.'),
      ('unidades','Conteo mensual observado. Cero significa ausencia de ventas; vacío significa desconocido. Objetivo: unidades del mes siguiente.'),
      ('lag1, lag2, lag3, lag6, lag12','Cantidades observadas a 1, 2, 3, 6 y 12 meses antes del mes previsto. Nulos de entrada se imputan con la media dentro del pipeline.'),
      ('mean, std, recent','Media y desviación de la ventana de 12 meses; media de los últimos 3. Unidad: unidades por serie y mes.'),
      ('zero_share, missing','Proporción de ceros entre datos observados y número de faltantes en la ventana. Sin confundir desconocidos con cero.'),
      ('month_sin y month_cos','Codificación cíclica del mes previsto. Valores adimensionales calculados con el calendario.')
    ],[.33,.67])
    add('Los rezagos representan persistencia y recurrencia; las estadísticas de ventana resumen nivel y variación; la proporción de ceros describe intermitencia; los faltantes distinguen calidad de observación de ausencia de ventas; seno y coseno representan el calendario sin un salto artificial entre diciembre y enero. Estas señales describen ventas observadas, no demanda perdida por quiebre de stock.','small')
    table('Tabla 2. Configuración común de los cinco candidatos', ['Algoritmo','Configuración fijada'],[
      ('Ridge','Media, indicador de faltantes, StandardScaler; alpha=10.'),
      ('Poisson','Media, indicador, escalado; alpha=0.1; max_iter=500.'),
      ('Random Forest','60 árboles, profundidad 10, mínimo 5 por hoja; n_jobs=2; semilla 42.'),
      ('Extra Trees','60 árboles, profundidad 10, mínimo 5 por hoja; n_jobs=2; semilla 42.'),
      ('Hist Gradient Boosting','150 iteraciones, 31 hojas, regularización L2=1; semilla 42; imputación con media.')
    ],[.40,.60])
    add('Los doce predictores y los hiperparámetros corresponden al laboratorio mensual, no al motor diario de referencia ni al conjunto extendido experimental. Todos los candidatos incluyen imputación con media e indicadores de faltantes. La selección usa el menor MAE de validación; el ganador se reajusta con los objetivos conocidos hasta el corte. La Tabla 11 del anexo C presenta los resultados individuales de los cinco candidatos y la referencia en cada ventana. Las estimaciones negativas se recortan a cero. El artefacto conserva variables, frecuencia, fecha, series admitidas y hash SHA-256.')
    add('MAE, RMSE y R² describen errores de regresión con propiedades distintas; la métrica principal permanece fijada antes de la prueba (Scikit-learn developers, s. f.-b). No se cambia el criterio después de observar qué alternativa gana.','small')
    sub('2.4 Agentes y supervisión humana')
    paragraphs('2.4')
    roles=load(EVID/'arquitectura-agentes.json')['roles']
    add('La Tabla 8 del anexo B especifica, para cada uno de los ocho roles, objetivo, entrada, herramienta autorizada, salida, límite y criterio de aceptación. Tener ocho roles disponibles no obliga a invocarlos en todas las tareas; un rol sin evidencia suficiente no debe producir una conclusión inventada.','small')
    sub('2.5 Protocolo de evaluación')
    paragraphs('2.5')
    add('El estudio nuevo fijó dos repeticiones por escenario y modalidad, límite de 360 s por análisis y controles de presupuesto, vigencia y ausencia de compras automáticas. Para las ocho preguntas del asistente se fijó un límite de 30 s por caso y se verificó información de la base, respuesta del proveedor y ausencia de costos privados.','small')
    add('Las pruebas automáticas de permisos, integridad y recuperación utilizan SQLite temporal y respuestas controladas; se separan de las llamadas reales del estudio del proveedor. El criterio funcional exige satisfacer todos los controles del caso. El tiempo se mide de inicio a término, incluyendo proveedor. Los percentiles de una muestra pequeña no se interpretan como garantía de servicio.')
    add('La Tabla 9 del anexo C presenta entradas, expectativas, aceptación, resultados y archivos de evidencia para casos normales, límites, error, privacidad y desempeño. Todas sus filas identifican fecha y versión. El protocolo conserva también los fallos; un resultado incompleto no se convierte en un caso satisfactorio.','small')
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
    add('Fuente: comparison.json de la ejecución local del 23/10/2026; n=15,054 pares serie-mes. MAE y RMSE: unidades por serie y mes; R²: adimensional. V1 y V2 usan exactamente los mismos objetivos observados.','small')
    add(f"V1 eligió {v1['winner']} y V2 eligió {v2['winner']} usando sus validaciones respectivas. El menor MAE de prueba corresponde a {min(scores,key=lambda r:r['mae'])['version']}. Un cálculo válido o un modelo ganador entre cinco candidatos no equivalen a superar una referencia simple. MAE se expresa en unidades por serie y mes; WAPE no es un porcentaje de exactitud.")
    add('El 79.53% de los objetivos de prueba son cero. Predecir siempre cero obtiene MAE 0.3867, inferior a los métodos de la Tabla 3, pero omite todas las ventas positivas. Se conserva como diagnóstico de dispersión, no como política de reposición. El promedio es la referencia operativa predefinida; que los modelos tampoco superen esta referencia exige mantenerlos como exploratorios.','small')
    add('En los 3,081 objetivos con ventas positivas, V2 registró MAE 1.2909 y sesgo -1.2718 unidades: subestimó esas ventas. El análisis por segmento impide interpretar un error global bajo, dominado por ceros, como capacidad suficiente de abastecimiento. Los segmentos y su tamaño se conservan en comparison.json.','small')
    plot=EVID/'ML/figura_2a_mae_84mm.png'
    if not plot.is_file():plot=ROOT/'ml/evaluations/carparts/03_evolucion_versiones.png'
    add('La Figura 2 representa el MAE de las dos versiones y de la referencia sobre la misma prueba temporal.','small')
    image(plot,'Figura 2. Error de predicción y comparación de versiones. Menor MAE es mejor. Fuente: evaluación temporal reproducible.')
    add('La reducción relativa de MAE de V2 frente a V1 fue 0.646%, por debajo del umbral de promoción del 1%. Además, ninguna versión superó el promedio. El promedio alcanzó menor MAE, aunque V2 tuvo menor RMSE y mayor R²: esta diferencia refleja que las métricas penalizan de forma distinta los errores grandes. La selección conserva MAE como criterio previo.','small')
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
    if demo_included:
        add('Para la entrega se habilitó un acceso de demostración con dos botones, administrador y cliente, sin contraseña. Se conservaron las sesiones y los controles asociados al rol, pero se permitió que cualquier visitante eligiera administrador. Es una configuración de exposición, sin protección de identidad. Se desactiva con DEMO_ACCESS_ENABLED=false, que invalida sus sesiones temporales; las contraseñas originales permanecen. La Figura 7 y render-demo.json documentan la comprobación final del acceso.','small')
        demo_checks=demo.get('checks',[])
        demo_passed=sum(bool(row.get('passed')) for row in demo_checks)
        add(f"En la revisión final del acceso se completaron {demo_passed}/{len(demo_checks)} comprobaciones satisfactorias. Las consultas de pronósticos, evaluación, laboratorio y expedientes de agentes respondieron correctamente. La sesión cliente recibió 403 al intentar consultar el ML administrativo. Estos controles son de consulta y permisos; no crean ventas ni órdenes.",'small')
        for row in demo_checks:
            if row.get('provider')=='catalog' and not row.get('passed'):
                add(f"La consulta comercial final tardó {row.get('seconds')} s y respondió mediante catálogo, no mediante el LLM. El precio y la disponibilidad se conservaron, pero ese resultado no satisface el criterio de respuesta del proveedor externo. La configuración de una API no garantiza que atienda una solicitud. Se conserva este fallo junto a las ocho consultas anteriores correctas, sin reemplazarlo por ellas.",'small')
        if recovery.get('passed') and recovery.get('mode')=='thehive':
            add(f"En una comprobación posterior, fechada el 23/10/2026 a las 13:58, la misma consulta obtuvo HTTP {recovery['http_status']} mediante TheHive en {recovery['seconds']} s, con precio S/ 160.00 y disponibilidad de 14 unidades. Se endureció la validación del adaptador para rechazar respuestas incompletas o ambiguas y registrar metadatos seguros. La causa del primer JSON inválido no se confirmó; una respuesta posterior correcta no prueba que el cambio haya causado la recuperación ni garantiza disponibilidad continua. render-provider-recovery.json conserva este resultado por separado.",'small')
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
    story.append(FrameBreak())
    add('El paquete adjunto incluye el cuaderno ejecutado, insumos CSV y Excel, modelos joblib de la evaluación, resultados JSON y archivos de pruebas. El archivo README indica dependencias, comandos y variables requeridas. Los identificadores de ejecución y hashes se conservan en los artefactos. Las claves API permanecen fuera del informe. Durante el acceso temporal de exposición no se requiere contraseña para elegir administrador o cliente; fuera de ese modo se conserva el inicio de sesión original.' if demo_included else 'El paquete adjunto incluye el cuaderno ejecutado, insumos CSV y Excel, modelos joblib de la evaluación, resultados JSON y archivos de pruebas. El archivo README indica dependencias, comandos y variables requeridas. Los identificadores de ejecución y hashes se conservan en los artefactos. Las credenciales de acceso se entregan por separado al docente; no se publican claves API en el informe.')
    add('Recorrido de exposición: mostrar la fuente y los cortes; abrir V1; importar el Excel; ejecutar o consultar V2; incorporar ventas posteriores; comparar con la referencia; abrir el expediente de agentes; explicar una corrección y el control del Auditor; consultar precio o compatibilidad en el asistente. Una función que no complete la prueba en Render se identifica en la Tabla 6 y se demuestra por separado con evidencia local.')
    add('La ejecución de resultados está fijada al código a89d21d38dd88f8f38dc3dcefefa5b2045a9c0f5 y a los archivos fechados el 23/10/2026. Las mejoras posteriores de acceso de demostración no cambian esos resultados experimentales. El manifiesto del ZIP permite comprobar tamaño y SHA-256 de cada artefacto. No se incluyen variables de entorno con sus valores, claves de proveedor ni datos personales.','small')
    if recovery.get('passed'):
        add(f"La última consulta desplegada verificada corresponde a la revisión {recovery['code_version']}, fechada el 23/10/2026. Su evidencia de recuperación es independiente del código de los experimentos históricos y se conserva en render-provider-recovery.json.",'small')
    add('El código completo de la aplicación se obtiene del repositorio GitHub. El ZIP es el paquete de informe, datos, modelos y evidencias, con los componentes necesarios para revisar el experimento; no sustituye el clon del repositorio para iniciar toda la tienda. Los comandos de reproducción se ejecutan desde ese clon, según el README.','small')

    wide_page()
    section('Anexo B Antecedentes y contrato de los agentes')
    add('La Tabla 7 compara los antecedentes empleados y delimita qué parte se reutilizó en este estudio. Son referencias metodológicas; sus resultados no se atribuyen a RODA.','small')
    table('Tabla 7. Comparación de antecedentes y vacío atendido',
          ['Antecedente','Propósito, técnica, datos y resultado','Límite y relación con RODA'],[
        ('Godahewa et al. (2021); dataset (2020)',
         'Archivo público de series con protocolos, referencias y métricas comparables. Car Parts aporta 2,674 series mensuales anónimas (1998-2002) con faltantes; posibilita repetir evaluaciones sobre una fuente licenciada.',
         'No aporta SKU, precios ni stock de RODA. Se reutilizó la fuente y su trazabilidad; se evaluaron cinco candidatos con cortes propios.'),
        ('Hyndman y Athanasopoulos (2021)',
         'Marco metodológico para referencias simples, error fuera de muestra y separación temporal. Su resultado es una guía de evaluación, no un experimento con ventas de esta tienda.',
         'No implementa la operación de compras. RODA aplica una referencia de doce meses y conserva un resultado negativo de promoción.'),
        ('Wu et al. (2023)',
         'AutoGen combina agentes conversacionales, herramientas y participación humana; describe colaboración y evaluaciones en tareas propias. Sus métricas no se trasladan a este estudio de ventas.',
         'No es una solución específica de repuestos ni una biblioteca instalada aquí. RODA implementa roles propios con auditoría y aprobación transaccional.')
    ],[.17,.48,.35],width=FW,source='síntesis de las referencias citadas; no es un metaanálisis.')
    add('La Tabla 8 reúne los siete elementos exigidos para cada agente. Las herramientas son contratos Python de lectura o validación; el modelo no recibe una conexión SQL ni permiso para ejecutar compras. La aceptación final combina decisiones tipadas con controles autoritativos del servidor.','small')
    role_rows=[
        ('Orquestador','Objetivo: elegir equipo y estrategia. Entrada: tarea, presupuesto y contexto. Herramienta: contexto. Salida: delegación y mensajes. Límite: roles obligatorios fijados por servidor; opcionales con evidencia; tres turnos. Aceptación: equipo válido, sin pronósticos ni incidentes inventados.'),
        ('Calidad de datos','Objetivo: detectar inconsistencias. Entrada: controles y procedencia. Herramienta: calidad. Salida: continuar, revisar o bloquear con hallazgos. Límite: lectura, sin corregir registros. Aceptación: transmitir los errores bloqueantes al Auditor y no afirmar verificaciones ajenas a la herramienta.'),
        ('Demanda ML','Objetivo: interpretar vigencia predictiva. Entrada: contrato, corte, hash y corrida. Herramienta: demanda. Salida: usar o descartar pronóstico. Límite: opcional; no entrena ni extrapola. Aceptación: corte del día anterior, hash vigente y ausencia de observaciones; de otro modo, política de inventario.'),
        ('Inventario','Objetivo: calcular necesidad neta. Entrada: stock, reservas, mínimos, máximos, tránsito y pronóstico válido. Herramientas: inventario y demanda. Salida: candidatos y cantidades justificadas. Límite: veinte productos, sin alterar stock. Aceptación: cálculo Python y distinción entre físico, reservado y en tránsito.'),
        ('Compras y proveedores','Objetivo: comparar alternativas. Entrada: candidatos, presupuesto y ofertas vigentes. Herramientas: ofertas y demanda. Salida: proveedor, cantidad, importe, cobertura y justificación. Límite: elegir offer_id registrado; lotes recalculados en Python. Aceptación: vigencia, costo viable, presupuesto y explicación de alternativas dominadas.'),
        ('Finanzas','Objetivo: revisar límite y margen. Entrada: plan, costos y precios. Herramienta: finanzas. Salida: conformidad o corrección a Compras. Límite: presupuesto no equivale a efectivo, margen no es ganancia neta. Aceptación: importe dentro del límite y ningún costo mayor o igual al precio.'),
        ('Pedidos y envíos','Objetivo: detectar incidencias. Entrada: estados, fechas, pagos y tracking. Herramienta: pedidos. Salida: atrasos o falta de seguimiento. Límite: opcional, sin confirmar pagos ni entregas ni enviar contactos al modelo. Aceptación: hallazgos derivados de fechas y estados registrados.'),
        ('Auditor','Objetivo: contrastar el expediente. Entrada: calidad, necesidad, alternativas, finanzas y correcciones. Herramienta: auditoría. Salida: pasar o bloquear con pendientes. Límite: no aprueba compras. Aceptación: sin error bloqueante, presupuesto y evidencia vigentes; observaciones resueltas antes del acto del administrador.')
    ]
    table('Tabla 8. Responsabilidades, herramientas y controles de los ocho roles',
          ['Rol','Objetivo, entrada, herramienta, salida, límite y aceptación'],role_rows,[.15,.85],width=FW,
          source='backend/services/agents.py, agent_data.py y arquitectura-agentes.json; revisión del 23/10/2026.')
    add('Supervisión humana: el administrador aprueba o rechaza después del Auditor. La aprobación vuelve a validar inventario y ofertas, usa una clave idempotente y crea órdenes dentro de una transacción. Confirmar recepciones, pagos o entregas sigue siendo una operación independiente. Los registros públicos muestran decisiones, herramientas y comprobaciones, sin cadena de razonamiento interna.','small')

    wide_page()
    section('Anexo C Protocolo, evidencia y cumplimiento')
    add('La Tabla 9 cierra el vínculo entre entrada, expectativa, resultado y aceptación. E1 identifica la comparación de agentes; E2, las ocho consultas del asistente; E3, las pruebas aisladas; E4, el notebook ejecutado y sus resultados; E5, el registro del despliegue. Todos los resultados que siguen se observaron el 23/10/2026 con el código a89d21d; la exportación histórica adicional de Render conserva su fecha del 22/10.','small')
    table('Tabla 9. Matriz de protocolo: normalidad, límites, fallos y desempeño',
          ['Caso y entrada','Esperado y aceptación','Observado y métrica','Evidencia verificable'],[
        ('Normal: CONTROL-001, ofertas y presupuesto fijados.',
         'Propuesta dentro del límite, ofertas vigentes y ninguna compra automática.',
         'Reglas 6/6 y equipo 6/6 cumplen en tres escenarios con dos repeticiones; agente único 4/6. Los fallos permanecen en el denominador.',
         'E1: Agentes/entrega-2026-10-23.json; caso, modalidad y repetición.'),
        ('Límite: todas las ofertas del producto vencidas.',
         'Bloqueo; no elegir una oferta vencida ni crear orden.',
         'Las dos repeticiones por cada una de las tres modalidades cumplieron los controles; estado de bloqueo y ausencia de compra.',
         'E1: case=vencidas; criterios de vigencia, presupuesto y escrituras.'),
        ('Error: respuesta JSON inválida o fallo transitorio del proveedor.',
         'Corrección acotada; agotados los intentos, registrar error sin compras.',
         'El equipo recuperó tres JSON inválidos. El agente único falló en dos ejecuciones de presupuesto tras tres errores de decodificación cada una.',
         'E1: requests y errors; E3: test_invalid_provider_decision_is_corrected_without_writes.'),
        ('Integridad: stock cambia antes de aprobar; repetición de la aprobación.',
         'Bloquear evidencia cambiada; una repetición no duplica compras.',
         'Pruebas aisladas de stock, transacción, rollback e idempotencia satisfactorias. Proveedor controlado: no son llamadas reales.',
         'E3: pruebas-agentes.txt; nombres changed_stock y atomic_and_idempotent.'),
        ('Privacidad: usuario solicita costo de compra y cambio de stock al asistente.',
         'No revelar costo privado ni ejecutar escrituras; responder con catálogo permitido.',
         'Caso de manipulación/privacidad cumplió con proveedor real. Las ocho consultas del asistente pasaron sus controles.',
         'E2: llm-entrega-2026-10-23.json; respuesta, criterios y proveedor efectivo.'),
        ('Acceso: empleado intenta aprobar o alterar ofertas.',
         'Rechazo del rol y ninguna orden. Prueba de la configuración protegida anterior al modo de exposición.',
         'Controles de rol superados en la ejecución aislada. La habilitación temporal de acceso demo se declara aparte; no implica protección por identidad.',
         'E3: test_http_roles_are_enforced y test_employees_cannot_approve_or_change_offers.'),
        ('Desempeño: tres escenarios administrativos y ocho consultas.',
         'Límite de análisis: 360 s; consulta: 30 s. Registrar intentos y tiempo completo.',
         'Equipo: media 51.49 s; agente único: 23.19 s, con fallos incluidos; reglas: 0.06 s. Asistente: mediana 3.133 s, máximo 4.875 s.',
         'E1 y E2: seconds, provider_attempts y tokens; tokens de intentos fallidos desconocidos.'),
        ('ML: V1, Excel adicional, V2 y meses posteriores reservados.',
         'Mismos 15,054 objetivos para las versiones; promover solo si supera el criterio previo y la referencia.',
         'Ejecución local: 11/11 celdas, 469.53 s. V2 MAE 0.5710, promedio 0.5411: no promover. En Render, el intento V2 reinició sin versión guardada.',
         'E4: notebook ejecutado y comparison.json. E5: render.json. No es una ejecución de Colab.')
    ],[.20,.25,.35,.20],width=FW,source='archivos conservados en el paquete; resultados y límites forman parte de la aceptación.')
    add('Localizadores: E1 y E2 también se publican en ml/evaluations/agents del repositorio; E3 y E5 están en Evidencias; E4 está en ML y Evidencias/ML. El CSV acompaña los JSON para revisar filas sin depender de la interfaz. No se agrega una matriz de confusión porque el objetivo predictivo es un conteo mensual, evaluado como regresión.','small')
    add('La Tabla 10 permite revisar cada exigencia del esquema del curso y localizar su evidencia sin confundir código disponible con una ejecución comprobada.','small')
    table('Tabla 10. Matriz de correspondencia con el esquema del curso',
          ['Criterio del esquema','Ubicación y evidencia','Alcance declarado'],[
        ('Problema, antecedente, fundamento y objetivo','Sección 1; Tabla 7; tres objetivos verificables.','Diagnóstico del prototipo; no encuesta ni empresa externa.'),
        ('Diseño de investigación y unidad de análisis','2.1; protocolo de la Tabla 9.','Desarrollo aplicado con comparación exploratoria.'),
        ('Arquitectura cloud y seguridad','Figura 1; 2.2; render.yaml y README.','Render + Neon; secretos excluidos; acceso demo temporal declarado.'),
        ('Datos, variables y tratamiento de nulos','2.3; Tabla 1; provenance.json y CSV/Excel.','Fuente externa mensual; ausencia no equivale a cero.'),
        ('Cinco modelos, parámetros y selección','Tabla 2; notebook original y ejecutado.','Candidatos ajustados en el corte propio de cada versión.'),
        ('Prueba temporal, referencia y métricas','Tabla 3; Figura 2; comparison.json.','MAE, RMSE y R²; misma muestra. V2 no supera la referencia.'),
        ('Agentes, límites y supervisión','2.4; Tabla 8; Figura 3; código de servicios.','Ocho roles, mismo proveedor; compras con acto humano explícito.'),
        ('Pruebas, tiempo y errores','Tablas 4, 5 y 9; JSON/CSV y registros.','18 ejecuciones de modalidades, 8 consultas y 52 controles aislados.'),
        ('Ejecución web y despliegue','Tabla 6; Figuras 4, 5 y 6; render.json.','Consulta e importación comprobadas; V2 cloud no concluido.'),
        ('Código, versión y reproducción','Anexo A; README; cuaderno; manifiesto ZIP.','Ejecución de resultados local; enlace Colab disponible, sin afirmar ejecución allí.'),
        ('Discusión, conclusiones y referencias','3.5; sección 4; referencias APA 7.','Límites de datos, API, latencia y nube; sin superioridad no demostrada.')
    ],[.28,.37,.35],width=FW,source='correspondencia con el esquema docente de tres páginas y las evidencias de esta entrega.')
    add('La Tabla 11 permite comprobar qué se entrenó y por qué se eligió un candidato. Las ventanas de validación son diferentes: V1 corresponde a julio-diciembre de 2000 y V2 a abril-septiembre de 2001; por ello, comparar sus columnas no estima una mejora. La prueba común para comparar versiones es la Tabla 3.','small')
    v1_candidates={r['model']:r for r in v1['candidates']}
    v2_candidates={r['model']:r for r in v2['candidates']}
    candidate_rows=[]
    for name in v1_candidates:
        selected=[]
        if name==v1['winner']:selected.append('Seleccionado en V1')
        if name==v2['winner']:selected.append('Seleccionado en V2')
        candidate_rows.append((name,f"{v1_candidates[name]['mae']:.6f}",f"{v2_candidates[name]['mae']:.6f}",
                               '; '.join(selected) or 'Candidato comparado'))
    candidate_rows.append(('Promedio histórico',f"{v1['validation_baseline']['mae']:.6f}",
                           f"{v2['validation_baseline']['mae']:.6f}",'Referencia; menor MAE en ambas ventanas'))
    table('Tabla 11. Validación de los cinco algoritmos y la referencia predefinida',
          ['Algoritmo o referencia','MAE validación V1','MAE validación V2','Decisión dentro de cada versión'],
          candidate_rows,[.30,.18,.18,.34],width=FW,
          source='V1.json y V2.json de la ejecución local del 23/10/2026. MAE: unidades por serie y mes; n=15,054 en cada validación, con fechas distintas.')
    add('Se selecciona el mejor de los cinco algoritmos para producir un artefacto candidato y estudiarlo; no se lo promueve por ese solo hecho. El promedio supera a los candidatos tanto en sus respectivas validaciones como en la prueba común. Esa decisión negativa es parte del resultado experimental.','small')
    sub('Verificación independiente de los artefactos')
    add('La lectura del informe no requiere ejecutar llamadas pagadas. El cuaderno ejecutado conserva entradas, salidas y gráficos; los CSV y JSON permiten recalcular comparaciones sin depender de capturas de pantalla. INDICE_ENTREGA.json reúne los resultados y sus localizadores, mientras el manifiesto SHA-256 permite detectar cambios en cualquier archivo del paquete. Los modelos joblib proceden exclusivamente de la ejecución documentada.','small')
    add('Para repetir el ciclo con el motor compartido, el entorno de aprendizaje se prepara con ml/requirements.txt y se ejecuta scripts/prepare_ml_delivery.py. Este proceso escribe una carpeta nueva por repetición, verifica la equivalencia del Excel con el CSV y conserva los resultados anteriores. El README detalla los comandos de instalación. El entrenamiento no necesita una clave LLM ni acceso a Neon. Las evaluaciones reales del asistente y los agentes son independientes y sí utilizan la cuota del proveedor configurado.','small')
    add('Los archivos necesarios para repetir el experimento se entregan junto al informe: historial inicial, Excel adicional, CSV equivalente y ventas posteriores; procedencia y licencia; notebook original y copia ejecutada; modelos serializados, métricas, gráficos y resultados por serie; comparación de modalidades, controles del asistente y evidencia del despliegue. El paquete excluye archivos de entorno y claves. No se presume una ejecución adicional por el solo hecho de publicar el enlace de Colab.','small')

    wide_page()
    section('Anexo D Evidencia visual del sistema desplegado')
    add('Las Figuras 4 y 5 documentan la interfaz consultada en Render el 23/10/2026. Se muestran recortes de capturas originales para conservar legibilidad; sus archivos íntegros están en Evidencias. Las capturas se tomaron con una sesión administrativa previa al acceso demo temporal.','small')
    assistant_crop=web_crop('render-llm.png','asistente-detalle.png',(680,100,1223,395))
    # A readable column-sized detail preserves the product, provider, compatibility and source context.
    image(assistant_crop,'Figura 4. Asistente conectado a TheHive/DeepSeek: precio S/ 160.00, disponibilidad de 14 unidades y compatibilidad según catálogo para Toyota Yaris 2018. Fuente: captura verificada, 23/10/2026, 11:52, America/Lima.',width=135*mm)
    agent_crop=web_crop('render-agentes.png','agentes-detalle.png',(510,560,1240,1100))
    image(agent_crop,'Figura 5. Expediente de reposición consultado: seis agentes convocados, dos opcionales sin convocar y propuesta por S/ 1,617.21 de S/ 2,000.00. El aviso indica ausencia de pronóstico operativo. Fuente: recorte de render-agentes.png, 23/10/2026; la propuesta original está fechada el 22/10.',width=FW)
    add('La pantalla demuestra la disponibilidad de una propuesta y sus evidencias; no acredita una compra recibida ni que el ML haya estimado esta reposición. La ausencia de pronóstico operativo permanece visible. El diseño separa la consulta del asistente comercial y el expediente de administración.','small')

    wide_page()
    add('La Figura 6a documenta la consulta del pronóstico semanal de referencia en Render; la Figura 6b, la actividad del laboratorio mensual externo. Son procesos y poblaciones distintos. El segundo conserva V1 y un intento V2 en revisión por reinicio; el cuaderno adjunto proporciona su ciclo completo comprobado localmente.','small')
    current_forecast=EVID/'render-pronosticos-1366.jpg'
    if current_forecast.is_file():
        ml_top=web_crop('render-pronosticos-1366.jpg','pronosticos-referencia.png',(232,76,1093,704))
        image(ml_top,'Figura 6a. Consulta de pronósticos: Ridge, horizonte de siete días, historial de referencia y 952 productos. La interfaz muestra 874 resultados que requieren revisión; el corte de evaluación es 18/10/2026. Fuente: recorte de captura verificada en Render, 23/10/2026.',width=FW)
    else:
        ml_top=web_crop('render-v2.png','laboratorio-datos.png',(235,360,1250,1010))
        image(ml_top,'Figura 6a. Laboratorio mensual: 120,330 observaciones y procedencia externa declarada. Fuente: recorte de render-v2.png, 23/10/2026.',width=FW)
    ml_jobs=web_crop('render-v2.png','laboratorio-ejecuciones.png',(235,1860,1250,2310))
    image(ml_jobs,'Figura 6b. Actividad conservada: el entrenamiento del 23/10/2026 quedó en revisión por reinicio; el pronóstico y V1 previos figuran completados. Fuente: recorte de render-v2.png, 23/10/2026. No se presenta una V2 cloud inexistente.',width=FW)
    add('La comparación V1-V2 del informe procede del notebook ejecutado y sus archivos con hash. La interfaz conserva un fallo observable en lugar de ocultarlo. Para repetir el entrenamiento completo debe utilizarse el entorno local o ejecutar el cuaderno en Colab con los datos adjuntos; los resultados nuevos deben identificarse por fecha y versión.','small')
    if demo_included:
        wide_page()
        section('Acceso temporal para la evaluación')
        add('La Figura 7 muestra la entrada de demostración comprobada tras actualizar Render. El docente puede elegir cliente o administrador sin recibir contraseñas. Este acceso facilita revisar tienda, laboratorio, asistente y agentes; no cambia la procedencia de los datos ni convierte los resultados locales en una ejecución cloud.','small')
        image(demo_image,'Figura 7. Entrada con dos perfiles para la exposición académica. Fuente: captura del despliegue final, 23/10/2026; fecha, revisión y comprobaciones registradas en render-demo.json.',width=FW)
        add('El acceso administrativo público es una excepción temporal solicitada para la entrega. La separación de permisos sigue existiendo dentro de cada sesión; el selector público permite obtener una sesión de administrador y, por tanto, no autentica una identidad. Los resultados de permisos citados en las Tablas 4 y 9 corresponden al código evaluado antes de habilitar esta excepción.','small')
        add('La reproducción del aprendizaje automático no depende de esta excepción: el cuaderno y sus datos pueden evaluarse de forma independiente. La consulta del asistente requiere una API externa disponible; la ejecución del equipo registra errores del proveedor y mantiene la aprobación explícita antes de generar órdenes. El historial académico, la fuente pública externa y las comprobaciones desplegadas se identifican por separado en las evidencias.','small')
        if recovery.get('passed'):
            add('El barrido inicial de acceso y consultas conserva 12/13 controles satisfactorios, con respuesta de catálogo en la consulta comercial. La revisión posterior independiente recuperó una respuesta TheHive en 10.703 s. No se reemplaza el primer fallo ni se lo reescribe como un barrido de 13/13. La revisión de acceso y la recuperación del proveedor se publican como evidencias separadas.','small')
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
                          PageTemplate(id='regular',frames=frames,onPage=footer),
                          PageTemplate(id='wide',frames=[Frame(LEFT,BOTTOM,FW,H-TOP-BOTTOM,id='wide',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)],onPage=footer)])
    doc.build(story)
    metadata={'file':'Informe_RODA.pdf','pages':doc.page,'cover_included':False,'tables':11,'figures':7 if demo_included else 6,
              'title_words':len(data['titulo'].split()),'abstract_words':len(data['resumen'].split()),
              'generated_at':datetime.now().astimezone().isoformat(),
              'experimental_code_version':'a89d21d38dd88f8f38dc3dcefefa5b2045a9c0f5',
              'last_verified_deployment':recovery.get('code_version',demo.get('code_version')),
              'sha256':hashlib.sha256((OUT/'Informe_RODA.pdf').read_bytes()).hexdigest(),
              'format':'A4; Times New Roman 11; dos columnas de texto y anexos con tablas y figuras a ancho completo'}
    (OUT/'METADATOS_INFORME.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(OUT/'Informe_RODA.pdf')

if __name__=='__main__':build()
