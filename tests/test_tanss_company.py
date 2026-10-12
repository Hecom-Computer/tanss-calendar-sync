from tanss_sync.tanss.models import TanssCompany


def test_firmenanschrift_fuer_outlook() -> None:
    company = TanssCompany.model_validate({
        "id": 4034,
        "name": "Remitex GmbH",
        "street": "Im Schorrenfeld 5",
        "postcode": "76661",
        "city": "Philippsburg-Huttenheim",
    })
    assert company.postal_address == "Im Schorrenfeld 5, 76661 Philippsburg-Huttenheim"
