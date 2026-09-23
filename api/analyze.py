"""Vercel serverless API for heuristic SEO audits."""
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request

app = Flask(__name__)
MAX_BYTES = 2_000_000
TIMEOUT = 15


@app.after_request
def add_cors_headers(response):
    """Keep the API usable from the hosted frontend and for preflight requests."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def score_range(value, minimum, maximum):
    if minimum <= value <= maximum:
        return 100.0
    if value < minimum:
        return round(max(0, value / minimum * 100), 1)
    return round(max(0, 100 - ((value - maximum) / maximum * 100)), 1)


def audit(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("La URL debe comenzar por http:// o https://")

    response = requests.get(
        url,
        timeout=TIMEOUT,
        allow_redirects=True,
        stream=True,
        headers={"User-Agent": "AnalizadorSEO/1.0"},
    )
    try:
        response.raise_for_status()
        content = response.raw.read(MAX_BYTES + 1, decode_content=True)
    finally:
        response.close()

    html = content[:MAX_BYTES].decode(response.encoding or "utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    final_url = response.url
    issues = []
    recommendations = []

    def add_issue(category, severity, message, recommendation):
        issues.append({"category": category, "severity": severity, "message": message})
        recommendations.append({"category": category, "message": recommendation})

    title = clean(soup.title.get_text()) if soup.title else ""
    description_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    description = clean(description_tag.get("content", "")) if description_tag else ""
    h1_count = len(soup.find_all("h1"))
    images = soup.find_all("img")
    missing_alt = sum(not clean(image.get("alt", "")) for image in images)
    scripts = len(soup.find_all("script", src=True))
    stylesheets = len(soup.find_all("link", rel=lambda value: value and "stylesheet" in value))
    text = clean(soup.get_text(" ", strip=True))
    word_count = len(text.split())
    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    lang = soup.html.get("lang") if soup.html else None
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    links = soup.find_all("a", href=True)
    final_host = urlparse(final_url).netloc
    external_links = sum(
        urlparse(urljoin(final_url, link["href"])).netloc not in ("", final_host)
        for link in links
    )

    seo_checks = [
        ("Título", score_range(len(title), 30, 60), 1.5),
        ("Meta description", score_range(len(description), 120, 160), 1.2),
        ("H1 único", 100 if h1_count == 1 else 0, 1.2),
        ("Canonical", 100 if canonical and canonical.get("href") else 0, 1),
    ]
    if not title:
        add_issue("SEO", "high", "Falta la etiqueta title.", "Añade un title único de 30 a 60 caracteres.")
    elif not 30 <= len(title) <= 60:
        add_issue("SEO", "medium", "El title está fuera del rango recomendado.", "Ajusta el title a 30-60 caracteres.")
    if not description:
        add_issue("SEO", "medium", "Falta la meta description.", "Añade una meta description de 120-160 caracteres.")
    elif not 120 <= len(description) <= 160:
        add_issue("SEO", "low", "La meta description no tiene una longitud óptima.", "Ajusta la meta description a 120-160 caracteres.")
    if h1_count != 1:
        add_issue("SEO", "high", f"Se detectaron {h1_count} elementos H1.", "Usa exactamente un H1 principal.")
    if not canonical or not canonical.get("href"):
        add_issue("SEO", "medium", "Falta la URL canonical.", "Añade una etiqueta link rel=canonical.")

    accessibility_checks = [
        ("Idioma", 100 if lang else 0, 1),
        ("Texto alternativo", 100 if not images else 100 - missing_alt / len(images) * 100, 1.2),
        ("Viewport", 100 if viewport else 0, 1),
    ]
    if not lang:
        add_issue("Accesibilidad", "medium", "Falta el atributo lang.", "Añade lang al elemento html.")
    if missing_alt:
        add_issue("Accesibilidad", "medium", f"{missing_alt} imágenes no tienen alt.", "Añade texto alternativo descriptivo.")
    if not viewport:
        add_issue("Accesibilidad", "medium", "Falta meta viewport.", "Añade configuración viewport para móviles.")

    performance_checks = [
        ("Scripts externos", max(0, 100 - max(0, scripts - 6) * 12), 1),
        ("Hojas de estilo", max(0, 100 - max(0, stylesheets - 3) * 15), 1),
        ("Imágenes", max(0, 100 - max(0, len(images) - 15) * 4), 1),
    ]
    if scripts > 8:
        add_issue("Rendimiento", "medium", f"Hay {scripts} scripts externos.", "Reduce scripts y usa carga diferida.")
    if stylesheets > 4:
        add_issue("Rendimiento", "low", f"Hay {stylesheets} hojas CSS.", "Combina y minimiza CSS.")
    if len(images) > 20:
        add_issue("Rendimiento", "low", f"Hay {len(images)} imágenes.", "Optimiza imágenes y usa formatos modernos y lazy loading.")

    security_headers = [
        "Content-Security-Policy",
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Strict-Transport-Security",
    ]
    missing_headers = [header for header in security_headers if not response.headers.get(header)]
    security_checks = [
        ("HTTPS", 100 if final_url.startswith("https://") else 0, 1.5),
        ("Cabeceras", 100 - len(missing_headers) / len(security_headers) * 100, 1),
    ]
    if not final_url.startswith("https://"):
        add_issue("Seguridad", "critical", "La página no utiliza HTTPS.", "Activa HTTPS y redirige HTTP a HTTPS.")
    if missing_headers:
        add_issue("Seguridad", "low", "Faltan cabeceras de seguridad.", "Revisa: " + ", ".join(missing_headers) + ".")

    content_checks = [
        ("Volumen", min(100, word_count / 400 * 100), 1),
        ("Estructura", 100 if soup.find_all(["h2", "h3"]) else 50, 1),
    ]
    if word_count < 300:
        add_issue("Contenido", "medium", f"El contenido tiene solo {word_count} palabras.", "Amplía el contenido con información útil.")

    categories = {}
    category_definitions = [
        ("SEO", seo_checks, 30),
        ("Accesibilidad", accessibility_checks, 20),
        ("Rendimiento", performance_checks, 20),
        ("Seguridad", security_checks, 15),
        ("Contenido", content_checks, 10),
    ]
    for name, checks, weight in category_definitions:
        denominator = sum(item[2] for item in checks)
        category_score = round(sum(item[1] * item[2] for item in checks) / denominator, 1)
        categories[name] = {
            "weight": weight,
            "score": category_score,
            "checks": [{"name": item[0], "score": round(item[1], 1)} for item in checks],
        }

    total_weight = sum(item["weight"] for item in categories.values())
    overall = round(sum(item["score"] * item["weight"] for item in categories.values()) / total_weight, 1)
    grade = "A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else "D" if overall >= 60 else "F"
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda item: severity_order[item["severity"]])
    deduped = list({(item["category"], item["message"]): item for item in recommendations}.values())

    return {
        "url": url,
        "final_url": final_url,
        "status_code": response.status_code,
        "overall_score": overall,
        "grade": grade,
        "categories": categories,
        "metrics": {
            "title": title,
            "description": description,
            "word_count": word_count,
            "h1_count": h1_count,
            "images": len(images),
            "missing_alt": missing_alt,
            "links": len(links),
            "external_links": external_links,
        },
        "issues": issues,
        "recommendations": deduped,
    }


@app.route("/api/analyze", methods=["GET", "POST", "OPTIONS"])
def analyze_route():
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "GET":
        return jsonify({
            "service": "analizador-seo",
            "usage": "POST /api/analyze con {url: https://example.com}",
        })
    try:
        data = request.get_json(silent=True) or {}
        url = str(data.get("url", "")).strip()
        if not url:
            raise ValueError("Debes proporcionar una URL en el campo 'url'.")
        return jsonify(audit(url))
    except requests.RequestException as exc:
        return jsonify({"error": f"No se pudo consultar la página: {exc}"}), 502
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Error interno: {exc}"}), 500
