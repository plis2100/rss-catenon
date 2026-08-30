import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup


WEB_URL = "https://www.catenon.com/es/news"
BASE_URL = "https://www.catenon.com"
ARCHIVO_RSS = Path("catenon.xml")

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

CABECERAS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

MESES = {
    "enero": 1,
    "january": 1,
    "febrero": 2,
    "february": 2,
    "marzo": 3,
    "march": 3,
    "abril": 4,
    "april": 4,
    "mayo": 5,
    "may": 5,
    "junio": 6,
    "june": 6,
    "julio": 7,
    "july": 7,
    "agosto": 8,
    "august": 8,
    "septiembre": 9,
    "september": 9,
    "octubre": 10,
    "october": 10,
    "noviembre": 11,
    "november": 11,
    "diciembre": 12,
    "december": 12,
}


def limpiar_texto(texto):
    return re.sub(r"\s+", " ", texto or "").strip()


def escapar_xml(texto):
    return (
        str(texto)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def descargar(url):
    ultimo_error = None

    for intento in range(1, 4):
        try:
            respuesta = requests.get(
                url,
                headers=CABECERAS,
                timeout=90,
                allow_redirects=True,
                verify=False,
            )
            respuesta.raise_for_status()

            if len(respuesta.text.strip()) < 300:
                raise RuntimeError(
                    "Catenon devolvió una página incompleta"
                )

            return respuesta.text

        except (
            requests.RequestException,
            RuntimeError,
        ) as error:
            ultimo_error = error

            print(
                f"Intento {intento} fallido para "
                f"{url}: {error}"
            )

            if intento < 3:
                time.sleep(4 * intento)

    raise RuntimeError(
        f"No se pudo descargar {url}: {ultimo_error}"
    )


def es_enlace_noticia(url):
    ruta = urlparse(url).path.lower().rstrip("/")

    if not ruta.startswith("/es/news/"):
        return False

    slug = ruta.removeprefix("/es/news/")

    return bool(slug) and "/" not in slug


def convertir_fecha(texto):
    texto = limpiar_texto(texto).lower()

    coincidencia = re.search(
        r"\b(\d{1,2})\s+"
        r"(enero|january|febrero|february|marzo|march|"
        r"abril|april|mayo|may|junio|june|julio|july|"
        r"agosto|august|septiembre|september|octubre|october|"
        r"noviembre|november|diciembre|december)"
        r"(?:\s+de)?[,]?\s+(\d{4})\b",
        texto,
    )

    if coincidencia:
        dia = int(coincidencia.group(1))
        mes = MESES[coincidencia.group(2)]
        anio = int(coincidencia.group(3))

        try:
            return datetime(
                anio,
                mes,
                dia,
                12,
                0,
                0,
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None

    coincidencia = re.search(
        r"\b(enero|january|febrero|february|marzo|march|"
        r"abril|april|mayo|may|junio|june|julio|july|"
        r"agosto|august|septiembre|september|octubre|october|"
        r"noviembre|november|diciembre|december)"
        r"\s+(\d{1,2})[,]?\s+(\d{4})\b",
        texto,
    )

    if coincidencia:
        mes = MESES[coincidencia.group(1)]
        dia = int(coincidencia.group(2))
        anio = int(coincidencia.group(3))

        try:
            return datetime(
                anio,
                mes,
                dia,
                12,
                0,
                0,
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None

    coincidencia = re.search(
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b",
        texto,
    )

    if coincidencia:
        dia = int(coincidencia.group(1))
        mes = int(coincidencia.group(2))
        anio = int(coincidencia.group(3))

        try:
            return datetime(
                anio,
                mes,
                dia,
                12,
                0,
                0,
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None

    return None


def convertir_fecha_iso(valor):
    if not valor:
        return None

    try:
        fecha = datetime.fromisoformat(
            valor.strip().replace("Z", "+00:00")
        )

        if fecha.tzinfo is None:
            fecha = fecha.replace(
                tzinfo=timezone.utc
            )

        return fecha.astimezone(timezone.utc)

    except ValueError:
        return None


def obtener_enlaces(html):
    soup = BeautifulSoup(html, "html.parser")
    noticias = []
    vistos = set()

    for enlace in soup.find_all("a", href=True):
        url = urljoin(
            BASE_URL,
            enlace.get("href"),
        )
        url = url.split("#")[0].split("?")[0].rstrip("/")

        if not es_enlace_noticia(url):
            continue

        if url in vistos:
            continue

        titulo = limpiar_texto(
            enlace.get_text(" ", strip=True)
        )

        if titulo.lower() in {
            "continuar leyendo",
            "leer más",
            "leer mas",
            "ver más",
            "ver mas",
        }:
            titulo = ""

        noticias.append(
            {
                "url": url,
                "titulo_inicial": titulo,
            }
        )

        vistos.add(url)

    if not noticias:
        raise RuntimeError(
            "No se encontraron enlaces de noticias de Catenon"
        )

    return noticias[:40]


def obtener_fecha(soup, texto, posicion):
    meta = soup.find(
        "meta",
        attrs={"property": "article:published_time"},
    )

    if meta and meta.get("content"):
        fecha = convertir_fecha_iso(
            meta.get("content")
        )

        if fecha:
            return fecha

    tiempo = soup.find("time")

    if tiempo:
        fecha = convertir_fecha_iso(
            tiempo.get("datetime")
        )

        if fecha:
            return fecha

        fecha = convertir_fecha(
            tiempo.get_text(" ", strip=True)
        )

        if fecha:
            return fecha

    fecha = convertir_fecha(texto)

    if fecha:
        return fecha

    # Respaldo excepcional para una noticia sin fecha visible.
    return datetime.now(timezone.utc) - timedelta(
        minutes=posicion
    )


def obtener_descripcion(soup):
    meta = soup.find(
        "meta",
        attrs={"name": "description"},
    )

    if meta and meta.get("content"):
        descripcion = limpiar_texto(
            meta.get("content")
        )

        if len(descripcion) >= 40:
            return descripcion[:1200]

    for selector in [
        "article p",
        "main p",
        ".post-content p",
        ".entry-content p",
    ]:
        parrafos = soup.select(selector)

        textos = [
            limpiar_texto(
                parrafo.get_text(" ", strip=True)
            )
            for parrafo in parrafos
        ]

        textos = [
            texto
            for texto in textos
            if len(texto) >= 40
        ]

        if textos:
            return " ".join(textos)[:1200]

    return ""


def completar_noticia(
    noticia,
    posicion,
):
    html = descargar(noticia["url"])
    soup = BeautifulSoup(html, "html.parser")

    encabezado = soup.find("h1")

    if encabezado:
        titulo = limpiar_texto(
            encabezado.get_text(" ", strip=True)
        )
    else:
        titulo = noticia["titulo_inicial"]

    if len(titulo) < 10:
        titulo = noticia["titulo_inicial"]

    texto_pagina = limpiar_texto(
        soup.get_text(" ", strip=True)
    )

    fecha = obtener_fecha(
        soup,
        texto_pagina,
        posicion,
    )

    descripcion = obtener_descripcion(soup)

    return {
        "titulo": titulo,
        "url": noticia["url"],
        "fecha": fecha,
        "descripcion": descripcion,
    }


def obtener_noticias():
    html = descargar(WEB_URL)
    enlaces = obtener_enlaces(html)
    noticias = []

    for posicion, enlace in enumerate(enlaces):
        try:
            noticias.append(
                completar_noticia(
                    enlace,
                    posicion,
                )
            )
        except Exception as error:
            print(
                f"No se pudo completar "
                f"{enlace['url']}: {error}"
            )

    noticias.sort(
        key=lambda noticia: noticia["fecha"],
        reverse=True,
    )

    if not noticias:
        raise RuntimeError(
            "No se pudieron obtener noticias de Catenon"
        )

    return noticias[:40]


def crear_rss(noticias):
    ahora = datetime.now(timezone.utc)

    partes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "<channel>",
        "<title>Catenon - Noticias</title>",
        f"<link>{escapar_xml(WEB_URL)}</link>",
        (
            "<description>Últimas noticias oficiales "
            "publicadas por Catenon</description>"
        ),
        "<language>es</language>",
        f"<lastBuildDate>{format_datetime(ahora)}</lastBuildDate>",
        "<ttl>60</ttl>",
    ]

    for noticia in noticias:
        partes.extend(
            [
                "<item>",
                f"<title>{escapar_xml(noticia['titulo'])}</title>",
                f"<link>{escapar_xml(noticia['url'])}</link>",
                (
                    f'<guid isPermaLink="true">'
                    f"{escapar_xml(noticia['url'])}</guid>"
                ),
                (
                    f"<pubDate>"
                    f"{format_datetime(noticia['fecha'])}"
                    f"</pubDate>"
                ),
                (
                    f"<description>"
                    f"{escapar_xml(noticia['descripcion'])}"
                    f"</description>"
                ),
                "</item>",
            ]
        )

    partes.extend(
        [
            "</channel>",
            "</rss>",
        ]
    )

    return "\n".join(partes)


def guardar_rss(contenido):
    temporal = ARCHIVO_RSS.with_suffix(
        ".xml.tmp"
    )

    temporal.write_text(
        contenido,
        encoding="utf-8",
    )

    temporal.replace(
        ARCHIVO_RSS
    )


def main():
    noticias = obtener_noticias()
    contenido = crear_rss(noticias)
    guardar_rss(contenido)

    print(
        f"RSS de Catenon creada correctamente con "
        f"{len(noticias)} noticias"
    )

    for noticia in noticias[:10]:
        print(
            noticia["fecha"].strftime("%d/%m/%Y"),
            "-",
            noticia["titulo"],
        )


if __name__ == "__main__":
    main()
