import json
import os
import re

import database as db
import settings as cfg
from translate import translate_names

# Persisted category keys remain stable across UI languages.
_GROCERY_CATEGORY = "продукты"
_OTHER_CATEGORY = "прочее"
CATEGORIES = ["мясо и рыба", "молочное и яйца", "овощи и фрукты", "хлеб и бакалея", "сладости и снеки",
              "напитки", "алкоголь", "бытовая химия", "гигиена и косметика", "дети", "дом и прочее",
              "пакеты и залог", _GROCERY_CATEGORY, "скидки и бонусы"]

_KEYWORDS = [
    ("алкоголь", ["brendis", "brandy", "vynas", "vyno", "alus", "alaus", "degtin", "viski", "whisk", "romas", "liker",
                  "šampan", "putojant", "sidras", "vodka", "džinas", " gin ", "tekila", "konjak", "aperit", "vermut", "cider"]),
    ("дети", ["sauskeln", "pampers", "kūdik", "vaikiš", "mišinys kūdik", "tyrelė", "huggies", "libero"]),
    ("гигиена и косметика", ["šampūn", "dantų", "dezodor", "kremas", "tualetinis pop", "higien", "skustuv", "įklot",
                             "tampon", "vata", "drėgnos serv", "balzam", "losjon", "muilas", "kondicionierius plauk",
                             "šveitikl", "nagų", "plaukų", "dušo žel", "burnos", "skalavimo"]),
    ("бытовая химия", ["skalbikl", "rankšluos", "skalbim", "plovikl", "valikl", "šluost", "maišeliai šiukšl", "šiukšl", "folija", "kempin",
                       "indų", "minkštikl", "balikl", "kapsul skalb", "tabletės indapl", "oro gaivikl", "popieriniai rankšl"]),
    ("пакеты и залог", ["pirkinių maiš", "maišas", "maišelis", "depozit", "tara", "pet (", "užstat"]),
    ("напитки", ["vanduo", "vandens", "sultys", "sulčių", "gėrimas", "gėrimai", "limonad", "kola", "coca", "pepsi",
                 "energinis", "gira ", "kvass", "mineralinis", "nektaras", "kokteilis", "arbata šalt", "tonikas", "sprite", "fanta"]),
    ("сладости и снеки", ["kramtom", "orbit", "šokolad", "saldain", "guminuk", "sausain", "batonėl", "kinder", "tortas", "pyrag", "ledai",
                          "traškuč", "čipsai", "riešut", "vafl", "meduol", "zefyr", "želė", "marmelad", "karamel",
                          "snickers", "mars", "twix", "bounty", "milka", "oreo", "popkorn", "krekeriai", "halva", "chalva"]),
    ("мясо и рыба", ["višč", "lydek", "karš", "saliam", "blauzdel", "petel", "vytint", "dešra", "dešrel", "kumpis", "mėsa", "mėsos", "vištien", "broiler", "sparnel", "kiaulien", "jautien",
                     "faršas", "lašiš", "žuvis", "žuvies", "filė", "silkė", "krevet", "upėtak", "menkė", "tunas", "šprot",
                     "kepenėl", "karbonad", "šonkaul", "kotlet", "kalakut", "antien", "šašlyk", "kebab", "krabų", "ikrai",
                     "skumbr", "lydeka", "ešer", "šlaunel", "krūtinėl", "nugarin", "sprandin", "bekon", "lašinuk", "skilandis"]),
    ("молочное и яйца", ["pienas", "pieno", "kefyras", "jogurt", "varškė", "varškės", "sūris", "sūrio", "sūrel", "grietin",
                         "sviestas", "rūgpien", "pasukos", "kiaušin", "margarin", "mascarpone", "mocarel", "fermentin",
                         "plombyr", "glaistyt"]),
    ("овощи и фрукты", ["šilauog", "bulv", "mork", "banan", "obuol", "pomidor", "agurk", "svogūn", "mork", "bulv", "salot", "žalumyn", "krap",
                        "citrin", "apelsin", "vynuog", "braškė", "mėlyn", "avokad", "paprik", "kopūst", "česnak", "kriauš",
                        "persik", "slyv", "uogos", "gryb", "pievagryb", "cukinij", "brokol", "salier", "špinat", "mandarin",
                        "kivi", "melion", "arbūz", "ananas", "mango", "burokėl", "ridik", "petraž", "bazilik", "imbier",
                        "abrikos", "vyšn", "trešn", "serbent", "aviet", "spanguol", "nektarin", "greipfrut", "porai", "moliūg"]),
    ("хлеб и бакалея", ["duona", "duonos", "baton", "bandel", "miltai", "cukrus", "ryžiai", "makaron", "kruop", "aliej",
                        "druska", "padaž", "majonez", "kečup", "konserv", "pupel", "avižin", "dribsn", "grikiai", "sriub",
                        "prieskon", "kava", "kavos", "arbata", "medus", "uogien", "džem", "riestain", "lavaš", "tortilij",
                        "spageč", "lęšiai", "sėklos", "actas", "garstyč", "sojų", "kokosų", "pica", "koldūn", "virtin",
                        "blyn", "lazan", "manų", "perlin", "kukurūz", "žirnel", "alyvuog", "traškučiai duon", "sausainiai duon"]),
    ("дом и прочее", ["filtravim", "brita", "vienkart", "baterij", "lemput", "žvak", "servet", "popierius", "rašikl", "sąsiuvin", "žurnal", "laikrašt",
                      "gėlė", "gėlių", "vazon", "indas", "puodel", "šaukšt", "peil", "šakut", "lėkšt", "rankšluost",
                      "kojinės", "pėdkeln", "degtuk", "žiebtuv", "klijai", "lipni juost"]),
]

