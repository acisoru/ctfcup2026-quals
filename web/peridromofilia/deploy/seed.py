import json
import os
import random
import secrets

from mongoengine import connect

from models import CatalogEntry, GoldenProfile, Member, OwnedCard, Trade
from stations import STATIONS

connect("peridromofilia", host="mongodb://mongo:27017/peridromofilia")


def seed_catalog():
    if CatalogEntry.objects.count() > 0:
        return
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog.json")
    with open(path) as f:
        data = json.load(f)
    for e in data:
        CatalogEntry(
            n=e["n"], name=e["name"], park=e.get("start"),
            size=e["size"], year=e.get("year"), kind=e["kind"],
        ).save()
    print("catalog seeded:", len(data))


def seed_members():
    if Member.objects.count() > 0:
        return
    veterans = [
        ("troika_1998", "Костя Ветров", 1998),
        ("nina_kad", "Нина Кадочникова", 2003),
    ]
    members = {}
    for username, nickname, since in veterans:
        profile = GoldenProfile(nickname=nickname, home_station=random.choice(STATIONS),
                                member_since=since)
        Member(username=username, password_hash=secrets.token_hex(16), profile=profile).save()
    members["troika_1998"] = Member.objects(username="troika_1998").first()
    members["nina_kad"] = Member.objects(username="nina_kad").first()

    keeper = Member(username="Вахтер Галина Ивановна", password_hash=secrets.token_hex(16))
    keeper.save()
    Member.objects(username="Вахтер Галина Ивановна").update(
        __raw__={"$set": {"profile": {"_cls": "ServiceCard"}}}
    )
    members["keeper"] = Member.objects(username="Вахтер Галина Ивановна").first()

    people = [
        ("misha_radial", "Миша Радиалкин"),
        ("olga_sokolova", "Ольга Соколова"),
        ("dima_ogurtsov", "Дима Огурцов"),
        ("vera_pribyt", "Вера Прибыткова"),
        ("kolya_mostov", "Коля Мостовой"),
        ("asya_zaytseva", "Ася Зайцева"),
        ("gennady_skam", "Геннадий Скамейкин"),
        ("luba_kabluk", "Люба Каблукова"),
        ("artem_polezhaev", "Артур Полежаевский"),
        ("sonya_krasnorot", "Соня Красноворотинская"),
        ("pasha_trest", "Паша Трестовый"),
        ("manya_vokzal", "Маня Вокзальная"),
    ]
    for username, nickname in people:
        profile = {"nickname": nickname, "home_station": random.choice(STATIONS)}
        Member(username=username, password_hash=secrets.token_hex(16),
               profile=profile).save()
        members[username] = Member.objects(username=username).first()

    all_cards = [e.n for e in CatalogEntry.objects]
    for username, member in members.items():
        for n in random.sample(all_cards, random.randint(2, 9)):
            OwnedCard(card=n, member=member).save()
    print("members seeded:", len(members))


def seed_trades():
    if Trade.objects.count() > 0:
        return
    all_cards = [e.n for e in CatalogEntry.objects]
    members = list(Member.objects)
    notes = [
        "Обменяюсь, обсудим на воскресной встрече.",
        "Дубликат, отдам не дорого.",
        "Меняю на что-нибудь из моего вишлиста.",
        "Карты в хорошем состоянии, хранились в альбоме.",
        "Отдам за две обычные стоечные.",
        "Ищу именно этот тираж, доплата сверху возможна.",
        "Поменяю, заберу на Савёловской.",
        "Обмен только при личной встрече, каморка по воскресеньям.",
        "Тираж маленький, прошу не предлагать мусор.",
        "Карту привезли с фестиваля, состояние показываю на встрече.",
        "Отдам за равноценную подарочную.",
        "Меняю с доплатой в мою сторону.",
        "Ждать долго не буду, поменяюсь быстро.",
        "Есть небольшой скол на углу, честно предупреждаю.",
        "Эту карту ищу третий год.",
        "Обмены через камеру хранения, Галина Ивановна передаст.",
        "Только обмен, деньгами не интересуюсь.",
        "Отдам двумя за одну редкую.",
        "Повторка куплена на радостях, теперь девать некуда.",
        "Состояние коллекционное, из запечатанной пачки.",
        "Откликнувшимся накину бонусом стоечную.",
        "Карта с закрытого мероприятия, больше такой не будет.",
        "Хочу закрыть дыру в коллекции, предлагаю щедро.",
        "Меняю на две любых тройки про МЦК.",
        "Спам не пишите, отвечаю по делу.",
        "Не горит, но пусть висит.",
        "Могу подождать, обмен не срочный.",
        "Карта почти не использована, лежала в шкафу.",
        "Меняю на что-нибудь про космос.",
        "Обмен при встрече, почтой не занимаюсь.",
        "Номер из начала тиража, для любителей ровных.",
        "Использована всего пару поездок, состояние на осмотр.",
        "Ровняю коллекцию к выставке, строго обмен.",
        "Смотрю любые предложения, пишите смело.",
        "Привезена из Питера, у нас такой вроде не было.",
        "Обмен в каморке у камеры хранения, после полудня.",
        "Ищу этот же тираж другого цвета.",
        "Дубликаты под обмен, список в моей коллекции.",
        "Могу добавить стоечную в придачу.",
        "Кому-то повезёт, карта в одни руки.",
        "Обменяю на воскресной встрече, стучаться три раза.",
        "Не ищу навара, просто не моя тема.",
        "Тираж подарочный, по рукам ходит мало.",
        "Проверена на чтение в метро, работает.",
        "Кто заберёт до Нового года, тому бонусом открытку.",
        "Разбираю дубль, забирайте пока дают.",
        "Меняю на любой выпуск с Таганской.",
        "Условия обсуждаемы, но в разумных пределах.",
        "Углы целые, лёгкая потёртость по краю.",
        "Взята у казанского коллекционера, мне не нужна.",
        "Вторая такая у меня уже есть, эта лишняя.",
        "Обменяю через Галину Ивановну, работает безотказно.",
    ]
    for member in members:
        for _ in range(random.randint(1, 4)):
            offer, want = random.sample(all_cards, 2)
            Trade(member=member, offer=offer, want=want,
                  note=random.choice(notes)).save()
    print("trades seeded:", Trade.objects.count())


if __name__ == "__main__":
    seed_catalog()
    seed_members()
    seed_trades()
