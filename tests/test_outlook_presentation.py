"""Outlook-spezifische TANSS-Darstellung darf keine Nutzdaten verfälschen."""

from __future__ import annotations

import datetime as dt
import html

import pytest

from tanss_sync.domain.appointment import Appointment, AppointmentKind, ServiceLocation
from tanss_sync.domain.identity import SyncKey
from tanss_sync.microsoft.mapper import GraphMapper
from tanss_sync.microsoft.presentation import default_categories, without_sync_info
from tanss_sync.util.html import HtmlText
from tanss_sync.util.timezone import TimeConverter


def termin(*, travel_role: str = "main") -> Appointment:
    value = Appointment(key=SyncKey("m.bay@example.com", "uid-1", -1, travel_role))
    value.subject = "Kundentermin"
    value.body = "Besprechung beim Kunden"
    value.location = "Beispielstraße 1, 68159 Mannheim"
    value.start = dt.datetime(2026, 10, 12, 8, tzinfo=dt.UTC)
    value.end = dt.datetime(2026, 10, 12, 9, tzinfo=dt.UTC)
    value.ticket_id = 12345
    value.service_location = ServiceLocation.CUSTOMER
    return value


def mapper(**kwargs) -> GraphMapper:
    return GraphMapper(TimeConverter(), ticket_url_template=(
        "https://ticket.example/index.php?ticket={ticket_id}"),
        sync_categories=True, category_prefix="TANSS",
        travel_navigation_links=True, **kwargs)


def test_ticket_link_wird_nur_mit_expliziter_vorlage_erzeugt() -> None:
    payload = mapper().to_create_payload(termin())
    text = payload["body"]["content"]
    assert "TANSS-Informationen" in text
    assert "TANSS-Ticket #12345" in text
    assert "[TANSS-SYNC-INFO]" not in text
    assert "https://ticket.example/index.php?ticket=12345" in text
    assert payload["categories"] == ["TANSS - Vor Ort"]


def test_navigation_steht_im_fahrtblock_und_vor_ort_termin() -> None:
    payload = mapper().to_create_payload(termin())
    assert "Route in Google Maps: https://www.google.com/maps/search/?api=1&query=" in payload["body"]["content"]


def test_ortsaenderung_aktualisiert_auch_den_kartenlink() -> None:
    payload = mapper().to_update_payload(
        termin(), {"location"}, existing_body="Besprechung beim Kunden")
    assert payload["location"] == {"displayName": "Beispielstraße 1, 68159 Mannheim"}
    assert "Route in Google Maps:" in payload["body"]["content"]

    payload = mapper().to_create_payload(termin(travel_role="travel_to"))
    assert "Route in Google Maps: https://www.google.com/maps/search/?api=1&query=" in payload["body"]["content"]


def test_sync_block_wird_beim_lesen_nicht_zu_tanss_nutztext() -> None:
    body = mapper().to_create_payload(termin())["body"]["content"]
    assert without_sync_info(body) == "Besprechung beim Kunden"


def test_lesbarer_infoblock_ersetzt_alte_marker() -> None:
    body = "Besprechung\n\n[TANSS-SYNC-INFO]\nTANSS-Link: alt\n[/TANSS-SYNC-INFO]"
    assert without_sync_info(body) == "Besprechung"


def test_veraltete_outlook_darstellung_wird_einmalig_aktualisiert() -> None:
    tanss = termin()
    graph = termin()
    graph.outlook_body_raw = (
        "Besprechung beim Kunden\n\n[TANSS-SYNC-INFO]\n"
        "TANSS-Link: alt\n[/TANSS-SYNC-INFO]")
    assert mapper().presentation_needs_refresh(graph, tanss)

    graph.outlook_body_raw = mapper().to_create_payload(tanss)["body"]["content"]
    assert not mapper().presentation_needs_refresh(graph, tanss)


def test_outlook_link_formatierung_erzeugt_keine_endlosschleife() -> None:
    tanss = termin()
    graph = termin()
    expected = mapper().to_create_payload(tanss)["body"]["content"]
    url = "https://ticket.example/index.php?ticket=12345"
    graph.outlook_body_raw = expected.replace(url, f"[{url}](<{url}>)")
    graph.outlook_body_raw = graph.outlook_body_raw.replace("\n", "  \n")
    assert not mapper().presentation_needs_refresh(graph, tanss)


def test_veraenderter_link_wird_weiterhin_aktualisiert() -> None:
    tanss = termin()
    graph = termin()
    expected = mapper().to_create_payload(tanss)["body"]["content"]
    url = "https://ticket.example/index.php?ticket=12345"
    graph.outlook_body_raw = expected.replace(url, f"[{url}](<https://evil.example/>)")
    assert mapper().presentation_needs_refresh(graph, tanss)


def test_outlook_html_mit_automatisch_verlinkter_url_ist_stabil() -> None:
    tanss = termin()
    graph = termin()
    expected = mapper().to_create_payload(tanss)["body"]["content"]
    url = "https://ticket.example/index.php?ticket=12345"
    markup = html.escape(expected).replace(url, f'<a href="{url}">{url}</a>')
    graph.outlook_body_raw = HtmlText().to_text("<html><body>" + markup.replace("\n", "<br>") + "</body></html>")
    assert not mapper().presentation_needs_refresh(graph, tanss)


def test_geaenderte_ticketnummer_bleibt_erkennbar() -> None:
    tanss = termin()
    graph = termin()
    graph.outlook_body_raw = mapper().to_create_payload(tanss)["body"]["content"]
    tanss.ticket_id = 99999
    assert mapper().presentation_needs_refresh(graph, tanss)


def test_eigene_outlook_kategorien_bleiben_bei_update_erhalten() -> None:
    payload = mapper().to_update_payload(
        termin(), {"subject"}, existing_categories=["Wichtig", "TANSS - Remote"])
    assert payload["categories"] == ["Wichtig", "TANSS - Vor Ort"]


def test_private_tanss_termin_erhaelt_private_kategorie() -> None:
    value = termin()
    value.kind = AppointmentKind.PRIVATE
    payload = mapper().to_create_payload(value)
    assert payload["categories"] == ["TANSS - Privat"]


@pytest.mark.parametrize(("kind", "category"), [
    (AppointmentKind.VACATION, "TANSS - Urlaub"),
    (AppointmentKind.OVERTIME, "TANSS - Zeitausgleich"),
])
def test_abwesenheit_erhaelt_eindeutige_kategorie(
        kind: AppointmentKind, category: str) -> None:
    value = termin()
    value.kind = kind
    payload = mapper().to_create_payload(value)
    assert payload["categories"] == [category]


def test_standardkategorien_enthalten_urlaub_und_zeitausgleich() -> None:
    categories = default_categories("TANSS")
    assert "TANSS - Urlaub" in categories
    assert "TANSS - Zeitausgleich" in categories
