"""Abwesenheits-Titel aus TANSS sinnvoll für Outlook aufbereiten."""

from __future__ import annotations

import datetime as dt

from tanss_sync.domain.appointment import AppointmentKind
from tanss_sync.sync.engine import _include_existing_absences
from tanss_sync.tanss.mapper import TanssMapper
from tanss_sync.tanss.models import TanssPlanningType, TanssSupport
from tanss_sync.util.timezone import TimeConverter


def _support(planning_type: str) -> TanssSupport:
    return TanssSupport(
        id=139668,
        date=int(dt.datetime(2026, 10, 26, 7, tzinfo=dt.UTC).timestamp()),
        duration=540,
        employeeId=6862,
        companyId=0,
        planningType=planning_type,
    )


def test_leerer_urlaubsbetreff_wird_in_outlook_lesbar() -> None:
    appointment = TanssMapper(TimeConverter()).to_appointment(
        _support("VACATION"), "m.fabrinsky@example.com", "pending:139668")

    assert appointment.kind is AppointmentKind.VACATION
    assert appointment.subject == "Urlaub"


def test_leerer_zeitausgleich_bekommt_einen_eigenen_betreff() -> None:
    appointment = TanssMapper(TimeConverter()).to_appointment(
        _support("OVERTIME"), "m.fabrinsky@example.com", "pending:139668")

    assert appointment.kind is AppointmentKind.OVERTIME
    assert appointment.subject == "Zeitausgleich"


def test_bestehender_urlaub_wird_trotz_aktivierungsfilter_ergänzt() -> None:
    vacation = _support("VACATION")
    old_appointment = _support("APPOINTMENT_FIX")

    items = _include_existing_absences([old_appointment], [old_appointment, vacation])

    assert [item.planning_type for item in items] == [
        TanssPlanningType.APPOINTMENT_FIX,
        TanssPlanningType.VACATION,
    ]
