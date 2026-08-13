from __future__ import annotations

from faker import Faker

from .config import DEFAULT_CONFIG, FakerConfig
from .models import PIIType


class FakeValueFactory:
    def __init__(self, config: FakerConfig | None = None) -> None:
        self._config = config or DEFAULT_CONFIG.faker
        self._faker = Faker(self._config.locale)
        self._faker.seed_instance(self._config.seed)
        self._fallback = Faker("en_US")
        self._fallback.seed_instance(self._config.seed)

    def fake_for(self, original: str, entity_type: PIIType) -> str:
        generators = {
            PIIType.PERSON: self._person,
            PIIType.EMAIL_ADDRESS: self._email,
            PIIType.PHONE_NUMBER: self._phone,
            PIIType.ORGANIZATION: self._company,
            PIIType.LOCATION: self._city,
            PIIType.ADDRESS: self._address,
            PIIType.US_SSN: lambda: self._fallback.ssn(),
            PIIType.CREDIT_CARD: lambda: self._fallback.credit_card_number(),
            PIIType.DATE_OF_BIRTH: lambda: self._faker.date_of_birth(
                minimum_age=25, maximum_age=75
            ).strftime("%d %B %Y"),
            PIIType.IP_ADDRESS: self._ip,
            PIIType.DATE_TIME: lambda: self._faker.date(),
            PIIType.URL: lambda: self._faker.url(),
            PIIType.IN_PAN: self._pan,
            PIIType.IN_AADHAAR: self._aadhaar,
        }
        builder = generators.get(entity_type, lambda: self._faker.word().title())
        fake = builder().strip()
        return fake or original

    def _person(self) -> str:
        return self._faker.name()

    def _email(self) -> str:
        return self._faker.email()

    def _phone(self) -> str:
        return self._faker.numerify("+91 9#### #####")

    def _company(self) -> str:
        name = self._faker.company()
        if "limited" not in name.casefold():
            name = f"{name} Private Limited"
        return name

    def _city(self) -> str:
        return self._faker.city()

    def _address(self) -> str:
        return " ".join(self._faker.address().split())

    def _ip(self) -> str:
        return self._faker.ipv4()

    def _pan(self) -> str:
        return self._faker.bothify(text="?????####?", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ").upper()

    def _aadhaar(self) -> str:
        return self._faker.numerify(text="#### #### ####")
