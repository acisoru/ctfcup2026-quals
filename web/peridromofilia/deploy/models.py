from datetime import datetime

from mongoengine import DateTimeField, Document, EmbeddedDocument, EmbeddedDocumentField, \
    IntField, LongField, ReferenceField, StringField


class Profile(EmbeddedDocument):
    nickname = StringField(max_length=64)
    home_station = StringField(max_length=64)
    meta = {"allow_inheritance": True}

    def badge(self) -> str:
        return "Пассажир"


class GoldenProfile(Profile):
    member_since = IntField()

    def badge(self) -> str:
        return "Золотой друг клуба"


class ServiceCard(EmbeddedDocument):
    def badge(self) -> str:
        try:
            with open("/flag.txt") as f:
                return "Служебный доступ: " + f.read().strip()
        except FileNotFoundError:
            return "Служебный доступ: [карта считана вне фонда]"


class Member(Document):
    username = StringField(required=True, unique=True, max_length=32, regex=r"^[a-zA-Zа-яА-ЯёЁ0-9_ ]{3,32}$")
    password_hash = StringField(required=True)
    profile = EmbeddedDocumentField(Profile)

    def card_type(self) -> str:
        if self.profile is None:
            return "—"
        return type(self.profile).__name__

    def display(self):
        p = self.profile
        return {
            "username": self.username,
            "nickname": getattr(p, "nickname", None) if p is not None else None,
            "home_station": getattr(p, "home_station", None) if p is not None else None,
            "badge": p.badge() if p is not None else None,
            "card": self.card_type(),
        }


class Trip(Document):
    member = ReferenceField(Member, required=True)
    station_from = StringField(required=True, max_length=64)
    station_to = StringField(required=True, max_length=64)
    created = DateTimeField(default=datetime.utcnow)


class CatalogEntry(Document):
    n = IntField(required=True, unique=True)
    name = StringField(required=True, max_length=140)
    park = LongField()
    size = IntField()
    year = IntField()
    kind = StringField(max_length=40)


class OwnedCard(Document):
    member = ReferenceField(Member, required=True)
    card = IntField(required=True)
    created = DateTimeField(default=datetime.utcnow)


class Trade(Document):
    member = ReferenceField(Member, required=True)
    offer = IntField(required=True)
    want = IntField(required=True)
    note = StringField(max_length=200)
    created = DateTimeField(default=datetime.utcnow)
