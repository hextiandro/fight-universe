"""Conector de eventos de la UFC en Wikipedia.

Lee la página de un evento y propone su cartelera. No resuelve entidades ni escribe en la
base de datos: emite candidatos con menciones sin resolver, que es el contrato de
`connectors.base`.

Los enlaces de cada peleador se conservan como pista: el título de su página de Wikipedia
es un identificador externo, y por tanto el nivel 1 de la resolución de entidades.
"""

import hashlib
import os
import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from ..domain.vocab import parse_division, parse_method, parse_round, parse_time
from .base import Candidate, Mention, RawDoc

API = "https://en.wikipedia.org/w/api.php"
SOURCE_ID = "wikipedia-events"


# Wikimedia rechaza con 403 los agentes sin contacto: debe ser una URL o un correo.
DEFAULT_CONTACT = "https://github.com/hextiandro/fight-universe"


def user_agent() -> str:
    """El contacto puede personalizarse con WIKIMEDIA_CONTACT (correo o URL)."""
    contact = os.environ.get("WIKIMEDIA_CONTACT") or DEFAULT_CONTACT
    return f"FightUniversePipeline/0.1 ({contact})"


class WikipediaEvents:
    id = SOURCE_ID
    trust = 60  # referencia comunitaria: útil, pero no verifica por sí sola

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": user_agent()}, timeout=20.0, follow_redirects=True
        )

    def fetch_page(self, title: str) -> RawDoc:
        response = self._client.get(
            API,
            params={
                "action": "parse",
                "page": title,
                "prop": "text",
                "format": "json",
                "formatversion": "2",
                "redirects": "1",
            },
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise LookupError(f"Wikipedia no tiene la página «{title}»: {data['error'].get('info')}")
        parsed = data["parse"]
        html = parsed["text"]
        return RawDoc(
            source_id=self.id,
            url=f"https://en.wikipedia.org/wiki/{parsed['title'].replace(' ', '_')}",
            hash=hashlib.sha256(html.encode()).hexdigest(),
            payload={"title": parsed["title"], "html": html},
            fetched_at=datetime.now(),
        )

    LIST_PAGE = "List of UFC events"

    def window(self, months: int = 6, today: date | None = None) -> list[dict[str, str]]:
        """Eventos de los últimos `months` meses y los ya anunciados.

        La ventana acotada es lo que mantiene el planeta legible: el histórico completo
        son más de 700 eventos.
        """
        today = today or date.today()
        floor = today - timedelta(days=months * 30)
        doc = self.fetch_page(self.LIST_PAGE)
        soup = BeautifulSoup(doc.payload["html"], "lxml")

        found: dict[str, dict[str, str]] = {}
        for table in soup.find_all("table"):
            headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
            if "event" not in headers or "date" not in headers:
                continue
            offset = headers.index("event")  # la tabla de pasados lleva una columna "#" delante
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < offset + 2:
                    continue
                event = self._event_row(cells[offset], cells[offset + 1])
                if event and floor <= date.fromisoformat(event["date"]):
                    found.setdefault(event["title"], event)
        return sorted(found.values(), key=lambda e: e["date"])

    @staticmethod
    def _event_row(name_cell: Tag, date_cell: Tag) -> dict[str, str] | None:
        link = name_cell.find("a")
        title = link.get("title") if isinstance(link, Tag) else None
        if not isinstance(title, str):
            return None
        raw = date_cell.get_text(" ", strip=True)
        for fmt in ("%b %d, %Y", "%B %d, %Y"):
            try:
                return {"title": title, "date": datetime.strptime(raw, fmt).date().isoformat()}
            except ValueError:
                continue
        return None

    def fetch(self, since: datetime | None = None) -> Iterable[RawDoc]:
        """Descarga las páginas de los eventos de la ventana."""
        for event in self.window():
            yield self.fetch_page(event["title"])

    def extract(self, doc: RawDoc) -> Iterable[Candidate]:
        soup = BeautifulSoup(doc.payload["html"], "lxml")
        event_title = doc.payload["title"]

        event = self._extract_event(soup, event_title)
        if event:
            yield Candidate(
                kind="event",
                payload=event,
                source_id=self.id,
                raw_doc_hash=doc.hash,
                confidence=self.trust,
                mentions=[Mention(entity_type="event", text=event_title, hints={"wikipedia": event_title})],
            )

        for position, fight in enumerate(self._extract_fights(soup)):
            yield Candidate(
                kind="fight",
                payload={**fight["payload"], "eventTitle": event_title, "cardPosition": position},
                source_id=self.id,
                raw_doc_hash=doc.hash,
                confidence=self.trust,
                mentions=[
                    Mention(entity_type="event", text=event_title, hints={"wikipedia": event_title}),
                    *fight["mentions"],
                ],
            )

    # ── detalles de la fuente ──

    def _extract_event(self, soup: BeautifulSoup, title: str) -> dict[str, Any] | None:
        infobox = soup.find("table", class_=re.compile("infobox"))
        if not isinstance(infobox, Tag):
            return None
        fields: dict[str, str] = {}
        for row in infobox.find_all("tr"):
            header, value = row.find("th"), row.find("td")
            if isinstance(header, Tag) and isinstance(value, Tag):
                fields[header.get_text(" ", strip=True).lower()] = value.get_text(" ", strip=True)

        date_text = fields.get("date", "")
        date = None
        for fmt in ("%B %d, %Y", "%d %B %Y"):
            try:
                date = datetime.strptime(date_text.split("(")[0].strip(), fmt).date().isoformat()
                break
            except ValueError:
                continue

        return {
            "name": title,
            "date": date,
            "venue": fields.get("venue"),
            "city": fields.get("city"),
        }

    def _extract_fights(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        fights: list[dict[str, Any]] = []
        # Se busca por contenido, no por clase: las carteleras usan "toccolours" o
        # "wikitable" según el evento, y eso cambia con el tiempo.
        for table in soup.find_all("table"):
            headers = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
            if not any(h.startswith("weight class") for h in headers):
                continue
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 7:
                    continue
                fight = self._parse_row(cells)
                if fight:
                    fights.append(fight)
        return fights

    def _parse_row(self, cells: list[Tag]) -> dict[str, Any] | None:
        division = parse_division(cells[0].get_text(" ", strip=True))
        if division is None:
            return None  # femenino o peso pactado: fuera de alcance

        left, outcome, right = cells[1], cells[2].get_text(" ", strip=True).lower(), cells[3]
        method, detail = parse_method(cells[4].get_text(" ", strip=True))
        names = [self._name_and_link(left), self._name_and_link(right)]
        if not all(n["text"] for n in names):
            return None

        # "def." indica ganador; "vs." es sin resultado (NC o empate).
        winner = names[0]["text"] if outcome.startswith("def") else None
        return {
            "payload": {
                "status": "completed" if method else "scheduled",
                "divisionId": division,
                "fighters": [n["text"] for n in names],
                "winner": winner,
                "method": method,
                "methodDetail": detail,
                "round": parse_round(cells[5].get_text(strip=True)),
                "time": parse_time(cells[6].get_text(strip=True)),
            },
            "mentions": [
                Mention(
                    entity_type="fighter",
                    text=n["text"],
                    hints={k: v for k, v in {"wikipedia": n["link"], "division": division}.items() if v},
                )
                for n in names
            ],
        }

    @staticmethod
    def _name_and_link(cell: Tag) -> dict[str, str | None]:
        link = cell.find("a")
        title = link.get("title") if isinstance(link, Tag) else None
        text = cell.get_text(" ", strip=True)
        text = re.sub(r"\s*\(c\)\s*$", "", text)  # marca de campeón
        return {"text": text, "link": title if isinstance(title, str) else None}
