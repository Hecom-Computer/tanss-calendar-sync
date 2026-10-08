"""Private TANSS-Termine bleiben bei der Outlook-Synchronisation privat."""

from __future__ import annotations

import datetime as dt

from tanss_sync.domain.appointment import Appointment, AppointmentKind
from tanss_sync.domain.identity import SyncKey
from tanss_sync.microsoft.mapper import GraphMapper
from tanss_sync.sync.compare import fields_to_write, fingerprint
from tanss_sync.util.timezone import TimeConverter


def appointment(kind: AppointmentKind) -> Appointment:
    value = Appointment(key=SyncKey("m.bay@example.com", "uid-1"), kind=kind)
    value.subject = "Privattermin"
    value.start = dt.datetime(2026, 10, 9, 8, tzinfo=dt.UTC)
    value.end = dt.datetime(2026, 10, 9, 9, tzinfo=dt.UTC)
    return value


def test_privater_tanss_termin_wird_in_outlook_privat_angelegt() -> None:
    payload = GraphMapper(TimeConverter()).to_create_payload(
        appointment(AppointmentKind.PRIVATE))

    assert payload["sensitivity"] == "private"


def test_aenderung_zu_privat_wird_in_outlook_aktualisiert() -> None:
    private = appointment(AppointmentKind.PRIVATE)
    normal = appointment(AppointmentKind.FIXED)

    assert fingerprint(private) != fingerprint(normal)
    assert fields_to_write(private, normal) == {"sensitivity"}

    payload = GraphMapper(TimeConverter()).to_update_payload(
        private, {"sensitivity"})
    assert payload == {"sensitivity": "private"}


def test_aufgehobene_vertraulichkeit_wird_in_outlook_zurueckgesetzt() -> None:
    normal = appointment(AppointmentKind.FIXED)
    private = appointment(AppointmentKind.PRIVATE)

    assert fields_to_write(normal, private) == {"sensitivity"}

    payload = GraphMapper(TimeConverter()).to_update_payload(
        normal, {"sensitivity"})
    assert payload == {"sensitivity": "normal"}
