# app/engine/formulas.py
# ============================================================
# Формулы пересчёта для ComputedPair. Каждая формула — пара
# функций: пересчёт "вперёд" (a → b) и "назад" (b → a).
# Используется и на бэкенде (materials_api-подобные роутеры) и
# зеркально дублируется в JS на фронте (engine/page.py генерирует
# JS-код по этому же принципу) — расчёт должен совпадать в обе
# стороны, чтобы не было расхождений сервер/браузер.
# ============================================================

from typing import Callable


def _vat_forward(a: float, rate: float) -> float:
    """price_excl_vat -> price_incl_vat"""
    return round(a * (1 + rate / 100), 2)


def _vat_backward(b: float, rate: float) -> float:
    """price_incl_vat -> price_excl_vat"""
    return round(b / (1 + rate / 100), 2)


# Реестр формул: имя -> (forward, backward)
FORMULAS: dict[str, tuple[Callable[[float, float], float], Callable[[float, float], float]]] = {
    "vat": (_vat_forward, _vat_backward),
}


def apply_formula(formula: str, changed_field: str, field_a: str, field_b: str,
                   value_a: float, value_b: float, rate: float) -> tuple[float, float]:
    """
    Пересчитывает пару значений в зависимости от того, какое поле
    изменил пользователь. Возвращает (новое value_a, новое value_b).
    """
    forward, backward = FORMULAS[formula]
    if changed_field == field_a:
        return value_a, forward(value_a, rate)
    elif changed_field == field_b:
        return backward(value_b, rate), value_b
    else:
        # изменилась ставка (rate_field) — пересчитываем b от a по умолчанию
        return value_a, forward(value_a, rate)


# JS-эквиваленты формул — используются при генерации страницы (engine/page.py),
# чтобы пересчёт в браузере (на лету, до сохранения) совпадал с бэкендом.
FORMULAS_JS: dict[str, dict[str, str]] = {
    "vat": {
        "forward": "Math.round(a * (1 + rate / 100) * 100) / 100",   # b = a * (1+rate/100)
        "backward": "Math.round(b / (1 + rate / 100) * 100) / 100",  # a = b / (1+rate/100)
    }
}
