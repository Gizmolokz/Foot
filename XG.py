#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Predictor — футбольный предиктор с УСИЛЕННЫМИ МЕТРИКАМИ
1. Традиционный алгоритм (голы, форы, λ + тоталы на голы) - НЕЙТРАЛЬНОЕ ПОЛЕ
2. λ-алгоритм (атакующая эффективность + прогноз угловых) - С УЧЁТОМ ДОМАШНЕГО ПРЕИМУЩЕСТВА
3. TMPR (Team Momentum Performance Ranking) - УСИЛЕННОЕ ВЛИЯНИЕ ТЕКУЩЕЙ ФОРМЫ
4. НОВЫЕ МЕТРИКИ: Отборы %, Дуэли, Выносы
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import math, os, time
from typing import List, Dict, Optional, Tuple

# ---------------- КОНСТАНТЫ ДОМАШНЕГО ПРЕИМУЩЕСТВА ----------------
HOME_ADVANTAGE = {
    'home_xg_boost': 0.22,
    'away_xg_penalty': -0.12,
    'home_corners_boost': 1.05,
    'away_corners_penalty': 0.97
}

# Константы для преобразования λ в xG (с учетом новых метрик)
LAMBDA_TO_XG_COEFFS = {
    'base_coef': 1.5,
    'possession_factor_mult': 0.7,
    'efficiency_base': 0.95,
    'max_xg': 3.0,
    'tackle_success_factor': 0.0004,  # +0.04% за каждый % выше 60%
    'duels_won_factor': 0.0003,  # +0.03% за каждый % выше 50%
    'clearances_factor': 0.0002  # +0.02% за каждый вынос соперника
}

# ---------------- РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ ДЛЯ НОВЫХ МЕТРИК ----------------
ENHANCEMENT_FACTORS = {
    'shots_on_target_weight': 0.04,
    'goal_chance_weight': 0.12,
    'total_shots_factor': 0.005,
    'max_enhancement_per_match': 1.15,
    'min_accuracy_for_bonus': 0.25,

    # НОВЫЕ МЕТРИКИ - РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ
    'tackle_success_bonus': 0.0007,  # +0.07% за каждый % выше 60% (ранее 0.002)
    'duels_won_bonus': 0.0005,  # +0.05% за каждый % выше 50% (ранее 0.0015)
    'clearances_attack_factor': 0.005,  # +0.005 xG за каждый вынос соперника (ранее 0.015)
    'clearances_defense_penalty': 0.003,  # -0.003 xG за каждый свой вынос (ранее 0.009)
    'panic_clearance_threshold': 0.35,  # >35% панических выносов = плохо
    'max_clearances_impact': 0.15  # Макс +15% от метрик выносов (ранее 25%)
}

# ---------------- УСИЛЕННЫЕ КОНСТАНТЫ TMPR С НОВЫМИ МЕТРИКАМИ ----------------
TMPR_CONFIG = {
    'min_value': 100.0,
    'max_value': 500.0,
    'neutral_point': 300.0,

    # РЕАЛИСТИЧНЫЕ И НАГЛЯДНЫЕ КОЭФФИЦИЕНТЫ
    'scaling_factor': 0.001,
    'max_boost_percentage': 30.0,
    'max_penalty_percentage': 25.0,

    # Домашний/гостевой эффект
    'home_boost': 0.02,
    'away_penalty': -0.02,

    # РЕАЛИСТИЧНЫЙ ЭФФЕКТ НОВЫХ МЕТРИК НА TMPR
    'new_metrics_impact': {
        'tackle_success': {
            'elite_threshold': 75.0,  # >75% = элитная оборона
            'good_threshold': 65.0,  # 65-75% = хорошая
            'poor_threshold': 55.0,  # <55% = плохая
            'elite_bonus': 0.8,  # +0.8 TMPR за каждый % выше 75 (ранее 1.5)
            'good_bonus': 0.5,  # +0.5 TMPR за каждый % выше 65 (ранее 1.0)
            'poor_penalty': -0.6  # -0.6 TMPR за каждый % ниже 55 (ранее -1.2)
        },
        'duels_won': {
            'elite_threshold': 60.0,  # >60% = физическое доминирование
            'good_threshold': 52.0,  # 52-60% = хорошее
            'poor_threshold': 45.0,  # <45% = слабое
            'elite_bonus': 0.7,  # +0.7 TMPR за каждый % выше 60 (ранее 1.3)
            'good_bonus': 0.4,  # +0.4 TMPR за каждый % выше 52 (ранее 0.8)
            'poor_penalty': -0.5  # -0.5 TMPR за каждый % ниже 45 (ранее -1.0)
        },
        'clearances': {
            'elite_threshold': 12.0,  # <12 выносов = контроль обороны
            'crisis_threshold': 28.0,  # >28 выносов = кризис обороны
            'elite_bonus': 1.0,  # +1.0 TMPR за каждый вынос ниже 12 (ранее 2.0)
            'crisis_penalty': -0.8,  # -0.8 TMPR за каждый вынос выше 28 (ранее -1.5)
            'panic_ratio_penalty': -0.4  # -0.4 TMPR за каждый % панических выше 35% (ранее -0.8)
        }
    },

    # Остальные настройки...
    'form_effect': {
        'elite_threshold': 400.0,
        'good_threshold': 350.0,
        'poor_threshold': 250.0,
        'crisis_threshold': 200.0,

        'elite_bonus': 0.0002,
        'good_bonus': 0.0001,
        'poor_penalty': -0.00015,
        'crisis_penalty': -0.00025
    },

    'confidence_threshold': 350.0,
    'crisis_threshold': 250.0,

    'sensitivity_levels': {
        'low': {'threshold': 30, 'factor': 0.0003},
        'medium': {'threshold': 80, 'factor': 0.0007},
        'high': {'threshold': 150, 'factor': 0.0012},
        'extreme': {'factor': 0.0020}
    }
}


# ---------------- Helpers ----------------
def safe_float(s):
    try:
        if s is None:
            return None
        st = str(s).strip().replace(',', '.')
        if st == '':
            return None
        return float(st)
    except:
        return None


def poisson_pmf(k: int, mu: float) -> float:
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-mu) * (mu ** k) / math.factorial(k)


def poisson_cdf(k: int, mu: float) -> float:
    return sum(poisson_pmf(i, mu) for i in range(0, k + 1))


def prob_ge(k: int, mu: float) -> float:
    if k <= 0:
        return 1.0
    return 1.0 - poisson_cdf(k - 1, mu)


def prob_le(k: int, mu: float) -> float:
    if k < 0:
        return 0.0
    return poisson_cdf(k, mu)


def calculate_corners_prediction(avg_corners: float, avg_possession: float, is_home: bool = True) -> float:
    """Рассчитывает прогноз угловых для команды"""
    base_multiplier = 0.9 if is_home else 0.8
    base_prediction = avg_corners * base_multiplier

    if avg_possession > 60:
        base_prediction = min(base_prediction + 1, 12)
    elif avg_possession < 40:
        base_prediction = max(base_prediction - 1, 1)

    base_prediction = max(1, min(base_prediction, 10))

    if avg_corners > 7.0:
        base_prediction = min(8, base_prediction)
    elif avg_corners < 3.0:
        base_prediction = max(2, base_prediction)

    return base_prediction


def calculate_individual_totals(xg: float) -> Dict[str, float]:
    totals = {}
    totals['ТБ 0.5'] = prob_ge(1, xg) * 100
    totals['ТБ 1.5'] = prob_ge(2, xg) * 100
    totals['ТБ 2.5'] = prob_ge(3, xg) * 100
    totals['ТБ 3.5'] = prob_ge(4, xg) * 100

    totals['ТМ 0.5'] = 100 - totals['ТБ 0.5']
    totals['ТМ 1.5'] = 100 - totals['ТБ 1.5']
    totals['ТМ 2.5'] = 100 - totals['ТБ 2.5']
    totals['ТМ 3.5'] = 100 - totals['ТБ 3.5']

    return totals


def calculate_total_totals(xg_home: float, xg_away: float) -> Dict[str, float]:
    totals = {}
    total_goals = xg_home + xg_away

    totals['ТБ 0.5'] = prob_ge(1, total_goals) * 100
    totals['ТБ 1.5'] = prob_ge(2, total_goals) * 100
    totals['ТБ 2.5'] = prob_ge(3, total_goals) * 100
    totals['ТБ 3.5'] = prob_ge(4, total_goals) * 100

    totals['ТМ 0.5'] = 100 - totals['ТБ 0.5']
    totals['ТМ 1.5'] = 100 - totals['ТБ 1.5']
    totals['ТМ 2.5'] = 100 - totals['ТБ 2.5']
    totals['ТМ 3.5'] = 100 - totals['ТБ 3.5']

    return totals


# ---------------- НОВЫЕ ФУНКЦИИ ДЛЯ НОВЫХ МЕТРИК ----------------
def calculate_enhanced_xg_with_new_metrics(base_xg: float, team_data: List[Dict],
                                           opp_data: List[Dict], is_home: bool = True) -> float:
    """
    Улучшенный xG с учетом новых метрик: Отборы %, Дуэли, Выносы
    РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ
    """
    enhanced_xg = base_xg

    # Базовые метрики (уже существующие)
    avg_shots_on_target = sum([d.get('shots_on_target', 0) for d in team_data]) / 3
    avg_goal_chances = sum([d.get('goal_scoring_chances', 0) for d in team_data]) / 3
    avg_total_shots = sum([d.get('total_shots', 0) for d in team_data]) / 3

    # Новые метрики - наши показатели
    avg_tackle_success = sum([d.get('tackle_success', 50) for d in team_data]) / 3
    avg_duels_won = sum([d.get('duels_won', 50) for d in team_data]) / 3
    avg_clearances = sum([d.get('clearances', 0) for d in team_data]) / 3

    # Новые метрики - показатели соперника
    avg_opp_clearances = sum([d.get('clearances', 0) for d in opp_data]) / 3

    # 1. Базовые улучшения (существующие)
    sot_bonus = avg_shots_on_target * ENHANCEMENT_FACTORS['shots_on_target_weight']
    sot_bonus = min(sot_bonus, 0.4)

    gsc_bonus = avg_goal_chances * ENHANCEMENT_FACTORS['goal_chance_weight']
    gsc_bonus = min(gsc_bonus, 0.6)

    total_shots_bonus = 0
    if avg_total_shots > 0:
        accuracy = (avg_shots_on_target / avg_total_shots)
        if accuracy > ENHANCEMENT_FACTORS['min_accuracy_for_bonus']:
            total_shots_bonus = avg_total_shots * ENHANCEMENT_FACTORS['total_shots_factor']
            total_shots_bonus = min(total_shots_bonus, 0.2)

    # 2. Улучшения от новых метрик - РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ

    # 2.1 Отборы % - оборонительная эффективность
    if avg_tackle_success > 60:
        tackle_bonus = (avg_tackle_success - 60) * ENHANCEMENT_FACTORS['tackle_success_bonus']
        tackle_bonus = min(tackle_bonus, 0.08)  # до +8% (ранее 15%)
        enhanced_xg *= (1 + tackle_bonus)

    # 2.2 Дуэли - физическое превосходство
    if avg_duels_won > 50:
        duels_bonus = (avg_duels_won - 50) * ENHANCEMENT_FACTORS['duels_won_bonus']
        duels_bonus = min(duels_bonus, 0.06)  # до +6% (ранее 12%)
        enhanced_xg *= (1 + duels_bonus)

    # 2.3 Выносы соперника - наше атакующее давление
    if avg_opp_clearances > 0:
        clearances_attack_bonus = avg_opp_clearances * ENHANCEMENT_FACTORS['clearances_attack_factor']
        clearances_attack_bonus = min(clearances_attack_bonus, 0.15)  # до +0.15 xG (ранее 0.3)
        enhanced_xg += clearances_attack_bonus

    # 2.4 Наши выносы - наше оборонительное давление (снижает xG)
    if avg_clearances > 15:
        clearances_defense_penalty = (avg_clearances - 15) * ENHANCEMENT_FACTORS['clearances_defense_penalty']
        clearances_defense_penalty = min(clearances_defense_penalty, 0.10)  # до -0.1 xG (ранее 0.2)
        enhanced_xg -= clearances_defense_penalty

    # 3. Объединяем все улучшения
    total_enhancement = sot_bonus + gsc_bonus + total_shots_bonus
    total_enhancement = min(total_enhancement, ENHANCEMENT_FACTORS['max_enhancement_per_match'])

    enhanced_xg += total_enhancement
    enhanced_xg = max(enhanced_xg, 0.1)

    # Ограничения
    max_limit = 3.5 if is_home else 3.0
    enhanced_xg = min(enhanced_xg, max_limit)

    return round(enhanced_xg, 2)


def calculate_defensive_pressure_index(team_data: List[Dict]) -> Dict[str, any]:
    """
    Расчет индекса оборонительного давления на основе новых метрик
    """
    avg_tackle_success = sum([d.get('tackle_success', 50) for d in team_data]) / 3
    avg_duels_won = sum([d.get('duels_won', 50) for d in team_data]) / 3
    avg_clearances = sum([d.get('clearances', 0) for d in team_data]) / 3

    # Индекс оборонительного давления (чем ниже, тем лучше оборона)
    pressure_index = 0

    # Отрицательные факторы (плохая оборона)
    if avg_tackle_success < 55:
        pressure_index += (55 - avg_tackle_success) * 0.5

    if avg_duels_won < 45:
        pressure_index += (45 - avg_duels_won) * 0.4

    if avg_clearances > 25:
        pressure_index += (avg_clearances - 25) * 0.3

    # Положительные факторы (хорошая оборона)
    if avg_tackle_success > 70:
        pressure_index -= (avg_tackle_success - 70) * 0.3

    if avg_duels_won > 55:
        pressure_index -= (avg_duels_won - 55) * 0.2

    if avg_clearances < 12:
        pressure_index -= (12 - avg_clearances) * 0.4

    # Интерпретация
    if pressure_index <= -10:
        defense_quality = "ЭЛИТНАЯ оборона"
        description = "Отличные показатели отборов и контроля"
    elif pressure_index <= -5:
        defense_quality = "ХОРОШАЯ оборона"
        description = "Надежные оборонительные действия"
    elif pressure_index <= 5:
        defense_quality = "СРЕДНЯЯ оборона"
        description = "Стандартные оборонительные показатели"
    elif pressure_index <= 15:
        defense_quality = "СЛАБАЯ оборона"
        description = "Проблемы в оборонительных действиях"
    else:
        defense_quality = "КРИЗИС обороны"
        description = "Системные проблемы в защите"

    return {
        'pressure_index': round(pressure_index, 1),
        'defense_quality': defense_quality,
        'defense_description': description,
        'avg_tackle_success': round(avg_tackle_success, 1),
        'avg_duels_won': round(avg_duels_won, 1),
        'avg_clearances': round(avg_clearances, 1)
    }


