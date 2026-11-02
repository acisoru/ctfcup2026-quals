import hashlib
import secrets
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from mongoengine import connect
from mongoengine.errors import DoesNotExist, NotUniqueError
from mongoengine.queryset.visitor import Q

from models import CatalogEntry, GoldenProfile, Member, OwnedCard, Trade, Trip
from stations import is_station

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

connect("peridromofilia", host="mongodb://mongo:27017/peridromofilia")


def hash_password(username: str, password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), username.encode(), 100_000).hex()


def card_name(n: int) -> str:
    e = CatalogEntry.objects(n=n).first()
    return e.name if e else "неизвестная тройка"


KINDS = [
    "стоечная", "подарочная", "прочая",
    "Стрелка", "банковская", "Тройка + Подорожник", "Тройка + Стрелка", "виртуальная",
]

_catalog_total = None


def catalog_total():
    global _catalog_total
    if _catalog_total is None:
        _catalog_total = CatalogEntry.objects.count()
    return _catalog_total


@app.context_processor
def inject_globals():
    return {"me": session.get("u")}


@app.errorhandler(Exception)
def on_error(e):
    return jsonify({"error": str(e)}), 400


@app.route("/")
def index():
    wall = [m.display() for m in Member.objects().order_by("-id")[:8]]
    trips = Trip.objects().order_by("-id")[:8]
    fresh = []
    for oc in OwnedCard.objects().order_by("-id")[:8]:
        fresh.append({
            "nickname": oc.member.display().get("nickname") or oc.member.username,
            "name": card_name(oc.card), "n": oc.card,
        })
    return render_template("index.html", wall=wall, trips=trips, fresh=fresh,
                           total=catalog_total(), members_total=Member.objects.count())


@app.route("/members")
def members():
    q = request.args.get("q", "").strip()
    if q:
        found = Member.objects(Q(profile__home_station__icontains=q) | Q(profile__nickname__icontains=q))
    else:
        found = Member.objects()
    rows = []
    for m in found.order_by("-id")[:100]:
        d = m.display()
        d["cards"] = OwnedCard.objects(member=m).count()
        rows.append(d)
    return render_template("members.html", members=rows, q=q)


@app.route("/catalog")
def catalog():
    q = request.args.get("q", "").strip()
    kind = request.args.get("kind", "").strip()
    year = request.args.get("year", "").strip()
    flt = {}
    if q:
        flt["name__icontains"] = q
    if kind in KINDS:
        flt["kind"] = kind
    if year.isdigit():
        flt["year"] = int(year)
    sort = request.args.get("sort", "n")
    if sort not in ("n", "year", "-year"):
        sort = "n"
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    per = 50
    qs = CatalogEntry.objects(**flt)
    count = qs.count()
    entries = list(qs.order_by(sort)[(page - 1) * per: page * per])
    owned = set()
    if "u" in session:
        member = Member.objects(username=session["u"]).first()
        if member is not None:
            owned = set(OwnedCard.objects(member=member).scalar("card"))
    pages = max(1, (count + per - 1) // per)
    return render_template("catalog.html", entries=entries, q=q, kind=kind, year=year, sort=sort,
                           kinds=KINDS, count=count, page=page, pages=pages, owned=owned,
                           total=catalog_total())


@app.route("/collection")
def collection():
    if "u" not in session:
        return redirect(url_for("index"))
    member = Member.objects(username=session["u"]).first()
    cards = OwnedCard.objects(member=member).order_by("-id")
    rows = []
    for oc in cards:
        e = CatalogEntry.objects(n=oc.card).first()
        if e is None:
            continue
        rows.append({"n": e.n, "name": e.name, "year": e.year, "size": e.size,
                     "kind": e.kind, "added": oc.created})
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(kinds.items()))
    return render_template("collection.html", rows=rows, total=catalog_total(), summary=summary)


@app.route("/trades")
def trades():
    if "u" not in session:
        return redirect(url_for("index"))
    member = Member.objects(username=session["u"]).first()
    rows = []
    for t in Trade.objects().order_by("-id")[:100]:
        rows.append({
            "id": t.id,
            "mine": t.member == member,
            "nickname": t.member.display().get("nickname") or t.member.username,
            "offer": card_name(t.offer) + f" (№{t.offer})",
            "want": card_name(t.want) + f" (№{t.want})",
            "note": t.note,
            "created": t.created,
        })
    mine = []
    for c in OwnedCard.objects(member=member).scalar("card"):
        e = CatalogEntry.objects(n=c).first()
        if e is not None:
            mine.append({"n": e.n, "name": e.name})
    return render_template("trades.html", trades=rows, mine=mine)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/me")
def me():
    if "u" not in session:
        return redirect(url_for("index"))
    member = Member.objects(username=session["u"]).first()
    trips = Trip.objects(member=member).order_by("-id")[:10]
    cards = OwnedCard.objects(member=member).count()
    return render_template("me.html", d=member.display(), trips=trips, cards=cards,
                           trips_total=Trip.objects(member=member).count())