_TOTAL_TOP_RE = re.compile(r"Apsipirkimo suma:\s*(\d+[.,]\d{2})\s*EUR", re.I)
_TOTAL_RE = re.compile(r"(?:apsipirkimo suma|kvito suma|mokėtina suma|iš viso|mok[eė]ti|total)\D{0,40}?(\d{1,5}[,.]\d{2})", re.I)
_MONEY_RE = re.compile(r"(\d{1,5}[,.]\d{2})\s*(?:€|eur)", re.I)
_ITEM_RE = re.compile(r"^(?P<name>.*?)\s{2,}(?P<price>-?\d{1,5},\d{2})\s*(?P<tax>[A-Z#]?)\s*$")
_QTY_RE = re.compile(r"^\s+-?\d+,\d{2,3}\s+X\s+")
_DISCOUNT_RE = re.compile(r"nuolaida", re.I)
_SKIP_RE = re.compile(r"^(Kvitas bazėje|PVM mokėtojo|UAB MAXIMA|Kasa Nr|J\d\s|Sveiki|Tai vienintelis|Išsaugokite|prekes ar)", re.I)


def _num(s):
    return float(s.replace(",", "."))


_WHOLE_WORD = {"gin", "mars", "kola", "gira", "tara", "vata", "kava", "alus", "pica", "medus", "actas", "sojų", "pet ("}


def _kw_regex(words):
    parts = []
    for w in words:
        w = w.strip()
        parts.append(r"\b" + re.escape(w) + (r"\b" if w in _WHOLE_WORD else ""))
    return re.compile("|".join(parts), re.I)


_KEYWORD_RES = [(cat, _kw_regex(words)) for cat, words in _KEYWORDS]


def categorize(name):
    n = name.lower()
    for cat, rx in _KEYWORD_RES:
        if rx.search(n):
            return cat
    return _GROCERY_CATEGORY


