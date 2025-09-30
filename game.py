
class FishingGame:
    def __init__(self, store):
        self.store = store

    def cmd_start(self, uid: str):
        u = self.store.load_user(uid)
        # 닉네임이 설정되지 않았다면 안내
        if not u.get("nick_locked"):
            return (
                "처음 오셨네요! 닉네임을 설정해 주세요. (닉네임은 이후 변경 불가)\n"
                "예) /닉네임 낚시왕카카오"
            )

        # --- 상태 ---
        status_block = (
            f"[상태]\n"
            f"{u.get('title','낚린이')} {u.get('nick','-')} | "
            f"Lv.{u.get('lv',1)}  Exp:{u.get('exp',0)}/{u.get('next_exp',100)}\n"
            f"Gold:{u.get('gold',0)} | 제한골드:{u.get('limit_gold',0)}\n"
            f"장소: {u.get('place','민물')} | "
            f"장착 낚시대: {u.get('rod','대나무 낚싯대')}"
        )

        # --- 가방 ---
        bag_items = u.get("bag", [])
        bag_text = f"[가방]\n{len(bag_items)}/5칸 사용중\n"
        for idx in range(5):
            if idx < len(bag_items):
                item = bag_items[idx]
                bag_text += f"{idx+1}. {item}\n"
            else:
                bag_text += f"{idx+1}. 비어있음\n"
        bag_text += "\n보유하지 않은 물품: 지렁이, 집어제, 케미라이트1등급, 케미라이트2등급, 케미라이트3등급"

        # --- 출석 ---
        if u.get("attended_today", False):
            attend_text = "[출석]\n오늘은 이미 출석하셨습니다. (기준: 서울 00:00)"
        else:
            attend_text = "[출석]\n오늘 출석을 아직 하지 않으셨습니다.\n✅ `/출석` 입력하면 보상 골드를 받을 수 있습니다."

        # --- 낚시 상태 ---
        if u.get("fishing", False):
            fish_text = f"[낚시 상태]\n⏳ {u.get('place','민물')}에서 낚시중 (남은 시간: {u.get('remain',10)}초)"
        else:
            fish_text = "[낚시 상태]\n🎣 현재 낚시중이 아닙니다.\n예) `/장소 민물` → `/낚시 15s` → 시간이 지나면 `/릴감기`"

        # --- 상점/아이템 관리 ---
        shop_text = (
            "[상점/아이템 관리]\n"
            "• /상점\n"
            "• /구매 [번호]\n"
            "• /판매 [번호]\n"
            "• /전부판매"
        )

        # --- 기타 명령어 ---
        etc_text = (
            "[기타 명령어]\n"
            "• /초보자찬스   (낚린이 전용, 하루 3회)\n"
            "• /케미라이트 사용\n"
            "• /집어제사용"
        )

        return f"{status_block}\n\n{bag_text}\n\n{attend_text}\n\n{fish_text}\n\n{shop_text}\n\n{etc_text}"
