"""Vercel serverless API for heuristic SEO audits."""
import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

MAX_BYTES = 2_000_000
TIMEOUT = 15


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def check_score(value, ideal_min, ideal_max, hard_max=None):
    if ideal_min <= value <= ideal_max:
        return 100.0
    if value < ideal_min:
        return round(max(0, value / ideal_min * 100), 1) if ideal_min else 0
    limit = hard_max or ideal_max * 2
    return round(max(0, (limit - value) / (limit - ideal_max) * 100), 1)


def audit(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("La URL debe comenzar por http:// o https://")

    response = requests.get(
        url,
        timeout=TIMEOUT,
        headers={"User-Agent": "AnalizadorSEO/1.0 (+https://github.com/totalavance-gif/analizador-seo)"},
        allow_redirects=True,
        stream=True,
    )
    content = response.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(content) > MAX_BYTES:
        content = content[:MAX_BYTES]
    html = content.decode(response.encoding or "utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    final_url = response.url
    issues = []
    recommendations = []

    def issue(category, severity, message, recommendation):
        issues.append({"category": category, "severity": severity, "message": message})
        recommendations.append({"category": category, "message": recommendation})

    title = clean(soup.title.get_text()) if soup.title else ""
    description_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    description = clean(description_tag.get("content", "")) if description_tag else ""
    h1_count = len(soup.find_all("h1"))
    canonical_tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    lang = soup.html.get("lang") if soup.html else None
    images = soup.find_all("img")
    missing_alt = sum(1 for image in images if not clean(image.get("alt", "")))
    scripts = len(soup.find_all("script", src=True))
    stylesheets = len(soup.find_all("link", rel=lambda value: value and "stylesheet" in value))
    body_text = clean(soup.get_text(" ", strip=True))
    word_count = len(body_text.split())
    links = soup.find_all("a", href=True)
    external_links = sum(1 for link in links if urlparse(urljoin(final_url, link["href"])).netloc not in ("", urlparse(final_url).netloc))

    seo_checks = [
        ("Título", check_score(len(title), 30, 60), 1.5),
        ("Meta description", check_score(len(description), 120, 160), 1.2),
        ("H1 único", 100 if h1_count == 1 else 0, 1.2),
        ("Canonical", 100 if canonical_tag and canonical_tag.get("href") else 0, 1),
    ]
    if not title: issue("SEO", "high", "Falta la etiqueta title.", "Añade un title único de entre 30 y 60 caracteres.")
    elif not 30 <= len(title) <= 60: issue("SEO", "medium", "El title está fuera del rango recomendado.", "Ajusta el title a 30-60 caracteres.")
    if not description: issue("SEO", "medium", "Falta la meta description.", "Añade una meta description de 120-160 caracteres.")
    elif not 120 <= len(description) <= 160: issue("SEO", "low", "La meta description no tiene una longitud óptima.", "Ajusta la meta description a 120-160 caracteres.")
    if h1_count != 1: issue("SEO", "high", f"Se detectaron {h1_count} elementos H1.", "Usa exactamente un H1 principal.")
    if not canonical_tag or not canonical_tag.get("href"): issue("SEO", "medium", "Falta la URL canonical.", "Añade una etiqueta link rel=canonical.")

    a11y_checks = [
        ("Idioma", 100 if lang else 0, 1),
        ("Texto alternativo", 100 if not images else (100 - missing_alt / len(images) * 100), 1.2),
        ("Viewport", 100 if soup.find("meta", attrs={"name": "viewport"}) else 0, 1),
    ]
    if not lang: issue("Accesibilidad", "medium", "Falta el atributo lang.", "Añade lang al elemento html.")
    if missing_alt: issue("Accesibilidad", "medium", f"{missing_alt} imágenes no tienen alt.", "Añade texto alternativo descriptivo a las imágenes.")
    if not soup.find("meta", attrs={"name": "viewport"}): issue("Accesibilidad", "medium", "Falta meta viewport.", "Añade configuración viewport para móviles.")

    performance_checks = [
        ("Scripts externos", max(0, 100 - max(0, scripts - 6) * 12), 1),
        ("Hojas de estilo", max(0, 100 - max(0, stylesheets - 3) * 15), 1),
        ("Imágenes", max(0, 100 - max(0, len(images) - 15) * 4), 1),
    ]
    if scripts > 8: issue("Rendimiento", "medium", f"Hay {scripts} scripts externos.", "Reduce scripts y usa carga diferida cuando sea posible.")
    if stylesheets > 4: issue("Rendimiento", "low", f"Hay {stylesheets} hojas CSS.", "Combina y minimiza hojas de estilo.")
    if len(images) > 20: issue("Rendimiento", "low", f"Hay {len(images)} imágenes.", "Optimiza imágenes y usa formatos modernos y lazy loading.")

    security_headers = ["Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy", "Strict-Transport-Security"]
    present_headers = sum(1 for header in security_headers if response.headers.get(header))
    security_checks = [("HTTPS", 100 if final_url.startswith("https://") else 0, 1.5), ("Cabeceras", present_headers / len(security_headers) * 100, 1)]
    if not final_url.startswith("https://"): issue("Seguridad", "critical", "La página no utiliza HTTPS.", "Activa HTTPS y redirige HTTP a HTTPS.")
    missing_headers = [header for header in security_headers if not response.headers.get(header)]
    if missing_headers: issue("Seguridad", "low", "Faltan cabeceras de seguridad.", "Revisa: " + ", ".join(missing_headers) + ".")

    content_checks = [("Volumen", min(100, word_count / 400 * 100), 1), ("Estructura", 100 if soup.find_all(["h2", "h3"]) else 50, 1)]
    if word_count < 300: issue("Contenido", "medium", f"El contenido tiene solo {word_count} palabras.", "Amplía el contenido con información útil y específica.")

    categories = {}
    for name, checks, weight in [("SEO", seo_checks, 30), ("Accesibilidad", a11y_checks, 20), ("Rendimiento", performance_checks, 20), ("Seguridad", security_checks, 15), ("Contenido", content_checks, 10)]:
        total_weight = sum(item[2] for item in checks)
        score = round(sum(item[1] * item[2] for item in checks) / total_weight, 1)
        categories[name] = {"weight": weight, "score": score, "checks": [{"name": item[0], "score": round(item[1], 1)} for item in checks]}

    total_weight = sum(item["weight"] for item in categories.values())
    overall = round(sum(item["score"] * item["weight"] for item in categories.values()) / total_weight, 1)
    grade = "A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else "D" if overall >= 60 else "F"
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda item: severity_order[item["severity"]])
    unique_recommendations = list({(item["category"], item["message"]): item for item in recommendations}.values())

    return {"url": url, "final_url": final_url, "status_code": response.status_code, "overall_score": overall, "grade": grade, "categories": categories, "metrics": {"title": title, "description": description, "word_count": word_count, "h1_count": h1_count, "images": len(images), "missing_alt": missing_alt, "links": len(links), "external_links": external_links}, "issues": issues, "recommendations": unique_recommendations}


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        self._send(200, {"service": "analizador-seo", "usage": "POST /api/analyze con {\"url\": \"https://example.com\"}"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
            url = str(data.get("url", "")).strip()
            if not url: raise ValueError("Debes proporcionar una URL en el campo 'url'.")
            self._send(200, audit(url))
        except requests.RequestException as exc:
            self._send(502, {"error": f"No se pudo consultar la página: {exc}"})
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            self._send(500, {"error": f"Error interno: {exc}"})
