# Analizador SEO

Agente heurístico para auditorías SEO, accesibilidad, rendimiento, seguridad y contenido. Expone una función serverless compatible con Vercel.

## Uso local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

Vercel instala las dependencias automáticamente. Para probar la función localmente:

```bash
vercel dev
curl -X POST http://localhost:3000/api/analyze \\
  -H 'Content-Type: application/json' \\
  -d '{"url":"https://example.com"}'
```

## Despliegue en Vercel

1. Importa este repositorio en [Vercel](https://vercel.com/new).
2. Selecciona el framework **Other**.
3. Mantén la configuración predeterminada y pulsa **Deploy**.

También puedes usar la CLI:

```bash
npm i -g vercel
vercel
vercel --prod
```

## API

`POST /api/analyze`

```json
{"url":"https://example.com"}
```

La respuesta incluye puntuación global de 0 a 100, grado A-F, puntuaciones ponderadas por categoría, métricas, incidencias por severidad y recomendaciones.

> Nota: el despliegue usa una petición HTTP directa y análisis del HTML recibido. Las páginas cuyo contenido se genera exclusivamente con JavaScript pueden requerir un navegador externo o una integración con Lighthouse.
