# RODA · Reposición asistida de repuestos

Proyecto universitario que integra una tienda de repuestos, inventario con kardex,
aprendizaje automático, un asistente de catálogo y ocho roles administrativos
coordinados. El aporte principal es preparar decisiones de reposición con evidencia,
controles de presupuesto y aprobación humana.

## Acceso y material de entrega

| Recurso | Acceso |
|---|---|
| Sistema desplegado | [RODA en Render](https://roda-repuestos.onrender.com) |
| Entrada a la demostración | [Ingresar como administrador o cliente](https://roda-repuestos.onrender.com/ingresar) |
| Informe técnico sin carátula | [Informe_RODA.pdf](output/entrega-2026-10-23/Informe_RODA.pdf) |
| Cuaderno para ejecutar en Colab | [Abrir entrenamiento](https://colab.research.google.com/github/NEYEN111/REPUESTOS/blob/main/notebooks/RODA_ML_Datos_Reales.ipynb) |
| Cuaderno ejecutado con resultados visibles | [Ejecución completa del 23/10/2026](ml/evaluations/entrega-2026-10-23/RODA_ML_Datos_Reales_Ejecutado.ipynb) |
| Dataset inicial | [01_historial_inicial.csv](ml/examples/carparts/01_historial_inicial.csv) |
| Datos nuevos para importar | [02_datos_nuevos.xlsx](ml/examples/carparts/02_datos_nuevos.xlsx) · [CSV equivalente](ml/examples/carparts/02_datos_nuevos.csv) |
| Ventas posteriores para evaluar | [03_ventas_posteriores.csv](ml/examples/carparts/03_ventas_posteriores.csv) |
| Fuente y huellas de los datos | [provenance.json](ml/examples/carparts/provenance.json) |

El acceso con dos botones se habilita para la entrega mediante
`DEMO_ACCESS_ENABLED=true`. Conserva sesiones y permisos por rol; permite entrar
como administrador sin contraseña mientras el modo esté activo. Se desactiva
cambiando la variable a `false`, que también invalida esas sesiones de demostración.
Su valor predeterminado es `false`; las contraseñas originales se conservan.
El Blueprint de esta entrega lo activa expresamente. Las sesiones demo duran
cuatro horas; al desactivarlo se recupera el acceso habitual con contraseña.

## Recorrido sugerido de revisión

1. **Inventario y stock:** consultar disponibles, reservados, alertas y movimientos.
2. **Análisis predictivo → Laboratorio y versiones:** revisar historial, versiones,
   predicciones y evaluación posterior. Los archivos de la tabla anterior reproducen
   el recorrido V1 → datos nuevos → V2.
3. **Modelos y evaluación:** contrastar los cinco algoritmos con una referencia simple.
4. **Agentes:** revisar propuestas, ofertas, auditoría y registro de participación.
   Una propuesta de compra necesita aprobación; ejecutar un análisis no compra mercadería.
5. **Tienda → Asistente:** preguntar por un SKU, precio, disponibilidad o compatibilidad
   y contrastar la respuesta con la ficha del producto.

Render Free puede necesitar tiempo para despertar. El entrenamiento grande de V2
no terminó en la prueba desplegada del 23/10: se registró un reinicio del servidor.
La evidencia del ciclo completo corresponde a la ejecución local adjunta; no se
presenta como un entrenamiento completado en Render ni en Google Colab.

## Qué se entrenó y cómo se evaluó

La tarea del laboratorio es estimar **unidades observadas del siguiente mes por
serie**. Se usa [Car Parts, Monash Forecasting Repository](https://zenodo.org/records/4656022),
con licencia CC BY 4.0: 2,674 series anónimas, 136,374 filas mensuales de enero de
1998 a marzo de 2002 y 6,122 valores desconocidos. No hay correspondencia con los SKU
de RODA, precios, existencias o ventas actuales de Perú. No se inventan esos campos.

| Algoritmo | Motivo de comparación |
|---|---|
| Ridge | Referencia lineal regularizada para las variables históricas |
| Poisson | Regresión para cantidades no negativas |
| Random Forest | Relaciones no lineales e interacciones mediante un conjunto de árboles |
| Extra Trees | Contrastar árboles con mayor aleatorización |
| Hist. Gradient Boosting | Corrección progresiva de errores mediante árboles |

Se usan configuraciones fijas, semilla 42 y selección por MAE en los últimos seis
meses disponibles de cada versión. La imputación de entradas se ajusta dentro del
pipeline; los objetivos desconocidos se excluyen. No se mezclan fechas al azar.
El modelo seleccionado se reajusta con el historial conocido hasta su corte.

| Etapa | Periodos | Filas del archivo | Uso |
|---|---|---:|---|
| Historial inicial | 1998-01 a 2000-12 | 96,264 | Entrenar y seleccionar V1 |
| Datos nuevos | 2001-01 a 2001-09 | 24,066 | Ampliar el historial y entrenar V2 |
| Ventas posteriores | 2001-10 a 2002-03 | 16,044 | Evaluar ambas versiones congeladas |

La prueba común conserva 15,054 objetivos conocidos de 2,509 series. Cada mes usa
observaciones anteriores disponibles; no es un pronóstico fijo de seis meses. Las
tablas de validación de V1 y V2 corresponden a periodos diferentes y no deben usarse
solas para afirmar una mejora.

Resultados de la ejecución completa del 23/10/2026:

| Método | MAE ↓ | RMSE ↓ | R² ↑ |
|---|---:|---:|---:|
| V1 · Hist. Gradient Boosting | 0.574727 | 1.033989 | 0.102265 |
| V2 · Extra Trees | 0.571015 | 1.033127 | 0.103762 |
| Promedio histórico de 12 meses | **0.541074** | 1.046048 | 0.081204 |
| Cero ventas · diagnóstico | 0.386675 | 1.157774 | -0.125547 |

MAE y RMSE se expresan en unidades por serie y mes. V2 reduce el MAE de V1 en
0.646%; no alcanza el umbral práctico del 1% y el promedio mantiene menor MAE.
**No se aprueba reposición automática con estos resultados.** El laboratorio mensual
externo y el pronóstico operativo a siete días son procesos distintos.

El 79.53% de los objetivos de prueba son cero. Estimar siempre cero reduce aún más
el MAE, pero omite toda venta positiva y empeora RMSE y R². Se conserva como
diagnóstico: el MAE aislado no demuestra una política de abastecimiento útil.

El cuaderno ejecutado completó 11 celdas de código sin errores en 469.53 segundos
en Windows: diez ajustes para seleccionar los cinco algoritmos en V1 y V2, más dos
reajustes finales. El [resumen verificable](ml/evaluations/entrega-2026-10-23/resumen_ejecucion.json)
registra entorno, particiones, configuración, huellas y artefactos.

## Evidencia de LLM y agentes

Las llamadas de la evaluación utilizaron DeepSeek a través de TheHive. Los escenarios
se ejecutaron en bases SQLite temporales con datos académicos; no alteraron pedidos
ni inventario de Neon.

| Evaluación | Resultado observado | Evidencia |
|---|---|---|
| Asistente: precio, stock, compatibilidad, ambigüedad, contexto y controles | 8/8 casos; mediana 3.13 s | [JSON con entradas, criterios y respuestas](ml/evaluations/agents/llm-entrega-2026-10-23.json) |
| Reglas sin LLM | 6/6 casos; media 0.06 s | [Comparación de modalidades](ml/evaluations/agents/entrega-2026-10-23.json) |
| Agente único | 4/6 casos; media 23.19 s | [CSV de resultados](ml/evaluations/agents/entrega-2026-10-23.csv) |
| Equipo multiagente | 6/6 casos; media 51.49 s | [Comparación de modalidades](ml/evaluations/agents/entrega-2026-10-23.json) |

La comparación abarca presupuesto, alternativas de proveedor y ofertas vencidas,
con dos repeticiones por escenario y modalidad. Los ocho roles son Orquestador,
Calidad de datos, Demanda ML, Inventario, Compras y proveedores, Finanzas,
Pedidos y envíos, y Auditor. Comparten servicios
Python y controles deterministas; no representan ocho modelos entrenados distintos.

La muestra no demuestra superioridad estadística del equipo: las reglas resolvieron
todos los casos y fueron más rápidas. El equipo agrega revisión por especialidad,
evidencia y trazabilidad, con mayor coste y latencia. Los fallos del agente único y
los reintentos de JSON se conservan en los registros.

## Ejecutar en Windows

Requisitos: Python 3.12 y Node.js con npm. Desde la carpeta del proyecto:

```powershell
git clone https://github.com/NEYEN111/REPUESTOS.git
cd REPUESTOS
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Abre [http://127.0.0.1:8000](http://127.0.0.1:8000). El script prepara los entornos,
instala dependencias, genera datos si faltan y compila el frontend. No utilices
`-Reseed` sobre datos que quieras conservar.

Variables de configuración en `.env` o en Render, sin publicar sus valores:

| Variable | Uso |
|---|---|
| `DATABASE_URL` | Conexión PostgreSQL de Neon |
| `RODA_FORCE_SQLITE=1` | Forzar la base local en vez de PostgreSQL |
| `SEED_PASSWORD` | Contraseña inicial de las cuentas del seed |
| `LLM_PROVIDER=thehive` | Proveedor de las llamadas al LLM |
| `THEHIVE_API_KEY` | Clave privada del proveedor |
| `THEHIVE_MODEL=deepseek-ai/deepseek-v4.1-flash-1017` | Modelo configurado |
| `ASSISTANT_ENABLED=true` | Habilitar el asistente |
| `DEMO_ACCESS_ENABLED=false` | Habilitación temporal del acceso de demostración |

La configuración de despliegue está en [render.yaml](render.yaml). Las claves y las
conexiones privadas no forman parte del repositorio ni del informe.

## Reproducir el entrenamiento

**En Colab:** abre el enlace de entrenamiento, selecciona un entorno Python y
ejecuta las celdas en orden. No necesita una clave LLM ni acceso a Neon. Al terminar
se descarga un ZIP con modelos, métricas y gráficos. El cuaderno fuente lee la
versión CSV de los datos nuevos; el Excel entregable contiene los mismos valores.

**En Windows:** el siguiente proceso ejecuta una copia del cuaderno, importa y
verifica el Excel y guarda cada repetición en una carpeta nueva:

```powershell
python -m venv .venv-ml
.\.venv-ml\Scripts\python.exe -m pip install -r ml\requirements.txt
.\.venv-ml\Scripts\python.exe scripts\prepare_ml_delivery.py
```

Se conservan las fuentes y los resultados originales. La copia ejecutada y el índice
de la entrega se actualizan para apuntar a la repetición más reciente. Los modelos
`.joblib` generados localmente se incluyen en el paquete de entrega; se excluyen de
Git por ser artefactos de ejecución. No deben cargarse modelos de origen desconocido.

Para repetir las evaluaciones de llamadas reales sin reemplazar la evidencia publicada:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_agent_modes.py --repetitions 2 --output artifacts\revision\agentes.json
.\.venv\Scripts\python.exe scripts\evaluate_assistant.py --output artifacts\revision\asistente.json
```

Requieren el proveedor configurado y consumen su cuota. Los scripts
`scripts/verify_agents.py` y `scripts/verify_assistant.py` comprueban controles
aislados con respuestas de prueba; sus resultados se distinguen de las llamadas reales.

## Estructura

- `backend/services/`: funciones de negocio, inventario, LLM y coordinación de agentes.
- `frontend/`: tienda y área de gestión en React y TypeScript.
- `ml/lab_engine.py`: motor compartido entre laboratorio web y cuaderno.
- `ml/examples/carparts/`: datos públicos preparados y procedencia.
- `ml/evaluations/`: métricas y ejecuciones conservadas.
- `notebooks/`: cuadernos de entrenamiento y evaluación.
- `output/entrega-2026-10-23/`: informe y evidencias de la entrega.

La revisión debe distinguir los resultados locales, las consultas comprobadas en
Render y las limitaciones de la muestra. El proyecto demuestra integración y
evaluación académica; las métricas no acreditan precisión comercial en Perú.
