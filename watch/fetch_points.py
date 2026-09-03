#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""学校対抗得点（天皇杯・奥野杯）の公式速報を取り込む。
   https://www.swim-g.net/intercollege/points/{id}/plotdata.json （1分更新）
   得点はこちらで計算しない。公式が確定した値をそのまま持ってくる。"""
import json, re, subprocess, sys

URL = "https://www.swim-g.net/intercollege/points/7026401/plotdata.json"
LABEL = re.compile(r'(★?)(.+?)[　\s]*\(\s*([\d.]+)点\)')

def fetch(url=URL):
    r = subprocess.run(["curl","-s","--max-time","30","-A","Mozilla/5.0",url],
                       capture_output=True, text=True)
    return json.loads(r.stdout.lstrip('﻿'))

def build(plot):
    out = {"genders": []}
    for blk in plot.get("PlotList", []):
        ticks = [t[1] for t in blk.get("ticks_data", [])]
        events = [t for t in ticks if t and t != '-']
        teams = []
        for i, s in enumerate(blk.get("series_data", [])):
            m = LABEL.match(s.get("label",""))
            if not m: continue
            pts = dict(blk["point_data"][i]) if i < len(blk.get("point_data",[])) else {}
            rks = dict(blk["rank_data"][i])  if i < len(blk.get("rank_data",[]))  else {}
            gains, prev = [], 0.0
            for j in sorted(pts):
                cur = pts[j]
                if cur != prev and j < len(ticks) and ticks[j] not in ('', '-'):
                    gains.append({"ev": ticks[j], "gain": round(cur-prev,1), "total": round(cur,1)})
                prev = cur
            last = max(pts) if pts else None
            rk = rks.get(last) if last is not None else None
            # 学校対抗の対象外（団体出場校でない＝個人出場校）は順位に巨大な番兵が入る
            if rk is not None and rk > 1000: rk = None
            teams.append({"team": m.group(2).strip(), "seed": bool(m.group(1)),
                          "points": round(float(m.group(3)),1),
                          "rank": rk,
                          "gains": gains})
        teams.sort(key=lambda t: (-t["points"], t["team"]))
        # 公式の順位が無い（0点）チームは順位を空にする
        done = max((len(t["gains"]) and max(i for i,_ in enumerate(t["gains"]))+1) or 0 for t in teams) if teams else 0
        nev = max((len([g for g in t["gains"]]) for t in teams), default=0)
        out["genders"].append({
            "gender": blk.get("class_name","").strip(),
            "events": events,
            "eventsDone": len({g["ev"] for t in teams for g in t["gains"]}),
            "teams": teams})
    return out

if __name__ == "__main__":
    d = build(fetch())
    json.dump(d, open(sys.argv[1] if len(sys.argv)>1 else "points.json","w"), ensure_ascii=False, indent=1)
    for g in d["genders"]:
        print(f"【{g['gender']}】{len(g['teams'])}校 ／ {g['eventsDone']}/{len(g['events'])}種目")
        for t in g["teams"][:5]:
            print(f"   {t['rank'] or '-':>2} {'★' if t['seed'] else '  '}{t['team']:<10} {t['points']:6.1f}点")
