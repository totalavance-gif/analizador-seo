# Analizador SEO

Agente heurístico para auditorías SEO, accesibilidad, rendimiento, seguridad y contenido. Expone una API serverless compatible con Vercel y una interfaz web básica.

## Funcionalidades

- Puntuación ponderada de 0 a 100.
- Clasificación A-F.
- Auditoría SEO: `title`, meta description, H1 y canonical.
- Accesibilidad: idioma, texto alternativo y viewport.
- Rendimiento: scripts, hojas de estilo e imágenes.
- Seguridad: HTTPS y cabeceras HTTP.
- Contenido: volumen y estructura de encabezados.
- Incidencias ordenadas por severidad.
- Recomendaciones de mejora.

## Uso local

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python api/analyze.py
```

La API local se ejecuta en `http://127.0.0.1:5000`.

```bash
curl -X POST http://127.0.0.1:5000/api/analyze \\
  -H 'Content-Type: application/json' \\
  -d '{"url":"https://example.com"}'
```

También puedes usar Vercel CLI:

```bash
npm install -g vercel
vercel dev
```

## API

### `GET /api/analyze`

Devuelve información básica del servicio.

### `POST /api/analyze`

Solicitud:

```json
{
  "url": "https://example.com"
}
```

La respuesta incluye:

- `overall_score`
- `grade`
- `categories`
- `metrics`
- `issues`
- `recommendations`

## Despliegue en Vercel

1. Importa `totalavance-gif/analizador-seo` desde [Vercel](https://vercel.com/new).
2. Selecciona **Other** como framework si Vercel lo solicita.
3. Pulsa **Deploy**.

O utiliza la CLI:

```bash
vercel login
vercel
vercel --prod
```

## Limitaciones

El análisis obtiene el HTML recibido mediante HTTP. Las páginas cuyo contenido se genera exclusivamente con JavaScript pueden necesitar un navegador externo o una futura integración con Lighthouse.

No introduzcas credenciales ni URLs internas o privadas en el analizador.
