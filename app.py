
# -*- coding: utf-8 -*-
import os, json, random
from datetime import datetime, time, date
from flask import Flask, request, jsonify

app = Flask(__name__)
DATA_PATH = os.environ.get("DATA_PATH", "data.json")

# -----------------------------
# 상수/정책
# -----------------------------
RESTRICTED_CAP = 1000  # 제한골드 최대 보유치(일반 규칙)
BAG_CAP = 5            # 가방 칸 수 
PRICES = {
    "지렁이": 10,                  # 제한골드 사용 가능
    "떡밥": 10,                    # 제한골드 사용 가능
    "집어제": 2000,                # 변경된 가격
    "케미라이트1등급": 1000,       # 변경된 가격
    "케미라이트2등급": 350,
    "케미라이트3등급": 200,
    "철제 낚싯대": 5000,           # 변경된 가격
    "강화 낚싯대": 20000,          # 변경된 가격
    "프로 낚싯대": 100000,         # 변경된 가격
    "레전드 낚싯대": 500000,       # 변경된 가격
}
CONSUMABLES = {"지렁이", "떡밥", "집어제", "케미라이트1등급", "케미라이트2등급", "케미라이트3등급"}
RESTRICTED_ALLOWED = {"지렁이", "떡밥"}

# -----------------------------
# 저장/로드
# -----------------------------
def load_store():
    if not os.path.exists(DATA_PATH): return {"users":{}}
    try:
        with open(DATA_PATH,"r",encoding="utf-8") as f: return json.load(f)
    except: return {"users":{}}

def save_store(store):
    tmp=DATA_PATH+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(store,f,ensure_ascii=False,indent=2)
    os.replace(tmp,DATA_PATH)

def today_str(): return date.today().isoformat()

def kakao_text(t): 
    return jsonify({"version":"2.0","template":{"outputs":[{"simpleText":{"text":t}}]}})

def fmt_money(g,r): return f"Gold: 💰{g:,} | 제한골드: 💰{r:,}"

def is_night(now=None): 
    now=now or datetime.now(); t=now.time()
    return (t>=time(20,0)) or (t<time(5,0))

# -----------------------------
# 유저 데이터
# -----------------------------
def get_user(store, uid):
    u = store["users"].get(uid)
    if u is None:
        u={"nickname":None,"nick_locked":False,"gold":0,"restricted_gold":0,
           "level":1,"exp":0,"rod":"철제 낚싯대","inventory":{},"fish":[],
           "attendance_last":None,"newbie":{"date":None,"count":0},
           "additive_uses":0,"location":None,"records":{"min":None,"max":None},
           "casting":None,"active_buff":None}
        store["users"][uid]=u
    return u

# -----------------------------
# 레벨/EXP
# -----------------------------
def level_threshold(lv:int)->int: return 100+50*(lv-1)
def add_exp(u, amount):
    u["exp"]+=amount
    while u["exp"]>=level_threshold(u["level"]):
        u["exp"]-=level_threshold(u["level"]); u["level"]+=1

# -----------------------------
# 기록
# -----------------------------
def update_records(u, fish_obj):
    rec=u["records"]
    if rec["min"] is None or fish_obj["cm"]<rec["min"]["cm"]: rec["min"]=fish_obj
    if rec["max"] is None or fish_obj["cm"]>rec["max"]["cm"]: rec["max"]=fish_obj

# -----------------------------
# 가방
# -----------------------------
def bag_full(u): return len(u["fish"])>=BAG_CAP

def add_consumable(u,name,qty):
    before=u["inventory"].get(name,0)
    after=before+qty
    if after<=0:
        if name in u["inventory"]: del u["inventory"][name]
    else:
        u["inventory"][name]=after

# -----------------------------
# 홈 화면
# -----------------------------
def home_text(u):
    lines = []
    lines += [
        "🎣 낚시 RPG 사용법",
        "1) /장소 [바다|민물] ← 먼저 장소를 설정하세요",
        "2) /낚시 [1~60]s ← 해당 초 만큼 캐스팅 (예: /낚시 15s)",
        "3) 시간이 끝나면 /릴감기 로 결과 확인",
        "4) /기록 → 잡아본 물고기 확인",  # ✅ 추가된 부분
        "",
        "🏪 상점 이용 방법",
        "/상점 → 상점 목록 보기",
        "/구매 [이름] [갯수] → 예: /구매 지렁이 10개, /구매 케미라이트1등급 1개",
        "/아이템판매 [이름] [수량] → 되팔기(구매가의 50%)",
        "",
        "(출석/보너스)",
        "/출석 → 출석 보상 받기",
        "/초보자찬스 → 낚린이 전용 보너스(1일 2회, 잔액 0일 때만 수령)",
        "",
    ]
    return "\n".join(lines)

