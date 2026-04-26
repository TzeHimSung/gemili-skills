import re, json

# ============================================================
# PHASE 1+2: Extract all articles from 3 pages
# ============================================================
all_articles = {}
seen = set()

for fname, page in [('/tmp/yahoo_p1.html',1),('/tmp/yahoo_p2.html',2),('/tmp/yahoo_p3.html',3)]:
    html = open(fname).read()
    id_positions = [(m.start(), m.group(1)) for m in re.finditer(r'"id":(\d+)', html)]
    cc_positions = [(m.start(), int(m.group(1))) for m in re.finditer(r'"commentCount":(\d+)', html)]
    
    for id_pos, pid in id_positions:
        if pid in seen:
            continue
        # Find next commentCount after this id
        cc = None
        for cc_pos, cc_val in cc_positions:
            if cc_pos > id_pos:
                cc = cc_val
                break
        if cc is None:
            continue
        
        between = html[id_pos:cc_pos]
        title_matches = list(re.finditer(r'"title":"((?:[^"\\]|\\.)*)"', between))
        if not title_matches:
            continue
        title = title_matches[-1].group(1)
        
        # Get articleUrl after commentCount
        after_cc = html[cc_pos:cc_pos+2000]
        aurl_m = re.search(r'"articleUrl":"((?:[^"\\]|\\.)*)"', after_cc)
        aurl = aurl_m.group(1).replace('\\u0026','&') if aurl_m else ''
        
        seen.add(pid)
        all_articles[pid] = {
            'pid': pid, 'title': title, 'cc': cc,
            'aurl': aurl, 'page': page,
            'purl': f'https://news.yahoo.co.jp/pickup/{pid}',
            'curl': f'{aurl}/comments' if aurl else ''
        }

# ============================================================
# PHASE 3: Filter sports
# ============================================================
SPORTS_KW = [
    '阪神','タイガース','マラソン','新庄','有原','近本','甲子園',
    'セ・リーグ','パ・リーグ','日本ハム','サッカー','Jリーグ','大相撲',
    'プロ野球','死球','藤川監督','柔道','フワちゃん大金星','延長10回',
    'ハト乱入','得点ランク','8失点KO','朗希','上田綺世',
    '高校生NO.1左腕','社会人に進んだ','ホワイトソックス','ムラカミ効果',
    'ネコが球場侵入','永山が奮闘','炎鵬'
]

non_sports = [a for a in all_articles.values() 
              if not any(kw in a['title'] for kw in SPORTS_KW)]
non_sports.sort(key=lambda x: x['cc'], reverse=True)

# ============================================================
# PHASE 4: Categorize
# ============================================================
def categorize(t):
    intl = ['米','トランプ','アメリカ','ワシントン','マリ','国防相',
            '軍民両用','日米','原油','ホルムズ','イラン','中国','日産',
            '自民','滋賀','高市','首相','米大統領','銃撃','発砲','デモ',
            '排外','外国人','政治的暴力','世論分断','大阪','アフリカ',
            'CNN','夕食会','大統領']
    ent = ['MEGUMI','東方神起','内村','24時間','孤独のグルメ','食堂',
           '三山凌輝','秋元','アイドル','中丸','アニメ','主婦','芸能界',
           '松山千春','有吉弘行','松本人志','櫻井','嵐','歌手','橋本マナミ',
           '篠田麻里子']
    sci = ['蜃気楼','地震','気温','GW期間','山林火災','気温変化']
    
    for kw in intl:
        if kw in t:
            return '🌍国際政治'
    for kw in ent:
        if kw in t:
            return '🎬エンタメ'
    for kw in sci:
        if kw in t:
            return '🔬科学自然'
    return '🏥国内社会'

for a in non_sports:
    a['cat'] = categorize(a['title'])

# ============================================================
# OUTPUT
# ============================================================
print(f'爬取: {len(all_articles)}篇 | 体育筛除: {len(all_articles)-len(non_sports)}篇 | 最终: {len(non_sports)}篇')
print()

# By category grouping
cats = {}
for a in non_sports:
    cats.setdefault(a['cat'], []).append(a)

for cat_name in ['🌍国際政治', '🏥国内社会', '🎬エンタメ', '🔬科学自然']:
    items = cats.get(cat_name, [])
    items.sort(key=lambda x: x['cc'], reverse=True)
    print(f'\n## {cat_name} ({len(items)}篇)')
    for i, a in enumerate(items):
        url = a['aurl'][:50] if a['aurl'] else '(no url)'
        print(f'{a["cc"]:5d}💬|{a["pid"]}|{a["title"][:60]}')
        print(f'      pickup: {a["purl"]}')
        if a['aurl']:
            print(f'      article: {a["aurl"]}')