def parse_receipt_items(text):
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("Kvitas bazėje")) + 1
    except StopIteration:
        start = 0
    items, pending = [], ""
    for raw in lines[start:]:
        line = raw.rstrip()
        if line.startswith("====") or line.startswith("----"):
            if items:
                break
            continue
        if not line.strip() or _QTY_RE.match(line) or _SKIP_RE.match(line.strip()):
            continue
        m = _ITEM_RE.match(line)
        if not m:
            if _ITEM_RE.match(line.strip() + "  0,00"):
                pass
            pending = (pending + " " + line.strip()).strip()
            continue
        name = (pending + " " + m.group("name").strip()).strip()
        pending = ""
        price = _num(m.group("price"))
        if _DISCOUNT_RE.search(name) or price < 0:
            if items:
                items[-1]["amount"] = round(items[-1]["amount"] + price, 2)
                items[-1]["discount"] = round(items[-1].get("discount", 0) - price, 2)
            continue
        if not name or "X" == name.strip():
            continue
        items.append({"name": re.sub(r"\s+", " ", name)[:120], "amount": round(price, 2)})
    return items


_RECEIPT_MARKERS = re.compile(r"kvitas|apsipirkimo suma|kvito suma|mokėtina suma", re.I)


def looks_like_receipt(mail):
    return bool(_RECEIPT_MARKERS.search(mail.get("subject", "") + "\n" + mail.get("body", "")[:3000]))


def parse_total(text):
    """Find the receipt total only by explicit markers; the largest amount in an email can give false positives in newsletters."""
    m = _TOTAL_TOP_RE.search(text) or _TOTAL_RE.search(text)
    return _num(m.group(1)) if m else None



# ======================= generic total extraction (any store) =======================
_ZW = re.compile(r"[​‌‍‎‏﻿͏ ]")
_AMT = re.compile(r"(?<![\d.,])(\d{1,6}(?:[ .]\d{3})*[.,]\d{2})(?![\d])")
_TOTAL_STRONG = re.compile(r"bendra suma|suma apmokėti|mokėtina suma|iš viso mokėti|viso mokėti|total in eur|viso eur|grand total|amount due|total amount|amount paid|total paid|к оплате|apsipirkimo suma|kvito suma|galutinė suma|mokėti viso", re.I)
_TOTAL_WEAK = re.compile(r"(?<![\w])(iš viso|viso|total|apmokėti|mokėti|итого|сумма к оплате)(?![\w])", re.I)
_TOTAL_EXCLUDE = re.compile(r"tarpin|be pvm|pvm suma|viso pvm|pvm\s*\d|nuolaid|sutaup|subtotal|(?<![\w])net(?![\w])|neto|discount|mokesč|be mokes|delivery fee|pristatymo mokest|likutis|balance|points|taškai|pinig", re.I)
_TAX_ONLY = re.compile(r"(?<![\w])tax(?![\w])", re.I)
_TAX_INCL = re.compile(r"includ|incl(?![\w])|su pvm|with|su mokes", re.I)
_RECEIPT_SUBJECT = re.compile(r"kvit|čekis|cekis|receipt|invoice|sąskait|saskait|faktūr|order|užsakym|uzsakym|bill|чек|dokument|payment|apmok|pirkin|заказ|счет|счёт|purchase", re.I)


def _amount_str(s):
    """'1.234,56' / '1,234.56' / '1 234,56' / '12.50' -> float. The last separator is decimal; the others separate thousands."""
    s = s.replace(" ", "").replace("\u00a0", "")
    if "," in s and "." in s:
        dec = max(s.rfind(","), s.rfind("."))
        s = s[:dec].replace(",", "").replace(".", "") + "." + s[dec + 1:]
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    elif "." in s and re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    return float(s)


def _amounts(text):
    out = []
    for a in _AMT.findall(text):
        try:
            out.append(_amount_str(a))
        except ValueError:
            continue
    return out


