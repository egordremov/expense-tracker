import json
import os
import re

import settings as cfg

# Lithuanian stem -> Russian word. Match the start of the word; the longest stem wins.
_DICT = {
    # beverages / alcohol
    "brendis": "бренди", "brendž": "бренди", "alus": "пиво", "alaus": "пиво", "vynas": "вино", "vyno": "вино",
    "degtin": "водка", "viskis": "виски", "viski": "виски", "romas": "ром", "likeris": "ликёр", "šampan": "шампанское",
    "putojant": "игристое", "sidras": "сидр", "vanduo": "вода", "vandens": "вода", "sultys": "сок", "sulčių": "сок",
    "gėrimas": "напиток", "gėrimai": "напитки", "limonad": "лимонад", "gira": "квас", "mineralin": "минеральная",
    "negazuot": "негазированная", "gazuot": "газированная", "natūral": "натуральная", "energinis": "энергетик",
    "nektaras": "нектар", "kava": "кофе", "kavos": "кофе", "arbata": "чай", "arbatos": "чай", "kakav": "какао",
    # meat / fish
    "dešra": "колбаса", "dešrel": "сосиски", "kumpis": "ветчина", "kumpio": "ветчина", "mėsa": "мясо", "mėsos": "мясо",
    "vištien": "курица", "višč": "куриные", "broiler": "бройлер", "sparnel": "крылышки", "blauzdel": "голени",
    "kiaulien": "свинина", "jautien": "говядина", "faršas": "фарш", "lašiš": "лосось", "žuvis": "рыба", "žuvies": "рыба",
    "filė": "филе", "silkė": "сельдь", "krevet": "креветки", "upėtak": "форель", "menkė": "треска", "tunas": "тунец",
    "šprot": "шпроты", "kepenėl": "печень", "karbonad": "карбонад", "šonkaul": "рёбрышки", "kotlet": "котлеты",
    "kalakut": "индейка", "antien": "утка", "šašlyk": "шашлык", "krūtinėl": "грудка", "nugarin": "корейка",
    "sprandin": "шейка", "bekon": "бекон", "lašinuk": "сало", "saliam": "салями", "lydek": "хек", "karšis": "карась", "karšių": "карася",
    "vytint": "вяленые", "karštai": "горячего копчения", "šaltai": "холодного копчения", "broil": "бройлер", "šv": "св.", "vidurinės": "средние", "dalys": "части", "lazdel": "палочки", "skilandis": "скиландис", "rūkyt": "копчёные", "rūkyta": "копчёная", "virta": "варёная",
    "virtos": "варёные", "pjaustyt": "нарезка", "kept": "жареная", "šviež": "свежая", "atlant": "атлантический",
    "petel": "плечики", "peteliai": "плечики", "vidurin": "средняя часть", "dalys": "части",
    # dairy
    "pienas": "молоко", "pieno": "молочный", "pienišk": "молочные", "kefyras": "кефир", "jogurt": "йогурт",
    "varškė": "творог", "varškės": "творожный", "sūris": "сыр", "sūrio": "сыр", "sūrel": "сырок", "grietin": "сметана",
    "grietinėl": "сливки", "sviestas": "масло", "rūgpien": "простокваша", "kiaušin": "яйца", "margarin": "маргарин",
    "glaistyt": "глазированный", "plombyr": "пломбир", "rieb": "жирности", "namin": "домашний", "fermentin": "твёрдый",
    # vegetables / fruit
    "banan": "бананы", "obuol": "яблоки", "pomidor": "томаты", "agurk": "огурцы", "svogūn": "лук", "mork": "морковь",
    "bulv": "картофель", "salot": "салат", "žalumyn": "зелень", "krap": "укроп", "citrin": "лимоны", "apelsin": "апельсины",
    "vynuog": "виноград", "braškė": "клубника", "mėlyn": "голубика", "šilauog": "голубика", "avokad": "авокадо",
    "paprik": "перец", "kopūst": "капуста", "česnak": "чеснок", "kriauš": "груши", "persik": "персики", "slyv": "сливы",
    "uogos": "ягоды", "gryb": "грибы", "pievagryb": "шампиньоны", "cukinij": "цукини", "brokol": "брокколи",
    "salier": "сельдерей", "špinat": "шпинат", "mandarin": "мандарины", "kivi": "киви", "melion": "дыня", "arbūz": "арбуз",
    "ananas": "ананас", "mango": "манго", "burokėl": "свёкла", "ridik": "редис", "petraž": "петрушка", "bazilik": "базилик",
    "imbier": "имбирь", "abrikos": "абрикосы", "vyšn": "вишня", "trešn": "черешня", "serbent": "смородина",
    "aviet": "малина", "spanguol": "клюква", "nektarin": "нектарины", "greipfrut": "грейпфрут", "porai": "лук-порей",
    "moliūg": "тыква", "laišk": "перо", "plaut": "мытая", "lietuvišk": "литовский", "rinkinys": "набор",
    # pantry staples
    "duona": "хлеб", "duonos": "хлеб", "baton": "батон", "bandel": "булочки", "miltai": "мука", "cukrus": "сахар",
    "ryžiai": "рис", "makaron": "макароны", "kruop": "крупа", "aliej": "масло растит.", "druska": "соль", "padaž": "соус",
    "majonez": "майонез", "kečup": "кетчуп", "konserv": "консервы", "pupel": "фасоль", "avižin": "овсяные",
    "dribsn": "хлопья", "grikiai": "гречка", "sriub": "суп", "prieskon": "приправа", "medus": "мёд", "uogien": "варенье",
    "džem": "джем", "riestain": "сушки", "lavaš": "лаваш", "tortilij": "тортильи", "spageč": "спагетти", "lęšiai": "чечевица",
    "sėklos": "семечки", "actas": "уксус", "garstyč": "горчица", "sojų": "соевый", "kokosų": "кокосовый", "pica": "пицца",
    "koldūn": "пельмени", "virtin": "вареники", "blyn": "блины", "lazan": "лазанья", "manų": "манная", "kukurūz": "кукуруза",
    "žirnel": "горошек", "alyvuog": "оливки",
    # sweets / snacks
    "šokolad": "шоколад", "šokoladin": "шоколадный", "saldain": "конфеты", "guminuk": "мармеладки", "sausain": "печенье",
    "batonėl": "батончики", "tortas": "торт", "pyrag": "пирог", "ledai": "мороженое", "traškuč": "чипсы", "čipsai": "чипсы",
    "riešut": "орехи", "vafl": "вафли", "meduol": "пряники", "zefyr": "зефир", "želė": "желе", "marmelad": "мармелад",
    "karamel": "карамель", "kramtom": "жевательная", "guma": "резинка", "kiaušinis": "яйцо", "popkorn": "попкорн",
    "krekeriai": "крекеры", "chalva": "халва", "halva": "халва", "rykliuk": "акулы", "rinkin": "набор", "mint": "мятные", "mentos": "MENTOS",
    # cleaning supplies / personal care / household goods
    "skalbim": "для стирки", "skalbikl": "гель для стирки", "plovikl": "средство для мытья", "valikl": "чистящее",
    "šluost": "салфетки", "šiukšl": "для мусора", "folija": "фольга", "kempin": "губки", "indų": "для посуды",
    "minkštikl": "кондиционер", "balikl": "отбеливатель", "rankšluos": "полотенца", "popier": "бумажные",
    "popierius": "бумага", "tualetinis": "туалетная", "šampūn": "шампунь", "dantų": "зубная", "pasta": "паста",
    "dezodor": "дезодорант", "kremas": "крем", "higien": "гигиенический", "skustuv": "бритва", "įklot": "прокладки",
    "tampon": "тампоны", "vata": "вата", "muilas": "мыло", "skystasis": "жидкое", "balzam": "бальзам", "losjon": "лосьон",
    "vyrišk": "мужской", "purškiam": "спрей", "kosmetin": "косметические", "servet": "салфетки", "vienkart": "одноразовые",
    "lėkšt": "тарелки", "šakut": "вилки", "šaukšt": "ложки", "peil": "ножи", "puodel": "стаканы", "medin": "деревянные",
    "kojinės": "носки", "baterij": "батарейки", "lemput": "лампочка", "žvak": "свечи", "filtravim": "фильтрующий",
    "kaset": "картридж", "maišas": "пакет", "maišel": "пакет", "pirkinių": "для покупок", "didelis": "большой",
    "depozit": "залог", "spalvot": "цветных", "audin": "тканей", "pakuot": "упаковка", "vnt": "шт.", "rūšis": "сорт",
    "aukščiausia": "высший", "ekstra": "экстра", "klasik": "классический", "saldus": "сладкое", "pusiau": "полу",
    "baltasis": "белое", "raudon": "красное", "šviesusis": "светлое", "tamsusis": "тёмное", "nefiltruot": "нефильтрованное",
    "butelis": "бутылка", "tipo": "типа", "gintarin": "янтарное", "auksinis": "золотое", "sk": "вкус", "su": "с",

    # --- additions from real receipts ---
    "marinuot": "маринованные", "marinat": "маринад", "marin": "марин.", "kapsul": "капсулы", "vaisių": "фруктовый",
    "vaisiai": "фрукты", "kietasis": "твёрдый", "kiet": "твёрдый", "įdaru": "с начинкой", "įdar": "начинка", "įd": "начинка",
    "greitai": "быстрого приготовления", "paruošiam": "", "paruoš": "", "užaugint": "выращено", "ant": "на", "kraiko": "подстилке",
    "laikomų": "содержания", "sluoksn": "слоя", "pelėsiu": "с плесенью", "pelės": "плесень", "vištų": "куриные", "šoninė": "грудинка",
    "šoninės": "грудинки", "sausai": "сухого посола", "silkių": "сельди", "kaulo": "кости", "biskvit": "бисквитный",
    "liet": "литовск.", "vanilė": "ваниль", "vanilės": "ванильный", "saulėgrąž": "подсолнечное", "pikantišk": "пикантный",
    "ispanišk": "испанская", "šiųmeč": "молодая", "žolel": "травы", "brand": "выдержка", "mėn": "мес.", "atvėsint": "охлаждённые",
    "atšaldyt": "охлаждённая", "smulkiavais": "мелкоплодные", "kumpinė": "ветчинная", "spr": "шейка", "įv": "разные",
    "įvair": "разные", "vitamin": "витамины", "prancūzišk": "французский", "sviesto": "масла", "mažas": "малый", "maži": "мелкие",
    "lydyt": "плавленый", "tepam": "мягкий", "riekel": "ломтики", "riek": "ломтики", "indaplov": "для посудомойки",
    "aštr": "острый", "aitr": "острый", "plastikin": "пластиковый", "uogų": "ягодный", "stiklo": "стеклянная", "barbekiu": "барбекю",
    "odos": "кожи", "kariu": "карри", "vazonėl": "в горшочке", "koše": "пюре", "šlaunel": "бёдрышки", "kmyn": "тмин",
    "bruknių": "брусничный", "papr": "перец", "žal": "зелёный", "citr": "лимон", "medumi": "с мёдом", "medaus": "мёд",
    "pienin": "молочный", "pien": "молочный", "saldžios": "сладкий", "rit": "рул.", "lap": "лист.", "jūrin": "морская",
    "raugint": "квашеная", "kaimišk": "деревенская", "tams": "тёмный", "rugin": "ржаной", "makar": "макароны",
    "azijietišk": "азиатский", "sūdyt": "солёный", "ikrai": "икра", "maltinuk": "котлета", "mėsain": "бургер",
    "slyvin": "сливовидные", "trumpavais": "короткоплодные", "trupint": "тёртый", "trum": "трюфель", "žalios": "зелёный",
    "besėkl": "без косточек", "migdol": "миндаль", "ekstrakt": "экстракт", "dydž": "размер", "poros": "пары", "sparn": "крылышки",
    "anti": "антибиотиков", "smulk": "рубленые", "ne": "не", "daugiau": "более", "juodoji": "чёрный", "masdam": "маасдам",
    "baltagūž": "белокочанная", "terijaki": "терияки", "daržov": "овощной", "tun": "тунец", "mentė": "лопатка", "mentės": "лопатки",
    "šaldyt": "замороженные", "mišrain": "салат", "čeder": "чеддер", "švel": "мягкий", "raikyt": "нарезанный", "sušiai": "суши",
    "sušis": "суши", "kepti": "жареные", "kept": "жареный", "traškuč": "чипсы", "salotos": "салат", "sriuba": "суп",
    "gira": "квас", "butelis": "бутылка", "vienkartin": "одноразовый", "mm": "мм", "kg": "кг", "ml": "мл", "cm": "см",
    "vn": "шт.", "vnt": "шт.", "g": "г", "l": "л", "s": "", "m": "", "r": "", "a": "", "k": "",
    "ir": "и", "be": "без", "oda": "кожей", "kibirėl": "в ведёрке", "tinklel": "в сетке", "nauja": "новинка",
}
_STEMS = sorted(_DICT, key=len, reverse=True)
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ž]+|\d+[,.]?\d*|[^\sA-Za-zÀ-ž\d]+")


