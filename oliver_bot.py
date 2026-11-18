import urllib.request
import json
from datetime import datetime, timedelta
import time
from collections import deque

TOKEN = "9297235611:AAHalsTb-daLvjhV3YAQd2XNAruK4kqp_2c"
API = "https://api.telegram.org/bot" + TOKEN
KL = "https://api.binance.com/api/v3/klines"
KL = KL + "?interval=1m&limit=60&symbol="
PX = "https://api.binance.com/api/v3/ticker/price?symbol="
PAIRS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT"]
HDR = {"Content-Type": "application/json"}
MIN_SAMPLES = 5

def call(url, payload=None):
    data = None
    if payload:
        data = json.dumps(payload).encode()
    r = urllib.request.Request(url, data=data, headers=HDR)
    r = urllib.request.urlopen(r, timeout=10)
    return json.loads(r.read().decode())

def send(cid, text):
    p = {}
    p["chat_id"] = cid
    p["text"] = text
    call(API + "/sendMessage", p)

def price(sym):
    return float(call(PX + sym)["price"])

def ema(vals, p):
    k = 2.0 / (p + 1)
    e = vals[0]
    for v in vals[1:]:
        e = v * k + e * (1 - k)
    return e

def rsi(vals, p=14):
    g = 0.0
    l = 0.0
    last = vals[-(p + 1):]
    for i in range(1, len(last)):
        d = last[i] - last[i - 1]
        if d > 0:
            g += d
        else:
            l -= d
    if l == 0:
        return 100.0
    rs = (g / p) / (l / p)
    return 100.0 - 100.0 / (1 + rs)

def analyze(sym):
    kl = call(KL + sym)
    closes = [float(k[4]) for k in kl[:-1]]
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    r = rsi(closes)
    if e9 > e21 and 50 < r < 70:
        why = "EMA9 > EMA21 and RSI " + str(round(r, 1)) + " (uptrend momentum)"
        return "UP", why
    if e9 < e21 and 30 < r < 50:
        why = "EMA9 < EMA21 and RSI " + str(round(r, 1)) + " (downtrend momentum)"
        return "DOWN", why
    return None, None

def get_chat():
    while True:
        try:
            d = call(API + "/getUpdates")
            for u in d.get("result", []):
                if "message" in u:
                    return u["message"]["chat"]["id"]
            print("Send Hi to the bot")
        except Exception as e:
            print("Err: " + str(e))
        time.sleep(5)

def rel(stats, sym, dr):
    s = stats.get(sym + "|" + dr)
    if s is None:
        return None
    if s[1] < MIN_SAMPLES:
        return None
    return s[0] * 100.0 / s[1]

def main():
    cid = get_chat()
    print("Connected")
    hist = deque(maxlen=30)
    stats = {}
    n = 1
    last = ""
    act = None
    while True:
        try:
            now = datetime.now()
            m = now.strftime("%H:%M")
            s = now.second

            if act is not None:
                if now >= act["close_dt"]:
                    cp = price(act["sym"])
                    d = cp - act["entry"]
                    up = act["dir"] == "UP"
                    key = act["sym"] + "|" + act["dir"]
                    if d == 0:
                        res = "DRAW"
                    elif (d > 0) == up:
                        res = "WIN"
                    else:
                        res = "LOSS"
                    if res != "DRAW":
                        if key not in stats:
                            stats[key] = [0, 0]
                        stats[key][1] += 1
                        if res == "WIN":
                            stats[key][0] += 1
                    hist.append(res)
                    w = hist.count("WIN")
                    l = hist.count("LOSS")
                    dr = hist.count("DRAW")
                    t = "REPORT #" + str(act["n"]) + "\n"
                    t += act["sym"] + " " + act["dir"] + "\n"
                    t += "Entry: " + str(act["entry"]) + "\n"
                    t += "Close: " + str(cp) + "\n"
                    t += "Result: " + res + "\n"
                    t += "Last " + str(len(hist)) + ": "
                    t += str(w) + " WIN / "
                    t += str(l) + " LOSS / "
                    t += str(dr) + " DRAW"
                    send(cid, t)
                    print("Report sent #" + str(act["n"]))
                    act = None

            if m != last and s >= 40 and act is None:
                last = m
                best = None
                best_score = -1
                for sym in PAIRS:
                    try:
                        dr, why = analyze(sym)
                    except Exception as e:
                        print("Skip " + sym + ": " + str(e))
                        continue
                    if dr is None:
                        continue
                    rl = rel(stats, sym, dr)
                    score = 50.0
                    if rl is not None:
                        score = rl
                    if score > best_score:
                        best_score = score
                        best = (sym, dr, why, rl)

                if best is None:
                    print("No signal this minute")
                else:
                    sym = best[0]
                    dr = best[1]
                    why = best[2]
                    rl = best[3]
                    p = price(sym)
                    t1 = now + timedelta(minutes=1)
                    t2 = now + timedelta(minutes=2)
                    t2 = t2.replace(second=0, microsecond=0)
                    act = {}
                    act["n"] = n
                    act["sym"] = sym
                    act["dir"] = dr
                    act["entry"] = p
                    act["close_dt"] = t2
                    if rl is None:
                        rtxt = "NEW (not enough results yet)"
                    else:
                        rtxt = str(round(rl, 1)) + "% past win rate"
                    t = "SIGNAL #" + str(n) + "\n"
                    t += "Candle: " + t1.strftime("%H:%M") + "\n"
                    t += sym + " " + dr + "\n"
                    t += "Entry: " + str(p) + "\n"
                    t += "Reason: " + why + "\n"
                    t += "Reliability: " + rtxt + "\n"
                    t += "Not financial advice"
                    send(cid, t)
                    print("Signal sent #" + str(n))
                    n = n % 100 + 1

            time.sleep(1)
        except Exception as e:
            print("Error: " + str(e))
            time.sleep(5)

if __name__ == "__main__":
    main()
