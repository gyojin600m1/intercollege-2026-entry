# -*- coding: utf-8 -*-
"""SEIKO速報のスタートリストPDFから 組・水路 を取り出す。
   行の形: 水路 加盟 登録No 氏名 ヨミガナ 所属名 学年
   リレーは 氏名/ヨミガナ の代わりにチーム名が入るので分岐する。"""
import pdfplumber, re, json, os, sys, glob
NOTYET = "まだ作成されていません"
def parse(path):
    with pdfplumber.open(path) as pdf:
        txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
    if NOTYET in txt or not txt.strip():
        return None, txt
    head = {}
    m = re.search(r'競技No\.\s*:\s*(\d+)\s+(男子|女子)\s+(\S+)\s+(\S+?)\s+(予選|決勝|Ｂ決勝|B決勝|準決勝.*?|タイム決勝)', txt)
    if m:
        head = dict(no=int(m.group(1)), gender=m.group(2), dist=m.group(3), stroke=m.group(4), round=m.group(5))
    rows=[]; heat=None
    for line in txt.split("\n"):
        line = line.strip()
        h = re.match(r'^(\d+)組$', line)
        if h: heat = int(h.group(1)); continue
        if heat is None: continue
        # 水路 加盟 登録No 氏名 ヨミガナ 所属 学年
        m2 = re.match(r'^(\d)\s+(学\S+|\S+?)\s+(\d+)\s+(.+?)\s+([ｦ-ﾟ]+(?:\s+[ｦ-ﾟ]+)*)\s+(\S+)\s+(大\d)$', line)
        if m2:
            rows.append(dict(heat=heat, lane=int(m2.group(1)), fed=m2.group(2), regno=int(m2.group(3)),
                             name=m2.group(4).strip(), kana=m2.group(5), team=m2.group(6), grade=m2.group(7)))
            continue
        # リレー: 水路 登録No チーム名 加盟（次の行にヨミガナ・学種。泳者は当日発表なので空欄）
        m3 = re.match(r'^(\d)\s+(\d+)\s+(\S+)\s+(学\S+)$', line)
        if m3:
            rows.append(dict(heat=heat, lane=int(m3.group(1)), regno=int(m3.group(2)),
                             team=m3.group(3), fed=m3.group(4), relay=True))
    return dict(head=head, rows=rows), txt

if __name__ == "__main__":
    out={}; notyet=[]; bad=[]
    for p in sorted(glob.glob('pdf/*.pdf')):
        b=os.path.basename(p); day=int(b[:2]); no=int(b[3:6])
        d,txt = parse(p)
        if d is None: notyet.append((day,no)); continue
        if not d['rows']: bad.append((day,no)); continue
        out[f"{day}-{no}"]=d
    json.dump(out,open('startlists.json','w'),ensure_ascii=False)
    print(f"読めた {len(out)}件 ／ 未公開 {len(notyet)}件 ／ 行が取れなかった {len(bad)}件")
    if notyet: print('  未公開:', notyet[:12], '...' if len(notyet)>12 else '')
    if bad: print('  要確認:', bad)
    tot=sum(len(v['rows']) for v in out.values())
    print('  総行数', tot)
