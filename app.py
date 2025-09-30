# -*- coding: utf-8 -*-
# app.py - Kakao Fishing RPG (single file)
from __future__ import annotations

import re
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

from flask import Flask, request, jsonify

# ───────────────────────────────────────────────────────────────────────────────
# Timezone
# ───────────────────────────────────────────────────────────────────────────────
KST = timezone(timedelta(hours=9))
CHEMI_NIGHT_START = 20  # 20:00
CHEMI_NIGHT_END = 5     # 05:00

def now_kst() -> datetime:
    return datetime.now(KST)

def is_chemilight_time(dt: datetime) -> bool:
    h = dt.hour
    # 20:00~23:59 or 00:00~04:59
    return (h >= CHEMI_NIGHT_START) or (h < CHEMI_NIGHT_END)

# ───────────────────────────────────────────────────────────────────────────────
# Kakao helpers
# ───────────────────────────────────────────────────────────────────────────────
class KakaoResp:
    @staticmethod
    def text(msg: str) -> Dict[str, Any]:
        return {
            "version": "2.0",
            "template": {
                "outputs": [
                    {"simpleText": {"text": msg}}
                ]
            }
        }

# ───────────────────────────────────────────────────────────────────────────────
# Game core
# ───────────────────────────────────────────────────────────────────────────────
MAX_SLOTS = 5

# 상점 단가 (되팔기 50%는 confirm 후 처리)
UNIT_PRICE: Dict[str, int] = {
    "지렁이": 10,
    "떡밥": 10,
    "집어제": 500,
    "케미라이트1등급": 600,  # 최상급
    "케미라이트2등급": 350,
    "케미라이트3등급": 200,
    # 낚싯대
    "철제 낚싯대": 1000,
    "강화 낚싯대": 5000,
    "프로 낚싯대": 20000,
    "레전드 낚싯대": 100000,
}
CONSUMABLE_KEYS: List[str] = [
    "지렁이", "떡밥", "집어제",
    "케미라이트1등급", "케미라이트2등급", "케미라이트3등급"
]
FRESH_FISH = {
    "민물": ["붕어", "잉어", "송어"],
    "바다": ["농어", "전갱이", "우럭"],
}

def next_exp_for_level(lv: int) -> int:
    # 100 + 50*(lv-1)
    return 100 + 50 * max(0, lv - 1)

def clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))

def parse_qty(text: str) -> int:
    """
    '10개', '10장', '10' 등에서 숫자만 추출. 없으면 1 반환
    """
    m = re.search(r'(\d+)', text)
    return int(m.group(1)) if m else 1

# ───────────────────────────────────────────────────────────────────────────────
# State store (in-memory)
# ───────────────────────────────────────────────────────────────────────────────
class MemoryStore:
    def __init__(self):
        self.users: Dict[str, Dict[str, Any]] = {}

    def _ensure(self, uid: str) -> Dict[str, Any]:
        if uid not in self.users:
            self.users[uid] = {
                "nick": None,
                "nick_locked": False,
                "title": "낚린이",
                "lv": 1,
                "exp": 0,
                "gold": 120,
                "limit_gold": 150,  # 출석 등으로 쌓이는 제한골드
                "rod": "대나무 낚싯대",
                "place": "민물",
                "bag": {
                    "fish": [],  # [{"name","cm","grade"}]
                    "consumables": {k: 0 for k in CONSUMABLE_KEYS},  # 종류별 수량
                },
                "effects": {
                    "chemi": None,        # "케미라이트1등급" | "…2등급" | "…3등급"
                    "additive_uses": 0,   # 집어제 효과 남은 횟수 (3회 지속)
                },
                "fishing": {
                    "active": False,
                    "cast_at": None,
                    "duration": 0,  # seconds
                },
                "beginner_used": 0,      # 초보자찬스 (1일 3회 가정: 단순 카운팅)
                "attended_today": False,
                "pending_sale": None,    # {"name":str,"qty":int} or {"rod":str}
            }
        return self.users[uid]

    def load_user(self, uid: str) -> Dict[str, Any]:
        return self._ensure(uid)

    def save_user(self, uid: str, data: Dict[str, Any]) -> None:
        self.users[uid] = data