_INVOICE_ISSUED = re.compile(r"išrašyta\s+(\d{1,6}[.,]\d{2})\s*(?:€|eur)?\s*sąskait", re.I)
_NOT_PURCHASE = re.compile(r"atšauk|anuliuo|cancel|refund|grąžin|nepavyko|failed|declined|nesėkming|priminim|reminder|unpaid|neapmokėt|отмен|возврат|напомин|не удал|не прош", re.I)
_PROMO_SUBJECT = re.compile(r"nuolaid|akcij|pasiūlym|sutaupyk|išpardav|dovan|laimėk|pigiau|pigiausi|kainos|%|(?<![\w])off(?![\w])|(?<![\w])sale(?![\w])|(?<![\w])deal(?![\w])|discount|скидк|акци|распродаж|дешевле|naujien|prasidėjo|jau čia|tik šiandien|savaitgal|newsletter|promo", re.I)
_REF_PATTERNS = [
    re.compile(r"(?:order id|užsakymo id|order-id)\s*[:#]?\s*([0-9a-f]{12,})", re.I),
    re.compile(r"(?:užsakym\w*\s*(?:numeris|nr\.?|id|№)|order\s*(?:number|no\.?|#|id)|заказ\w*\s*№?|invoice\s*(?:number|no\.?|#)|sąskait\w*\s*(?:nr\.?|numeris))\s*[:#]?\s*([A-Z]{0,3}-?\d{5,})", re.I),
    re.compile(r"#\s?(\d{5,})"),
    re.compile(r"(?<![\w])([A-Z]{1,3}-\d{6,})(?![\w])"),
]


def receipt_ref(mail):
    """Order/invoice number from the subject and start of the text, used to merge emails for one order (confirmation, ready for pickup, invoice)."""
    hay = (mail.get("subject") or "") + "\n" + (mail.get("body") or "")[:2500] + "\n" + (mail.get("pdf_text") or "")[:2500]
    for rx in _REF_PATTERNS:
        m = rx.search(hay)
        if m:
            ref = m.group(1)
            return ref.lower() if rx is _REF_PATTERNS[0] else re.sub(r"\D", "", ref)
    return None


def find_total(text):
    """-> (amount, 'strong'|'weak') or (None, None). Find the total by keywords; the number may precede or follow the keyword, or appear on subsequent lines."""
    if not text:
        return None, None
    m = _INVOICE_ISSUED.search(text)
    if m:                                                   # "invoice issued for X EUR" is the service cost, not the outstanding balance
        try:
            return _amount_str(m.group(1)), "strong"
        except ValueError:
            pass
    lines = [l.strip() for l in _ZW.sub(" ", text).splitlines()]
    strong, weak = [], []
    for i, line in enumerate(lines):
        if not line or _TOTAL_EXCLUDE.search(line) or (_TAX_ONLY.search(line) and not _TAX_INCL.search(line)):
            continue
        kind = "strong" if _TOTAL_STRONG.search(line) else ("weak" if _TOTAL_WEAK.search(line) else None)
        if not kind:
            continue
        m_kw = (_TOTAL_STRONG if kind == "strong" else _TOTAL_WEAK).search(line)
        after = _amounts(line[m_kw.end():])
        before = _amounts(line[:m_kw.start()])
        val = after[0] if after else (before[-1] if before else None)
        if val is None:                                   # number on subsequent lines (vertical layout)
            for nxt in lines[i + 1:i + 4]:
                if not nxt:
                    continue
                if _TOTAL_EXCLUDE.search(nxt) or (_TOTAL_STRONG.search(nxt) or _TOTAL_WEAK.search(nxt)):
                    break
                vals = _amounts(nxt)
                if vals and len(nxt) <= 24:
                    val = vals[0]
                    break
                if re.search(r"[A-Za-zА-Яа-я]{4,}", nxt):
                    break
        if val is not None and val > 0:
            (strong if kind == "strong" else weak).append(round(val, 2))
    for bucket, kind in ((strong, "strong"), (weak, "weak")):
        if bucket:
            counts = {}
            for v in bucket:
                counts[v] = counts.get(v, 0) + 1
            best = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
            return best, kind
    return None, None


