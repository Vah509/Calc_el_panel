# app/invoice_print/amount_in_words.py
# ============================================================
# Сумма прописью на украинском (гривні / копійки) — для печатной
# формы счёта (см. pdf_builder.py, "Всього на суму: ..."). Согласовано
# 2026-08-31: автогенерация нужна, сверено на реальном образце
# СФ-0000040 (105532.44 -> "Сто п'ять тисяч п'ятсот тридцять дві
# гривні 44 копійки" — совпадает 1-в-1).
#
# Отдельный модуль (не внутри pdf_builder.py) — переиспользуется и
# будущим Excel-экспортёром счёта (см. HANDOFF: "нужно учесть, что
# нужно будет ещё экселевский вариант счёта"), не хочется дублировать
# грамматику в двух местах.
#
# Согласование родов (важные грабли): "гривня" — женский род, поэтому
# ПОСЛЕДНЯЯ тройка числа (единицы/десятки/сотни перед словом
# "гривня") должна склоняться в женском роде ("одна", "дві", а не
# "один", "два") — при этом "тисяча"/"тисячі"/"тисяч" САМИ по себе
# всегда женского рода независимо от рода следующего за числом
# существительного, поэтому тройка ТЫСЯЧ тоже всегда женского рода
# (см. _int_to_words: thousands-часть feminine=True всегда, rem-часть
# feminine=feminine_units — параметр).
# ============================================================

_ONES_M = ["", "один", "два", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять"]
_ONES_F = ["", "одна", "дві", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять"]
_TEENS = ["десять", "одинадцять", "дванадцять", "тринадцять", "чотирнадцять",
          "п'ятнадцять", "шістнадцять", "сімнадцять", "вісімнадцять", "дев'ятнадцять"]
_TENS = ["", "", "двадцять", "тридцять", "сорок", "п'ятдесят",
         "шістдесят", "сімдесят", "вісімдесят", "дев'яносто"]
_HUNDREDS = ["", "сто", "двісті", "триста", "чотириста", "п'ятсот",
             "шістсот", "сімсот", "вісімсот", "дев'ятсот"]


def _million_form(n: int) -> str:
    last_two = n % 100
    last_one = n % 10
    if 11 <= last_two <= 14:
        return "мільйонів"
    if last_one == 1:
        return "мільйон"
    if 2 <= last_one <= 4:
        return "мільйони"
    return "мільйонів"


def _three_digit_words(n: int, feminine: bool) -> list[str]:
    words = []
    h, rem = divmod(n, 100)
    if h:
        words.append(_HUNDREDS[h])
    t, o = divmod(rem, 10)
    if t == 1:
        words.append(_TEENS[o])
    else:
        if t:
            words.append(_TENS[t])
        if o:
            words.append((_ONES_F if feminine else _ONES_M)[o])
    return words


def _thousand_form(n: int) -> str:
    last_two = n % 100
    last_one = n % 10
    if 11 <= last_two <= 14:
        return "тисяч"
    if last_one == 1:
        return "тисяча"
    if 2 <= last_one <= 4:
        return "тисячі"
    return "тисяч"


def _hryvnia_form(n: int) -> str:
    last_two = n % 100
    last_one = n % 10
    if 11 <= last_two <= 14:
        return "гривень"
    if last_one == 1:
        return "гривня"
    if 2 <= last_one <= 4:
        return "гривні"
    return "гривень"


def _kopiyka_form(n: int) -> str:
    last_two = n % 100
    last_one = n % 10
    if 11 <= last_two <= 14:
        return "копійок"
    if last_one == 1:
        return "копійка"
    if 2 <= last_one <= 4:
        return "копійки"
    return "копійок"


def _int_to_words(n: int, feminine_units: bool) -> str:
    """feminine_units — род ПОСЛЕДНЕЙ тройки (единиц числа), т.к.
    именно она согласуется с существительным, идущим после всего
    числа (гривня/копійка — женский род).

    ВАЖНО (баг найден 2026-08-31 на реальном счёте Вахтанга — сумма
    оказалась ≥ 1 000 000, IndexError в _HUNDREDS): числo нужно
    разбивать на тройки РЕКУРСИВНО (мільйони -> тисячі -> одиниці),
    каждая тройка сама по себе всегда 0-999 и подаётся в
    _three_digit_words независимо. Раньше "тисячи" получали ВЕСЬ
    n // 1000 целиком (могло быть >999 при n >= 1_000_000) и падали
    на _HUNDREDS[h] при h >= 10. Тестовые случаи (макс. 105 532)
    этот баг не ловили — нужно тестировать суммы за миллион отдельно
    (см. HANDOFF)."""
    if n == 0:
        return "нуль"
    parts = []
    millions, rem_after_millions = divmod(n, 1_000_000)
    thousands, rem = divmod(rem_after_millions, 1000)
    if millions:
        m_words = _three_digit_words(millions, feminine=False)
        parts.append(" ".join(m_words))
        parts.append(_million_form(millions))
    if thousands:
        t_words = _three_digit_words(thousands, feminine=True)
        parts.append(" ".join(t_words))
        parts.append(_thousand_form(thousands))
    if rem or not (millions or thousands):
        r_words = _three_digit_words(rem, feminine=feminine_units)
        if r_words:
            parts.append(" ".join(r_words))
    return " ".join(p for p in parts if p)


def amount_in_words_uk(total: float) -> str:
    """105532.44 -> 'Сто п'ять тисяч п'ятсот тридцять дві гривні 44 копійки'"""
    total = round(total + 1e-9, 2)
    hryvni = int(total)
    kopiyky = int(round((total - hryvni) * 100))
    words = _int_to_words(hryvni, feminine_units=True)
    words = words[0].upper() + words[1:] if words else words
    return f"{words} {_hryvnia_form(hryvni)} {kopiyky:02d} {_kopiyka_form(kopiyky)}"
