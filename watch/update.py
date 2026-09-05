#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""インカレ2026 速報の見張り。
   SEIKOのスタートリスト/種目別結果を5分おきに取り、アプリに反映して公開する。
   検算に落ちたら公開せず通知する（間違ったものを出さない）。
   launchd から動く。画面を開いていなくても、Claudeを開いていなくても動く。"""
import json, os, re, subprocess, sys, time, unicodedata
from concurrent.futures import ThreadPoolExecutor

HERE  = os.path.dirname(os.path.abspath(__file__))
APP   = os.path.dirname(HERE)
SRC   = os.path.expanduser('~/swim-entry-app/samples/インカレ2026.json')
BUILD = os.path.expanduser('~/swim-entry-app/build.py')
OUT   = os.path.expanduser('~/swim-entry-app/out/インカレ2026/index.html')
LOG   = os.path.join(HERE, 'log.txt')
SEEN  = os.path.join(HERE, '.seen.json')
PDF   = os.path.join(HERE, 'pdf')
BASE  = "https://swim.seiko.co.jp/2026/S70401"
LABEL = "com.fukuda.swim.intercollege-2026"
STOP_AFTER = "2026-09-07 09:00"          # 大会翌朝に自分で止まる
# 動かす時間帯（開始, 終了）。開始は "9:55" のように分まで書ける。
# レース開始の5分前から動かし、終わったら止める。夜中は回さない。
WINDOW = {"2026-09-03": ("9:00","18:15"),   # 1日目 終了（20競技すべて反映済み）
          "2026-09-04": ("9:55","21:00"),   # 2日目 レース10:00から
          "2026-09-05": ("9:55","21:00"),
          "2026-09-06": ("9:55","21:00")}

def _hm(v):
    h, _, m = str(v).partition(":")
    return int(h)*60 + (int(m) if m else 0)
HOME_TAB = "origin"                       # 鹿児島出身の選手は結果が出たら必ず知らせる

sys.path.insert(0, HERE)
import parse_start, parse_rank, fetch_points

def log(m):
    with open(LOG,'a') as f: f.write(time.strftime('%m/%d %H:%M ')+m+'\n')

def notify(title,msg):
    subprocess.run(["osascript","-e",
        f'display notification "{msg[:200].replace(chr(34),chr(39)).replace(chr(10)," ")}" '
        f'with title "{title.replace(chr(34),chr(39))}" sound name "Glass"'],check=False)

def stop_myself():
    subprocess.run(["launchctl","bootout",f"gui/{os.getuid()}/{LABEL}"],check=False)

def load(p,d):
    try:
        with open(p) as f: return json.load(f)
    except Exception: return d

IT=str.maketrans({"髙":"高","﨑":"崎","栁":"柳","𠮷":"吉","濵":"浜","邉":"辺","邊":"辺",
                  "齋":"斎","齊":"斉","冨":"富","德":"徳","曻":"昇","澤":"沢","瀨":"瀬"})
key=lambda s: unicodedata.normalize('NFKC', re.sub(r'[\s　]','',str(s or ''))).translate(IT)

def fetch(kind, day, no):
    ch = 'S' if kind=='start' else 'R'
    name = f"{day:02d}{ch}{no:03d}.pdf"
    dest = os.path.join(PDF, kind, name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    r = subprocess.run(["curl","-s","--max-time","40","-A","Mozilla/5.0",
                        f"{BASE}/{kind}/{name}","-o",dest], capture_output=True)
    return dest if r.returncode==0 and os.path.getsize(dest)>1000 else None

def main():
    now = time.strftime('%Y-%m-%d %H:%M')
    if now > STOP_AFTER:                       # 停止判定は時間帯ガードより先に置く
        log('大会が終わったので見張りを止めた'); stop_myself(); return
    today = time.strftime('%Y-%m-%d')
    mins = int(time.strftime('%H'))*60 + int(time.strftime('%M'))
    byhand = '--now' in sys.argv          # 手で動かすときは時間帯を気にしない
    win = WINDOW.get(today)
    if not byhand and (not win or not (_hm(win[0]) <= mins < _hm(win[1]))): return   # 時間外は何もしない

    d = json.load(open(SRC, encoding='utf-8'))
    DAY = {'1日目':1,'2日目':2,'3日目':3,'4日目':4}
    prog = {p['no']: dict(p, d=DAY[p['day']]) for p in d['program']}
    seen = load(SEEN, {})
    done_r = set(seen.get('ranking', []))      # 取り込み済みの競技No
    done_s = set(seen.get('start', []))

    # --- 今日ぶんを中心に、未取得のものを取りに行く ---
    dayno = {1:'2026-09-03',2:'2026-09-04',3:'2026-09-05',4:'2026-09-06'}
    todays = [n for n,p in prog.items() if dayno.get(p['d'])==today]
    want_s = [n for n in todays if n not in done_s]
    want_r = [n for n in todays if n not in done_r]

    new_s = {}
    with ThreadPoolExecutor(5) as ex:
        for n, path in zip(want_s, ex.map(lambda n: fetch('start', prog[n]['d'], n), want_s)):
            if not path: continue
            try:
                r,_ = parse_start.parse(path)
            except Exception as e:
                log(f'  スタートリスト読めず No.{n} {type(e).__name__}'); continue
            if r and r['rows']: new_s[n] = r['rows']
    new_r = {}
    with ThreadPoolExecutor(5) as ex:
        for n, path in zip(want_r, ex.map(lambda n: fetch('ranking', prog[n]['d'], n), want_r)):
            if not path: continue
            try:
                r = parse_rank.parse(path)
            except Exception as e:
                log(f'  結果PDF読めず No.{n} {type(e).__name__}'); continue
            if r: new_r[n] = r

    # 学校対抗得点は公式の速報をそのまま取り込む（結果の有無と関係なく毎回見る）
    pts_changed = False
    try:
        pts = fetch_points.build(fetch_points.fetch())
        if pts.get('genders'):
            pts['note'] = ('※ 得点は大会公式の学校対抗得点速報の値をそのまま表示しています。'
                           '最終種目の得点は会場での結果発表後に反映されます。')
            if json.dumps(d.get('teamPoints'), ensure_ascii=False, sort_keys=True) != \
               json.dumps(pts, ensure_ascii=False, sort_keys=True):
                d['teamPoints'] = pts; pts_changed = True
    except Exception as e:
        log(f'  学校対抗得点の取得に失敗: {type(e).__name__}')

    if not new_s and not new_r and not pts_changed:
        log(f'変化なし（結果 {len(done_r)}/{len(prog)}競技 取り込み済み）'); return
    if pts_changed and not new_s and not new_r:
        c = d['summary']['counts']
        c['individualEntries'] = len({(e.get('id') or e.get('name'), e.get('team'), e.get('distance'), e.get('stroke'))
                              for e in d['entries'] if e.get('entryType')!='リレーのみ'})
        c['relayEntries'] = len(d['relays'])
        json.dump(d, open(SRC,'w'), ensure_ascii=False, indent=1)
        b = subprocess.run(['python3', BUILD, SRC], capture_output=True, text=True)
        if b.returncode == 0:
            subprocess.run(['cp', OUT, os.path.join(APP,'index.html')], check=False)
            subprocess.run(['git','add','index.html'], cwd=APP, check=False)
            cm = subprocess.run(['git','commit','-q','-m',f"学校対抗得点を更新 {time.strftime('%m/%d %H:%M')}"],
                                cwd=APP, capture_output=True, text=True)
            if cm.returncode == 0:
                subprocess.run(['git','push','-q'], cwd=APP, capture_output=True, text=True)
            tops = ' / '.join(f"{x['gender']}{x['teams'][0]['team']}{x['teams'][0]['points']:g}"
                              for x in pts['genders'] if x['teams'])
            log(f'  学校対抗得点を更新（{tops}）')
        return

    # ============ ここから反映。1つでも辻褄が合わなければ何も書かない ============
    def sec(t):
        if not t: return None
        m,_,r = t.rpartition(':'); return (int(m)*60 if m else 0)+float(r)
    problems = []

    # 決勝のスタートリスト → 出場者を entries に足す
    added = 0
    for n, rows in new_s.items():
        p = prog[n]
        if p['round'] == '予選': continue          # 予選は申込時に入っている
        hl = [(r['heat'], r['lane']) for r in rows]
        if len(set(hl)) != len(hl): problems.append(f'No.{n} 組・水路の重複'); continue
        have_i = {(key(e['name']), key(e['team'])) for e in d['entries'] if n in (e.get('programNos') or [])}
        have_r = {key(x['team']) for x in d['relays'] if n in (x.get('programNos') or [])}
        for r in rows:
            if r.get('relay') and key(r['team']) in have_r: continue
            if not r.get('relay') and (key(r['name']), key(r['team'])) in have_i: continue
            if r.get('relay'):
                d['relays'].append(dict(team=r['team'], gender=p['gender'], distance=p['distance'],
                    stroke=p['stroke'], programNos=[n], heat=r['heat'], lane=r['lane'], time=''))
            else:
                d['entries'].append(dict(name=r['name'], kana=r['kana'], team=r['team'],
                    grade='大学'+re.sub(r'\D','',r['grade']), gender=p['gender'],
                    distance=p['distance'], stroke=p['stroke'], programNos=[n],
                    heat=r['heat'], lane=r['lane'], time=''))
            added += 1

    # 結果 → 組・水路で突合して result を入れる
    filled = miss = 0; kagoshima = []; hit_n = {}
    for n, rows in new_r.items():
        seat = {}
        for e in d['entries']:
            if n in (e.get('programNos') or []) and e.get('heat'): seat[(e['heat'],e['lane'])] = e
        for r in d['relays']:
            if n in (r.get('programNos') or []) and r.get('heat'): seat[(r['heat'],r['lane'])] = r
        tt = sorted((x['rank'], sec(x['time'])) for x in rows if x['rank'] and x['time'])
        if any(tt[i][1] > tt[i+1][1]+0.005 for i in range(len(tt)-1)):
            problems.append(f'No.{n} 順位と記録が逆転'); continue
        for x in rows:
            e = seat.get((x['heat'], x['lane']))
            if not e: miss += 1; continue
            e['result'] = {k2:v for k2,v in (('rank',x['rank']),('time',x['time']),
                                             ('note',x['note']),('rec',x.get('rec'))) if v}
            filled += 1; hit_n[n] = hit_n.get(n,0)+1
            if e.get('name') and any(s.get('origin') and s['name']==e['name'] for s in d['swimmers']):
                kagoshima.append((e['name'], e['team'], prog[n]['gender']+prog[n]['distance']+prog[n]['stroke'],
                                  prog[n]['round'], x['rank'], x['time'] or x['note']))

    if problems:
        log('  ⚠ 検算に落ちたので反映しない: ' + ' / '.join(problems[:4]))
        notify('インカレ 要確認', '検算に落ちたので自動更新を止めました: '+problems[0]); return
    if miss:
        log(f'  ⚠ 組・水路が名簿に無い行 {miss}件（無視して続行）')

    # 件数の再計算（build.py の検算に通す）
    c = d['summary']['counts']
    c['individualEntries'] = len({(e.get('id') or e.get('name'), e.get('team'), e.get('distance'), e.get('stroke'))
                              for e in d['entries'] if e.get('entryType')!='リレーのみ'})
    c['relayEntries'] = len(d['relays'])
    d['meta']['laneConfirmed'] = True
    json.dump(d, open(SRC,'w'), ensure_ascii=False, indent=1)

    b = subprocess.run(['python3', BUILD, SRC], capture_output=True, text=True)
    if b.returncode != 0:
        log('  ⚠ ビルド失敗: '+(b.stderr or b.stdout).strip().split('\n')[-1][:100])
        notify('インカレ 要確認','ビルドに失敗しました'); return

    subprocess.run(['cp', OUT, os.path.join(APP,'index.html')], check=False)
    subprocess.run(['git','add','index.html'], cwd=APP, check=False)
    msg = f"速報を反映 {time.strftime('%m/%d %H:%M')}（結果{len(done_r)+len(new_r)}競技）"
    cm = subprocess.run(['git','commit','-q','-m',msg], cwd=APP, capture_output=True, text=True)
    if cm.returncode == 0:
        ps = subprocess.run(['git','push','-q'], cwd=APP, capture_output=True, text=True)
        log(f'  公開を更新した（結果{len(new_r)}競技・{filled}行・追加{added}件）' if ps.returncode==0
            else '  pushに失敗（次回やり直す）')
        if ps.returncode != 0: return
    else:
        log('  中身に変化なし（コミットせず）')

    # 1行も入らなかった競技は取得済みにしない（先にスタートリストが要る）
    full = {n for n, rows in new_r.items() if hit_n.get(n,0) == len(rows)}
    seen['ranking'] = sorted(done_r | full); seen['start'] = sorted(done_s | set(new_s))
    short = {n: f"{hit_n.get(n,0)}/{len(new_r[n])}" for n in set(new_r) - full}
    if short: log(f'  全員は入らなかった競技（次回やり直す）: {short}')
    seen['updated'] = now
    json.dump(seen, open(SEEN,'w'), ensure_ascii=False, indent=1)

    for n in sorted(new_r):
        p = prog[n]
        log(f"  ★ No.{n} {p['gender']}{p['distance']}{p['stroke']} {p['round']} {len(new_r[n])}人")
    for nm, tm, ev, rd, rk, t in kagoshima[:6]:
        notify(f'🌋 {nm}（{tm}）', f'{ev} {rd} {rk}位 {t}')
        log(f'    🌋 {nm} {tm} {ev} {rd} {rk}位 {t}')

if __name__ == '__main__':
    main()