# ======================= Wolt / order.site (Sushi Lovers, etc.) =======================
_WOLT_MARK = re.compile(r"order id|užsakymo id|receipt #|kvitas #|wolt", re.I)
_WOLT_DETAIL = re.compile(r"^(?P<name>.*?)\s*(?P<vat>\d{1,2})%\s+(?P<qty>\d+)\s+(?P<net>\d+[.,]\d{2})\s+(?P<gross>\d+[.,]\d{2})\s+(?P<price>\d+[.,]\d{2})\s*$")
_WOLT_TOTAL = re.compile(r"(total in eur|viso eur)[^\d\n]*?(\d+[.,]\d{2})", re.I)
_WOLT_SUMMARY = re.compile(r"^.+\S\s{2,}\d+[.,]\d{2}\s*$")
_WOLT_HEADER = re.compile(r"^(item vat|% quantity|price|gross unit|prekė pvm|% kiekis|kaina|vieneto|\(bruto\)|net price|neto kaina)", re.I)


def parse_wolt(text):
    """Wolt/order.site PDF receipt: item rows in the form "name 21% quantity net gross amount". -> (items, total) or None."""
    if not text or not _WOLT_MARK.search(text):
        return None
    items, totals, pending = [], [], ""
    for raw in _ZW.sub(" ", text).splitlines():
        line = raw.strip()
        if not line:
            continue
        mt = _WOLT_TOTAL.search(line)
        if mt:
            totals.append(_num(mt.group(2)))
            pending = ""
            continue
        m = _WOLT_DETAIL.match(line)
        if m:
            name = re.sub(r"\s+", " ", (pending + " " + m.group("name")).strip())
            pending = ""
            price = _num(m.group("price"))
            if price > 0 and name and not re.match(r"^(vat|pvm)\b", name, re.I):
                items.append({"name": name[:120], "amount": round(price, 2)})
            continue
        if _WOLT_SUMMARY.match(line) or _WOLT_HEADER.match(line):
            pending = ""
            continue
        pending = (pending + " " + line).strip()[-200:]
    if not items and not totals:
        return None
    return items, (round(sum(totals), 2) if totals else None)


# ======================= Maxima =======================
_MAXIMA_MARK = re.compile(r"kvitas bazėje|apsipirkimo suma|maximoje", re.I)


def parse_maxima(text):
    items = parse_receipt_items(text)
    if not items:
        return None
    return [{"name": it["name"], "amount": it["amount"]} for it in items], parse_total(text)


# ======================= Claude =======================
_claude_failures = 0


def reset_claude_breaker():
    global _claude_failures
    _claude_failures = 0


def claude_available():
    return bool(cfg.get("ANTHROPIC_API_KEY")) and _claude_failures < 3


