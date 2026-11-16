"""Числа прописью на таджикском языке (для договоров и кассовых ордеров)."""

ONES = ["", "як", "ду", "се", "чор", "панҷ", "шаш", "ҳафт", "ҳашт", "нӯҳ"]
TEENS = ["даҳ", "ёздаҳ", "дувоздаҳ", "сенздаҳ", "чордаҳ", "понздаҳ",
         "шонздаҳ", "ҳабдаҳ", "ҳаждаҳ", "нуздаҳ"]
TENS = ["", "", "бист", "сӣ", "чил", "панҷоҳ", "шаст", "ҳафтод", "ҳаштод", "навад"]
HUNDREDS = ["", "сад", "дусад", "сесад", "чорсад", "панҷсад", "шашсад",
            "ҳафтсад", "ҳаштсад", "нӯҳсад"]
SCALES = [(10 ** 9, "миллиард"), (10 ** 6, "миллион"), (10 ** 3, "ҳазор")]


def _triplet(n):
    parts = []
    h, rest = divmod(n, 100)
    if h:
        parts.append(HUNDREDS[h])
    if 10 <= rest < 20:
        parts.append(TEENS[rest - 10])
    else:
        t, o = divmod(rest, 10)
        if t:
            parts.append(TENS[t])
        if o:
            parts.append(ONES[o])
    return parts


def tj_number_words(n):
    """1234 -> 'як ҳазору дусаду сиву чор'."""
    n = int(n)
    if n == 0:
        return "сифр"
    if n < 0:
        return "минус " + tj_number_words(-n)
    groups = []
    for value, word in SCALES:
        if n >= value:
            count, n = divmod(n, value)
            groups.append(_join(_triplet(count)) + " " + word)
    if n:
        groups.append(_join(_triplet(n)))
    return _join(groups)


def _conj(word):
    # Соединительный «-у»; после гласной — «-ю» (сӣ -> сию, ду -> дую)
    if word.endswith("ӣ"):
        return word[:-1] + "ию"
    if word[-1] in "аеиоуёэюя":
        return word + "ю"
    return word + "у"


def _join(parts):
    return " ".join(_conj(p) if i < len(parts) - 1 else p for i, p in enumerate(parts))


def tj_amount_words(amount, currency="USD"):
    amount = round(amount or 0.0, 2)
    whole = int(amount)
    cents = int(round((amount - whole) * 100))
    if currency == "USD":
        unit, sub = "доллари ИМА", "сент"
    else:
        unit, sub = "сомонӣ", "дирам"
    return "%s %s %02d %s" % (tj_number_words(whole), unit, cents, sub)
