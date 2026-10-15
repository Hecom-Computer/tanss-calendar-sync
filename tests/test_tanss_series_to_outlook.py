"""TANSS-Serien werden als eine echte Outlook-Serie angelegt."""

from __future__ import annotations

from datetime import UTC, datetime

from tanss_sync.microsoft.mapper import GraphMapper
from tanss_sync.sync.engine import _include_existing_series_masters
from tanss_sync.tanss.mapper import TanssMapper
from tanss_sync.tanss.models import TanssSupport
from tanss_sync.util.timezone import TimeConverter


def test_tanss_master_rule_becomes_graph_recurrence() -> None:
    support = TanssSupport(
        id=31298,
        date=int(datetime(2026, 10, 19, 9, tzinfo=UTC).timestamp()),
        duration=60,
        employeeId=6859,
        companyId=0,
        planningType="APPOINTMENT_FIX",
        outlookTitle="Wöchentliches Meeting 2026",
        recurrenceRule="RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO;UNTIL=20261228T100000Z",
    )

    appointment = TanssMapper(TimeConverter()).to_appointment(
        support, "t.stadler@hecom.de", "pending:31298")
    payload = GraphMapper(TimeConverter()).to_create_payload(appointment)

    assert payload["recurrence"] == {
        "pattern": {"type": "weekly", "interval": 1, "daysOfWeek": ["monday"]},
        "range": {
            "type": "endDate",
            "startDate": "2026-10-19",
            "endDate": "2026-12-28",
            "recurrenceTimeZone": "Europe/Berlin",
        },
    }


def test_existing_series_master_is_adopted_but_not_old_single_appointment() -> None:
    master = TanssSupport(
        id=31298, date=int(datetime(2026, 10, 19, 9, tzinfo=UTC).timestamp()),
        duration=60, employeeId=6859, companyId=0, planningType="APPOINTMENT_FIX",
        recurrenceRule="RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO",
    )
    old_single = TanssSupport(
        id=31299, date=int(datetime(2026, 10, 20, 9, tzinfo=UTC).timestamp()),
        duration=60, employeeId=6859, companyId=0, planningType="APPOINTMENT_FIX",
    )

    adopted = _include_existing_series_masters([], [master, old_single])

    assert adopted == [master]