def _with_claude(mail, store, text):
    """-> expense list, [] if Claude considers the email not to be a receipt, None on error (3 consecutive errors disable Claude for the rest of the sync)."""
    global _claude_failures
    from anthropic import Anthropic
    default = (store.default_category or "").strip()
    prompt = (
        f"Письмо от магазина/сервиса «{store.name}» (Литва). Извлеки покупки как расходы в EUR.\n"
        f"Категории: {', '.join(CATEGORIES)}, рестораны и доставка, техника и дом, коммунальные и связь, подписки, транспорт, здоровье, одежда, прочее"
        + (f". Если позиции не делятся на категории — используй «{default}»." if default else ".") + "\n"
        "Сгруппируй позиции по категориям: одна запись = одна категория с суммой по ней; description — названия позиций через «; » на русском (бренды латиницей).\n"
        "Если это реклама/рассылка/уведомление без покупки, отмена заказа, возврат денег, неуспешная оплата или напоминание об оплате — верни [].\n"
        'Ответ — только JSON-массив объектов {"category","amount","description","date"} '
        f'(date в формате YYYY-MM-DD, по умолчанию {mail["date"][:10]}).\n\n'
        f"Тема: {mail['subject']}\n\n{text[:14000]}"
    )
    try:
        client = Anthropic(api_key=cfg.get("ANTHROPIC_API_KEY"))
        resp = client.messages.create(model=cfg.get("CLAUDE_MODEL"), max_tokens=1500, messages=[{"role": "user", "content": prompt}])
        raw = "".join(getattr(b, "text", "") for b in resp.content)
        m = re.search(r"\[.*\]", raw, re.S)
        data = json.loads(m.group()) if m else []
        out = []
        for it in data:
            if not isinstance(it, dict):
                continue
            try:
                amount = float(str(it.get("amount", 0)).replace(",", "."))
            except ValueError:
                continue
            if abs(amount) < 0.01:
                continue
            d = str(it.get("date") or mail["date"][:10])[:10]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                d = mail["date"][:10]
            out.append({"category": str(it.get("category") or default or _OTHER_CATEGORY)[:60], "amount": round(amount, 2),
                        "description": str(it.get("description", ""))[:200], "description_lt": "", "date": d})
        _claude_failures = 0
        return out
    except Exception as e:
        _claude_failures += 1
        print(f"claude parse failed ({_claude_failures}): {e!r}")
        return None


# ======================= result assembly =======================
def _clean_subject(mail):
    s = re.sub(r"^(\s*(fwd?|re|fw)\s*:\s*)+", "", mail.get("subject") or "", flags=re.I)
    return re.sub(r"\s+", " ", s).strip()[:120]


def _build(mail, store, items, total, mode):
    date = mail["date"][:10]
    default = (getattr(store, "default_category", "") or "").strip()
    if not items:
        if total is None:
            return []
        return [{"category": default or _OTHER_CATEGORY, "amount": round(total, 2), "date": date,
                 "description": _clean_subject(mail) or store.name, "description_lt": (mail.get("subject") or "")[:120]}]
    by_cat = {}
    for it in items:
        cat = default or categorize(it["name"])
        entry = by_cat.setdefault(cat, {"amount": 0.0, "names": []})
        entry["amount"] = round(entry["amount"] + it["amount"], 2)
        entry["names"].append(it["name"][:60].rstrip(" ,("))
    names_all = [n for v in by_cat.values() for n in v["names"]]
    ru = {}
    if mode == "rules" or cfg.get("ANTHROPIC_API_KEY"):   # dictionary is tailored to Maxima groceries; use only Claude for other items
        try:
            ru = translate_names(names_all, db.translations_get, db.translations_put, allow_dict=(mode == "rules"))
        except Exception as e:
            print(f"Translation failed; keeping original item names: {e!r}")
    out = []
    for cat, v in by_cat.items():
        if abs(v["amount"]) < 0.01:
            continue
        tail = " …" if len(v["names"]) > 6 else ""
        out.append({"category": cat, "amount": v["amount"], "date": date,
                    "description": "; ".join(ru.get(n, n) for n in v["names"][:6]) + tail,
                    "description_lt": "; ".join(v["names"][:6]) + tail})
    items_sum = round(sum(e["amount"] for e in out), 2)
    if total is not None and abs(items_sum - total) >= 0.01:
        diff = round(total - items_sum, 2)
        if abs(diff) <= max(20.0, 0.3 * total):
            out.append({"category": "скидки и бонусы" if mode == "rules" else (default or _OTHER_CATEGORY), "amount": diff, "date": date,
                        "description": "оплата бонусами Maxima / округление" if mode == "rules" else "разница с итогом чека (сборы, скидки)",
                        "description_lt": ""})
        else:
            mail["_suspicious"] = diff
            print(f"Receipt {mail.get('uid')}: total {total} vs items {items_sum}; skipping the reconciliation entry")
    return out


