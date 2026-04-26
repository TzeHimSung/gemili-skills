#!/usr/bin/env python3
"""
Yahoo JP Roast - 完整爬取管道
用法: python3 yahoo_jp_roast.py [--pages 3] [--top 20]
输出: 筛体育→按评论降序→分类→带链接的完整排名表
"""
import re, sys, os, subprocess

PAGES = 3
TOP_N = None  # None = all

# ===== STEP 1: curl all pages =====
html_files = []
for page in range(1, PAGES + 1):
    url = f"https://news.yahoo.co.jp/topics/top-picks?page={page}" if page > 1 else "https://news.yahoo.co.jp/topics/top-picks"
    fname = f"/tmp/yahoo_p{page}.html"
    subprocess.run(['curl', '-s', '-L', '-H', 'User-Agent: Mozilla/5.0', url, '-o', fname], timeout=15)
    html_files.append((fname, page))

# ===== STEP 2: extract all articles =====
all_articles = {}
seen = set()

for fname, page in html_files:
    html = open(fname).read()
    id_positions = [(m.start(), m.group(1)) for m in re.finditer(r'"id":(\d+)', html)]
    cc_positions = [(m.start(), int(m.group(1))) for m in re.finditer(r'"commentCount":(\d+)', html)]
    
    for id_pos, pid in id_positions:
        if pid in seen: continue
        cc = next((cc_val for cc_pos, cc_val in cc_positions if cc_pos > id_pos), None)
        if cc is None: continue
        
        between = html[id_pos:cc_pos]
        title_matches = list(re.finditer(r'"title":"((?:[^"\\]|\\.)*)"', between))
        if not title_matches: continue
        title = title_matches[-1].group(1)
        
        after_cc = html[cc_pos:cc_pos+2000]
        aurl_m = re.search(r'"articleUrl":"((?:[^"\\]|\\.)*)"', after_cc)
        aurl = aurl_m.group(1).replace('\\u0026','&') if aurl_m else ''
        
        seen.add(pid)
        all_articles[pid] = {
            'pid': pid, 'title': title, 'cc': cc,
            'aurl': aurl, 'page': page,
            'purl': f'https://news.yahoo.co.jp/pickup/{pid}',
        }

# ===== STEP 3: filter sports =====
SPORTS_KW = ['阪神','タイガース','マラソン','新庄','有原','近本','甲子園','セ・リーグ','パ・リーグ','日本ハム','サッカー','Jリーグ','大相撲','プロ野球','死球','藤川監督','柔道','フワちゃん大金星','延長10回','ハト乱入','得点ランク','8失点KO','朗希','上田綺世','高校生NO.1左腕','ホワイトソックス','ムラカミ効果','ネコが球場侵入','永山','炎鵬']

articles = [a for a in all_articles.values() if not any(kw in a['title'] for kw in SPORTS_KW)]
articles.sort(key=lambda x: x['cc'], reverse=True)

if TOP_N:
    articles = articles[:TOP_N]

# ===== STEP 4: categorize =====
def cat(t):
    intl = ['米','トランプ','アメリカ','ワシントン','マリ','国防相','軍民両用','日米','原油','ホルムズ','イラン','中国','日産','自民','滋賀','高市','首相','米大統領','銃撃','発砲','デモ','排外','外国人','政治的暴力','世論分断','大阪','アフリカ','CNN','夕食会','大統領']
    ent = ['MEGUMI','東方神起','内村','24時間','孤独のグルメ','食堂','三山凌輝','秋元','アイドル','中丸','アニメ','主婦','芸能界','松山千春','有吉弘行','松本人志','櫻井','嵐','歌手','橋本マナミ','篠田麻里子']
    sci = ['蜃気楼','地震','気温','GW期間','山林火災','気温変化']
    for kw in intl: 
        if kw in t: return '🌍国際政治'
    for kw in ent: 
        if kw in t: return '🎬エンタメ'
    for kw in sci: 
        if kw in t: return '🔬科学自然'
    return '🏥国内社会'

for a in articles:
    a['cat'] = cat(a['title'])

# ===== STEP 5: output =====
print(f'# Yahoo JP 热榜 ({PAGES}页, {len(all_articles)}篇→筛体育→{len(articles)}篇)')
print()

for cat_name in ['🌍国際政治', '🏥国内社会', '🎬エンタメ', '🔬科学自然']:
    items = [a for a in articles if a['cat'] == cat_name]
    if not items: continue
    print(f'## {cat_name} ({len(items)}篇)')
    print()
    for a in items:
        print(f'- [{a["cc"]}💬]({a["purl"]}) {a["title"]}')
        if a['aurl']:
            print(f'  原文: {a["aurl"]}')
    print()
