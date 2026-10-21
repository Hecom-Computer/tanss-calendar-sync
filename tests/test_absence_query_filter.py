from datetime import UTC, datetime
from unittest.mock import Mock

from tanss_sync.tanss.repository import TanssRepository


def test_absence_query_is_filtered_without_affecting_regular_query():
    client = Mock()
    client.put_with_meta.return_value = ([], {})
    repo = TanssRepository(client)
    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2027, 4, 1, tzinfo=UTC)
    repo.list_appointments(6862, start, end, created_from=start, with_recurring=True)
    main_body = client.put_with_meta.call_args.args[1]
    repo.list_appointments(6862, start, end, with_recurring=True, absences_only=True)
    absence_body = client.put_with_meta.call_args.args[1]
    assert 'planningTypes' not in main_body
    assert 'creationTimeframe' in main_body
    assert set(absence_body['planningTypes']) == {
        'VACATION', 'ILLNESS', 'ABSENCE', 'OVERTIME', 'STAND_BY', 'CUSTOM'
    }
    assert 'creationTimeframe' not in absence_body
    assert absence_body['employees'] == [6862]
    assert absence_body['fetchRecurring'] is True
