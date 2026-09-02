#!/bin/bash
cd "$(dirname "$0")"
echo "インカレの速報を今すぐ確認して、新しい結果があればアプリに反映します。"
echo
/usr/bin/python3 update.py --now
echo
echo "----- 最近の記録 -----"
tail -n 20 log.txt
echo
echo "公開ページ: https://gyojin600m1.github.io/intercollege-2026-entry/"
echo "このウィンドウは閉じて大丈夫です。"
