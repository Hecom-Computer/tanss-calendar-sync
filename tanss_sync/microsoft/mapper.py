"""Umrechnung zwischen ``GraphEvent`` und ``Appointment``."""

from __future__ import annotations

from ..domain.appointment import Appointment, AppointmentKind, Attendee
from ..domain.identity import SyncKey
from ..domain.uid import NO_SEQUENCE
from ..util.html import HtmlText
from ..util.timezone import TimeConverter
from .models import GraphEvent
from .presentation import decorate_body, merge_categories, without_sync_info

# Felder des Appointment -> Graph-Eigenschaften. Nur was hier steht, wird geschrieben.
_UPDATABLE = {
    "subject": "subject",
    "body": "body",
    "location": "location",
    "start": "start",
    "end": "end",
    "show_as": "showAs",
    "sensitivity": "sensitivity",
}


class GraphMapper:
    def __init__(self, time: TimeConverter, *, html: HtmlText | None = None,
                 ticket_url_template: str | None = None,
                 sync_categories: bool = False, category_prefix: str = "TANSS",
                 travel_navigation_links: bool = False) -> None:
        self.time = time
        self.html = html or HtmlText()
        self.ticket_url_template = ticket_url_template
        self.sync_categories = sync_categories
        self.category_prefix = category_prefix
        self.travel_navigation_links = travel_navigation_links

    # ------------------------------------------------------------------ lesen

    def to_appointment(self, event: GraphEvent, mailbox: str, uid: str,
                       *, own_domains: set[str] | None = None) -> Appointment:
        own_domains = own_domains or set()
        raw_body_text = self.html.to_text(event.body.get("content", ""))
        body_text = without_sync_info(raw_body_text)

        # "Noch nicht zugesagt" gibt es nur, wo es etwas zuzusagen GAB. Graph meldet
        # bei einem selbst angelegten Termin ohne Eingeladene ebenfalls
        # response == "none" - da hat aber niemand eine Einladung offen gelassen,
        # es ist schlicht ein eigener Termin. Ohne diese Unterscheidung landet jeder
        # in Outlook eingetragene Termin in TANSS als orangefarbene Terminvormerkung
        # statt als fester Termin.
        eingeladene = [a for a in event.attendees
                       if (a.get("emailAddress", {}) or {}).get("address")]

        kind = AppointmentKind.FIXED
        if event.sensitivity == "private":
            kind = AppointmentKind.PRIVATE
        elif eingeladene and event.response in ("none", "notResponded"):
            kind = AppointmentKind.TENTATIVE

        attendees = [
            Attendee(
                email=(a.get("emailAddress", {}) or {}).get("address", "").lower(),
                name=(a.get("emailAddress", {}) or {}).get("name"),
                required=a.get("type") != "optional",
                response=(a.get("status", {}) or {}).get("response", "none"),
                is_organizer=False,
            )
            for a in event.attendees
            if (a.get("emailAddress", {}) or {}).get("address")
        ]
        organizer = event.organizer_address
        if organizer:
            attendees.append(Attendee(email=organizer, is_organizer=True,
                                      response="organizer"))

        return Appointment(
            key=SyncKey(mailbox=mailbox, uid=uid, sequence=NO_SEQUENCE),
            # Ohne Eingeladene gibt es keine offene Antwort: Der Postfachinhaber ist
            # der Veranstalter. Sonst stuende an einem selbst eingetragenen Termin in
            # TANSS der Status "angefragt", obwohl nie jemand gefragt wurde.
            own_response=event.response if eingeladene else "organizer",
            categories=list(event.categories),
            graph_event_id=event.id,
            series_master_id=event.series_master_id,
            subject=event.subject,
            body=body_text,
            outlook_body_raw=raw_body_text,
            location=(event.location or {}).get("displayName", ""),
            start=self.time.from_graph(event.start),
            end=self.time.from_graph(event.end),
            all_day=event.is_all_day,
            kind=kind,
            show_as=event.show_as,  # type: ignore[arg-type]
            is_cancelled=event.is_cancelled,
            mailbox=mailbox,
            attendees=attendees,
            teams_url=event.teams_join_url or self.html.extract_teams_url(body_text),
            tanss_hash=self.html.extract_tanss_hash(body_text),
            origin="OUTLOOK",
            created=event.created,
            last_modified=event.last_modified,
            tanss_support_id=event.tanss_support_id,
        )

    def presentation_needs_refresh(self, graph: Appointment,
                                   tanss: Appointment) -> bool:
        """Erkennt einen veralteten oder fehlenden Outlook-Infoblock.

        Nur wenn der fachliche Nutztext auf beiden Seiten identisch ist, darf die
        Darstellung ohne einen fachlichen TANSS-Änderungsvorgang aktualisiert werden.
        """
        raw = graph.outlook_body_raw
        if raw is None or graph.body.strip() != tanss.body.strip():
            return False
        return raw.strip() != self._body(tanss).strip()

    # ------------------------------------------------------------------ schreiben

    def to_create_payload(self, appointment: Appointment, *,
                          include_attendees: bool = False) -> dict:
        """Payload für einen neuen Termin.

        **Ohne ``attendees``**, wo immer möglich: Graph verschickt beim Anlegen eines
        Termins mit Teilnehmern automatisch Einladungen an alle — das lässt sich nicht
        abschalten. Ein Termin, der ohnehin nur den Kalender des Mitarbeiters füllen
        soll, braucht keine Teilnehmer und löst dann auch keine Mail aus.
        """
        payload: dict = {
            "subject": appointment.subject,
            "body": {"contentType": "text", "content": self._body(appointment)},
            "start": self.time.to_graph(appointment.start),
            "end": self.time.to_graph(appointment.end),
            "showAs": appointment.show_as,
            "isAllDay": appointment.all_day,
        }
        if appointment.kind.is_absence or appointment.key.travel_role != "main":
            # Ein Urlaubsantrag ueber zwei Wochen sind zehn Kalendereintraege, und zu
            # jedem Vor-Ort-Termin kommen zwei Fahrt-Bloecke. Mit der
            # Outlook-Voreinstellung poppte fuer jeden davon eine Erinnerung auf.
            payload["isReminderOn"] = False
        if appointment.location:
            payload["location"] = {"displayName": appointment.location}
        if appointment.kind is AppointmentKind.PRIVATE:
            payload["sensitivity"] = "private"
        if self.sync_categories:
            payload["categories"] = merge_categories([], appointment,
                                                        prefix=self.category_prefix)
        if include_attendees and appointment.attendees:
            payload["attendees"] = [
                {"emailAddress": {"address": a.email, "name": a.name or a.email},
                 "type": "required" if a.required else "optional"}
                for a in appointment.attendees if not a.is_organizer
            ]
        return payload

    def to_update_payload(self, appointment: Appointment, changed: set[str], *,
                          existing_body: str | None = None,
                          existing_categories: list[str] | None = None) -> dict:
        """Nur die tatsächlich geänderten Felder.

        ``attendees`` fehlt hier bewusst: Schon das bloße Mitsenden löst
        Aktualisierungsmails an alle Teilnehmer aus. Teilnehmer pflegt dieses Werkzeug
        nicht — sie kommen aus Outlook und bleiben dort.
        """
        payload: dict = {}
        for field in changed:
            target = _UPDATABLE.get(field)
            if target is None:
                continue
            if field == "sensitivity":
                payload[target] = ("private" if appointment.kind is AppointmentKind.PRIVATE
                                   else "normal")
                continue
            if field == "body":
                # Teams-Block und TANSS-Hash aus dem bestehenden Text retten.
                merged = self.html.preserve_blocks(existing_body, self._body(appointment))
                payload["body"] = {"contentType": "text", "content": merged}
            elif field == "location":
                payload["location"] = {"displayName": appointment.location}
            elif field in ("start", "end"):
                payload[target] = self.time.to_graph(getattr(appointment, field))
            else:
                payload[target] = getattr(appointment, field)
        if payload and self.sync_categories:
            payload["categories"] = merge_categories(existing_categories or [], appointment,
                                                        prefix=self.category_prefix)
        return payload

    def _body(self, appointment: Appointment) -> str:
        return decorate_body(
            appointment.body, appointment,
            ticket_url_template=self.ticket_url_template,
            travel_navigation_links=self.travel_navigation_links,
        )