def calculate_tmpr_with_new_metrics(tmpr_base: float, team_data: List[Dict]) -> float:
    """
    Расчет TMPR с учетом новых метрик
    РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ
    """
    tmpr_adjusted = tmpr_base

    # Рассчитываем средние значения новых метрик
    avg_tackle_success = sum([d.get('tackle_success', 50) for d in team_data]) / 3
    avg_duels_won = sum([d.get('duels_won', 50) for d in team_data]) / 3
    avg_clearances = sum([d.get('clearances', 0) for d in team_data]) / 3

    impact = TMPR_CONFIG['new_metrics_impact']

    # 1. Влияние % отборов - РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ
    tackle_impact = impact['tackle_success']
    if avg_tackle_success >= tackle_impact['elite_threshold']:
        tmpr_adjusted += (avg_tackle_success - tackle_impact['elite_threshold']) * tackle_impact['elite_bonus']
    elif avg_tackle_success >= tackle_impact['good_threshold']:
        tmpr_adjusted += (avg_tackle_success - tackle_impact['good_threshold']) * tackle_impact['good_bonus']
    elif avg_tackle_success < tackle_impact['poor_threshold']:
        tmpr_adjusted += (avg_tackle_success - tackle_impact['poor_threshold']) * tackle_impact['poor_penalty']

    # 2. Влияние выигранных дуэлей - РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ
    duels_impact = impact['duels_won']
    if avg_duels_won >= duels_impact['elite_threshold']:
        tmpr_adjusted += (avg_duels_won - duels_impact['elite_threshold']) * duels_impact['elite_bonus']
    elif avg_duels_won >= duels_impact['good_threshold']:
        tmpr_adjusted += (avg_duels_won - duels_impact['good_threshold']) * duels_impact['good_bonus']
    elif avg_duels_won < duels_impact['poor_threshold']:
        tmpr_adjusted += (avg_duels_won - duels_impact['poor_threshold']) * duels_impact['poor_penalty']

    # 3. Влияние выносов - РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ
    clearances_impact = impact['clearances']
    if avg_clearances <= clearances_impact['elite_threshold']:
        tmpr_adjusted += (clearances_impact['elite_threshold'] - avg_clearances) * clearances_impact['elite_bonus']
    elif avg_clearances >= clearances_impact['crisis_threshold']:
        tmpr_adjusted -= (avg_clearances - clearances_impact['crisis_threshold']) * clearances_impact['crisis_penalty']

    # Ограничиваем диапазон
    tmpr_adjusted = max(TMPR_CONFIG['min_value'], min(TMPR_CONFIG['max_value'], tmpr_adjusted))

    return round(tmpr_adjusted, 1)


# ---------------- УСОВЕРШЕНСТВОВАННЫЕ ФУНКЦИИ TMPR ----------------
def apply_tmpr_effect(base_value: float, tmpr_self: float, tmpr_opponent: float,
                      is_home: bool = True, value_type: str = 'lambda') -> Tuple[float, Dict]:
    """
    УСОВЕРШЕНСТВОВАННЫЙ ЭФФЕКТ TMPR С НОВЫМИ МЕТРИКАМИ
    """
    tmpr_self = max(TMPR_CONFIG['min_value'], min(TMPR_CONFIG['max_value'], tmpr_self))
    tmpr_opponent = max(TMPR_CONFIG['min_value'], min(TMPR_CONFIG['max_value'], tmpr_opponent))

    diff = tmpr_self - tmpr_opponent
    abs_diff = abs(diff)

    sensitivity = TMPR_CONFIG['sensitivity_levels']

    if abs_diff <= sensitivity['low']['threshold']:
        base_multiplier = 1.0 + (diff * sensitivity['low']['factor'])
    elif abs_diff <= sensitivity['medium']['threshold']:
        low_range = sensitivity['low']['threshold'] * sensitivity['low']['factor']
        medium_diff = abs_diff - sensitivity['low']['threshold']
        effect = low_range + (medium_diff * sensitivity['medium']['factor'])
        base_multiplier = 1.0 + (effect if diff > 0 else -effect)
    elif abs_diff <= sensitivity['high']['threshold']:
        low_range = sensitivity['low']['threshold'] * sensitivity['low']['factor']
        medium_range = (sensitivity['medium']['threshold'] - sensitivity['low']['threshold']) * sensitivity['medium'][
            'factor']
        high_diff = abs_diff - sensitivity['medium']['threshold']
        effect = low_range + medium_range + (high_diff * sensitivity['high']['factor'])
        base_multiplier = 1.0 + (effect if diff > 0 else -effect)
    else:
        low_range = sensitivity['low']['threshold'] * sensitivity['low']['factor']
        medium_range = (sensitivity['medium']['threshold'] - sensitivity['low']['threshold']) * sensitivity['medium'][
            'factor']
        high_range = (sensitivity['high']['threshold'] - sensitivity['medium']['threshold']) * sensitivity['high'][
            'factor']
        extreme_diff = abs_diff - sensitivity['high']['threshold']
        effect = low_range + medium_range + high_range + (extreme_diff * sensitivity['extreme']['factor'])
        base_multiplier = 1.0 + (effect if diff > 0 else -effect)

    form_multiplier = 1.0
    form_effect = TMPR_CONFIG['form_effect']

    if tmpr_self >= form_effect['elite_threshold']:
        elite_bonus = (tmpr_self - form_effect['elite_threshold']) * form_effect['elite_bonus']
        form_multiplier += elite_bonus
    elif tmpr_self >= form_effect['good_threshold']:
        good_bonus = (tmpr_self - form_effect['good_threshold']) * form_effect['good_bonus']
        form_multiplier += good_bonus

    if tmpr_self <= form_effect['crisis_threshold']:
        crisis_penalty = (form_effect['crisis_threshold'] - tmpr_self) * form_effect['crisis_penalty']
        form_multiplier += crisis_penalty
    elif tmpr_self <= form_effect['poor_threshold']:
        poor_penalty = (form_effect['poor_threshold'] - tmpr_self) * form_effect['poor_penalty']
        form_multiplier += poor_penalty

    if is_home:
        venue_multiplier = 1.0 + TMPR_CONFIG['home_boost']
    else:
        venue_multiplier = 1.0 + TMPR_CONFIG['away_penalty']

    final_multiplier = base_multiplier * form_multiplier * venue_multiplier

    max_boost = 1.0 + (TMPR_CONFIG['max_boost_percentage'] / 100.0)
    min_penalty = 1.0 - (TMPR_CONFIG['max_penalty_percentage'] / 100.0)

    if final_multiplier > max_boost:
        excess = final_multiplier - max_boost
        final_multiplier = max_boost + (excess * 0.3)
    elif final_multiplier < min_penalty:
        deficit = min_penalty - final_multiplier
        final_multiplier = min_penalty - (deficit * 0.3)

    if value_type == 'xg':
        enhanced_multiplier = 1.0 + ((final_multiplier - 1.0) * 1.3)
        enhanced_value = base_value * enhanced_multiplier
    else:
        enhanced_value = base_value * final_multiplier

    if value_type == 'xg':
        enhanced_value = round(enhanced_value, 2)
    else:
        enhanced_value = round(enhanced_value, 3)

    effect_info = {
        'tmpr_self': tmpr_self,
        'tmpr_opponent': tmpr_opponent,
        'diff': diff,
        'base_effect_percent': (base_multiplier - 1.0) * 100,
        'form_effect_percent': (form_multiplier - 1.0) * 100,
        'venue_effect_percent': (venue_multiplier - 1.0) * 100,
        'total_effect_percent': (final_multiplier - 1.0) * 100,
        'enhanced_effect_percent': (enhanced_multiplier - 1.0) * 100 if value_type == 'xg' else (
                                                                                                            final_multiplier - 1.0) * 100,
        'base_value': base_value,
        'enhanced_value': enhanced_value,
        'is_home': is_home,
        'value_type': value_type,
        'final_multiplier': final_multiplier
    }

    return enhanced_value, effect_info


def get_tmpr_interpretation(tmpr_value: float) -> str:
    """Интерпретация значения TMPR"""
    if tmpr_value >= 450:
        return "🔥 ПИК ФОРМЫ - выдающиеся показатели"
    elif tmpr_value >= 400:
        return "⭐ ЭЛИТНАЯ ФОРМА - доминирующие выступления"
    elif tmpr_value >= 350:
        return "📈 ХОРОШАЯ ФОРМА - уверенные выступления"
    elif tmpr_value >= 300:
        return "✅ СРЕДНИЙ УРОВЕНЬ - стабильные показатели"
    elif tmpr_value >= 250:
        return "⚠️  НЕСТАБИЛЬНО - проблемы с реализацией"
    elif tmpr_value >= 200:
        return "📉 ПЛОХАЯ ФОРМА - системные проблемы"
    else:
        return "🔥 КРИЗИС - глубокая негативная динамика"


def format_tmpr_analysis(tmpr1: float, tmpr2: float,
                         lambda_effect1: Dict, lambda_effect2: Dict,
                         xg_effect1: Dict, xg_effect2: Dict) -> List[str]:
    """Расширенное форматирование анализа TMPR"""
    lines = []

    diff = tmpr1 - tmpr2

    lines.append("\n🏆 TEAM MOMENTUM PERFORMANCE RANKING (С НОВЫМИ МЕТРИКАМИ)")
    lines.append("=" * 70)

    lines.append(f"📊 РЕЙТИНГИ ФОРМЫ:")
    lines.append(f"   • К1 (Дома): {tmpr1:.1f} - {get_tmpr_interpretation(tmpr1)}")
    lines.append(f"   • К2 (Гости): {tmpr2:.1f} - {get_tmpr_interpretation(tmpr2)}")
    lines.append(f"   • Разница: {diff:+.1f} баллов ({abs(diff):.1f} абс.)")

    if abs(diff) < 15:
        lines.append(f"   ⚖️  Форма команд ОЧЕНЬ близка (минимальное влияние)")
    elif abs(diff) < 40:
        lines.append(f"   ↕️  Небольшое преимущество в форме (умеренное влияние)")
    elif abs(diff) < 80:
        lines.append(f"   ↗️  ЗАМЕТНОЕ преимущество в форме (значительное влияние)")
    elif abs(diff) < 120:
        lines.append(f"   ⚡ ВЫРАЖЕННОЕ преимущество в форме (сильное влияние)")
    elif abs(diff) < 180:
        lines.append(f"   🚨 ОГРОМНОЕ преимущество в форме (максимальное влияние)")
    else:
        lines.append(f"   💥 КРИТИЧЕСКОЕ преимущество в форме (доминирующее влияние)")

    lines.append("\n🔬 ВЛИЯНИЕ НА АТАКУЮЩУЮ ЭФФЕКТИВНОСТЬ (λ):")
    lines.append(f"   • К1: λ {lambda_effect1['base_value']:.3f} → {lambda_effect1['enhanced_value']:.3f} "
                 f"({lambda_effect1['enhanced_effect_percent']:+.1f}%)")
    lines.append(f"   • К2: λ {lambda_effect2['base_value']:.3f} → {lambda_effect2['enhanced_value']:.3f} "
                 f"({lambda_effect2['enhanced_effect_percent']:+.1f}%)")

    lines.append("\n🎯 ВЛИЯНИЕ НА ОЖИДАЕМЫЕ ГОЛЫ (xG):")
    lines.append(f"   • К1: xG {xg_effect1['base_value']:.2f} → {xg_effect1['enhanced_value']:.2f} "
                 f"({xg_effect1['enhanced_effect_percent']:+.1f}%)")
    lines.append(f"   • К2: xG {xg_effect2['base_value']:.2f} → {xg_effect2['enhanced_value']:.2f} "
                 f"({xg_effect2['enhanced_effect_percent']:+.1f}%)")

    lines.append("\n📈 ДЕТАЛИЗАЦИЯ ЭФФЕКТА ДЛЯ К1:")
    lines.append(f"   • Разница форм: {lambda_effect1['base_effect_percent']:+.1f}%")
    lines.append(f"   • Абс. уровень формы: {lambda_effect1['form_effect_percent']:+.1f}%")
    lines.append(f"   • Фактор поля: {lambda_effect1['venue_effect_percent']:+.1f}%")
    lines.append(f"   • ИТОГО влияние на λ: {lambda_effect1['total_effect_percent']:+.1f}%")
    lines.append(f"   • УСИЛЕННОЕ влияние на xG: {xg_effect1['enhanced_effect_percent']:+.1f}%")

    lines.append(f"\n📉 ДЕТАЛИЗАЦИЯ ЭФФЕКТА ДЛЯ К2:")
    lines.append(f"   • Разница форм: {lambda_effect2['base_effect_percent']:+.1f}%")
    lines.append(f"   • Абс. уровень формы: {lambda_effect2['form_effect_percent']:+.1f}%")
    lines.append(f"   • Фактор поля: {lambda_effect2['venue_effect_percent']:+.1f}%")
    lines.append(f"   • ИТОГО влияние на λ: {lambda_effect2['total_effect_percent']:+.1f}%")
    lines.append(f"   • УСИЛЕННОЕ влияние на xG: {xg_effect2['enhanced_effect_percent']:+.1f}%")

    total_tmpr_impact = abs(lambda_effect1['total_effect_percent']) + abs(lambda_effect2['total_effect_percent'])

    lines.append(f"\n💎 ОБЩЕЕ ВЛИЯНИЕ TMPR НА МАТЧ: {total_tmpr_impact:.1f}%")

    if total_tmpr_impact < 10:
        lines.append("   💡 МИНИМАЛЬНОЕ влияние - форма не ключевой фактор")
    elif total_tmpr_impact < 20:
        lines.append("   🔍 УМЕРЕННОЕ влияние - стоит учитывать")
    elif total_tmpr_impact < 35:
        lines.append("   ⚠️  ЗНАЧИТЕЛЬНОЕ влияние - важный фактор")
    elif total_tmpr_impact < 50:
        lines.append("   🚨 СИЛЬНОЕ влияние - определяющий фактор")
    else:
        lines.append("   💥 КРИТИЧЕСКОЕ влияние - доминирующий фактор")

    if abs(diff) > 100:
        lines.append("\n💡 РЕКОМЕНДАЦИЯ: TMPR имеет КРИТИЧЕСКОЕ значение для прогноза")
    elif abs(diff) > 60:
        lines.append("\n💡 РЕКОМЕНДАЦИЯ: TMPR - ВАЖНЫЙ фактор при принятии решения")
    elif abs(diff) > 30:
        lines.append("\n💡 РЕКОМЕНДАЦИЯ: Учитывать TMPR как дополнительный фактор")
    else:
        lines.append("\n💡 РЕКОМЕНДАЦИЯ: Минимальное влияние TMPR")

    return lines