# ───────────────────────────────────────────────────────────────────────────────
# Game logic
# ───────────────────────────────────────────────────────────────────────────────
class FishingGame:
    def __init__(self, store: MemoryStore):
        self.store = store

    # ── 슬롯 계산: 물고기 개수 + 소모품 "종류" 보유(>0) 수 ─────────────────
    def calc_used_slots(self, u: Dict[str, Any]) -> int:
        used = len(u["bag"]["fish"])
        used += sum(1 for k, v in u["bag"]["consumables"].items() if v > 0)
        return used

    # ── 홈( / ) : 통합 UI ─────────────────────────────────────────────────
    def cmd_home(self, uid: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)

        if not u.get("nick_locked"):
            return KakaoResp.text(
                "처음 오셨네요! 닉네임을 설정해 주세요. (닉네임은 이후 변경 불가)\n"
                "예) /닉네임 낚시왕"
            )

        # [사용법 3줄]
        guide = (
            "🎣 낚시 RPG 사용법\n"
            "1) /장소 [바다|민물]   ← 먼저 장소를 설정하세요\n"
            "2) /낚시 [1~60]s      ← 해당 초 만큼 캐스팅 (예: /낚시 15s)\n"
            "3) 시간이 끝나면 /릴감기 로 결과 확인"
        )

        # [상점 이용 방법] + 공지
        shop_help = (
            "🏪 상점 이용 방법\n"
            "/상점               → 상점 목록 보기\n"
            "/구매 [이름] [갯수] → 예) /구매 지렁이 10개\n"
            "/아이템판매 [이름] [갯수]\n"
            "/전부판매"
        )

        extra_help = (
            "/출석               → 출석 보상 받기\n"
            "/초보자찬스         → 낚린이 전용 보너스(1일 3회)"
        )

        # [상태]
        status_lines = []
        status_lines.append(f"닉네임: {u['nick']}")
        status_lines.append(f"[상태] {u['title']} | Lv.{u['lv']}  Exp:{u['exp']}/{next_exp_for_level(u['lv'])}")
        status_lines.append(f"Gold:💰{u['gold']} | 제한골드:💰{u['limit_gold']}")
        status_lines.append(f"장소: {u['place']} | 장착 낚시대: {u['rod']}")
        if u["effects"]["additive_uses"] > 0:
            status_lines.append(f"집어제 효과 남은 횟수: {u['effects']['additive_uses']}회")
        status_text = "\n".join(status_lines)

        # [가방]
        lines = []
        used = self.calc_used_slots(u)
        lines.append("[가방]")
        lines.append(f"{used}/{MAX_SLOTS}칸 사용중")

        # 인벤토리 표현: 물고기 → 소모품(종류) 순으로 1~5
        entries: List[str] = []
        # 물고기
        for f in u["bag"]["fish"]:
            entries.append(f"{f['name']} {f['cm']}cm ({f['grade']})")
        # 소모품(종류당 1칸, 수량 표시 & 사용법은 보유시에만 노출)
        for key in CONSUMABLE_KEYS:
            cnt = u["bag"]["consumables"][key]
            if cnt > 0:
                if key == "집어제":
                    entries.append(f"{key} ({cnt}개) - 소모품 · 사용: /집어제사용 (3회 지속)")
                elif key.startswith("케미라이트"):
                    entries.append(f"{key} ({cnt}개) - 소모품 · 사용: /{key} 사용 (1회성 · 20:00~05:00)")
                else:
                    entries.append(f"{key} ({cnt}개) - 소모품")

        # 1~5 줄
        for i in range(MAX_SLOTS):
            if i < len(entries):
                lines.append(f"{i+1}. {entries[i]}")
            else:
                lines.append(f"{i+1}. 비어있음")

        # 미보유 소모품 목록
        lack = [k for k in CONSUMABLE_KEYS if u["bag"]["consumables"][k] <= 0]
        lines.append("")
        lines.append("보유하지 않은 물품: " + (", ".join(lack) if lack else "없음"))
        bag_text = "\n".join(lines)

        # [출석]
        if u["attended_today"]:
            attend_text = "[출석]\n오늘은 이미 출석하셨습니다. (기준: 서울 00:00)"
        else:
            attend_text = "[출석]\n오늘 출석을 아직 하지 않으셨습니다.\n✅ `/출석` 입력하면 보상 골드를 받을 수 있습니다."

        # [낚시 상태]
        fish_text = "[낚시 상태]"
        if u["fishing"]["active"]:
            cast_at = u["fishing"]["cast_at"]
            dur = u["fishing"]["duration"]
            remain = max(0, int((cast_at + timedelta(seconds=dur) - now_kst()).total_seconds()))
            fish_text += f"\n⏳ {u['place']}에서 낚시중 (남은 시간: {remain}초)"
        else:
            fish_text += "\n🎣 현재 낚시중이 아닙니다.\n예) `/장소 민물` → `/낚시 15s` → 시간이 지나면 `/릴감기`"

        # 초보자찬스 현황(낚린이일 때만 표기)
        if u["title"] == "낚린이":
            extra_help += f"\n(오늘 사용: {u['beginner_used']}회, 남은 횟수: {max(0, 3 - u['beginner_used'])}회)"

        ui = f"{guide}\n\n{shop_help}\n\n{extra_help}\n\n{status_text}\n\n{bag_text}\n\n{attend_text}\n\n{fish_text}"
        return KakaoResp.text(ui)

    # ── 닉네임 ─────────────────────────────────────────────────────────────
    def set_nick(self, uid: str, name: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        if u["nick_locked"]:
            return KakaoResp.text("닉네임은 이미 설정되어 변경할 수 없습니다.")
        name = name.strip()
        if not name:
            return KakaoResp.text("닉네임을 입력해 주세요. 예) /닉네임 낚시왕")
        u["nick"] = name
        u["nick_locked"] = True
        self.store.save_user(uid, u)
        return KakaoResp.text(f"닉네임이 '{name}'(으)로 설정되었습니다. 이제 '/'를 입력해 홈 화면을 보세요!")

    # ── 장소 설정 ─────────────────────────────────────────────────────────
    def set_place(self, uid: str, place: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        if place not in ["바다", "민물"]:
            return KakaoResp.text("장소는 바다 또는 민물만 가능합니다. 예) /장소 민물")
        u["place"] = place
        self.store.save_user(uid, u)
        need = "지렁이" if place == "바다" else "떡밥"
        return KakaoResp.text(f"장소를 {place}(으)로 설정했어요.\n이제 `/낚시 [1~60]s` 으로 시작하세요! (소모품: {need})")

    # ── 상점 UI ───────────────────────────────────────────────────────────
    def shop(self, uid: str) -> Dict[str, Any]:
        txt = (
            "🏪 상점\n\n"
            "[소모품]\n"
            f"- 지렁이 (1개)          | 💰{UNIT_PRICE['지렁이']}   ← 제한골드 사용 가능\n"
            f"- 떡밥 (1개)            | 💰{UNIT_PRICE['떡밥']}   ← 제한골드 사용 가능\n"
            f"- 집어제 (1개)          | 💰{UNIT_PRICE['집어제']}  ※ 사용 시 3회 지속\n"
            f"- 케미라이트3등급 (1개) | 💰{UNIT_PRICE['케미라이트3등급']}  ※ 사용 1회성, 20:00~05:00\n"
            f"- 케미라이트2등급 (1개) | 💰{UNIT_PRICE['케미라이트2등급']}  ※ 사용 1회성, 20:00~05:00\n"
            f"- 케미라이트1등급 (1개) | 💰{UNIT_PRICE['케미라이트1등급']}  ※ 사용 1회성, 20:00~05:00\n\n"
            "[장비]\n"
            f"- 철제 낚싯대           | 💰{UNIT_PRICE['철제 낚싯대']}\n"
            f"- 강화 낚싯대           | 💰{UNIT_PRICE['강화 낚싯대']}\n"
            f"- 프로 낚싯대           | 💰{UNIT_PRICE['프로 낚싯대']}\n"
            f"- 레전드 낚싯대        | 💰{UNIT_PRICE['레전드 낚싯대']}\n"
            "\n────────────────────────\n"
            "구매 방법: /구매 [이름] [갯수]\n"
            "예) /구매 지렁이 10개\n"
            "되팔기: /아이템판매 [이름] [수량] (구매가의 50% 환불)\n"
            "정책: 제한골드는 지렁이/떡밥만 가능, 케미라이트는 20:00~05:00에만 사용\n"
            "      집어제는 3회 지속, 케미라이트는 1회성"
        )
        return KakaoResp.text(txt)

    # ── 구매 (이름/수량) ──────────────────────────────────────────────────
    def buy(self, uid: str, name: str, qty: int) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        name = name.strip()
        if name not in UNIT_PRICE:
            return KakaoResp.text("상점에 없는 물품입니다. /상점 으로 목록을 확인하세요.")

        if qty <= 0:
            qty = 1

        unit = UNIT_PRICE[name]
        total = unit * qty

        # 제한골드: 지렁이/떡밥만
        use_restrict_first = name in ["지렁이", "떡밥"]
        rg = u["limit_gold"]
        g = u["gold"]

        # 가방 슬롯 시뮬레이션: 새 종류 첫 소지 → 슬롯 1 증가
        will_add_new_kind = False
        if name in CONSUMABLE_KEYS and u["bag"]["consumables"][name] == 0:
            will_add_new_kind = True
        used_before = self.calc_used_slots(u)
        used_after = used_before + (1 if will_add_new_kind else 0)
        if name in CONSUMABLE_KEYS and used_after > MAX_SLOTS:
            return KakaoResp.text(f"가방이 부족해요. (구매 후 {used_after}/{MAX_SLOTS}칸)")

        # 결제
        if use_restrict_first:
            use_rg = min(total, rg)
            remain = total - use_rg
            if remain > g:
                return KakaoResp.text(
                    f"⚠ 골드가 부족합니다.\n"
                    f"필요: 💰{total} / 보유: 💰{g} | 제한골드: 💰{rg}"
                )
            u["limit_gold"] -= use_rg
            u["gold"] -= remain
        else:
            if total > g:
                return KakaoResp.text(
                    f"⚠ 골드가 부족합니다.\n"
                    f"필요: 💰{total} / 보유: 💰{g}"
                )
            u["gold"] -= total

        # 인벤토리 반영
        if name in CONSUMABLE_KEYS:
            u["bag"]["consumables"][name] += qty
        else:
            # 장비 구매: 즉시 장착(단순화)
            u["rod"] = name

        self.store.save_user(uid, u)
        return KakaoResp.text(f"{name}({qty}개)를 구매했어요.\n잔액 일반 💰{u['gold']} | 제한 💰{u['limit_gold']}")

    # ── 되팔기(confirm 흐름) ───────────────────────────────────────────────
    def sell_item_prepare(self, uid: str, name: str, qty: int) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        name = name.strip()
        if name not in UNIT_PRICE:
            return KakaoResp.text("판매할 수 없는 항목입니다.")

        if name in CONSUMABLE_KEYS:
            have = u["bag"]["consumables"].get(name, 0)
            if have <= 0:
                return KakaoResp.text("해당 아이템을 보유하고 있지 않습니다.")
            if qty <= 0 or qty > have:
                qty = min(have, max(1, qty))
        else:
            qty = 1  # 장비는 1개

        refund = int(UNIT_PRICE[name] * 0.5) * qty
        u["pending_sale"] = {"name": name, "qty": qty}
        self.store.save_user(uid, u)
        return KakaoResp.text(
            "⚠ 되팔기 안내\n"
            "상점에서 산 물건을 되팔면 구매가격의 50%만 환불됩니다.\n\n"
            f"판매 대상: {name} ×{qty}\n"
            f"환불 예정: 💰{refund}\n\n"
            "진행하시겠습니까?\n"
            "/판매확인  |  /판매취소"
        )

    def sell_item_confirm(self, uid: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        p = u.get("pending_sale")
        if not p:
            return KakaoResp.text("대기 중인 판매가 없습니다.")
        name = p["name"]
        qty = p["qty"]
        refund = int(UNIT_PRICE[name] * 0.5) * qty

        if name in CONSUMABLE_KEYS:
            u["bag"]["consumables"][name] = max(0, u["bag"]["consumables"][name] - qty)
        else:
            # 장비 판매: 현재 장착 중이면 기본 장비로 복구
            if u["rod"] == name:
                u["rod"] = "대나무 낚싯대"

        u["gold"] += refund
        u["pending_sale"] = None
        self.store.save_user(uid, u)
        return KakaoResp.text(f"{name} ×{qty} 판매 완료! 환불 금액 💰{refund}\n현재 골드: 💰{u['gold']}")

    def sell_item_cancel(self, uid: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        u["pending_sale"] = None
        self.store.save_user(uid, u)
        return KakaoResp.text("판매를 취소했습니다.")

    # ── 전부판매(물고기만) ────────────────────────────────────────────────
    def sell_all_fish(self, uid: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        total = 0
        for f in u["bag"]["fish"]:
            cm = f["cm"]
            grade = f["grade"]   # 소형/중형/대형
            mult = 1 if grade == "소형" else 2 if grade == "중형" else 3
            total += cm * mult
        u["bag"]["fish"] = []
        u["gold"] += total
        self.store.save_user(uid, u)
        return KakaoResp.text(f"물고기 전부 판매! +💰{total}\n현재 골드: 💰{u['gold']}")

    # ── 출석 / 초보자찬스 ────────────────────────────────────────────────
    def attend(self, uid: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        if u["attended_today"]:
            return KakaoResp.text("오늘은 이미 출석하셨습니다. (기준: 서울 00:00)")
        u["attended_today"] = True
        u["limit_gold"] += 150
        self.store.save_user(uid, u)
        return KakaoResp.text("✅ 출석 보상 150골드! (제한골드에 적립)")

    def beginner_bonus(self, uid: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        if u["title"] != "낚린이":
            return KakaoResp.text("초보자찬스는 낚린이 전용입니다.")
        if u["beginner_used"] >= 3:
            return KakaoResp.text("오늘 초보자찬스를 모두 사용했습니다. (1일 3회)")
        u["beginner_used"] += 1
        u["limit_gold"] += 1000
        self.store.save_user(uid, u)
        left = 3 - u["beginner_used"]
        return KakaoResp.text(f"✅ 초보자찬스! 제한골드 💰1000 적립\n(오늘 사용: {u['beginner_used']}회, 남은 횟수: {left}회)")

    # ── 소모품 사용 ──────────────────────────────────────────────────────
    def use_additive(self, uid: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        if u["bag"]["consumables"]["집어제"] <= 0:
            return KakaoResp.text("집어제가 없습니다.")
        u["bag"]["consumables"]["집어제"] -= 1
        u["effects"]["additive_uses"] = 3
        self.store.save_user(uid, u)
        return KakaoResp.text("✅ 집어제 1개를 사용했습니다. (남은 수량 감소)\n효과가 3회 낚시 동안 지속됩니다.")

    def use_chemilight(self, uid: str, grade: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        key = f"케미라이트{grade}등급"
        if key not in u["bag"]["consumables"]:
            return KakaoResp.text("잘못된 케미라이트 등급입니다.")
        if u["bag"]["consumables"][key] <= 0:
            return KakaoResp.text(f"{key}가 없습니다.")
        t = now_kst()
        if not is_chemilight_time(t):
            hhmm = t.strftime("%H:%M")
            return KakaoResp.text(
                f"케미라이트는 낮 시간({hhmm})에는 사용할 수 없습니다. 사용 가능 시간: 20:00~05:00 (서울 기준)"
            )
        # 1개만 소모, 1회성
        u["bag"]["consumables"][key] -= 1
        u["effects"]["chemi"] = key   # 다음 낚시 1회만 적용
        self.store.save_user(uid, u)
        return KakaoResp.text(f"✅ {key} 1개를 사용했습니다. (남은 수량: {u['bag']['consumables'][key]}개)")

    # ── 낚시: 시작/릴감기 ───────────────────────────────────────────────
    def cast(self, uid: str, sec: int) -> Dict[str, Any]:
        u = self.store.load_user(uid)

        if self.calc_used_slots(u) >= MAX_SLOTS:
            # 가방 가득 → 소모품/전부판매 가이드
            return self._full_bag_guidance(u)

        if sec < 1 or sec > 60:
            return KakaoResp.text("올바른 형식: /낚시 [1~60]s   (예: /낚시 15s)")

        place = u["place"]
        need = "지렁이" if place == "바다" else "떡밥"
        if u["bag"]["consumables"][need] <= 0:
            return KakaoResp.text(f"{place} 낚시는 {need}가 필요합니다. /상점 에서 구매해 주세요.")

        u["fishing"]["active"] = True
        u["fishing"]["cast_at"] = now_kst()
        u["fishing"]["duration"] = sec
        self.store.save_user(uid, u)

        return KakaoResp.text(
            f"[캐스팅 시작] 장소: {place} | 시간: {sec}초\n"
            "끝나면 /릴감기 로 결과를 확인하세요.\n"
            "(조기 릴 시 실패확률 +80%p, 성공률 상한 95%)"
        )

    def reel(self, uid: str) -> Dict[str, Any]:
        u = self.store.load_user(uid)
        if not u["fishing"]["active"]:
            return KakaoResp.text("현재 낚시가 진행 중이 아닙니다. /낚시 [1~60]s 로 시작하세요.")

        cast_at = u["fishing"]["cast_at"]
        dur = u["fishing"]["duration"]
        elapsed = int((now_kst() - cast_at).total_seconds())
        early = elapsed < dur

        # 기본 성공 확률
        success_chance = 0.65
        if early:
            success_chance = clamp(success_chance - 0.80, 0.0, 0.95)  # 조기 릴 패널티

        # 집어제(+5%p, 3회 지속)
        if u["effects"]["additive_uses"] > 0:
            success_chance += 0.05

        success = random.random() < clamp(success_chance, 0.0, 0.95)

        # 소모품 소비(먹이 1개)
        need = "지렁이" if u["place"] == "바다" else "떡밥"
        if u["bag"]["consumables"][need] > 0:
            u["bag"]["consumables"][need] -= 1

        # 집어제 남은 횟수 차감(릴을 감아 결과 산정 시 1 차감)
        if u["effects"]["additive_uses"] > 0:
            u["effects"]["additive_uses"] -= 1

        u["fishing"]["active"] = False

        if not success:
            msg = "아쉽게도 물고기가 도망갔습니다…"
            if early:
                msg += " (조기 릴 페널티 적용)"
            self.store.save_user(uid, u)
            return KakaoResp.text(msg)

        # 성공 → 물고기 생성
        fish = self._gen_fish(u["place"], u)

        # 가방 꽉 찼는지 체크 (잡았지만 담지 못함)
        if self.calc_used_slots(u) >= MAX_SLOTS:
            txt = (
                f"🎣 낚시 성공! {fish['name']} {fish['cm']}cm ({fish['grade']}) 을(를) 낚았지만...\n"
                f"가방이 가득 차서 더 이상 담을 수 없습니다! ({MAX_SLOTS}/{MAX_SLOTS}칸)"
            )
            self.store.save_user(uid, u)
            return KakaoResp.text(txt)

        # 담기
        u["bag"]["fish"].append(fish)

        # 경험치 = 등급별 규칙
        cm = fish["cm"]
        if fish["grade"] == "소형":
            gained = cm
        elif fish["grade"] == "중형":
            gained = cm * 10
        else:
            gained = cm * 100

        u["exp"] += gained
        # 레벨업 체크
        while u["exp"] >= next_exp_for_level(u["lv"]):
            u["exp"] -= next_exp_for_level(u["lv"])
            u["lv"] += 1

        self.store.save_user(uid, u)
        price = cm * (1 if fish["grade"] == "소형" else 2 if fish["grade"] == "중형" else 3)
        return KakaoResp.text(
            f"🎉 성공! {fish['name']} {cm}cm ({fish['grade']})\n"
            f"가격: 💰{price} | 경험치 +{gained}"
        )

    def _gen_fish(self, place: str, u: Dict[str, Any]) -> Dict[str, Any]:
        # 사이즈 및 등급 결정
        # 기본 분포(소/중/대): 60% / 30% / 10%  (케미 효과 적용)
        p_small, p_mid, p_big = 0.60, 0.30, 0.10

        chemi = u["effects"]["chemi"]
        if chemi:
            # 1등급: 대형 +5%p, 2등급: 중형 +3%p, 3등급: 소형 +1%p
            if chemi.endswith("1등급"):
                p_big = clamp(p_big + 0.05, 0, 1)
            elif chemi.endswith("2등급"):
                p_mid = clamp(p_mid + 0.03, 0, 1)
            elif chemi.endswith("3등급"):
                p_small = clamp(p_small + 0.01, 0, 1)
            # normalize
            s = p_small + p_mid + p_big
            p_small, p_mid, p_big = p_small / s, p_mid / s, p_big / s
            u["effects"]["chemi"] = None  # 1회성 소모

        r = random.random()
        if r < p_small:
            grade = "소형"
            cm = random.randint(15, 29)
        elif r < p_small + p_mid:
            grade = "중형"
            cm = random.randint(30, 59)
        else:
            grade = "대형"
            cm = random.randint(60, 100)

        species = random.choice(FRESH_FISH[place])
        return {"name": species, "cm": cm, "grade": grade}

    # ── 가방 Full 가이드(낚시 시작 차단 시) ─────────────────────────────
    def _full_bag_guidance(self, u: Dict[str, Any]) -> Dict[str, Any]:
        msg = [f"⚠ 가방이 가득 차 낚시를 진행할 수 없습니다. ({MAX_SLOTS}/{MAX_SLOTS}칸)"]

        # 사용 가능한 소모품 제안(밤 시간에만 케미)
        options: List[str] = []
        if u["bag"]["consumables"]["집어제"] > 0:
            options.append("/집어제사용")
        t = now_kst()
        if is_chemilight_time(t):
            for g in ["1", "2", "3"]:
                key = f"케미라이트{g}등급"
                if u["bag"]["consumables"][key] > 0:
                    options.append(f"/{key} 사용")
        else:
            # 낮인데 케미 들고 있으면 사유 안내
            if any(u["bag"]["consumables"][f"케미라이트{x}등급"] > 0 for x in ["1", "2", "3"]):
                hhmm = t.strftime("%H:%M")
                msg.append(f"※ 케미라이트는 낮 시간({hhmm})에는 사용할 수 없습니다. 사용 가능 시간: 20:00~05:00 (서울 기준)")

        if options:
            msg.append("\n가방이 가득 찼습니다. 아래 소모품 중 하나를 사용하시겠어요?")
            msg.extend([f"• {op}" for op in options])
            msg.append("\n소모품을 사용해 칸이 비면 다시 /낚시 를 시도해 주세요.")
        else:
            # 소모품 전혀 없음 → 전부판매 권유 + 예상 판매금액/판매 후 소지금
            total = 0
            for f in u["bag"]["fish"]:
                cm = f["cm"]
                mult = 1 if f["grade"] == "소형" else 2 if f["grade"] == "중형" else 3
                total += cm * mult
            msg.append("\n가방에 사용 가능한 소모품이 없습니다.\n대신 가방 속 물고기를 전부 판매하시겠습니까?")
            msg.append("👉 /전부판매 입력 시 즉시 판매 후 칸이 비워집니다.")
            msg.append(f"예상 판매 금액: 💰{total}")
            msg.append(f"판매 후 소지금: 💰{u['gold']+total} | 제한골드: 💰{u['limit_gold']}")

        # 현재 가방 요약
        used = self.calc_used_slots(u)
        msg.append(f"\n[가방]\n{used}/{MAX_SLOTS}칸 사용중")
        # 1~5 표시
        entries: List[str] = []
        for f in u["bag"]["fish"]:
            entries.append(f"{f['name']} {f['cm']}cm ({f['grade']})")
        for key in CONSUMABLE_KEYS:
            cnt = u["bag"]["consumables"][key]
            if cnt > 0:
                if key == "집어제":
                    entries.append(f"{key} ({cnt}개) - 소모품 · 사용: /집어제사용 (3회 지속)")
                elif key.startswith("케미라이트"):
                    entries.append(f"{key} ({cnt}개) - 소모품 · 사용: /{key} 사용 (1회성 · 20:00~05:00)")
                else:
                    entries.append(f"{key} ({cnt}개) - 소모품")

        for i in range(MAX_SLOTS):
            if i < len(entries):
                msg.append(f"{i+1}. {entries[i]}")
            else:
                msg.append(f"{i+1}. 비어있음")

        return KakaoResp.text("\n".join(msg))

# ───────────────────────────────────────────────────────────────────────────────
# Flask App
# ───────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
store = MemoryStore()
game = FishingGame(store)

CMD_PATTERNS = {
    "slash_home": re.compile(r"^/$"),
    "start": re.compile(r"^/시작$"),
    "nick": re.compile(r"^/닉네임\s+(.+)$"),
    "place": re.compile(r"^/장소\s+(바다|민물)$"),
    "shop": re.compile(r"^/상점$"),
    "buy": re.compile(r"^/구매\s+(\S+)\s+(\d+)(?:개|장)?$"),
    "sell_prepare": re.compile(r"^/아이템판매\s+(\S+)(?:\s+(\d+)(?:개|장)?)?$"),
    "sell_confirm": re.compile(r"^/판매확인$"),
    "sell_cancel": re.compile(r"^/판매취소$"),
    "sell_all": re.compile(r"^/전부판매$"),
    "attend": re.compile(r"^/출석$"),
    "beginner": re.compile(r"^/초보자찬스$"),
    "use_additive": re.compile(r"^/집어제사용$"),
    "use_chemi": re.compile(r"^/케미라이트(1|2|3)등급\s*사용$"),
    "cast": re.compile(r"^/낚시\s+(\d+)s$"),
    "reel": re.compile(r"^/릴감기$"),
}

def handle_command(user_id: str, text: str) -> Dict[str, Any]:
    text = text.strip()

    # / (홈): 닉네임 없으면 닉네임 설정 안내
    if CMD_PATTERNS["slash_home"].match(text):
        return game.cmd_home(user_id)

    # /시작: 닉네임 미설정 유저용(최초 안내), 닉네임 있으면 / 사용 유도
    if CMD_PATTERNS["start"].match(text):
        u = store.load_user(user_id)
        if not u["nick_locked"]:
            return KakaoResp.text("처음 오셨네요! 닉네임을 설정해 주세요.\n예) /닉네임 낚시왕")
        else:
            return KakaoResp.text("이미 닉네임이 설정되어 있습니다. '/' 를 입력해서 홈 화면을 보세요.")

    m = CMD_PATTERNS["nick"].match(text)
    if m:
        return game.set_nick(user_id, m.group(1))

    m = CMD_PATTERNS["place"].match(text)
    if m:
        return game.set_place(user_id, m.group(1))

    if CMD_PATTERNS["shop"].match(text):
        return game.shop(user_id)

    m = CMD_PATTERNS["buy"].match(text)
    if m:
        name = m.group(1)
        qty = int(m.group(2))
        return game.buy(user_id, name, qty)

    m = CMD_PATTERNS["sell_prepare"].match(text)
    if m:
        name = m.group(1)
        qty = int(m.group(2)) if m.group(2) else 1
        return game.sell_item_prepare(user_id, name, qty)

    if CMD_PATTERNS["sell_confirm"].match(text):
        return game.sell_item_confirm(user_id)

    if CMD_PATTERNS["sell_cancel"].match(text):
        return game.sell_item_cancel(user_id)

    if CMD_PATTERNS["sell_all"].match(text):
        return game.sell_all_fish(user_id)

    if CMD_PATTERNS["attend"].match(text):
        return game.attend(user_id)

    if CMD_PATTERNS["beginner"].match(text):
        return game.beginner_bonus(user_id)

    if CMD_PATTERNS["use_additive"].match(text):
        return game.use_additive(user_id)

    m = CMD_PATTERNS["use_chemi"].match(text)
    if m:
        grade = m.group(1)
        return game.use_chemilight(user_id, grade)

    m = CMD_PATTERNS["cast"].match(text)
    if m:
        sec = int(m.group(1))
        return game.cast(user_id, sec)

    if CMD_PATTERNS["reel"].match(text):
        return game.reel(user_id)

    # 기본: 홈 유도
    return KakaoResp.text("알 수 없는 명령입니다. '/' 를 입력해 홈 화면을 보세요.")

# 카카오 스킬 엔드포인트
@app.route("/kakao", methods=["POST"])
def kakao_webhook():
    body = request.get_json(force=True, silent=True) or {}
    user_id = (
        body.get("userRequest", {})
            .get("user", {})
            .get("id", "anon")
    )
    utter = body.get("userRequest", {}).get("utterance", "/").strip()
    resp = handle_command(user_id, utter)
    return jsonify(resp)

# 간단 테스트용
@app.route("/test")
def test():
    text = request.args.get("text", "/").strip()
    user_id = request.args.get("uid", "local")
    return jsonify(handle_command(user_id, text))

@app.route("/")
def health():
    return "OK"

if __name__ == "__main__":
    # 로컬 실행용
    app.run(host="0.0.0.0", port=5000, debug=True)

