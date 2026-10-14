"""Zusätzliche, nur für Outlook bestimmte Darstellungsinformationen.

Die Informationen in diesem Modul werden *nie* zurück nach TANSS geschrieben.
Sie helfen im Outlook-Kalender bei der Orientierung, ohne den eigentlichen
Termintext oder persönliche Kategorien zu verfälschen.
"""

from __future__ import annotations

from urllib.parse import urlencode

from ..domain.appointment import Appointment, AppointmentKind, ServiceLocation

# Die alten Marker bleiben nur für die Migration bereits geschriebener Termine.
# Neue Termine zeigen einen lesbaren Abschnitt ohne technische Klammer-Marker.
_LEGACY_START = "[TANSS-SYNC-INFO]"
_LEGACY_END = "[/TANSS-SYNC-INFO]"
_VISIBLE_START = "TANSS-Informationen"


def without_sync_info(text: str | None) -> str:
    """Entfernt ausschließlich den von uns erzeugten Informationsblock."""
    if not text:
        return ""
    legacy_start = text.find(_LEGACY_START)
    if legacy_start >= 0:
        end = text.find(_LEGACY_END, legacy_start)
        if end < 0:
            return text[:legacy_start].rstrip()
        return (text[:legacy_start] + text[end + len(_LEGACY_END):]).strip()

    # Der neue, bewusst sichtbare Abschnitt wird immer am Ende angehängt.
    # Damit gelangt er beim Rückweg Outlook -> TANSS nicht in den Nutztext.
    visible_start = text.find(_VISIBLE_START)
    return text[:visible_start].rstrip() if visible_start >= 0 else text.strip()


def ticket_url(template: str | None, ticket_id: int | None) -> str | None:
    """Baut nur aus einer explizit konfigurierten Vorlage einen Ticket-Link.

    TANSS-Installationen haben keine einheitliche Web-URL für Tickets. Deshalb
    wird hier bewusst nichts geraten oder aus der API-Adresse abgeleitet.
    """
    if not template or not ticket_id:
        return None
    return template.format(ticket_id=ticket_id)


def navigation_url(location: str) -> str | None:
    """Google-Maps-Suche für einen bereits im TANSS-Termin hinterlegten Ort."""
    location = location.strip()
    if not location:
        return None
    return "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": location})


def sync_info(appointment: Appointment, *, ticket_url_template: str | None,
              travel_navigation_links: bool) -> str:
    """Kompakter, klar abgegrenzter Infoblock für Outlook."""
    lines: list[str] = []
    link = ticket_url(ticket_url_template, appointment.ticket_id)
    if appointment.ticket_id:
        lines.append(f"TANSS-Ticket #{appointment.ticket_id}")
    if link:
        lines.append(f"Ticket öffnen: {link}")
    # Eine Adresse hilft nicht nur bei getrennten An- und Abfahrtblöcken,
    # sondern ebenso beim eigentlichen Vor-Ort-Termin. Remote- und interne
    # Termine bekommen keinen Link, auch wenn dort versehentlich ein Ort steht.
    needs_navigation = (
        appointment.key.travel_role != "main"
        or appointment.service_location is ServiceLocation.CUSTOMER
    )
    if travel_navigation_links and needs_navigation:
        navigation = navigation_url(appointment.location)
        if navigation:
            lines.append(f"Route in Google Maps: {navigation}")
    if not lines:
        return ""
    return "\n".join([_VISIBLE_START, *lines])


def decorate_body(body: str, appointment: Appointment, *, ticket_url_template: str | None,
                  travel_navigation_links: bool) -> str:
    """Ersetzt den eigenen Block idempotent und erhält den Nutztext."""
    base = without_sync_info(body)
    info = sync_info(appointment, ticket_url_template=ticket_url_template,
                     travel_navigation_links=travel_navigation_links)
    return "\n\n".join(part for part in (base, info) if part).strip()


def category_for(appointment: Appointment, *, prefix: str) -> str | None:
    """Eine TANSS-Kategorie, die sich von privaten Outlook-Kategorien abgrenzt."""
    prefix = prefix.strip()
    if not prefix:
        return None
    if appointment.kind is AppointmentKind.PRIVATE:
        label = "Privat"
    elif appointment.kind is AppointmentKind.VACATION:
        label = "Urlaub"
    elif appointment.kind is AppointmentKind.OVERTIME:
        label = "Zeitausgleich"
    elif appointment.kind.is_absence:
        label = "Abwesenheit"
    elif appointment.key.travel_role != "main":
        label = "Fahrt"
    elif appointment.service_location is ServiceLocation.CUSTOMER:
        label = "Vor Ort"
    elif appointment.service_location is ServiceLocation.REMOTE:
        label = "Remote"
    else:
        label = "Intern" if appointment.is_internal else "Termin"
    return f"{prefix} - {label}"


def merge_categories(existing: list[str], appointment: Appointment, *, prefix: str) -> list[str]:
    """Ersetzt nur unsere Kategorie; alle übrigen Outlook-Kategorien bleiben."""
    marker = f"{prefix.strip()} - "
    kept = [value for value in existing if not value.startswith(marker)]
    category = category_for(appointment, prefix=prefix)
    return [*kept, category] if category else kept


def default_categories(prefix: str) -> dict[str, str]:
    """Name -> Outlook-Farbe für die einmalige Anlage der Master-Kategorien."""
    return {
        f"{prefix} - Vor Ort": "preset0",
        f"{prefix} - Remote": "preset7",
        f"{prefix} - Fahrt": "preset22",
        f"{prefix} - Privat": "preset19",
        f"{prefix} - Urlaub": "preset24",
        f"{prefix} - Zeitausgleich": "preset3",
        f"{prefix} - Abwesenheit": "preset24",
        f"{prefix} - Intern": "preset14",
        f"{prefix} - Termin": "preset9",
    }