# ---------------- ФУНКЦИИ АНАЛИЗА УГЛОВЫХ ----------------
def get_detailed_corners_analysis(team1_data: List[Dict], team2_data: List[Dict],
                                  is_home_team1: bool = True, confidence_level: float = 55.0) -> Dict[str, any]:
    """Детальный анализ угловых с реалистичными прогнозами"""
    team1_avg_corners = sum([d.get('corners', 0) for d in team1_data]) / 3
    team2_avg_corners = sum([d.get('corners', 0) for d in team2_data]) / 3
    team1_avg_possession = sum([d.get('pos', 50) for d in team1_data]) / 3
    team2_avg_possession = sum([d.get('pos', 50) for d in team2_data]) / 3

    team1_prediction = calculate_corners_prediction(team1_avg_corners, team1_avg_possession, is_home=is_home_team1)
    team2_prediction = calculate_corners_prediction(team2_avg_corners, team2_avg_possession, is_home=not is_home_team1)
    total_corners_prediction = team1_prediction + team2_prediction

    analysis = {
        'total_corners': {
            'prediction': round(total_corners_prediction, 1),
            'team1_prediction': round(team1_prediction, 1),
            'team2_prediction': round(team2_prediction, 1),
            'team1_average': round(team1_avg_corners, 1),
            'team2_average': round(team2_avg_corners, 1)
        },
        'match_type': '',
        'risk_level': '',
        'recommendations': {
            'total': {},
            'team1': {},
            'team2': {},
            'best_overall': ''
        },
        'all_options': []
    }

    if total_corners_prediction < 6.0:
        analysis['match_type'] = "НИЗКОУГЛОВОЙ матч"
        analysis['risk_level'] = "НИЗКИЙ риск"
    elif total_corners_prediction < 9.0:
        analysis['match_type'] = "СРЕДНЕУГЛОВОЙ матч"
        analysis['risk_level'] = "УМЕРЕННЫЙ риск"
    else:
        analysis['match_type'] = "ВЫСОКОУГЛОВОЙ матч"
        analysis['risk_level'] = "ВЫСОКИЙ риск"

    thresholds = [4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
    best_threshold = None
    best_prob = 0
    best_type = None

    for threshold in thresholds:
        prob_over = (1 - poisson_cdf(int(threshold), total_corners_prediction)) * 100
        prob_under = poisson_cdf(int(threshold) - 1, total_corners_prediction) * 100

        analysis['all_options'].append({
            'threshold': threshold,
            'over_prob': prob_over,
            'under_prob': prob_under,
            'over_text': f"ТБ {threshold}: {prob_over:.1f}%",
            'under_text': f"ТМ {threshold}: {prob_under:.1f}%"
        })

        if prob_over >= confidence_level and prob_over > best_prob:
            best_prob = prob_over
            best_threshold = threshold
            best_type = 'over'
        elif prob_under >= confidence_level and prob_under > best_prob:
            best_prob = prob_under
            best_threshold = threshold
            best_type = 'under'

    if best_threshold:
        bet_type = "ТБ" if best_type == 'over' else "ТМ"
        analysis['recommendations']['total'] = {
            'recommended_bet': f"{bet_type} {best_threshold} ({best_prob:.1f}%)",
            'probability': best_prob,
            'confidence': "ВЫСОКАЯ уверенность" if best_prob >= 70 else "СРЕДНЯЯ уверенность",
            'justification': f"Ожидается матч со {analysis['match_type'].split()[0].lower()} количеством угловых | Прогноз общего тотала: {total_corners_prediction:.1f} | Средние команд: К1={team1_avg_corners:.1f}, К2={team2_avg_corners:.1f}"
        }

    team1_thresholds = [1.5, 2.5, 3.5, 4.5]
    team2_thresholds = [1.5, 2.5, 3.5, 4.5]

    best_team1_prob = 0
    best_team1_threshold = None
    best_team1_type = None

    for threshold in team1_thresholds:
        prob_over = (1 - poisson_cdf(int(threshold), team1_prediction)) * 100
        prob_under = poisson_cdf(int(threshold) - 1, team1_prediction) * 100

        if prob_over >= confidence_level and prob_over > best_team1_prob:
            best_team1_prob = prob_over
            best_team1_threshold = threshold
            best_team1_type = 'over'
        elif prob_under >= confidence_level and prob_under > best_team1_prob:
            best_team1_prob = prob_under
            best_team1_threshold = threshold
            best_team1_type = 'under'

    if best_team1_threshold:
        bet_type = "ТБ" if best_team1_type == 'over' else "ТМ"
        home_status = "домашняя" if is_home_team1 else "гостевая"
        strength = "сильная" if team1_prediction > team1_avg_corners else "слабая"
        analysis['recommendations']['team1'] = {
            'recommended_bet': f"{bet_type} {best_team1_threshold} ({best_team1_prob:.1f}%)",
            'probability': best_team1_prob,
            'confidence': "ВЫСОКАЯ уверенность" if best_team1_prob >= 70 else "СРЕДНЯЯ уверенность",
            'justification': f"{home_status.capitalize()} команда со {strength} атакой (среднее: {team1_avg_corners:.1f})"
        }

    best_team2_prob = 0
    best_team2_threshold = None
    best_team2_type = None

    for threshold in team2_thresholds:
        prob_over = (1 - poisson_cdf(int(threshold), team2_prediction)) * 100
        prob_under = poisson_cdf(int(threshold) - 1, team2_prediction) * 100

        if prob_over >= confidence_level and prob_over > best_team2_prob:
            best_team2_prob = prob_over
            best_team2_threshold = threshold
            best_team2_type = 'over'
        elif prob_under >= confidence_level and prob_under > best_team2_prob:
            best_team2_prob = prob_under
            best_team2_threshold = threshold
            best_team2_type = 'under'

    if best_team2_threshold:
        bet_type = "ТБ" if best_team2_type == 'over' else "ТМ"
        home_status = "домашняя" if not is_home_team1 else "гостевая"
        strength = "сильная" if team2_prediction > team2_avg_corners else "слабая"
        analysis['recommendations']['team2'] = {
            'recommended_bet': f"{bet_type} {best_team2_threshold} ({best_team2_prob:.1f}%)",
            'probability': best_team2_prob,
            'confidence': "ВЫСОКАЯ уверенность" if best_team2_prob >= 70 else "СРЕДНЯЯ уверенность",
            'justification': f"{home_status.capitalize()} команда со {strength} атакой (среднее: {team2_avg_corners:.1f})"
        }

    return analysis


def format_corners_analysis_for_display(analysis: Dict[str, any]) -> List[str]:
    """Форматирует анализ угловых для отображения"""
    lines = []

    lines.append("🎯 ДЕТАЛЬНЫЙ АНАЛИЗ УГЛОВЫХ")
    lines.append("=" * 60)

    lines.append("📊 ПРОГНОЗИРУЕМЫЕ УГЛОВЫЕ:")
    lines.append(
        f"   • К1: {analysis['total_corners']['team1_prediction']} (среднее: {analysis['total_corners']['team1_average']})")
    lines.append(
        f"   • К2: {analysis['total_corners']['team2_prediction']} (среднее: {analysis['total_corners']['team2_average']})")
    lines.append(f"   • Всего: {analysis['total_corners']['prediction']}")
    lines.append(f"   • Тип матча: {analysis['match_type']}")
    lines.append(f"   • Уровень риска: {analysis['risk_level']}")
    lines.append("")

    if analysis['recommendations']['total']:
        rec = analysis['recommendations']['total']
        lines.append("⭐ ОСНОВНАЯ РЕКОМЕНДАЦИАЦИЯ (общий тотал):")
        lines.append(f"   • {rec['recommended_bet']}")
        lines.append(f"   • Уверенность: {rec['confidence']}")
        lines.append(f"   • Обоснование: {rec['justification']}")
        lines.append("")

    lines.append("📈 ВСЕ РЕАЛИСТИЧНЫЕ ВАРИАНТЫ:")
    for option in analysis['all_options']:
        lines.append(
            f"   {'✅' if option['over_prob'] >= 55 or option['under_prob'] >= 55 else '   '} {option['over_text']} | {option['under_text']}")
    lines.append("")

    if analysis['recommendations']['team1'] or analysis['recommendations']['team2']:
        lines.append("👥 ИНДИВИДУАЛЬНЫЕ РЕКОМЕНДАЦИИ:")

        if analysis['recommendations']['team1']:
            rec1 = analysis['recommendations']['team1']
            lines.append(f"   • К1: {rec1['recommended_bet']}")
            lines.append(f"     Обоснование: {rec1['justification']}")
            lines.append(f"     Уверенность: {rec1['confidence']}")

        if analysis['recommendations']['team2']:
            rec2 = analysis['recommendations']['team2']
            lines.append(f"   • К2: {rec2['recommended_bet']}")
            lines.append(f"     Обоснование: {rec2['justification']}")
            lines.append(f"     Уверенность: {rec2['confidence']}")

    return lines


# ---------------- ФУНКЦИИ АНАЛИЗА КАЧЕСТВА АТАКИ ----------------
def analyze_shot_quality(team_data: List[Dict]) -> Dict[str, any]:
    """Анализ качества ударов команды"""
    total_shots_on_target = sum([d.get('shots_on_target', 0) for d in team_data])
    total_goal_chances = sum([d.get('goal_scoring_chances', 0) for d in team_data])
    total_shots = sum([d.get('total_shots', 0) for d in team_data])

    avg_shots = total_shots / 3
    avg_shots_on_target = total_shots_on_target / 3
    avg_goal_chances = total_goal_chances / 3

    accuracy = (total_shots_on_target / total_shots * 100) if total_shots > 0 else 0

    if accuracy > 40 and avg_goal_chances > 2:
        quality = "ВЫСОКАЯ"
        description = "Опасные атаки с хорошей точностью"
    elif accuracy > 30 and avg_goal_chances > 1:
        quality = "СРЕДНЯЯ"
        description = "Умеренная угроза ворот"
    else:
        quality = "НИЗКАЯ"
        description = "Слабые или неточные атаки"

    return {
        'accuracy_percentage': round(accuracy, 1),
        'avg_shots_per_match': round(avg_shots, 1),
        'avg_shots_on_target': round(avg_shots_on_target, 1),
        'avg_goal_chances': round(avg_goal_chances, 1),
        'quality_rating': quality,
        'quality_description': description,
        'danger_index': round((avg_shots_on_target * 1.0) + (avg_goal_chances * 1.5), 1)
    }


def get_match_analysis(p1g, pd, p2g, lambda1, lambda2, xg1, xg2):
    """Анализ матча с определением фаворита"""
    favorite = None
    if p1g >= 45:
        favorite = "К1"
    elif p2g >= 45:
        favorite = "К2"

    lambda_diff = abs(lambda1 - lambda2)
    xg_diff = abs(xg1 - xg2)

    analysis_lines = []

    if favorite:
        if favorite == "К1":
            if p1g >= 60:
                analysis_lines.append("✅ К1 - ЯВНЫЙ ФАВОРИТ")
                analysis_lines.append(f"   • Вероятность победы К1: {p1g:.1f}%")
            elif p1g >= 50:
                analysis_lines.append("⚡ К1 - ЛЕГКИЙ ФАВОРИТ")
                analysis_lines.append(f"   • Вероятность победы К1: {p1g:.1f}%")
            else:
                analysis_lines.append("📊 К1 - НЕЗНАЧИТЕЛЬНЫЙ ФАВОРИТ")
                analysis_lines.append(f"   • Вероятность победы К1: {p1g:.1f}%")
        else:
            if p2g >= 60:
                analysis_lines.append("✅ К2 - ЯВНЫЙ ФАВОРИТ")
                analysis_lines.append(f"   • Вероятность победы К2: {p2g:.1f}%")
            elif p2g >= 50:
                analysis_lines.append("⚡ К2 - ЛЕГКИЙ ФАВОРИТ")
                analysis_lines.append(f"   • Вероятность победы К2: {p2g:.1f}%")
            else:
                analysis_lines.append("📊 К2 - НЕЗНАЧИТЕЛЬНЫЙ ФАВОРИТ")
                analysis_lines.append(f"   • Вероятность победы К2: {p2g:.1f}%")
    else:
        if pd >= 40:
            analysis_lines.append("⚖️ ВЫСОКАЯ ВЕРОЯТНОСТЬ НИЧЬЕЙ")
            analysis_lines.append(f"   • Вероятность ничьей: {pd:.1f}%")
        else:
            analysis_lines.append("🎯 СБАЛАНСИРОВАННЫЙ МАТЧ БЕЗ ЯВНОГО ФАВОРИТА")
            analysis_lines.append(f"   • П1: {p1g:.1f}%, Ничья: {pd:.1f}%, П2: {p2g:.1f}%")

    if xg1 + xg2 > 3.0:
        analysis_lines.append("⚽ ОЖИДАЕТСЯ ЗРЕЛИЩНЫЙ МАТЧ С БОЛЬШИМ КОЛИЧЕСТВОМ ГОЛОВ")
    elif xg1 + xg2 < 1.5:
        analysis_lines.append("🛡️ ВЕРОЯТЕН НИЗКОВАЗЯЗНЫЙ МАТЧ С МАЛЫМ КОЛИЧЕСТВОМ ГОЛОВ")

    return "\n".join(analysis_lines)


def get_match_recommendation(p1_prob: float, p2_prob: float, draw_prob: float,
                             team1_quality: Dict, team2_quality: Dict,
                             home_advantage: bool = False) -> str:
    """Генерация рекомендации по исходу матча"""
    recommendations = []

    if p1_prob > p2_prob and p1_prob > draw_prob:
        favorite = "К1"
        favorite_prob = p1_prob
        underdog_prob = p2_prob
    elif p2_prob > p1_prob and p2_prob > draw_prob:
        favorite = "К2"
        favorite_prob = p2_prob
        underdog_prob = p1_prob
    else:
        favorite = "НИЧЬЯ"
        favorite_prob = draw_prob

    quality_diff = team1_quality['danger_index'] - team2_quality['danger_index']

    if favorite == "К1":
        if home_advantage:
            recommendations.append("🏠 К1 домашняя команда с преимуществом поля")

        if team1_quality['quality_rating'] == "ВЫСОКАЯ":
            recommendations.append("🎯 К1 показывает ВЫСОКУЮ эффективность в атаке")
        elif team1_quality['quality_rating'] == "НИЗКАЯ":
            recommendations.append("⚠️  Несмотря на фаворитизм, атака К1 слабая")

        if quality_diff > 3:
            recommendations.append("⚡ К1 значительно опаснее в атаке")

    elif favorite == "К2":
        if not home_advantage:
            recommendations.append("🏃 К2 гостевая команда (преодолевает гостевой фактор)")

        if team2_quality['quality_rating'] == "ВЫСОКАЯ":
            recommendations.append("🎯 К2 демонстрирует ВЫСОКУЮ результативность")

        if abs(quality_diff) > 3:
            recommendations.append("⚡ К2 имеет явное преимущество в качестве атак")

    else:
        recommendations.append("⚖️  Сбалансированный матч без явного фаворита")

        if abs(quality_diff) < 1:
            recommendations.append("📊 Команды имеют схожее качество атак")
        else:
            if team1_quality['danger_index'] > team2_quality['danger_index']:
                recommendations.append(f"📈 К1 немного опаснее ({quality_diff:.1f} баллов)")
            else:
                recommendations.append(f"📈 К2 немного опаснее ({abs(quality_diff):.1f} баллов)")

    return " | ".join(recommendations)


def get_final_recommendation_text(pick: str, probability: float,
                                  team1_quality: Dict, team2_quality: Dict,
                                  is_home_team: bool = False) -> str:
    """Краткое обоснование итоговой рекомендации"""
    if pick == "П1":
        if is_home_team:
            base = "Домашняя команда с преимуществом поля"
        else:
            base = "Команда 1"

        if probability >= 60:
            strength = "явный фаворит"
        elif probability >= 50:
            strength = "легкий фаворит"
        else:
            strength = "незначительный фаворит"

        if team1_quality['quality_rating'] == "ВЫСОКАЯ":
            quality = "имеет опасную атаку"
        elif team1_quality['quality_rating'] == "СРЕДНЯЯ":
            quality = "показывает умеренную эффективность"
        else:
            quality = "несмотря на слабую атаку"

        return f"{base} {strength} ({probability:.1f}%) {quality}"

    elif pick == "П2":
        if not is_home_team:
            base = "Гостевая команда преодолевает фактор поля"
        else:
            base = "Команда 2"

        if probability >= 60:
            strength = "явный фаворит"
        elif probability >= 50:
            strength = "легкий фаворит"
        else:
            strength = "незначительный фаворит"

        if team2_quality['quality_rating'] == "ВЫСОКАЯ":
            quality = "демонстрирует высокую результативность"
        elif team2_quality['quality_rating'] == "СРЕДНЯЯ":
            quality = "показывает стабильную игру"
        else:
            quality = "несмотря на скромные показатели"

        return f"{base} {strength} ({probability:.1f}%) {quality}"

    else:
        if probability >= 40:
            strength = "высокая вероятность"
        elif probability >= 30:
            strength = "умеренная вероятность"
        else:
            strength = "возможная"

        diff = abs(team1_quality['danger_index'] - team2_quality['danger_index'])
        if diff < 2:
            balance = "сбалансированный матч"
        else:
            balance = "команды близки по силе"

        return f"{strength} ничьей ({probability:.1f}%) - {balance}"


# ---------------- Params ----------------
DEFAULT_WEIGHTS = [0.5, 0.33, 0.17]
COEFFS = {
    "alpha_box": 0.12,
    "alpha_out": 0.02,
    "alpha_touches": 0.015,
    "pos_baseline": 50.0
}
DEFAULT_CONFIDENCE = 55.0


# ---------------- ТРАДИЦИОННЫЙ АЛГОРИТМ ----------------
def weighted_avg(values: List[float], weights: Optional[List[float]] = None) -> float:
    if not values:
        return 0.0
    if weights is None or len(weights) != len(values):
        weights = [1.0 / len(values)] * len(values)
    total = sum(weights)
    if total == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total


def calculate_lambda_traditional(team_stats):
    ud = team_stats['ud']
    kas = team_stats['kas']
    vlad = team_stats['vlad']
    ugl = team_stats['ugl']

    ud_norm = ud / 15.0
    kas_norm = kas / 40.0
    vlad_norm = vlad / 70.0
    ugl_norm = ugl / 10.0

    lambda_base = (0.7 * ud_norm + 0.3 * kas_norm + 0.1 * vlad_norm + 0.05 * ugl_norm)

    ud_kas_ratio = ud / kas if kas > 0 else 0
    correction = 1 - 0.48 * ud_kas_ratio
    correction = max(correction, 0.1)

    lambda_final = lambda_base * correction
    return lambda_final


def calculate_expected_goals_from_stats(team_last3: List[Dict], opp_last3: List[Dict],
                                        weights: Optional[List[float]] = None, coeffs: Optional[Dict] = None) -> float:
    if coeffs is None:
        coeffs = COEFFS
    if weights is None:
        weights = DEFAULT_WEIGHTS

    def wavg(list_of_dicts, field):
        vals = [float(d.get(field, 0) or 0.0) for d in list_of_dicts]
        return weighted_avg(vals, weights)

    avg_pos = wavg(team_last3, 'pos')
    avg_sh_in = wavg(team_last3, 'shots_in_box')
    avg_sh_out = wavg(team_last3, 'shots_out_box')
    avg_touches = wavg(team_last3, 'touches_in_box')
    opp_avg_sh_in = wavg(opp_last3, 'shots_in_box')

    xg_attack = (coeffs['alpha_box'] * avg_sh_in + coeffs['alpha_out'] * avg_sh_out + coeffs[
        'alpha_touches'] * avg_touches)
    pos_factor = (avg_pos / coeffs['pos_baseline']) if coeffs['pos_baseline'] else 1.0
    xg_attack *= pos_factor

    opp_def_proxy = coeffs['alpha_box'] * opp_avg_sh_in
    xg = max(0.0, 0.5 * (xg_attack + opp_def_proxy))

    xg = max(xg, 0.1)
    xg = min(xg, 4.0)

    return xg


def compute_result_probs(xg_home: float, xg_away: float, max_k: int = 12):
    p1 = pd = p2 = 0.0
    probs_h = [poisson_pmf(k, xg_home) for k in range(max_k + 1)]
    probs_a = [poisson_pmf(k, xg_away) for k in range(max_k + 1)]
    rem_h = max(0.0, 1.0 - sum(probs_h))
    rem_a = max(0.0, 1.0 - sum(probs_a))
    probs_h[-1] += rem_h
    probs_a[-1] += rem_a

    for i, ph in enumerate(probs_h):
        for j, pa in enumerate(probs_a):
            p = ph * pa
            if i > j:
                p1 += p
            elif i == j:
                pd += p
            else:
                p2 += p

    s = p1 + pd + p2
    if s > 0:
        p1 /= s
        pd /= s
        p2 /= s

    return p1, pd, p2


def get_top_scores(xg_home: float, xg_away: float, top_n: int = 6):
    scores = []
    max_goals = 7

    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p_home = poisson_pmf(i, xg_home)
            p_away = poisson_pmf(j, xg_away)
            scores.append(((i, j), p_home * p_away))

    scores.sort(key=lambda x: x[1], reverse=True)

    total = sum(prob for _, prob in scores[:top_n])
    if total > 0:
        return [((h, a), round(prob / total * 100, 2)) for (h, a), prob in scores[:top_n]]
    return [((h, a), 0.0) for (h, a), _ in scores[:top_n]]


# ---------------- λ-АЛГОРИТМ С УСИЛЕННЫМ TMPR И НОВЫМИ МЕТРИКАМИ ----------------
def calculate_lambda_basic(vlad, ud, kas, ugl):
    ud_norm = ud / 15.0
    kas_norm = kas / 40.0
    vlad_norm = vlad / 70.0
    ugl_norm = ugl / 10.0

    lambda_base = (0.7 * ud_norm + 0.3 * kas_norm + 0.1 * vlad_norm + 0.05 * ugl_norm)

    if kas > 0:
        ud_kas_ratio = ud / kas
    else:
        ud_kas_ratio = 0

    correction = 1 - 0.48 * ud_kas_ratio
    correction = max(correction, 0.1)

    lambda_final = lambda_base * correction
    return lambda_final


def calculate_lambda_with_enhancement(vlad_values, ud_in_shtraf, ud_iz_za_shtraf, ugl_values, kas_values,
                                      tackle_success_values=None, duels_won_values=None, clearances_values=None):
    """Расчет λ с учетом новых метрик - РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ"""
    vlad_avg = sum(vlad_values) / 3
    ud_total_avg = sum([ud_in_shtraf[i] + ud_iz_za_shtraf[i] for i in range(3)]) / 3
    kas_avg = sum(kas_values) / 3
    ugl_avg = sum(ugl_values) / 3

    # Базовый λ
    lambda_base = calculate_lambda_basic(vlad_avg, ud_total_avg, kas_avg, ugl_avg)

    # Улучшения от новых метрик
    lambda_enhanced = lambda_base

    # Улучшение от лучшего матча
    third_scores = []
    for i in range(3):
        score = ud_in_shtraf[i] + kas_values[i] * 0.5
        third_scores.append((score, i))

    best_third_idx = max(third_scores, key=lambda x: x[0])[1]

    vlad_best = vlad_values[best_third_idx]
    ud_best = ud_in_shtraf[best_third_idx] + ud_iz_za_shtraf[best_third_idx]
    kas_best = kas_values[best_third_idx]
    ugl_best = ugl_values[best_third_idx]

    lambda_best = calculate_lambda_basic(vlad_best, ud_best, kas_best, ugl_best)
    lambda_enhanced = lambda_base * 0.7 + lambda_best * 0.3

    # Коррекция на дальние удары
    ud_total = sum(ud_in_shtraf) + sum(ud_iz_za_shtraf)
    ud_iz_za_total = sum(ud_iz_za_shtraf)

    if ud_total > 0:
        long_shot_ratio = ud_iz_za_total / ud_total
        if long_shot_ratio > 0.4:
            lambda_enhanced *= (1 - (long_shot_ratio - 0.4))

    # Бонус за угловые
    corners_bonus = min(ugl_avg / 5.0, 0.3)
    lambda_enhanced *= (1 + corners_bonus)

    # Баланс эффективности
    if kas_avg > 0:
        efficiency = ud_total_avg / kas_avg
        balance = (vlad_avg / 100.0) * efficiency
        if balance > 0.6:
            lambda_enhanced *= 0.8

    # Улучшения от новых метрик (если предоставлены) - РЕАЛИСТИЧНЫЕ КОЭФФИЦИЕНТЫ
    if tackle_success_values and duels_won_values and clearances_values:
        avg_tackle_success = sum(tackle_success_values) / 3
        avg_duels_won = sum(duels_won_values) / 3
        avg_clearances = sum(clearances_values) / 3

        # Бонус за высокий % отборов
        if avg_tackle_success > 60:
            tackle_bonus = (avg_tackle_success - 60) * LAMBDA_TO_XG_COEFFS['tackle_success_factor']
            lambda_enhanced *= (1 + min(tackle_bonus, 0.08))  # до +8% (ранее 15%)

        # Бонус за выигранные дуэли
        if avg_duels_won > 50:
            duels_bonus = (avg_duels_won - 50) * LAMBDA_TO_XG_COEFFS['duels_won_factor']
            lambda_enhanced *= (1 + min(duels_bonus, 0.06))  # до +6% (ранее 12%)

        # Бонус за низкое количество выносов (хорошая оборона)
        if avg_clearances < 15:
            clearances_bonus = (15 - avg_clearances) * LAMBDA_TO_XG_COEFFS['clearances_factor']
            lambda_enhanced *= (1 + min(clearances_bonus, 0.04))  # до +4% (ранее 8%)

    return lambda_enhanced


def lambda_to_xg_with_home_advantage(lambda_val, vlad, ud_total, kas, is_home=True):
    """УСИЛЕННАЯ конвертация λ в xG с домашним преимуществом"""
    base_coef = 1.5
    possession_factor = 1.0 + ((vlad - 50) / 100.0) * 0.7
    possession_factor = max(0.85, min(possession_factor, 1.15))

    if kas > 3:
        efficiency = 0.95 + (ud_total / kas * 0.3)
        efficiency = max(0.75, min(efficiency, 1.25))
    else:
        efficiency = 0.95

    xg_neutral = lambda_val * base_coef * possession_factor * efficiency
    xg_neutral = min(xg_neutral, 3.0)

    if is_home:
        xg = xg_neutral + 0.22
    else:
        xg = xg_neutral - 0.12

    xg = max(xg, 0.1)
    xg = min(xg, 3.2)

    return round(xg, 2), round(xg_neutral, 2)


def predict_match_lambda_with_tmpr(team1_data, team2_data, tmpr1, tmpr2):
    """
    Прогноз с учетом УСИЛЕННОГО TMPR и НОВЫХ МЕТРИК
    """
    # 1. Базовый расчет λ с новыми метриками
    lambda1_raw = calculate_lambda_with_enhancement(
        team1_data['vlad'],
        team1_data['ud_in_shtraf'],
        team1_data['ud_iz_za_shtraf'],
        team1_data['ugl'],
        team1_data['kas'],
        team1_data.get('tackle_success'),
        team1_data.get('duels_won'),
        team1_data.get('clearances')
    )

    lambda2_raw = calculate_lambda_with_enhancement(
        team2_data['vlad'],
        team2_data['ud_in_shtraf'],
        team2_data['ud_iz_za_shtraf'],
        team2_data['ugl'],
        team2_data['kas'],
        team2_data.get('tackle_success'),
        team2_data.get('duels_won'),
        team2_data.get('clearances')
    )

    # 2. Применяем TMPR к λ
    lambda1_tmpr, tmpr_effect1 = apply_tmpr_effect(
        lambda1_raw, tmpr1, tmpr2, is_home=True, value_type='lambda'
    )

    lambda2_tmpr, tmpr_effect2 = apply_tmpr_effect(
        lambda2_raw, tmpr2, tmpr1, is_home=False, value_type='lambda'
    )

    # 3. Рассчитываем базовые xG
    vlad1_avg = sum(team1_data['vlad']) / 3
    ud1_total_avg = sum([team1_data['ud_in_shtraf'][i] + team1_data['ud_iz_za_shtraf'][i] for i in range(3)]) / 3
    kas1_avg = sum(team1_data['kas']) / 3

    vlad2_avg = sum(team2_data['vlad']) / 3
    ud2_total_avg = sum([team2_data['ud_in_shtraf'][i] + team2_data['ud_iz_za_shtraf'][i] for i in range(3)]) / 3
    kas2_avg = sum(team2_data['kas']) / 3

    xg1_raw, xg1_neutral = lambda_to_xg_with_home_advantage(
        lambda1_raw, vlad1_avg, ud1_total_avg, kas1_avg, is_home=True
    )

    xg2_raw, xg2_neutral = lambda_to_xg_with_home_advantage(
        lambda2_raw, vlad2_avg, ud2_total_avg, kas2_avg, is_home=False
    )

    # 4. Применяем TMPR НАПРЯМУЮ К xG
    xg1_tmpr_direct, xg_tmpr_effect1 = apply_tmpr_effect(
        xg1_raw, tmpr1, tmpr2, is_home=True, value_type='xg'
    )

    xg2_tmpr_direct, xg_tmpr_effect2 = apply_tmpr_effect(
        xg2_raw, tmpr2, tmpr1, is_home=False, value_type='xg'
    )

    # 5. КОМБИНИРОВАННЫЙ xG
    xg1_from_lambda = lambda1_tmpr * 1.5
    xg2_from_lambda = lambda2_tmpr * 1.5

    xg1_combined = (xg1_tmpr_direct * 0.6) + (xg1_from_lambda * 0.4)
    xg2_combined = (xg2_tmpr_direct * 0.6) + (xg2_from_lambda * 0.4)

    # 6. Подготавливаем данные для улучшений
    team1_match_data = [
        {
            'shots_on_target': 4.0,
            'goal_scoring_chances': 2.0,
            'total_shots': 14.7,
            'tackle_success': team1_data.get('tackle_success', [50, 50, 50])[0],
            'duels_won': team1_data.get('duels_won', [50, 50, 50])[0],
            'clearances': team1_data.get('clearances', [10, 10, 10])[0]
        },
        {
            'shots_on_target': 4.0,
            'goal_scoring_chances': 2.0,
            'total_shots': 14.7,
            'tackle_success': team1_data.get('tackle_success', [50, 50, 50])[1],
            'duels_won': team1_data.get('duels_won', [50, 50, 50])[1],
            'clearances': team1_data.get('clearances', [10, 10, 10])[1]
        },
        {
            'shots_on_target': 4.0,
            'goal_scoring_chances': 2.0,
            'total_shots': 14.7,
            'tackle_success': team1_data.get('tackle_success', [50, 50, 50])[2],
            'duels_won': team1_data.get('duels_won', [50, 50, 50])[2],
            'clearances': team1_data.get('clearances', [10, 10, 10])[2]
        }
    ]

    team2_match_data = [
        {
            'shots_on_target': 4.3,
            'goal_scoring_chances': 2.3,
            'total_shots': 13.0,
            'tackle_success': team2_data.get('tackle_success', [50, 50, 50])[0],
            'duels_won': team2_data.get('duels_won', [50, 50, 50])[0],
            'clearances': team2_data.get('clearances', [10, 10, 10])[0]
        },
        {
            'shots_on_target': 4.3,
            'goal_scoring_chances': 2.3,
            'total_shots': 13.0,
            'tackle_success': team2_data.get('tackle_success', [50, 50, 50])[1],
            'duels_won': team2_data.get('duels_won', [50, 50, 50])[1],
            'clearances': team2_data.get('clearances', [10, 10, 10])[1]
        },
        {
            'shots_on_target': 4.3,
            'goal_scoring_chances': 2.3,
            'total_shots': 13.0,
            'tackle_success': team2_data.get('tackle_success', [50, 50, 50])[2],
            'duels_won': team2_data.get('duels_won', [50, 50, 50])[2],
            'clearances': team2_data.get('clearances', [10, 10, 10])[2]
        }
    ]

    # 7. Применяем улучшения с новыми метриками
    xg1_final = calculate_enhanced_xg_with_new_metrics(xg1_combined, team1_match_data, team2_match_data, is_home=True)
    xg2_final = calculate_enhanced_xg_with_new_metrics(xg2_combined, team2_match_data, team1_match_data, is_home=False)

    # 8. Пересчитываем вероятности с финальными xG
    p1g, pd, p2g = compute_result_probs(xg1_final, xg2_final)

    if p1g > p2g and p1g > pd:
        recommended_outcome = 'П1'
    elif p2g > p1g and p2g > pd:
        recommended_outcome = 'П2'
    else:
        recommended_outcome = 'Ничья/X'

    top_scores = get_top_scores(xg1_final, xg2_final, top_n=6)

    total_goals = xg1_final + xg2_final
    over_2_5_prob = round(sum(poisson_pmf(i, xg1_final) * poisson_pmf(j, xg2_final)
                              for i in range(8) for j in range(8) if i + j > 2.5) * 100, 1)
    over_1_5_prob = round(sum(poisson_pmf(i, xg1_final) * poisson_pmf(j, xg2_final)
                              for i in range(8) for j in range(8) if i + j > 1.5) * 100, 1)
    under_2_5_prob = 100 - over_2_5_prob
    under_1_5_prob = 100 - over_1_5_prob

    p0_1 = poisson_pmf(0, xg1_final)
    p0_2 = poisson_pmf(0, xg2_final)
    btts_prob = max(0.0, 1.0 - p0_1 - p0_2 + p0_1 * p0_2) * 100

    return {
        'lambdas': {
            'raw': (round(lambda1_raw, 3), round(lambda2_raw, 3)),
            'tmpr_enhanced': (round(lambda1_tmpr, 3), round(lambda2_tmpr, 3))
        },
        'expected_goals': {
            'raw': (round(xg1_raw, 2), round(xg2_raw, 2)),
            'tmpr_direct': (round(xg1_tmpr_direct, 2), round(xg2_tmpr_direct, 2)),
            'combined': (round(xg1_combined, 2), round(xg2_combined, 2)),
            'final': (round(xg1_final, 2), round(xg2_final, 2))
        },
        'tmpr_effects': {
            'team1_lambda': tmpr_effect1,
            'team2_lambda': tmpr_effect2,
            'team1_xg': xg_tmpr_effect1,
            'team2_xg': xg_tmpr_effect2
        },
        'outcomes': {'home_win': round(p1g * 100, 1), 'draw': round(pd * 100, 1), 'away_win': round(p2g * 100, 1)},
        'recommended_outcome': recommended_outcome,
        'top_scores': top_scores,
        'exact_score_prediction': f"{top_scores[0][0][0]}:{top_scores[0][0][1]}",
        'total_goals': round(total_goals, 2),
        'over_2_5_prob': over_2_5_prob,
        'over_1_5_prob': over_1_5_prob,
        'under_2_5_prob': under_2_5_prob,
        'under_1_5_prob': under_1_5_prob,
        'btts_prob': round(btts_prob, 1),
        'tmpr_values': (tmpr1, tmpr2),
        'tmpr_diff': round(tmpr1 - tmpr2, 1),
        'home_advantage_applied': True
    }


# ---------------- GUI ----------------
class UltraCompactPredictor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("XG Score — Футбольный предиктор (УСИЛЕННЫЙ TMPR + НОВЫЕ МЕТРИКИ)")
        self.geometry("980x720")  # Увеличили ширину для новых столбцов

        self.minsize(950, 650)
        self.configure(bg="black")

        # Шрифты
        self.header_font = ("Segoe UI", 12, "bold")
        self.input_font = ("Segoe UI", 12, "bold")
        self.output_font = ("Consolas", 12, "bold")
        self.small_font = ("Segoe UI", 9, "bold")
        self.label_font = ("Segoe UI", 8, "bold")

        # Основной контейнер
        main_container = tk.Frame(self, bg="black")
        main_container.pack(fill="both", expand=True, padx=8, pady=3)

        main_container.columnconfigure(0, weight=1)
        for i in range(5):
            main_container.rowconfigure(i, weight=1 if i == 4 else 0)

        # ========== ВВОД ДАННЫХ ==========
        input_frame = tk.Frame(main_container, bg="black")
        input_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        tk.Label(input_frame, text="ВВОД ДАННЫХ ПОСЛЕДНИХ 3 МАТЧЕЙ (С НОВЫМИ МЕТРИКАМИ: ОТБОРЫ, ДУЭЛИ, ВЫНОСЫ)",
                 font=("Segoe UI", 11, "bold"), bg="black", fg="#00FF66").pack(pady=(0, 8))

        teams_container = tk.Frame(input_frame, bg="black")
        teams_container.pack(fill="x", expand=True)

        self._create_extended_input_table(teams_container)

        # ========== TMPR ВВОД ==========
        self._create_tmpr_input(input_frame)

        # ========== НАСТРОЙКИ ==========
        settings_frame = tk.Frame(main_container, bg="black")
        settings_frame.grid(row=1, column=0, sticky="ew", pady=(3, 5))

        settings_row = tk.Frame(settings_frame, bg="black")
        settings_row.pack(fill="x", expand=True)

        # Алгоритм
        algo_frame = tk.Frame(settings_row, bg="black")
        algo_frame.pack(side="left", fill="x", expand=True, padx=(0, 15))

        tk.Label(algo_frame, text="Алгоритм:", font=self.small_font,
                 bg="black", fg="white").pack(anchor="w")

        self.algo_var = tk.StringVar(value="both")

        for text, value in [("Оба алгоритма", "both"),
                            ("Только традиционный", "traditional"),
                            ("Только λ-алгоритм", "lambda")]:
            rb = tk.Radiobutton(algo_frame, text=text, variable=self.algo_var,
                                value=value, font=("Segoe UI", 9, "bold"), bg="black",
                                fg="white", selectcolor="black", anchor="w")
            rb.pack(anchor="w")

        # Информация о новых метриках
        info_frame = tk.Frame(settings_row, bg="black")
        info_frame.pack(side="right", fill="x", expand=True, padx=(15, 0))

        tk.Label(info_frame, text="📊 НОВЫЕ МЕТРИКИ В АНАЛИЗЕ:",
                 font=self.small_font, bg="black", fg="#00AAFF").pack(anchor="e")

        new_metrics1 = tk.Label(info_frame, text="• Отборы %: >70% = элитная оборона | <55% = слабая",
                                font=("Segoe UI", 8, "bold"), bg="black", fg="#00AAFF")
        new_metrics1.pack(anchor="e")

        new_metrics2 = tk.Label(info_frame, text="• Дуэли: >60% = физическое доминирование | <45% = слабо",
                                font=("Segoe UI", 8, "bold"), bg="black", fg="#00AAFF")
        new_metrics2.pack(anchor="e")

        new_metrics3 = tk.Label(info_frame, text="• Выносы: <12 = контроль | >28 = кризис обороны",
                                font=("Segoe UI", 8, "bold"), bg="black", fg="#00AAFF")
        new_metrics3.pack(anchor="e")

        # ========== КНОПКИ ==========
        buttons_frame = tk.Frame(main_container, bg="black")
        buttons_frame.grid(row=2, column=0, sticky="ew", pady=(3, 8))

        self.btn_calc = tk.Button(buttons_frame, text="РАССЧИТАТЬ",
                                  font=("Segoe UI", 10, "bold"),
                                  bg="#00FF33", activebackground="#66FF66",
                                  command=self.on_calc, height=1)
        self.btn_calc.pack(side="left", fill="x", expand=True, padx=(0, 3))

        self.btn_reset = tk.Button(buttons_frame, text="СБРОС",
                                   font=("Segoe UI", 10, "bold"),
                                   bg="#FF3333", activebackground="#FF6666",
                                   command=self.on_reset, height=1)
        self.btn_reset.pack(side="left", fill="x", expand=True, padx=3)

        self.btn_save = tk.Button(buttons_frame, text="СОХРАНИТЬ ОТЧЕТ",
                                  font=("Segoe UI", 10, "bold"),
                                  bg="#FF33FF", activebackground="#FF66FF",
                                  command=self.on_save, height=1)
        self.btn_save.pack(side="left", fill="x", expand=True, padx=(3, 0))

        # ========== РЕЗУЛЬТАТЫ ==========
        output_frame = tk.Frame(main_container, bg="black")
        output_frame.grid(row=3, column=0, sticky="nsew")

        output_container = tk.Frame(output_frame, bg="black")
        output_container.pack(fill="both", expand=True)

        output_scrollbar = tk.Scrollbar(output_container)
        output_scrollbar.pack(side="right", fill="y")

        self.output = tk.Text(output_container, height=20, font=self.output_font,
                              bg="#000000", fg="#00FF66", wrap="word",
                              yscrollcommand=output_scrollbar.set)
        self.output.pack(side="left", fill="both", expand=True)
        output_scrollbar.config(command=self.output.yview)
        self.output.configure(state="disabled")

        # Статус бар
        self.status_bar = tk.Label(main_container, text="Готов к работе...",
                                   font=("Segoe UI", 8, "bold"), bg="black", fg="#888888",
                                   anchor="w", relief="sunken", bd=1)
        self.status_bar.grid(row=4, column=0, sticky="ew", pady=(5, 0))

    def _create_extended_input_table(self, parent):
        """Создает расширенную таблицу для ввода данных с новыми метриками"""
        # Заголовки в нужной последовательности - ИСПРАВЛЕНО: "Дуэли" вместо "Дуэли %"
        headers = ["", "Влад", "Все уд", "В створ", "Гол мом", "Угл",
                   "Уд в ш", "Уд из ш", "Касания", "Отборы %", "Дуэли", "Выносы"]

        table_frame = tk.Frame(parent, bg="black")
        table_frame.pack(fill="both", expand=True)

        # Настройка столбцов
        table_frame.grid_columnconfigure(0, weight=0, minsize=25)  # Номера матчей
        for col in range(1, len(headers)):
            table_frame.grid_columnconfigure(col, weight=1, minsize=55)  # Все остальные

        # Заголовки
        for col, header in enumerate(headers):
            header_label = tk.Label(table_frame, text=header, font=self.label_font,
                                    bg="black", fg="white", anchor="center",
                                    padx=1, pady=2, wraplength=60, justify="center")
            header_label.grid(row=0, column=col, sticky="nsew", padx=1, pady=1)

        self.team1_entries = []
        self.team2_entries = []

        entry_style = {
            'font': ("Segoe UI", 10, "bold"),
            'justify': "center",
            'relief': "solid",
            'bd': 1,
            'highlightbackground': "#00FF00",
            'highlightcolor': "#00FF00",
            'highlightthickness': 1,
            'width': 4,
            'insertbackground': "#00FF00"
        }

        # Команда 1 (Домашняя)
        for row in range(1, 4):
            match_label = tk.Label(table_frame, text=f"К1 М{row}",
                                   font=("Segoe UI", 9, "bold"), bg="black", fg="#00FF66",
                                   anchor="center", padx=2, pady=2)
            match_label.grid(row=row, column=0, sticky="nsew", padx=1, pady=2)

            row_entries = {}
            field_names = ["владение", "всего ударов", "уд в створ", "голевые моменты",
                           "угловые", "уд в штрафной", "уд из-за штрафной", "касания",
                           "отборы", "дуэли", "выносы"]

            for col in range(1, 12):
                entry_frame = tk.Frame(table_frame, bg="#00FF00", padx=0, pady=0)
                entry_frame.grid(row=row, column=col, padx=1, pady=2, sticky="nsew")
                entry_frame.grid_propagate(False)

                entry = tk.Entry(entry_frame, **entry_style,
                                 bg="#111111", fg="#00FF66")
                entry.pack(fill="both", expand=True, padx=1, pady=1)

                row_entries[field_names[col - 1]] = entry

            self.team1_entries.append(row_entries)

        # Разделитель
        separator = tk.Frame(table_frame, height=2, bg="#444444")
        separator.grid(row=4, column=0, columnspan=12, sticky="ew", pady=4)

        # Команда 2 (Гостевая)
        for row in range(5, 8):
            match_label = tk.Label(table_frame, text=f"К2 М{row - 4}",
                                   font=("Segoe UI", 9, "bold"), bg="black", fg="#FF6600",
                                   anchor="center", padx=2, pady=2)
            match_label.grid(row=row, column=0, sticky="nsew", padx=1, pady=2)

            row_entries = {}
            field_names = ["владение", "всего ударов", "уд в створ", "голевые моменты",
                           "угловые", "уд в штрафной", "уд из-за штрафной", "касания",
                           "отборы", "дуэли", "выносы"]

            for col in range(1, 12):
                entry_frame = tk.Frame(table_frame, bg="#00FF00", padx=0, pady=0)
                entry_frame.grid(row=row, column=col, padx=1, pady=2, sticky="nsew")
                entry_frame.grid_propagate(False)

                entry = tk.Entry(entry_frame, **entry_style,
                                 bg="#111111", fg="#FF6600")
                entry.pack(fill="both", expand=True, padx=1, pady=1)

                row_entries[field_names[col - 1]] = entry

            self.team2_entries.append(row_entries)

        for i in range(1, 8):
            table_frame.rowconfigure(i, weight=0, minsize=40)

    def _create_tmpr_input(self, parent):
        """Создает поля ввода для TMPR"""
        tmpr_frame = tk.Frame(parent, bg="black")
        tmpr_frame.pack(fill="x", pady=(10, 0))

        # Заголовок
        title_label = tk.Label(tmpr_frame, text="🏆 УСИЛЕННЫЙ TMPR (С УЧЕТОМ НОВЫХ МЕТРИК):",
                               font=("Segoe UI", 10, "bold"), bg="black", fg="#FFAA00")
        title_label.pack(anchor="w", pady=(0, 5))

        # Контейнер для полей ввода
        input_container = tk.Frame(tmpr_frame, bg="black")
        input_container.pack(fill="x", pady=5)

        # Стиль полей ввода TMPR
        tmpr_entry_style = {
            'font': ("Segoe UI", 10, "bold"),
            'justify': "center",
            'relief': "solid",
            'bd': 1,
            'highlightbackground': "#FFAA00",
            'highlightcolor': "#FFAA00",
            'highlightthickness': 1,
            'width': 10,
            'insertbackground': "#FFAA00"
        }

        # Поле для К1
        tk.Label(input_container, text="К1 TMPR:",
                 font=("Segoe UI", 9, "bold"), bg="black", fg="#00FF66").grid(row=0, column=0, padx=(0, 5))

        self.tmpr1_entry = tk.Entry(input_container, **tmpr_entry_style,
                                    bg="#111111", fg="#00FF66")
        self.tmpr1_entry.grid(row=0, column=1, padx=5)
        self.tmpr1_entry.insert(0, "300.0")

        # Поле для К2
        tk.Label(input_container, text="К2 TMPR:",
                 font=("Segoe UI", 9, "bold"), bg="black", fg="#FF6600").grid(row=0, column=2, padx=(20, 5))

        self.tmpr2_entry = tk.Entry(input_container, **tmpr_entry_style,
                                    bg="#111111", fg="#FF6600")
        self.tmpr2_entry.grid(row=0, column=3, padx=5)
        self.tmpr2_entry.insert(0, "300.0")

        # Подсказка
        hint_label = tk.Label(input_container,
                              text="(100.0-500.0, 300.0 = нейтрально, пример: 326.6, 287.3, 412.8)",
                              font=("Segoe UI", 8, "bold"), bg="black", fg="#888888")
        hint_label.grid(row=1, column=0, columnspan=4, pady=(5, 0))

        # Шкала интерпретации
        scale_frame = tk.Frame(tmpr_frame, bg="black")
        scale_frame.pack(fill="x", pady=(5, 0))

        scale_text = "Шкала: 100-200=Кризис | 200-300=Ниже среднего | 300-400=Среднее/Хорошее | 400-500=Элитная форма"
        scale_label = tk.Label(scale_frame, text=scale_text,
                               font=("Segoe UI", 8, "bold"), bg="black", fg="#888888")
        scale_label.pack(anchor="w")

    def _collect_extended_table(self, table_entries) -> List[Dict]:
        """Сбор данных с новыми метриками"""
        data = []
        field_map = {
            'владение': 'pos',
            'всего ударов': 'total_shots',
            'уд в створ': 'shots_on_target',
            'голевые моменты': 'goal_scoring_chances',
            'угловые': 'corners',
            'уд в штрафной': 'shots_in_box',
            'уд из-за штрафной': 'shots_out_box',
            'касания': 'touches_in_box',
            'отборы': 'tackle_success',
            'дуэли': 'duels_won',
            'выносы': 'clearances'
        }

        for row_widgets in table_entries:
            row = {}
            for widget_name, entry_widget in row_widgets.items():
                field_name = field_map.get(widget_name, widget_name)
                value = safe_float(entry_widget.get())

                if field_name in ['tackle_success', 'duels_won']:
                    # Проценты: ограничиваем 0-100
                    if value is None:
                        row[field_name] = 50.0  # нейтральное значение
                    else:
                        row[field_name] = max(0.0, min(100.0, value))
                else:
                    row[field_name] = value or 0.0

            # Заполняем отсутствующие поля
            for field in field_map.values():
                if field not in row:
                    if field in ['tackle_success', 'duels_won']:
                        row[field] = 50.0
                    else:
                        row[field] = 0.0

            data.append(row)
        return data

    def _prepare_lambda_data(self, team_data: List[Dict]) -> Dict:
        """Подготовка данных для λ-алгоритма с новыми метриками"""
        vlad_values = [d['pos'] for d in team_data]
        ud_in_shtraf = [d['shots_in_box'] for d in team_data]
        ud_iz_za_shtraf = [d['shots_out_box'] for d in team_data]
        ugl_values = [d['corners'] for d in team_data]
        kas_values = [d['touches_in_box'] for d in team_data]

        # Новые метрики
        tackle_success_values = [d.get('tackle_success', 50) for d in team_data]
        duels_won_values = [d.get('duels_won', 50) for d in team_data]
        clearances_values = [d.get('clearances', 0) for d in team_data]

        return {
            'vlad': vlad_values,
            'ud_in_shtraf': ud_in_shtraf,
            'ud_iz_za_shtraf': ud_iz_za_shtraf,
            'ugl': ugl_values,
            'kas': kas_values,
            'tackle_success': tackle_success_values,
            'duels_won': duels_won_values,
            'clearances': clearances_values
        }

    def _prepare_lambda_data_traditional(self, team_data: List[Dict]) -> Dict:
        """Подготовка данных для традиционного λ"""
        vlad_values = [d['pos'] for d in team_data]
        ud_in_shtraf = [d['shots_in_box'] for d in team_data]
        ud_iz_za_shtraf = [d['shots_out_box'] for d in team_data]
        ugl_values = [d['corners'] for d in team_data]
        kas_values = [d['touches_in_box'] for d in team_data]

        vlad_avg = sum(vlad_values) / len(vlad_values)
        total_ud = []
        for i in range(len(vlad_values)):
            total_ud.append(ud_in_shtraf[i] + ud_iz_za_shtraf[i])
        ud_avg = sum(total_ud) / len(total_ud)

        kas_avg = sum(kas_values) / len(kas_values)
        ugl_avg = sum(ugl_values) / len(ugl_values)

        return {
            'ud': ud_avg,
            'kas': kas_avg,
            'vlad': vlad_avg,
            'ugl': ugl_avg
        }

    def _get_lambda_advantage_text(self, lambda1, lambda2):
        if lambda1 == 0 and lambda2 == 0:
            return "Команды имеют нулевую атакующую эффективность"

        if lambda1 > lambda2:
            denominator = lambda2 if lambda2 > 0 else 0.001
            advantage_pct = ((lambda1 - lambda2) / denominator * 100)
            return f"К1 сильнее К2 в атаке на {advantage_pct:.1f}%"
        elif lambda2 > lambda1:
            denominator = lambda1 if lambda1 > 0 else 0.001
            advantage_pct = ((lambda2 - lambda1) / denominator * 100)
            return f"К2 сильнее К1 в атаке на {advantage_pct:.1f}%"
        else:
            return "Команды равны по атакующей эффективности"

    def _get_exact_score_recommendation(self, top_scores):
        if len(top_scores) < 1:
            return "Недостаточно данных для прогноза точного счета"

        best_score = top_scores[0]
        score_text = f"{best_score[0][0]}:{best_score[0][1]}"
        probability = best_score[1]

        if probability >= 20:
            confidence = "ВЫСОКАЯ уверенность"
        elif probability >= 10:
            confidence = "СРЕДНЯЯ уверенность"
        else:
            confidence = "НИЗКАЯ уверенность"

        alternatives = []
        for i in range(1, min(3, len(top_scores))):
            alt_score = top_scores[i]
            alt_text = f"{alt_score[0][0]}:{alt_score[0][1]} ({alt_score[1]}%)"
            alternatives.append(alt_text)

        recommendation = f"Рекомендуемый точный счет: {score_text} ({probability}%)\n"
        recommendation += f"Уровень уверенности: {confidence}\n"

        if alternatives:
            recommendation += f"Альтернативные варианты: {', '.join(alternatives)}"

        return recommendation

    def _get_input_data_summary(self, team1_data: List[Dict], team2_data: List[Dict]) -> List[str]:
        """Получение сводки введенных данных"""
        lines = []
        lines.append("=" * 90)
        lines.append("ВВЕДЕННЫЕ ДАННЫЕ ДЛЯ АНАЛИЗА (последние 3 матча, С НОВЫМИ МЕТРИКАМИ)")
        lines.append("=" * 90)

        lines.append("\n📊 ДАННЫЕ КОМАНДЫ 1 (Домашняя):")
        # ИСПРАВЛЕНО: "Дуэли" вместо "Дуэли%"
        headers = ["Матч", "Влад", "Все уд", "В створ", "Гол мом", "Угл", "Уд в ш", "Уд из ш", "Касания", "Отборы%",
                   "Дуэли", "Выносы"]
        lines.append("   " + " | ".join(headers))
        lines.append("   " + "-" * 85)

        for i, match in enumerate(team1_data, 1):
            match_data = [
                f"М{i}",
                f"{match.get('pos', 0):.0f}",
                f"{match.get('total_shots', 0):.0f}",
                f"{match.get('shots_on_target', 0):.0f}",
                f"{match.get('goal_scoring_chances', 0):.0f}",
                f"{match.get('corners', 0):.0f}",
                f"{match.get('shots_in_box', 0):.0f}",
                f"{match.get('shots_out_box', 0):.0f}",
                f"{match.get('touches_in_box', 0):.0f}",
                f"{match.get('tackle_success', 50):.0f}",
                f"{match.get('duels_won', 50):.0f}",
                f"{match.get('clearances', 0):.0f}"
            ]
            lines.append("   " + " | ".join(match_data))

        avg_team1 = {
            'pos': sum([d.get('pos', 0) for d in team1_data]) / 3,
            'total_shots': sum([d.get('total_shots', 0) for d in team1_data]) / 3,
            'shots_on_target': sum([d.get('shots_on_target', 0) for d in team1_data]) / 3,
            'goal_scoring_chances': sum([d.get('goal_scoring_chances', 0) for d in team1_data]) / 3,
            'corners': sum([d.get('corners', 0) for d in team1_data]) / 3,
            'shots_in_box': sum([d.get('shots_in_box', 0) for d in team1_data]) / 3,
            'shots_out_box': sum([d.get('shots_out_box', 0) for d in team1_data]) / 3,
            'touches_in_box': sum([d.get('touches_in_box', 0) for d in team1_data]) / 3,
            'tackle_success': sum([d.get('tackle_success', 50) for d in team1_data]) / 3,
            'duels_won': sum([d.get('duels_won', 50) for d in team1_data]) / 3,
            'clearances': sum([d.get('clearances', 0) for d in team1_data]) / 3
        }

        lines.append("\n   СРЕДНИЕ К1 за 3 матча:")
        avg_data = [
            f"{avg_team1['pos']:.1f}",
            f"{avg_team1['total_shots']:.1f}",
            f"{avg_team1['shots_on_target']:.1f}",
            f"{avg_team1['goal_scoring_chances']:.1f}",
            f"{avg_team1['corners']:.1f}",
            f"{avg_team1['shots_in_box']:.1f}",
            f"{avg_team1['shots_out_box']:.1f}",
            f"{avg_team1['touches_in_box']:.1f}",
            f"{avg_team1['tackle_success']:.1f}",
            f"{avg_team1['duels_won']:.1f}",
            f"{avg_team1['clearances']:.1f}"
        ]
        lines.append("   " + " | ".join(avg_data))

        lines.append("\n📊 ДАННЫЕ КОМАНДЫ 2 (Гостевая):")
        lines.append("   " + " | ".join(headers))
        lines.append("   " + "-" * 85)

        for i, match in enumerate(team2_data, 1):
            match_data = [
                f"М{i}",
                f"{match.get('pos', 0):.0f}",
                f"{match.get('total_shots', 0):.0f}",
                f"{match.get('shots_on_target', 0):.0f}",
                f"{match.get('goal_scoring_chances', 0):.0f}",
                f"{match.get('corners', 0):.0f}",
                f"{match.get('shots_in_box', 0):.0f}",
                f"{match.get('shots_out_box', 0):.0f}",
                f"{match.get('touches_in_box', 0):.0f}",
                f"{match.get('tackle_success', 50):.0f}",
                f"{match.get('duels_won', 50):.0f}",
                f"{match.get('clearances', 0):.0f}"
            ]
            lines.append("   " + " | ".join(match_data))

        avg_team2 = {
            'pos': sum([d.get('pos', 0) for d in team2_data]) / 3,
            'total_shots': sum([d.get('total_shots', 0) for d in team2_data]) / 3,
            'shots_on_target': sum([d.get('shots_on_target', 0) for d in team2_data]) / 3,
            'goal_scoring_chances': sum([d.get('goal_scoring_chances', 0) for d in team2_data]) / 3,
            'corners': sum([d.get('corners', 0) for d in team2_data]) / 3,
            'shots_in_box': sum([d.get('shots_in_box', 0) for d in team2_data]) / 3,
            'shots_out_box': sum([d.get('shots_out_box', 0) for d in team2_data]) / 3,
            'touches_in_box': sum([d.get('touches_in_box', 0) for d in team2_data]) / 3,
            'tackle_success': sum([d.get('tackle_success', 50) for d in team2_data]) / 3,
            'duels_won': sum([d.get('duels_won', 50) for d in team2_data]) / 3,
            'clearances': sum([d.get('clearances', 0) for d in team2_data]) / 3
        }

        lines.append("\n   СРЕДНИЕ К2 за 3 матча:")
        avg_data = [
            f"{avg_team2['pos']:.1f}",
            f"{avg_team2['total_shots']:.1f}",
            f"{avg_team2['shots_on_target']:.1f}",
            f"{avg_team2['goal_scoring_chances']:.1f}",
            f"{avg_team2['corners']:.1f}",
            f"{avg_team2['shots_in_box']:.1f}",
            f"{avg_team2['shots_out_box']:.1f}",
            f"{avg_team2['touches_in_box']:.1f}",
            f"{avg_team2['tackle_success']:.1f}",
            f"{avg_team2['duels_won']:.1f}",
            f"{avg_team2['clearances']:.1f}"
        ]
        lines.append("   " + " | ".join(avg_data))

        lines.append("\n📈 СРАВНЕНИЕ СРЕДНИХ ПОКАЗАТЕЛЕЙ:")
        lines.append("   " + "=" * 70)
        lines.append("   Показатель           К1 (Дома)   К2 (Гости)   Разница")
        lines.append("   " + "-" * 70)

        comparisons = [
            ("Владение (%)", avg_team1['pos'], avg_team2['pos']),
            ("Всего ударов", avg_team1['total_shots'], avg_team2['total_shots']),
            ("Удары в створ", avg_team1['shots_on_target'], avg_team2['shots_on_target']),
            ("Голевые моменты", avg_team1['goal_scoring_chances'], avg_team2['goal_scoring_chances']),
            ("Угловые", avg_team1['corners'], avg_team2['corners']),
            ("Уд. в штрафной", avg_team1['shots_in_box'], avg_team2['shots_in_box']),
            ("Уд. из-за штрафной", avg_team1['shots_out_box'], avg_team2['shots_out_box']),
            ("Касания в штрафной", avg_team1['touches_in_box'], avg_team2['touches_in_box']),
            ("Отборы (%)", avg_team1['tackle_success'], avg_team2['tackle_success']),
            ("Дуэли (%)", avg_team1['duels_won'], avg_team2['duels_won']),
            ("Выносы", avg_team1['clearances'], avg_team2['clearances'])
        ]

        for name, val1, val2 in comparisons:
            diff = val1 - val2
            diff_sign = "+" if diff > 0 else ""
            lines.append(f"   {name:<20} {val1:>9.1f} {val2:>12.1f} {diff_sign:>7}{diff:.1f}")

        lines.append("\n")

        return lines

    def on_calc(self):
        """Основная функция расчета с новыми метриками"""
        conf = DEFAULT_CONFIDENCE
        algorithm = self.algo_var.get()

        self.status_bar.config(text="Сбор данных с новыми метриками...", fg="#00FF66")
        self.update_idletasks()

        # Сбор данных с новыми метриками
        team1_data = self._collect_extended_table(self.team1_entries)
        team2_data = self._collect_extended_table(self.team2_entries)

        # Сбор TMPR
        self.status_bar.config(text="Обработка УСИЛЕННОГО TMPR с новыми метриками...", fg="#FFAA00")
        self.update_idletasks()

        tmpr1_str = self.tmpr1_entry.get().strip().replace(',', '.')
        tmpr2_str = self.tmpr2_entry.get().strip().replace(',', '.')

        tmpr1 = safe_float(tmpr1_str) or 300.0
        tmpr2 = safe_float(tmpr2_str) or 300.0

        tmpr1 = round(tmpr1, 1)
        tmpr2 = round(tmpr2, 1)

        tmpr1 = max(100.0, min(500.0, tmpr1))
        tmpr2 = max(100.0, min(500.0, tmpr2))

        lines = []

        self.status_bar.config(text="Анализ качества атак и обороны...", fg="#00FF66")
        self.update_idletasks()

        # Добавляем введенные данные в начало прогноза
        input_summary = self._get_input_data_summary(team1_data, team2_data)
        lines.extend(input_summary)

        lines.append("=" * 90)
        lines.append("ФУТБОЛЬНЫЙ ПРЕДИКТОР - УСИЛЕННЫЙ АНАЛИЗ С TMPR И НОВЫМИ МЕТРИКАМИ")
        lines.append("=" * 90)
        lines.append("")

        # Анализ качества ударов
        team1_quality = analyze_shot_quality(team1_data)
        team2_quality = analyze_shot_quality(team2_data)

        # Анализ оборонительного давления (новые метрики)
        team1_defense = calculate_defensive_pressure_index(team1_data)
        team2_defense = calculate_defensive_pressure_index(team2_data)

        lines.append("📊 КАЧЕСТВО АТАКИ КОМАНД:")
        lines.append(f"   К1: {team1_quality['quality_rating']} - {team1_quality['quality_description']}")
        lines.append(f"      Точность: {team1_quality['accuracy_percentage']}% | "
                     f"Уд. в створ: {team1_quality['avg_shots_on_target']:.1f} | "
                     f"Гол. моменты: {team1_quality['avg_goal_chances']:.1f}")
        lines.append(f"   К2: {team2_quality['quality_rating']} - {team2_quality['quality_description']}")
        lines.append(f"      Точность: {team2_quality['accuracy_percentage']}% | "
                     f"Уд. в створ: {team2_quality['avg_shots_on_target']:.1f} | "
                     f"Гол. моменты: {team2_quality['avg_goal_chances']:.1f}")
        lines.append("")

        lines.append("🛡️ АНАЛИЗ ОБОРОНЫ (НОВЫЕ МЕТРИКИ):")
        lines.append(f"   К1: {team1_defense['defense_quality']} - {team1_defense['defense_description']}")
        lines.append(f"      Отборы: {team1_defense['avg_tackle_success']}% | "
                     f"Дуэли: {team1_defense['avg_duels_won']}% | "
                     f"Выносы: {team1_defense['avg_clearances']:.1f}")
        lines.append(f"   К2: {team2_defense['defense_quality']} - {team2_defense['defense_description']}")
        lines.append(f"      Отборы: {team2_defense['avg_tackle_success']}% | "
                     f"Дуэли: {team2_defense['avg_duels_won']}% | "
                     f"Выносы: {team2_defense['avg_clearances']:.1f}")
        lines.append("")

        # --- ТРАДИЦИОННЫЙ АЛГОРИТМ ---
        if algorithm in ["both", "traditional"]:
            self.status_bar.config(text="Расчет традиционного алгоритма...", fg="#00FF66")
            self.update_idletasks()

            lines.append("─" * 45)
            lines.append("📈 ТРАДИЦИОННЫЙ АЛГОРИТМ (НЕЙТРАЛЬНОЕ ПОЛЕ)")
            lines.append("─" * 45)
            lines.append("   🎯 Используются ЧИСТЫЕ данные (без улучшений от новых метрик)")
            lines.append("   ⚠️  TMPR не применяется в традиционном алгоритме")
            lines.append("")

            xg1_pure = calculate_expected_goals_from_stats(team1_data, team2_data, DEFAULT_WEIGHTS, COEFFS)
            xg2_pure = calculate_expected_goals_from_stats(team2_data, team1_data, DEFAULT_WEIGHTS, COEFFS)

            xg1_trad = xg1_pure
            xg2_trad = xg2_pure

            p1g, pd, p2g = compute_result_probs(xg1_trad, xg2_trad)
            pick_match = "П1" if p1g > p2g and p1g > pd else ("П2" if p2g > p1g and p2g > pd else "Ничья/X")

            top_scores_trad = get_top_scores(xg1_trad, xg2_trad, top_n=6)
            total_totals = calculate_total_totals(xg1_trad, xg2_trad)
            indiv_totals_team1 = calculate_individual_totals(xg1_trad)
            indiv_totals_team2 = calculate_individual_totals(xg2_trad)

            team1_stats = self._prepare_lambda_data_traditional(team1_data)
            team2_stats = self._prepare_lambda_data_traditional(team2_data)
            lambda1_trad = calculate_lambda_traditional(team1_stats)
            lambda2_trad = calculate_lambda_traditional(team2_stats)

            lines.append("🎯 РЕКОМЕНДАЦИЯ ПО ИСХОДУ:")
            lines.append(f"   • {pick_match}")
            lines.append(f"   • П1: {p1g * 100:.1f}% | Ничья: {pd * 100:.1f}% | П2: {p2g * 100:.1f}%")
            lines.append("")

            lines.append("💡 ОБОСНОВАНИЕ РЕКОМЕНДАЦИИ:")
            recommendation = get_match_recommendation(p1g * 100, p2g * 100, pd * 100,
                                                      team1_quality, team2_quality,
                                                      home_advantage=False)
            lines.append(f"   {recommendation}")
            lines.append("")

            lines.append("📊 СТАТИСТИКА XG (ЧИСТЫЕ данные):")
            lines.append(f"   • Чистый xG: К1={xg1_trad:.2f} | К2={xg2_trad:.2f}")
            lines.append(f"   • Совокупный тотал: {xg1_trad + xg2_trad:.2f}")
            lines.append("   • Рассчитаны на основе владения, ударов, касаний, угловых")
            lines.append("   • БЕЗ учета ударов в створ, голевых моментов и всех новых метрик")
            lines.append("")

            lines.append("⚡ АТАКУЮЩАЯ ЭФФЕКТИВНОСТЬ (λ):")
            lines.append(f"   • К1: λ = {lambda1_trad:.3f}")
            lines.append(f"   • К2: λ = {lambda2_trad:.3f}")
            lines.append(f"   • {self._get_lambda_advantage_text(lambda1_trad, lambda2_trad)}")
            lines.append("")

            lines.append(get_match_analysis(p1g * 100, pd * 100, p2g * 100, lambda1_trad, lambda2_trad, xg1_trad,
                                            xg2_trad))
            lines.append("")

            lines.append("📊 ТОТАЛЫ ГОЛОВ:")
            for key in ['ТБ 0.5', 'ТБ 1.5', 'ТБ 2.5', 'ТБ 3.5',
                        'ТМ 0.5', 'ТМ 1.5', 'ТМ 2.5', 'ТМ 3.5']:
                if key in total_totals:
                    lines.append(f"   • {key}: {total_totals[key]:.1f}%")
            lines.append("")

            lines.append("📊 ИНДИВИДУАЛЬНЫЕ ТОТАЛЫ ГОЛОВ:")
            lines.append(
                f"   • ТБ 0.5: К1({indiv_totals_team1['ТБ 0.5']:.1f}%)  К2({indiv_totals_team2['ТБ 0.5']:.1f}%)")
            lines.append(
                f"   • ТБ 1.5: К1({indiv_totals_team1['ТБ 1.5']:.1f}%)  К2({indiv_totals_team2['ТБ 1.5']:.1f}%)")
            lines.append(
                f"   • ТБ 2.5: К1({indiv_totals_team1['ТБ 2.5']:.1f}%)  К2({indiv_totals_team2['ТБ 2.5']:.1f}%)")
            lines.append(
                f"   • ТБ 3.5: К1({indiv_totals_team1['ТБ 3.5']:.1f}%)  К2({indiv_totals_team2['ТБ 3.5']:.1f}%)")
            lines.append(
                f"   • ТМ 0.5: К1({indiv_totals_team1['ТМ 0.5']:.1f}%)  К2({indiv_totals_team2['ТМ 0.5']:.1f}%)")
            lines.append(
                f"   • ТМ 1.5: К1({indiv_totals_team1['ТМ 1.5']:.1f}%)  К2({indiv_totals_team2['ТМ 1.5']:.1f}%)")
            lines.append(
                f"   • ТМ 2.5: К1({indiv_totals_team1['ТМ 2.5']:.1f}%)  К2({indiv_totals_team2['ТМ 2.5']:.1f}%)")
            lines.append(
                f"   • ТМ 3.5: К1({indiv_totals_team1['ТМ 3.5']:.1f}%)  К2({indiv_totals_team2['ТМ 3.5']:.1f}%)")
            lines.append("")

            p0_1 = poisson_pmf(0, xg1_trad)
            p0_2 = poisson_pmf(0, xg2_trad)
            btts_prob = max(0.0, 1.0 - p0_1 - p0_2 + p0_1 * p0_2) * 100

            lines.append(f"⚽ ОБА ЗАБЬЮТ (BTTS): {btts_prob:.1f}% → "
                         f"{'Да' if btts_prob >= conf else 'Нет'}")
            lines.append("")

            lines.append("🎯 ПРОГНОЗ ТОЧНОГО СЧЕТА:")
            lines.append("   Топ-6 наиболее вероятных счетов:")
            for i, ((h, a), prob) in enumerate(top_scores_trad, 1):
                lines.append(f"   {i}. {h}:{a} - {prob:.2f}%")
            lines.append("")

            lines.append("💡 РЕКОМЕНДАЦИЯ ПО ТОЧНОМУ СЧЕТУ:")
            exact_recommendation = self._get_exact_score_recommendation(top_scores_trad)
            for line in exact_recommendation.split('\n'):
                lines.append(f"   {line}")
            lines.append("")

            corners_analysis_trad = get_detailed_corners_analysis(
                team1_data, team2_data, is_home_team1=True, confidence_level=conf
            )
            corners_lines_trad = format_corners_analysis_for_display(corners_analysis_trad)
            lines.extend(corners_lines_trad)
            lines.append("")

        # --- λ-АЛГОРИТМ С УСИЛЕННЫМ TMPR И НОВЫМИ МЕТРИКАМИ ---
        if algorithm in ["both", "lambda"]:
            self.status_bar.config(text="Расчет λ-алгоритма с УСИЛЕННЫМ TMPR и новыми метриками...", fg="#FFAA00")
            self.update_idletasks()

            lines.append("─" * 45)
            lines.append("🔬 λ-АЛГОРИТМ (С ДОМАШНИМ ПРЕИМУЩЕСТВОМ И НОВЫМИ МЕТРИКАМИ)")
            lines.append("─" * 45)
            lines.append("   🏠 К1: домашняя (+0.22 xG) | 🏃 К2: гостевая (-0.12 xG)")
            lines.append("   🎯 Используются УЛУЧШЕННЫЕ данные (с новыми метриками)")
            lines.append("   🛡️  НОВЫЕ МЕТРИКИ: Отборы %, Дуэли, Выносы")
            lines.append(f"   🏆 УСИЛЕННЫЙ TMPR: К1={tmpr1:.1f}, К2={tmpr2:.1f} (разница: {tmpr1 - tmpr2:+.1f})")
            lines.append("")

            team1_lambda_data = self._prepare_lambda_data(team1_data)
            team2_lambda_data = self._prepare_lambda_data(team2_data)

            self.status_bar.config(text="Применение УСИЛЕННОГО TMPR с новыми метриками...", fg="#FFAA00")
            self.update_idletasks()

            lambda_prediction = predict_match_lambda_with_tmpr(
                team1_lambda_data, team2_lambda_data, tmpr1, tmpr2
            )

            # Добавляем УСИЛЕННЫЙ анализ TMPR
            tmpr_analysis = format_tmpr_analysis(
                tmpr1, tmpr2,
                lambda_prediction['tmpr_effects']['team1_lambda'],
                lambda_prediction['tmpr_effects']['team2_lambda'],
                lambda_prediction['tmpr_effects']['team1_xg'],
                lambda_prediction['tmpr_effects']['team2_xg']
            )
            lines.extend(tmpr_analysis)
            lines.append("")

            xg1_final = lambda_prediction['expected_goals']['final'][0]
            xg2_final = lambda_prediction['expected_goals']['final'][1]

            p1g_lambda, pd_lambda, p2g_lambda = compute_result_probs(xg1_final, xg2_final)

            if p1g_lambda > p2g_lambda and p1g_lambda > pd_lambda:
                lambda_recommended = 'П1'
            elif p2g_lambda > p1g_lambda and p2g_lambda > pd_lambda:
                lambda_recommended = 'П2'
            else:
                lambda_recommended = 'Ничья/X'

            total_totals_lambda = calculate_total_totals(xg1_final, xg2_final)
            indiv_totals_team1_lambda = calculate_individual_totals(xg1_final)
            indiv_totals_team2_lambda = calculate_individual_totals(xg2_final)

            lines.append("🎯 РЕКОМЕНДАЦИЯ ПО ИСХОДУ:")
            lines.append(f"   • {lambda_recommended} (с учетом УСИЛЕННОГО TMPR и новых метрик)")
            lines.append(
                f"   • П1: {p1g_lambda * 100:.1f}% | Ничья: {pd_lambda * 100:.1f}% | П2: {p2g_lambda * 100:.1f}%")
            lines.append("")

            lines.append("💡 ОБОСНОВАНИЕ РЕКОМЕНДАЦИИ (с учетом новых метрик):")
            lambda_recommendation = get_match_recommendation(p1g_lambda * 100, p2g_lambda * 100, pd_lambda * 100,
                                                             team1_quality, team2_quality,
                                                             home_advantage=True)

            # Добавляем оборонительный анализ
            defense_analysis = []
            if team1_defense['defense_quality'] != team2_defense['defense_quality']:
                if "ЭЛИТНАЯ" in team1_defense['defense_quality']:
                    defense_analysis.append("🛡️ К1 имеет ЭЛИТНУЮ оборону")
                elif "КРИЗИС" in team2_defense['defense_quality']:
                    defense_analysis.append("⚠️ К2 в КРИЗИСЕ обороны")

            if defense_analysis:
                lines.append(f"   {lambda_recommendation} | {' | '.join(defense_analysis)}")
            else:
                lines.append(f"   {lambda_recommendation}")
            lines.append("")

            lines.append("⚡ АТАКУЮЩАЯ ЭФФЕКТИВНОСТЬ (λ с УСИЛЕННЫМ TMPR):")
            lines.append(f"   • К1: λ = {lambda_prediction['lambdas']['tmpr_enhanced'][0]:.3f} "
                         f"(raw: {lambda_prediction['lambdas']['raw'][0]:.3f})")
            lines.append(f"   • К2: λ = {lambda_prediction['lambdas']['tmpr_enhanced'][1]:.3f} "
                         f"(raw: {lambda_prediction['lambdas']['raw'][1]:.3f})")
            lines.append(
                f"   • {self._get_lambda_advantage_text(lambda_prediction['lambdas']['tmpr_enhanced'][0], lambda_prediction['lambdas']['tmpr_enhanced'][1])}")
            lines.append("")

            lines.append("📊 СТАТИСТИКА XG (с УСИЛЕННЫМ TMPR и новыми метриками):")
            lines.append(f"   • λ-базовый: К1={lambda_prediction['expected_goals']['raw'][0]:.2f} | "
                         f"К2={lambda_prediction['expected_goals']['raw'][1]:.2f}")
            lines.append(f"   • TMPR прямой: К1={lambda_prediction['expected_goals']['tmpr_direct'][0]:.2f} | "
                         f"К2={lambda_prediction['expected_goals']['tmpr_direct'][1]:.2f}")
            lines.append(f"   • Комбинированный: К1={lambda_prediction['expected_goals']['combined'][0]:.2f} | "
                         f"К2={lambda_prediction['expected_goals']['combined'][1]:.2f}")
            lines.append(f"   • ФИНАЛЬНЫЙ (с новыми метриками): К1={xg1_final:.2f} | К2={xg2_final:.2f}")
            lines.append("   • Эффект поля: К1(+0.22) | К2(-0.12)")
            lines.append("   • Улучшения от новых метрик: ВКЛЮЧЕНО")
            lines.append("   • УСИЛЕННЫЙ TMPR влияние: ВКЛЮЧЕНО")
            lines.append("")

            lines.append(get_match_analysis(p1g_lambda * 100, pd_lambda * 100, p2g_lambda * 100,
                                            lambda_prediction['lambdas']['tmpr_enhanced'][0],
                                            lambda_prediction['lambdas']['tmpr_enhanced'][1],
                                            xg1_final, xg2_final))
            lines.append("")

            lines.append("📊 ТОТАЛЫ ГОЛОВ:")
            for key in ['ТБ 0.5', 'ТБ 1.5', 'ТБ 2.5', 'ТБ 3.5',
                        'ТМ 0.5', 'ТМ 1.5', 'ТМ 2.5', 'ТМ 3.5']:
                if key in total_totals_lambda:
                    lines.append(f"   • {key}: {total_totals_lambda[key]:.1f}%")
            lines.append("")

            lines.append("📊 ИНДИВИДУАЛЬНЫЕ ТОТАЛЫ ГОЛОВ:")
            lines.append(
                f"   • ТБ 0.5: К1({indiv_totals_team1_lambda['ТБ 0.5']:.1f}%)  К2({indiv_totals_team2_lambda['ТБ 0.5']:.1f}%)")
            lines.append(
                f"   • ТБ 1.5: К1({indiv_totals_team1_lambda['ТБ 1.5']:.1f}%)  К2({indiv_totals_team2_lambda['ТБ 1.5']:.1f}%)")
            lines.append(
                f"   • ТБ 2.5: К1({indiv_totals_team1_lambda['ТБ 2.5']:.1f}%)  К2({indiv_totals_team2_lambda['ТБ 2.5']:.1f}%)")
            lines.append(
                f"   • ТБ 3.5: К1({indiv_totals_team1_lambda['ТБ 3.5']:.1f}%)  К2({indiv_totals_team2_lambda['ТБ 3.5']:.1f}%)")
            lines.append(
                f"   • ТМ 0.5: К1({indiv_totals_team1_lambda['ТМ 0.5']:.1f}%)  К2({indiv_totals_team2_lambda['ТМ 0.5']:.1f}%)")
            lines.append(
                f"   • ТМ 1.5: К1({indiv_totals_team1_lambda['ТМ 1.5']:.1f}%)  К2({indiv_totals_team2_lambda['ТМ 1.5']:.1f}%)")
            lines.append(
                f"   • ТМ 2.5: К1({indiv_totals_team1_lambda['ТМ 2.5']:.1f}%)  К2({indiv_totals_team2_lambda['ТМ 2.5']:.1f}%)")
            lines.append(
                f"   • ТМ 3.5: К1({indiv_totals_team1_lambda['ТМ 3.5']:.1f}%)  К2({indiv_totals_team2_lambda['ТМ 3.5']:.1f}%)")
            lines.append("")

            p0_1_lambda = poisson_pmf(0, xg1_final)
            p0_2_lambda = poisson_pmf(0, xg2_final)
            btts_prob_lambda = max(0.0, 1.0 - p0_1_lambda - p0_2_lambda + p0_1_lambda * p0_2_lambda) * 100

            lines.append(f"⚽ ОБА ЗАБЬЮТ (BTTS): {btts_prob_lambda:.1f}% → "
                         f"{'Да' if btts_prob_lambda >= conf else 'Нет'}")
            lines.append("")

            top_scores_lambda = lambda_prediction['top_scores']

            lines.append("🎯 ПРОГНОЗ ТОЧНОГО СЧЕТА:")
            lines.append("   Топ-6 наиболее вероятных счетов:")
            for i, ((h, a), prob) in enumerate(top_scores_lambda, 1):
                lines.append(f"   {i}. {h}:{a} - {prob:.2f}%")
            lines.append("")

            lines.append("💡 РЕКОМЕНДАЦИЯ ПО ТОЧНОМУ СЧЕТУ:")
            lambda_exact_recommendation = self._get_exact_score_recommendation(top_scores_lambda)
            for line in lambda_exact_recommendation.split('\n'):
                lines.append(f"   {line}")
            lines.append("")

            corners_analysis_lambda = get_detailed_corners_analysis(
                team1_data, team2_data, is_home_team1=True, confidence_level=conf
            )
            corners_lines_lambda = format_corners_analysis_for_display(corners_analysis_lambda)
            lines.extend(corners_lines_lambda)
            lines.append("")

        # --- СРАВНЕНИЕ АЛГОРИТМОВ ---
        if algorithm == "both":
            self.status_bar.config(text="Сравнение алгоритмов...", fg="#00FF66")
            self.update_idletasks()

            lines.append("=" * 90)
            lines.append("🎭 СРАВНЕНИЕ АЛГОРИТМОВ (С НОВЫМИ МЕТРИКАМИ)")
            lines.append("=" * 90)

            trad_pick = "П1" if p1g > p2g and p1g > pd else ("П2" if p2g > p1g and p2g > pd else "Ничья/X")
            lambda_pick = lambda_recommended

            lines.append("📊 СОВПАДЕНИЕ РЕКОМЕНДАЦИЙ:")
            if trad_pick == lambda_pick:
                lines.append(f"✅ ОБА алгоритма рекомендуют: {trad_pick}")
                lines.append(
                    f"   • Традиционный (чистые данные): П1={p1g * 100:.1f}% | Н={pd * 100:.1f}% | П2={p2g * 100:.1f}%")
                lines.append(
                    f"   • λ+УСИЛЕННЫЙ TMPR: П1={p1g_lambda * 100:.1f}% | Н={pd_lambda * 100:.1f}% | П2={p2g_lambda * 100:.1f}%")
            else:
                lines.append(f"⚠️  РАЗНЫЕ рекомендации:")
                lines.append(f"   • Традиционный (без TMPR): {trad_pick} ({max(p1g, pd, p2g) * 100:.1f}%)")
                lines.append(
                    f"   • λ-алгоритм (с УСИЛЕННЫМ TMPR): {lambda_pick} ({max(p1g_lambda, pd_lambda, p2g_lambda) * 100:.1f}%)")

            lines.append("")
            lines.append("📈 СРАВНЕНИЕ XG:")
            lines.append(
                f"   • Традиционный (чистые): К1={xg1_trad:.2f} | К2={xg2_trad:.2f} | Всего={xg1_trad + xg2_trad:.2f}")
            lines.append(
                f"   • λ+УСИЛЕННЫЙ TMPR: К1={xg1_final:.2f} | К2={xg2_final:.2f} | Всего={xg1_final + xg2_final:.2f}")
            lines.append(
                f"   • Влияние TMPR и новых метрик: К1={xg1_final - xg1_trad:+.2f} | К2={xg2_final - xg2_trad:+.2f}")
            lines.append("")

            lines.append("💡 АНАЛИЗ ВЛИЯНИЯ НОВЫХ МЕТРИК:")
            if abs(team1_defense['pressure_index'] - team2_defense['pressure_index']) > 8:
                lines.append("   🔬 Новые метрики показали ЗНАЧИТЕЛЬНУЮ разницу в оборонительном качестве")
                if team1_defense['pressure_index'] < team2_defense['pressure_index']:
                    lines.append(
                        f"   🛡️ К1 имеет лучше оборону на {team2_defense['pressure_index'] - team1_defense['pressure_index']:.1f} баллов")
                else:
                    lines.append(
                        f"   🛡️ К2 имеет лучше оборону на {team1_defense['pressure_index'] - team2_defense['pressure_index']:.1f} баллов")
            else:
                lines.append("   📊 Новые метрики показали схожее оборонительное качество команд")
            lines.append("")

            lines.append("💡 ОБОСНОВАНИЕ ИТОГОВОЙ РЕКОМЕНДАЦИИ:")

            lines.append("")
            lines.append("🏆 ИТОГОВАЯ РЕКОМЕНДАЦИЯ:")

            if trad_pick == lambda_pick:
                if trad_pick == "П1":
                    lines.append(
                        f"   ✅ П1 - {get_final_recommendation_text(trad_pick, p1g * 100, team1_quality, team2_quality, True)}")
                    lines.append(f"   🎯 Основано на совпадении обоих алгоритмов")
                elif trad_pick == "П2":
                    lines.append(
                        f"   ✅ П2 - {get_final_recommendation_text(trad_pick, p2g * 100, team1_quality, team2_quality, False)}")
                    lines.append(f"   🎯 Основано на совпадении обоих алгоритмов")
                else:
                    lines.append(
                        f"   ✅ Ничья - {get_final_recommendation_text('Ничья', pd * 100, team1_quality, team2_quality, False)}")
                    lines.append(f"   🎯 Основано на совпадении обоих алгоритмов")
            else:
                trad_confidence = max(p1g, pd, p2g)
                lambda_confidence = max(p1g_lambda, pd_lambda, p2g_lambda)

                tmpr_diff = abs(tmpr1 - tmpr2)
                defense_diff = abs(team1_defense['pressure_index'] - team2_defense['pressure_index'])

                # Критерии выбора между алгоритмами
                if tmpr_diff > 80 or defense_diff > 10:
                    # Сильное влияние TMPR или значительная разница в обороне
                    lines.append(f"   🔬 Предпочтение λ+УСИЛЕННЫЙ TMPR (сильное влияние новых метрик)")
                    if lambda_pick == "П1":
                        lines.append(
                            f"   📈 П1 - {get_final_recommendation_text(lambda_pick, p1g_lambda * 100, team1_quality, team2_quality, True)}")
                    elif lambda_pick == "П2":
                        lines.append(
                            f"   📈 П2 - {get_final_recommendation_text(lambda_pick, p2g_lambda * 100, team1_quality, team2_quality, False)}")
                    else:
                        lines.append(
                            f"   📈 Ничья - {get_final_recommendation_text('Ничья', pd_lambda * 100, team1_quality, team2_quality, False)}")
                elif lambda_confidence > trad_confidence:
                    lines.append(
                        f"   🔬 Предпочтение λ+TMPR алгоритму (выше уверенность: {lambda_confidence * 100:.1f}% vs {trad_confidence * 100:.1f}%)")
                    if lambda_pick == "П1":
                        lines.append(
                            f"   📈 П1 - {get_final_recommendation_text(lambda_pick, p1g_lambda * 100, team1_quality, team2_quality, True)}")
                    elif lambda_pick == "П2":
                        lines.append(
                            f"   📈 П2 - {get_final_recommendation_text(lambda_pick, p2g_lambda * 100, team1_quality, team2_quality, False)}")
                    else:
                        lines.append(
                            f"   📈 Ничья - {get_final_recommendation_text('Ничья', pd_lambda * 100, team1_quality, team2_quality, False)}")
                else:
                    lines.append(
                        f"   🔬 Предпочтение традиционному алгоритму (выше уверенность: {trad_confidence * 100:.1f}% vs {lambda_confidence * 100:.1f}%)")
                    if trad_pick == "П1":
                        lines.append(
                            f"   📈 П1 - {get_final_recommendation_text(trad_pick, p1g * 100, team1_quality, team2_quality, False)}")
                    elif trad_pick == "П2":
                        lines.append(
                            f"   📈 П2 - {get_final_recommendation_text(trad_pick, p2g * 100, team1_quality, team2_quality, False)}")
                    else:
                        lines.append(
                            f"   📈 Ничья - {get_final_recommendation_text('Ничья', pd * 100, team1_quality, team2_quality, False)}")

        elif algorithm == "traditional":
            lines.append("=" * 90)
            lines.append("✅ ИТОГОВАЯ РЕКОМЕНДАЦИЯ (ТРАДИЦИОННЫЙ - БЕЗ TMPR И НОВЫХ МЕТРИК)")
            lines.append("=" * 90)
            if pick_match == "П1":
                lines.append(
                    f"🎯 П1 - {get_final_recommendation_text('П1', p1g * 100, team1_quality, team2_quality, False)}")
            elif pick_match == "П2":
                lines.append(
                    f"🎯 П2 - {get_final_recommendation_text('П2', p2g * 100, team1_quality, team2_quality, False)}")
            else:
                lines.append(
                    f"🎯 Ничья - {get_final_recommendation_text('Ничья', pd * 100, team1_quality, team2_quality, False)}")

        elif algorithm == "lambda":
            lines.append("=" * 90)
            lines.append("✅ ИТОГОВАЯ РЕКОМЕНДАЦИЯ (λ-АЛГОРИТМ С УСИЛЕННЫМ TMPR И НОВЫМИ МЕТРИКАМИ)")
            lines.append("=" * 90)
            if lambda_recommended == "П1":
                lines.append(
                    f"🎯 П1 - {get_final_recommendation_text('П1', p1g_lambda * 100, team1_quality, team2_quality, True)}")
            elif lambda_recommended == "П2":
                lines.append(
                    f"🎯 П2 - {get_final_recommendation_text('П2', p2g_lambda * 100, team1_quality, team2_quality, False)}")
            else:
                lines.append(
                    f"🎯 Ничья - {get_final_recommendation_text('Ничья', pd_lambda * 100, team1_quality, team2_quality, False)}")

        lines.append(f"\n📅 Анализ выполнен: {time.strftime('%d.%m.%Y %H:%M:%S')}")
        lines.append(f"🏆 TMPR значения: К1={tmpr1:.1f}, К2={tmpr2:.1f} (разница: {tmpr1 - tmpr2:+.1f})")
        lines.append(
            f"🛡️ Индексы оборонительного давления: К1={team1_defense['pressure_index']:.1f}, К2={team2_defense['pressure_index']:.1f}")

        out_text = "\n".join(lines)
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", out_text)
        self.output.configure(state="disabled")

        self.status_bar.config(text="✅ Расчет завершен! УСИЛЕННЫЙ TMPR и новые метрики применены.", fg="#00FF66")

    def on_reset(self):
        """Сброс всех полей ввода"""
        for row in self.team1_entries + self.team2_entries:
            for k, v in row.items():
                try:
                    v.delete(0, 'end')
                except Exception:
                    pass

        # Сброс TMPR полей
        self.tmpr1_entry.delete(0, 'end')
        self.tmpr1_entry.insert(0, "300.0")
        self.tmpr2_entry.delete(0, 'end')
        self.tmpr2_entry.insert(0, "300.0")

        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")
        self.status_bar.config(text="Готов к работе...", fg="#888888")

    def on_save(self):
        """Сохранение результатов анализа"""
        output_text = self.output.get("1.0", "end").strip()

        if not output_text:
            messagebox.showwarning("Пусто", "Нет данных для сохранения. Нажмите 'Рассчитать'.")
            return

        full_text = output_text

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        try:
            os.makedirs(desktop, exist_ok=True)
        except Exception:
            desktop = os.path.expanduser("~")

        fname = f"Прогноз_матча_TMPR_НОВЫЕ_МЕТРИКИ_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        path = filedialog.asksaveasfilename(
            initialfile=os.path.join(desktop, fname),
            defaultextension=".txt",
            filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")],
            title="Сохранить отчет анализа"
        )

        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(full_text)
            messagebox.showinfo("Сохранено", f"Отчет успешно сохранен:\n{path}")
            self.status_bar.config(text=f"✅ Отчет сохранен: {os.path.basename(path)}", fg="#00FF66")
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить файл:\n{str(e)}")
            self.status_bar.config(text="❌ Ошибка сохранения", fg="#FF3333")


if __name__ == "__main__":
    app = UltraCompactPredictor()
    app.mainloop()