# -----------------------------
# 확률 계산 (보정 절반 + 중형 절반 감소)
# -----------------------------
def calc_prob(seconds:int,u)->dict:
    sec=min(seconds,60)
    base={"소형":0.30,"중형":0.005,"대형":0.00005}  # 중형 확률 절반으로 줄임
    base["소형"]+=0.05*(sec/60)  # 보정 절반
    base["중형"]+=0.005*(sec/60)
    base["대형"]+=0.000025*(sec/60)
    if u.get("additive_uses",0)>0:
        base["중형"]+=0.02; base["대형"]+=0.00005
    buff=u.get("active_buff")
    if buff=="케미라이트1등급":
        for k in base: base[k]*=1.30
    elif buff=="케미라이트2등급":
        for k in base: base[k]*=1.20
    elif buff=="케미라이트3등급":
        for k in base: base[k]*=1.05
    total=sum(base.values())
    base["실패"]=max(0.0,1.0-total)
    return base

# -----------------------------
# 낚시
# -----------------------------
def handle_cast(u,seconds:int):
    if not u.get("location"):
        return "⚠️ 먼저 /장소 [바다|민물] 을 설정하세요."
    if u.get("casting"):
        return "⚠️ 이미 캐스팅 중입니다. /릴감기 후 다시 시도하세요."
    if bag_full(u):
        return "⚠️ 가방이 가득 찼습니다."
    u["casting"]={"seconds":seconds,"start":datetime.now().isoformat()}
    return f"{seconds}초 캐스팅 시작! 시간이 끝나면 자동으로 결과가 나옵니다."

def handle_reel(u):
    if not u.get("casting"):
        return "⚠️ 캐스팅 기록이 없습니다."
    seconds=u["casting"]["seconds"]
    u["casting"]=None
    prob=calc_prob(seconds,u)
    roll=random.random()
    outcome="실패"; cum=0.0
    for k,v in prob.items():
        cum+=v
        if roll<=cum: outcome=k; break
    if outcome=="실패":
        return "뭔가가 걸렸다 !!\n🎣 낚시 실패... 다시 도전해 보세요!"
    loc=u["location"]
    fish_obj={"name":"고등어","cm":random.randint(20,40),"grade":outcome,"price":50,
              "location":loc,"caught_at":today_str()}
    u["fish"].append(fish_obj)
    update_records(u,fish_obj)
    add_exp(u,10)
    msg=[f"뭔가가 걸렸다 !!", f"🎣 {fish_obj['name']} {fish_obj['cm']}cm ({outcome}) 낚음!"]
    if loc=="바다":
        remain=u["inventory"].get("지렁이",0)
        msg.append(f"✅ 지렁이 1개 사용됨 (남은 지렁이: {remain}개)")
    else:
        remain=u["inventory"].get("떡밥",0)
        msg.append(f"✅ 떡밥 1개 사용됨 (남은 떡밥: {remain}개)")
    return "\n".join(msg)

# -----------------------------
# 명령 처리
# -----------------------------
def handle_cmd(u, utt:str):
    t = (utt or "").strip()
    if not u["nick_locked"]:
        if t.startswith("/닉네임 "):
            nickname = t.replace("/닉네임 ","",1).strip()
            u["nickname"] = nickname; u["nick_locked"]=True
            return f"닉네임이 '{nickname}'(으)로 설정되었습니다.\n이제 '/' 로 홈 화면을 확인해 보세요."
        if t=="/":
            return "🎣 낚시 RPG에 오신 것을 환영합니다!\n닉네임을 먼저 설정해 주세요."
        return ""
    if t in ("/","홈","home","메뉴"): return home_text(u)
    if t.startswith("/장소"):
        parts=t.split()
        if len(parts)>=2: u["location"]=parts[1]; return f"장소를 '{u['location']}'(으)로 설정했습니다."
        return "형식: /장소 [바다|민물]"
    if t=="/상점":
        return "상점 UI 출력됨"  # 실제는 shop_text(u) 호출
    if t.startswith("/낚시"):
        num=0
        for ch in t:
            if ch.isdigit(): num=num*10+int(ch)
        return handle_cast(u,num)
    if t=="/릴감기":
        return handle_reel(u)
    if t=="/기록":
        rec=u.get("records",{})
        return f"기록: {rec}"
    return ""

# -----------------------------
# 라우팅
# -----------------------------
@app.route("/skill",methods=["POST"])
def skill():
    body=request.get_json(silent=True) or {}
    user_req=body.get("userRequest",{})
    utter=(user_req.get("utterance") or "").strip()
    uid=user_req.get("user",{}).get("id") or "anonymous"
    store=load_store(); u=get_user(store,uid)
    text=handle_cmd(u,utter); save_store(store)
    return kakao_text(text or ""),200

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)