@app.route("/register", methods=["POST"])
def register():
    username = request.form.get("username", "").lower().strip()
    password = request.form.get("password", "")
    nickname = request.form.get("nickname", "").strip() or username
    home_station = request.form.get("home_station", "").strip()
    if home_station and not is_station(home_station):
        return render_template("index.html", error="Такой станции в московском метро нет",
                               wall=[], trips=[], fresh=[], total=0, members_total=0), 400
    if not username or not password:
        return render_template("index.html", error="Укажите логин и пароль",
                               wall=[], trips=[], fresh=[], total=0, members_total=0), 400
    member = Member(
        username=username,
        password_hash=hash_password(username, password),
        profile={"nickname": nickname, "home_station": home_station},
    )
    try:
        member.save()
    except NotUniqueError:
        return render_template("index.html", error="Такой логин уже занят",
                               wall=[], trips=[], fresh=[], total=0, members_total=0), 400
    session["u"] = username
    return redirect(url_for("me"))


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").lower().strip()
    password = request.form.get("password", "")
    member = Member.objects(username=username).first()
    if member is None or member.password_hash != hash_password(username, password):
        return render_template("index.html", error="Неверный логин или пароль",
                               wall=[], trips=[], fresh=[], total=0, members_total=0), 400
    session["u"] = username
    return redirect(url_for("me"))


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("u", None)
    return redirect(url_for("index"))


@app.route("/api/collection", methods=["POST"])
def collection_toggle():
    if "u" not in session:
        return jsonify({"error": "войдите в клуб"}), 400
    try:
        n = int(request.form.get("card", ""))
    except ValueError:
        return jsonify({"error": "неизвестная тройка"}), 400
    if CatalogEntry.objects(n=n).first() is None:
        return jsonify({"error": "неизвестная тройка"}), 400
    member = Member.objects(username=session["u"]).first()
    existing = OwnedCard.objects(member=member, card=n).first()
    if existing is None:
        OwnedCard(member=member, card=n).save()
    else:
        existing.delete()
    return redirect(request.form.get("back", url_for("catalog")))


@app.route("/collection/remove/<int:n>", methods=["POST"])
def collection_remove(n):
    if "u" not in session:
        return jsonify({"error": "войдите в клуб"}), 400
    member = Member.objects(username=session["u"]).first()
    OwnedCard.objects(member=member, card=n).first().delete()
    return redirect(url_for("collection"))


@app.route("/api/gold", methods=["POST"])
def upgrade_gold():
    if "u" not in session:
        return jsonify({"error": "войдите в клуб"}), 403
    member = Member.objects(username=session["u"]).first()
    if isinstance(member.profile, GoldenProfile):
        return jsonify({"ok": True, "badge": member.profile.badge()})
    member.profile = GoldenProfile(
        nickname=getattr(member.profile, "nickname", None),
        home_station=getattr(member.profile, "home_station", None),
        member_since=2026,
    )
    member.save()
    return jsonify({"ok": True, "badge": member.profile.badge()})


PROFILE_ALIASES = {
    "nickname": "set__profile__nickname",
    "home_station": "set__profile__home_station",
}


@app.route("/api/profile", methods=["PATCH", "POST"])
def update_profile():
    if "u" not in session:
        return jsonify({"error": "войдите в клуб"}), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "пустой запрос"}), 400
    if data.get("home_station") and not is_station(data["home_station"]):
        return jsonify({"error": "такой станции в московском метро нет"}), 400
    update = {PROFILE_ALIASES.get(k, k): v for k, v in data.items()}
    Member.objects(username=session["u"]).update(**update)
    return jsonify({"ok": True})


@app.route("/api/trip", methods=["POST"])
def add_trip():
    if "u" not in session:
        return jsonify({"error": "войдите в клуб"}), 403
    station_from = request.form.get("from", "").strip()
    station_to = request.form.get("to", "").strip()
    if not station_from or not station_to:
        return jsonify({"error": "укажите обе станции"}), 400
    member = Member.objects(username=session["u"]).first()
    Trip(member=member, station_from=station_from, station_to=station_to).save()
    return redirect(url_for("me"))


@app.route("/api/trade", methods=["POST"])
def add_trade():
    if "u" not in session:
        return jsonify({"error": "войдите в клуб"}), 403
    try:
        offer = int(request.form.get("offer", ""))
        want = int(request.form.get("want", ""))
    except ValueError:
        return jsonify({"error": "номера троек должны быть числами"}), 400
    if CatalogEntry.objects(n=offer).first() is None or CatalogEntry.objects(n=want).first() is None \
            or offer == want:
        return jsonify({"error": "укажите две разные тройки из каталога"}), 400
    member = Member.objects(username=session["u"]).first()
    Trade(member=member, offer=offer, want=want,
          note=request.form.get("note", "").strip()[:200]).save()
    return redirect(url_for("trades"))


@app.route("/api/trade/remove", methods=["POST"])
def remove_trade():
    if "u" not in session:
        return jsonify({"error": "войдите в клуб"}), 403
    member = Member.objects(username=session["u"]).first()
    try:
        Trade.objects(id=request.form.get("id", ""), member=member).first().delete()
    except (DoesNotExist, AttributeError):
        pass
    return redirect(url_for("trades"))


if __name__ == "__main__":
    app.run("0.0.0.0", 8080)
