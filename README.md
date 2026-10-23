# RODA

Prototipo universitario de reposición asistida de repuestos. Tienda, inventario,
pronóstico, asistente de catálogo y ocho roles administrativos con aprobación humana.

- Sistema: https://roda-repuestos.onrender.com
- Entrenamiento: https://colab.research.google.com/github/NEYEN111/REPUESTOS/blob/main/notebooks/RODA_ML_Datos_Reales.ipynb
- Evaluación ejecutada: `ml/evaluations/entrega-2026-10-23/`.

## Ejecutar en Windows

Desde la carpeta del proyecto: `powershell -ExecutionPolicy Bypass -File .\start.ps1`.
Abre http://127.0.0.1:8000. No utilices `-Reseed` sobre datos que quieras conservar.

Para la base local: `RODA_FORCE_SQLITE=1`. Para Neon configura `DATABASE_URL` en `.env`.
Para las llamadas del modelo: `LLM_PROVIDER=thehive`, `THEHIVE_API_KEY`,
`THEHIVE_MODEL=deepseek-ai/deepseek-v4.1-flash-1017` y `ASSISTANT_ENABLED=true`.
`SEED_PASSWORD` define la contraseña inicial; no publiques su valor ni claves.

## Reproducir la evaluación

Instala `ml/requirements.txt` en `.venv-ml`. Ejecuta el cuaderno completo o
`.venv-ml\Scripts\python.exe scripts\prepare_ml_delivery.py`.
El script crea una ejecución nueva sin reemplazar los resultados anteriores.

Los scripts `evaluate_agent_modes.py` y `evaluate_assistant.py` utilizan datos
temporales y llamadas reales a la API. Consulta `--help`; consumen cuota del proveedor.
`verify_agents.py` y `verify_assistant.py` comprueban controles con respuestas aisladas.

## Alcance comprobado

Car Parts es una fuente pública externa de ventas mensuales, sin correspondencia
con los SKU de la tienda. El promedio histórico obtuvo menor MAE que V1 y V2.
Las ventas académicas de RODA no prueban precisión de demanda real peruana.
Las compras requieren aprobación. El entrenamiento V2 grande no terminó en
la prueba de Render Free del 23/10; el ciclo completo se adjunta ejecutado localmente.
Consulta los resultados y límites del informe; no equivale a certificación comercial.