def _translate_token(tok):
    if not tok.isalpha():
        return tok
    if tok.isupper() and len(tok) > 1:
        return tok  # brand
    low = tok.lower()
    for stem in _STEMS:
        if low.startswith(stem):
            ru = _DICT[stem]
            return ru.capitalize() if tok[0].isupper() else ru
    return tok


def dict_translate(name):
    out = " ".join(t for t in (_translate_token(t) for t in _TOKEN_RE.findall(name)) if t != "")
    out = re.sub(r"(\s*\.\s*)+", ". ", out).replace(" ,", ",").strip(" .,")
    return re.sub(r"\s+([,.;:)])", r"\1", re.sub(r"\(\s+", "(", out))


def _claude_translate(names):
    from anthropic import Anthropic
    client = Anthropic(api_key=cfg.get("ANTHROPIC_API_KEY"))
    prompt = ("Переведи названия товаров из чека литовского супермаркета Maxima на русский, кратко и естественно, "
              "как в русском чеке. Бренды оставляй латиницей. Ответ — только JSON-объект {литовское: русское}.\n\n"
              + json.dumps(names, ensure_ascii=False))
    resp = client.messages.create(model=cfg.get("CLAUDE_MODEL"),
                                  max_tokens=4000, messages=[{"role": "user", "content": prompt}])
    text = "".join(getattr(b, "text", "") for b in resp.content)
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group()) if m else {}
    return {k: str(v)[:160] for k, v in data.items() if k in names and v}


def translate_names(names, cache_get, cache_put, allow_dict=True):
    """names -> {lt: ru}. cache_get(list)->dict, cache_put(dict, source). allow_dict=False uses only Claude (no grocery dictionary)."""
    names = list(dict.fromkeys(n for n in names if n))
    result = cache_get(names)
    missing = [n for n in names if n not in result]
    if missing and cfg.get("ANTHROPIC_API_KEY"):
        for i in range(0, len(missing), 40):
            batch = missing[i:i + 40]
            try:
                got = _claude_translate(batch)
                cache_put(got, "claude")
                result.update(got)
            except Exception as e:
                print(f"claude translate failed: {e}")
        missing = [n for n in names if n not in result]
    if missing and allow_dict:
        got = {n: dict_translate(n) for n in missing}
        cache_put(got, "dict")
        result.update(got)
    return result
