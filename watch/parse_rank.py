# -*- coding: utf-8 -*-
"""SEIKO「種目別競技結果」ranking/{日}R{競技No}.pdf を読む。
   スタートリストで 組/水路 → 選手 が確定しているので、ここは 組/水路・順位・記録 だけ取ればよい。
   列の座標は大会ごとにずれるので、位置ではなく『行の中の並び』で読む。"""
import pdfplumber, re, collections, json, sys, os
TIME = re.compile(r'^(?:\d{1,2}:)?\d{1,2}\.\d{2}$')
NOTE = ('棄権','失格','途中棄権','不出場','妨害','失格(','ＤＮＳ')
ENOTE = {'DNS':'棄権','WDR':'棄権','SCR':'棄権','DSQ':'失格','DNF':'途中棄権','NS':'棄権'}
NOTYET = ('まだ作成されていません','実施されません')

def parse(path):
    with pdfplumber.open(path) as pdf:
        first = pdf.pages[0].extract_text() or ''
        if any(x in first for x in NOTYET) or not first.strip():
            return None
        rows, cur, recX = [], None, None
        for page in pdf.pages:
            line = collections.defaultdict(list)
            for w in page.extract_words():
                line[round(w['top']/2)].append(w)
            for kk in sorted(line):
                ws = sorted(line[kk], key=lambda w: w['x0'])
                texts = [w['text'] for w in ws]
                # 列見出しから「記録」列の位置を覚える。
                # 1500m/800mは記録の前に「800m」列が増え、リレーは「（第１泳者）」列が増えるので、
                # 位置を決め打ちにすると通過タイムを記録と取り違える（2026-09-03 No.8で実害）。
                if '記録' in texts and '順位' in texts:
                    rw = next((w for w in ws if w['text'] == '記録'), None)
                    if rw: recX = rw['x0']
                    continue
                # 選手の1行目 = 「組/水路」を含む行（左寄り）
                hl = next((w for w in ws if w['x0'] < 170 and re.fullmatch(r'\d{1,2}/\d', w['text'])), None)
                if hl:
                    rank = [w['text'] for w in ws if w['x0'] < hl['x0'] and re.fullmatch(r'\d{1,3}', w['text'])]
                    h,l = hl['text'].split('/')
                    cur = dict(heat=int(h), lane=int(l),
                               rank=int(rank[-1]) if rank else None, time=None, note=None)
                    rows.append(cur)
                if cur is None: continue
                # 記録：行の中で一番右にある時計形式（ラップは左側に並ぶので右端を採る）
                # 記録は「その行で一番右にある時計」。リレーは第1泳者のスプリットが左に並ぶので右端を採る。
                # 反応時間は ( 0.59) と括弧付きなので TIME にマッチしない。
                # 最終記録の行の次にラップが並ぶため、一度入ったら上書きしない。
                if cur['time'] is None:
                    lo, hi = (recX - 40, recX + 60) if recX is not None else (380, 10**6)
                    cand=[w for w in ws if TIME.fullmatch(w['text']) and lo <= w['x0'] <= hi]
                    if cand: cur['time'] = max(cand, key=lambda w: w['x0'])['text']
                for w in ws:
                    t = w['text'].strip('（）() ')
                    if t in NOTE: cur['note'] = t.replace('ＤＮＳ','棄権')
                    elif t.upper() in ENOTE: cur['note'] = ENOTE[t.upper()]
        return rows

if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv)>1 else 'rk'
    out={}
    import glob
    for p in sorted(glob.glob(os.path.join(src,'*.pdf'))):
        no=int(os.path.basename(p)[3:6])
        try:
            r=parse(p)
        except Exception as e:
            print('  読めないPDF', os.path.basename(p), type(e).__name__); continue
        if r: out[no]=r
    print('結果のある競技No:',len(out),'／ のべ',sum(len(v) for v in out.values()),'行')
    for n,v in list(out.items())[:1]:
        print('例 No.',n)
        for x in v[:6]: print('   ',x)
        bad=[x for x in v if x['time'] is None and x['note'] is None]
        print('   記録もメモも無い行:',len(bad))
    # 検算: 順位の順にタイムが速い順になっているか
    def sec(t):
        if not t: return None
        m,_,r=t.rpartition(':'); return (int(m)*60 if m else 0)+float(r)
    ng=[]
    for n,v in out.items():
        tt=sorted((x['rank'],sec(x['time'])) for x in v if x['rank'] and x['time'])
        # 順位が上なら記録も速い（同順位＝同記録は正しいので許す）
        if any(tt[i][1] > tt[i+1][1]+0.005 for i in range(len(tt)-1)): ng.append(n)
        byr={}
        for r,t in tt: byr.setdefault(r,set()).add(t)
        if any(len(v2)>1 for v2 in byr.values()): ng.append(n)   # 同順位なのに記録が違う
        # 組・水路の重複は致命的
        hl=[(x['heat'],x['lane']) for x in v]
        if len(set(hl))!=len(hl): ng.append(n)
    print('矛盾する競技No:', sorted(set(ng)) or 'なし')
    json.dump(out,open('results.json','w'),ensure_ascii=False)