def suggest_category(sender):
    s = (sender or "").lower()
    rules = [
        ("рестораны и доставка", ["wolt", "bolt", "domino", "sushi", "pizza", "order.site", "mcdonald", "kfc", "burger", "cili", "caffeine", "vapiano", "restoran", "food"]),
        ("коммунальные и связь", ["penki", "telia", "tele2", "bite", "ignitis", "eso", "vilniaus vanden", "vandenys", "silum", "gren", "cgates", "init.lt", "esim"]),
        ("техника и дом", ["topocentras", "pigu", "senukai", "ikea", "varle", "kilobaitas", "ifixit", "jysk", "depo", "ermitaz", "1a.lt", "electronics"]),
        ("подписки", ["apple", "google", "spotify", "netflix", "youtube", "icloud", "microsoft", "adobe", "github", "openai", "anthropic"]),
        ("транспорт", ["bolt.eu", "citybee", "spark", "uber", "trafi", "stops", "rzd", "ryanair", "wizz", "airbaltic", "lufthansa", "flixbus", "ltg", "parking", "unipark"]),
        ("одежда и спорт", ["decathlon", "zara", "h&m", "hm.com", "reserved", "sportland", "nike", "adidas", "lindex", "aboutyou", "zalando"]),
        ("здоровье", ["eurovaistin", "gintarine", "benu", "camelia", "clinic", "klinik", "tonus", "lab", "medic"]),
        (_GROCERY_CATEGORY, ["maxima", "rimi", "iki.lt", "lidl", "norfa", "barbora", "lastmile", "express market"]),
    ]
    for cat, keys in rules:
        if any(k in s for k in keys):
            return cat
    return ""


def parse_expenses(mail, store):
    """-> (expenses, mode). mode: rules | wolt | claude | generic | newsletter | unparsed.
    Database, translation, and rule exceptions propagate; the email goes into failed_emails and is retried from saved text."""
    parser = (getattr(store, "parser", "auto") or "auto")
    subject = mail.get("subject") or ""
    if _NOT_PURCHASE.search(subject):
        return [], "newsletter"
    if mail.get("attachment_error"):
        return [], "unparsed"
    body, pdf = mail.get("body") or "", mail.get("pdf_text") or ""
    text = body + ("\n\n" + pdf if pdf else "")
    if parser in ("auto", "maxima") and _MAXIMA_MARK.search(text):
        r = parse_maxima(text)
        if r:
            return _build(mail, store, r[0], r[1], "rules"), "rules"
    if parser in ("auto", "wolt"):
        r = parse_wolt(pdf) or (parse_wolt(body) if not pdf else None)
        if r and r[0]:
            total = r[1]
            if total is None:
                total = find_total(body)[0]
            return _build(mail, store, r[0], total, "wolt"), "wolt"
    if parser in ("maxima", "wolt"):                        # explicit format: no Claude or generic total extraction
        return [], ("unparsed" if _RECEIPT_SUBJECT.search(subject) and not _PROMO_SUBJECT.search(subject) else "newsletter")
    promo = bool(_PROMO_SUBJECT.search(subject)) and not pdf
    receipt_like = bool(_RECEIPT_SUBJECT.search(subject)) and not promo
    if promo:                                               # store newsletter: the body may contain example amounts, loans, and prices
        return [], "newsletter"
    if parser == "auto" and claude_available() and (receipt_like or pdf):   # generic = total only, without Claude
        res = _with_claude(mail, store, text)
        if res is not None:
            return (res, "claude") if res else ([], "newsletter")
    total, conf = find_total(body)
    if total is None:
        total, conf = find_total(pdf)
    if total is not None and (receipt_like or pdf):
        return _build(mail, store, [], total, "generic"), "generic"
    if (receipt_like or pdf) and (_AMT.search(text) and re.search(r"€|eur\b", text, re.I)):
        return [], "unparsed"                               # looks like a receipt with amounts, but no total was found
    return [], "newsletter"
