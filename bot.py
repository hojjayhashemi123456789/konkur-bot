import os
import sys
import io
import re
import socket
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

import telebot
from telebot import types, apihelper

TOKEN = '8574451645:AAER4vkfOzip0KHolGmXqaeKfdmtN0f9bdk'

# =====================================================================
# 🌐 تنظیم هوشمند پروکسی و دور زدن فیلترینگ تلگرام (Smart Proxy Detection)
# =====================================================================
def check_local_port(host, port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            s.connect((host, port))
            return True
    except Exception:
        return False

PROXY_URL = os.environ.get("TELEGRAM_PROXY", "").strip()

if not PROXY_URL:
    common_local_proxies = [
        (10809, "http", "v2rayN / Xray (HTTP)"),
        (7890, "http", "Clash / Mihomo (HTTP)"),
        (2080, "http", "Nekoray (HTTP)"),
        (8080, "http", "Psiphon / HTTP Proxy"),
        (10808, "socks5h", "v2rayN (SOCKS5)"),
        (1080, "socks5h", "Shadowsocks (SOCKS5)")
    ]
    for port, scheme, app_name in common_local_proxies:
        if check_local_port('127.0.0.1', port):
            PROXY_URL = f"{scheme}://127.0.0.1:{port}"
            print(f"🔍 فیلترشکن فعال روی سیستم شناسایی شد ({app_name}): {PROXY_URL}")
            break

if PROXY_URL:
    apihelper.proxy = {'https': PROXY_URL, 'http': PROXY_URL}
    print(f"✅ اتصال تلگرام از طریق پروکسی برقرار شد: {PROXY_URL}")
else:
    print("ℹ️ پروکسی محلی شناسایی نشد؛ اتصال مستقیم یا حالت TUN Mode بررسی می‌شود.")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. شناسایی هوشمند فایل اکسل
def find_excel_file():
    candidates = [
        os.path.join(BASE_DIR, 'konkur_data.xlsx'),
        os.path.join(BASE_DIR, 'آخرین رتبه های قبولی تجربی 1400 تا 1403 - نسخه نهایی.xlsx'),
        'konkur_data.xlsx',
        'آخرین رتبه های قبولی تجربی 1400 تا 1403 - نسخه نهایی.xlsx'
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
            
    for search_dir in [BASE_DIR, os.getcwd()]:
        if os.path.exists(search_dir):
            for f in os.listdir(search_dir):
                if f.endswith('.xlsx') and not f.startswith('~$'):
                    return os.path.join(search_dir, f)
    return None

EXCEL_PATH = find_excel_file()
if not EXCEL_PATH or not os.path.exists(EXCEL_PATH):
    print("❌ خطا: فایل اکسل پایگاه داده در پوشه ربات پیدا نشد!")
    sys.exit(1)

print(f"📁 فایل پایگاه داده شناسایی شد: {os.path.basename(EXCEL_PATH)}")
print("در حال بارگذاری پایگاه داده جامع کنکور تجربی...")

xl = pd.ExcelFile(EXCEL_PATH)
sheet_names = xl.sheet_names
target_sheet = sheet_names[0]
for s in sheet_names:
    if 'تجمیع' in s or 'همه' in s:
        target_sheet = s
        break

print(f"📄 در حال خواندن شیت: {target_sheet}")
df = pd.read_excel(EXCEL_PATH, sheet_name=target_sheet)
df['رتبه در سهمیه'] = pd.to_numeric(df['رتبه در سهمیه'], errors='coerce')
df = df.dropna(subset=['رتبه در سهمیه'])
df['سهمیه'] = pd.to_numeric(df['سهمیه'], errors='coerce').fillna(0).astype(int)
# =====================================================================
# 🗺 پایگاه داده ۳۲ استان و کلمات کلیدی اتصال دانشگاه به استان
# =====================================================================
PROVINCES_32 = [
    'تهران', 'خراسان رضوی', 'اصفهان', 'فارس', 'آذربایجان شرقی',
    'مازندران', 'خوزستان', 'گیلان', 'البرز', 'آذربایجان غربی',
    'کرمان', 'سیستان و بلوچستان', 'کرمانشاه', 'همدان', 'یزد',
    'قزوین', 'گلستان', 'لرستان', 'هرمزگان', 'زنجان',
    'بوشهر', 'قم', 'مرکزی', 'چهارمحال و بختیاری', 'کردستان',
    'خراسان جنوبی', 'خراسان شمالی', 'سمنان', 'ایلام',
    'کهگیلویه و بویراحمد', 'اردبیل', 'مناطق آزاد و سایر (کیش، قشم و...)'
]

PROVINCE_KEYWORDS = {
    'تهران': ['تهران', 'بهشتی', 'ایران', 'شاهد', 'بقیه الله', 'بقیه اله', 'تربیت مدرس', 'امیرکبیر', 'شریف', 'الزهرا', 'علوم وتحقیقات', 'علوم و تحقیقات', 'ورامین', 'اسلامشهر', 'شهرری', 'دماوند', 'فیروزکوه', 'پاکدشت', 'پردیس', 'قضایی'],
    'خراسان رضوی': ['خراسان رضوی', 'مشهد', 'سبزوار', 'نیشابور', 'تربت حیدریه', 'تربت جام', 'گناباد', 'کاشمر', 'قوچان', 'جوین', 'درگز', 'خلیل آباد', 'تایباد', 'سرخس', 'فردوسی', 'ثامن الحجج'],
    'اصفهان': ['اصفهان', 'کاشان', 'نجف آباد', 'خوراسگان', 'خمینی شهر', 'شهرضا', 'شاهین شهر', 'لنجان', 'فلاورجان', 'گلپایگان', 'نطنز', 'آران و بیدگل', 'نایین', 'سمیرم'],
    'فارس': ['فارس', 'شیراز', 'فسا', 'جهرم', 'کازرون', 'گراش', 'لارستان', 'لار', 'لامرد', 'آباده', 'داراب', 'فیروزآباد', 'ممسنی', 'مرودشت', 'استهبان', 'اقلید', 'نی ریز', 'ارسنجان'],
    'آذربایجان شرقی': ['آذربایجان شرقی', 'تبریز', 'مراغه', 'بناب', 'مرند', 'اهر', 'میانه', 'سراب', 'اسکو', 'جلفا', 'شبستر', 'ملکان', 'سهند', 'آذرشهر', 'مدنی آذربایجان'],
    'مازندران': ['مازندران', 'ساری', 'بابل', 'آمل', 'تنکابن', 'رامسر', 'چالوس', 'نوشهر', 'بهشهر', 'بابلسر', 'قائمشهر', 'نور', 'محمودآباد', 'جویبار', 'سوادکوه'],
    'خوزستان': ['خوزستان', 'اهواز', 'جندی شاپور', 'آبادان', 'خرمشهر', 'دزفول', 'بهبهان', 'شوشتر', 'مسجد سلیمان', 'رامهرمز', 'ماهشهر', 'ایذه', 'شوش', 'اندیمشک', 'بستان', 'چمران'],
    'گیلان': ['گیلان', 'رشت', 'لنگرود', 'لاهیجان', 'انزلی', 'فومن', 'آستارا', 'رودسر', 'صومعه سرا', 'تالش', 'رودبار', 'شرق استا'],
    'البرز': ['البرز', 'کرج', 'ساوجبلاغ', 'نظرآباد', 'طالقان', 'هشتگرد', 'فردیس', 'خوارزمی'],
    'آذربایجان غربی': ['آذربایجان غربی', 'ارومیه', 'خوی', 'مهاباد', 'بوکان', 'میاندوآب', 'سلماس', 'نقده', 'پیرانشهر', 'ماکو', 'سردشت', 'شاهین دژ', 'تکاب', 'چالدران', 'قاضی طباطبایی'],
    'کرمان': ['کرمان', 'رفسنجان', 'جیرفت', 'بم', 'سیرجان', 'کهنوج', 'زرند', 'بافت', 'شهربابک', 'بردسیر', 'عنبرآباد', 'باهنر'],
    'سیستان و بلوچستان': ['سیستان', 'بلوچستان', 'زاهدان', 'زابل', 'ایرانشهر', 'چابهار', 'سراوان', 'خاش', 'نیک شهر'],
    'کرمانشاه': ['کرمانشاه', 'سنقر', 'اسلام آباد غرب', 'کنگاور', 'صحنه', 'پاوه', 'جوانرود', 'سرپل ذهاب', 'رازی'],
    'همدان': ['همدان', 'ملایر', 'مالیر', 'نهاوند', 'اسدآباد', 'اسد اباد', 'تویسرکان', 'بوعلی', 'بهار', 'کبودرآهنگ'],
    'یزد': ['یزد', 'میبد', 'اردکان', 'بافق', 'مهریز', 'تفت', 'ابرکوه'],
    'قزوین': ['قزوین', 'تاکستان', 'بوئین زهرا', 'آبیک'],
    'گلستان': ['گلستان', 'گرگان', 'گنبد کاووس', 'گنبد', 'علی آباد کتول', 'علی آباد', 'بندر ترکمن', 'آق قلا', 'مینودشت', 'کردکوی'],
    'لرستان': ['لرستان', 'خرم آباد', 'خرم اباد', 'بروجرد', 'دورود', 'الیگودرز', 'کوهدشت', 'نورآباد', 'پلدختر', 'ازنا'],
    'هرمزگان': ['هرمزگان', 'بندرعباس', 'بندر عباس', 'قشم', 'کیش', 'میناب', 'بندرلنگه', 'جاسک', 'رودان', 'بستک'],
    'زنجان': ['زنجان', 'ابهر', 'خرمدره', 'خدابنده', 'قیدار'],
    'بوشهر': ['بوشهر', 'دشتستان', 'برازجان', 'کنگان', 'عسلویه', 'گناوه', 'دشتی', 'جم', 'دیلم', 'تنگستان'],
    'قم': ['قم', 'حضرت معصومه'],
    'مرکزی': ['مرکزی', 'اراک', 'ساوه', 'خمین', 'محلات', 'شازند', 'دلیجان', 'تفرش', 'آشتیان'],
    'چهارمحال و بختیاری': ['چهارمحال', 'بختیاری', 'شهرکرد', 'بروجن', 'فارسان', 'لردگان'],
    'کردستان': ['کردستان', 'سنندج', 'سقز', 'مریوان', 'بانه', 'قروه', 'بیجار'],
    'خراسان جنوبی': ['خراسان جنوبی', 'بیرجند', 'طبس', 'فردوس', 'قائن', 'قائنات', 'قاینات', 'نهبندان', 'سرایان', 'بشرویه'],
    'خراسان شمالی': ['خراسان شمالی', 'بجنورد', 'اسفراین', 'شیروان', 'مانه', 'سملقان', 'جاجرم'],
    'سمنان': ['سمنان', 'شاهرود', 'دامغان', 'گرمسار', 'مهدی شهر'],
    'ایلام': ['ایلام', 'ایالم', 'دهلران', 'ایوان', 'آبدانان', 'دره شهر', 'مهران'],
    'کهگیلویه و بویراحمد': ['کهگیلویه', 'بویراحمد', 'یاسوج', 'گچساران', 'دوگنبدان', 'دهدشت'],
    'اردبیل': ['اردبیل', 'محقق اردبیلی', 'مشکین شهر', 'پارس آباد', 'مغان', 'خلخال', 'گرمی'],
    'مناطق آزاد و سایر (کیش، قشم و...)': ['کیش', 'قشم', 'چابهار', 'ارس', 'انزلی آزاد', 'بین الملل']
}

def get_province_of_uni(uni_str):
    u = str(uni_str).replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ')
    for prov, kws in PROVINCE_KEYWORDS.items():
        for kw in kws:
            if kw in u:
                return prov
    return 'سایر دانشگاه‌ها'

df['استان'] = df['دانشگاه قبولی'].apply(get_province_of_uni)
print(f"✅ تعداد {len(df):,} ردیف داده با موفقیت بارگذاری و نگاشت استانی شد.")
# =====================================================================
# 📚 ۲۶ رشته هدف و کلمات کلیدی تطبیق
# =====================================================================
TARGET_MAJORS = [
    'پزشکی', 'دندانپزشکی', 'داروسازی', 'فیزیوتراپی', 'دامپزشکی',
    'شنواییسنجی', 'گفتاردرمانی', 'اعضای مصنوعی', 'بیناییسنجی', 'پرستاری',
    'مامایی', 'اتاق عمل', 'هوشبری', 'رادیولوژی', 'پرتودرمانی',
    'پزشکی هستهای', 'علوم آزمایشگاهی', 'علوم تغذیه', 'فوریتهای پزشکی',
    'فناوری اطلاعات سلامت', 'کتابداری پزشکی', 'بهداشت حرفهای',
    'بهداشت محیط', 'بهداشت عمومی', 'زیست سلولی-مولکولی', 'علوم دامی'
]

MAJOR_ALIASES = {
    'پزشکی': ['پزشکی', 'پزشكی', 'دکتری عمومی'],
    'دندانپزشکی': ['دندانپزشکی', 'دندان‌پزشکی', 'دندان پزشکی', 'دندان'],
    'داروسازی': ['داروسازی', 'دارو‌سازی', 'دارو سازی', 'دارو'],
    'فیزیوتراپی': ['فیزیوتراپی', 'فیزیو تراپی', 'فیزیو'],
    'دامپزشکی': ['دامپزشکی', 'دام‌پزشکی', 'دام پزشکی', 'دامپزشک'],
    'شنواییسنجی': ['شنوایی سنجی', 'شنوایی شناسی', 'شنوایی', 'شنواییسنجی'],
    'گفتاردرمانی': ['گفتار درمانی', 'گفتاردرمانی', 'گفتار'],
    'اعضای مصنوعی': ['اعضای مصنوعی', 'ارتوز و پروتز', 'پروتز', 'اعضای‌مصنوعی'],
    'بیناییسنجی': ['بینایی سنجی', 'بینایی شناسی', 'بینایی', 'بیناییسنجی', 'اپتومتری'],
    'پرستاری': ['پرستاری', 'پرستار'],
    'مامایی': ['مامایی', 'ماما'],
    'اتاق عمل': ['اتاق عمل', 'اتاق‌عمل', 'تکنولوژی اتاق عمل'],
    'هوشبری': ['هوشبری', 'بیهوشی'],
    'رادیولوژی': ['رادیولوژی', 'پرتوشناسی', 'پرتو شناسی', 'رادیو'],
    'پرتودرمانی': ['پرتودرمانی', 'پرتو درمانی', 'رادیوتراپی'],
    'پزشکی هستهای': ['پزشکی هسته ای', 'پزشکی هسته‌ای', 'پزشکی هستهای', 'هسته ای'],
    'علوم آزمایشگاهی': ['علوم آزمایشگاهی', 'علوم ازمایشگاهی', 'آزمایشگاه', 'ازمایشگاه'],
    'علوم تغذیه': ['علوم تغذیه', 'تغذیه'],
    'فوریتهای پزشکی': ['فوریت های پزشکی', 'فوریت‌های پزشکی', 'فوریتهای پزشکی', 'فوریتها', 'فوریت'],
    'فناوری اطلاعات سلامت': ['فناوری اطلاعات سلامت', 'اطلاعات سلامت', 'مدارک پزشکی', 'hit'],
    'کتابداری پزشکی': ['کتابداری پزشکی', 'کتابداری', 'اطلاع رسانی پزشکی'],
    'بهداشت حرفهای': ['بهداشت حرفه ای', 'بهداشت حرفه‌ای', 'بهداشت حرفهای', 'ایمنی کار'],
    'بهداشت محیط': ['بهداشت محیط', 'محیط'],
    'بهداشت عمومی': ['بهداشت عمومی'],
    'زیست سلولی-مولکولی': ['زیست سلولی', 'سلولی مولکولی', 'سلولی و مولکولی', 'سلولی', 'ژنتیک'],
    'علوم دامی': ['علوم دامی', 'دامپروری']
}

def match_major_in_name(major_target, r_name):
    target_clean = major_target.replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ')
    name_clean = str(r_name).replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ')
    
    if target_clean == 'پزشکی':
        if any(x in name_clean for x in ['دندان', 'دام', 'هسته']):
            return False
        return 'پزشکی' in name_clean
    elif target_clean == 'دندانپزشکی':
        return any(x in name_clean for x in ['دندانپزشکی', 'دندان پزشکی', 'دندان'])
    elif target_clean == 'دامپزشکی':
        return any(x in name_clean for x in ['دامپزشکی', 'دام پزشکی', 'دامپزشک'])
    elif target_clean == 'پزشکی هستهای':
        return any(x in name_clean for x in ['پزشکی هسته', 'هسته ای', 'هستهای'])
    elif target_clean == 'رادیولوژی':
        return any(x in name_clean for x in ['رادیولوژی', 'پرتوشناسی', 'پرتو شناسی'])
    else:
        return target_clean in name_clean

# =====================================================================
# 📐 الگوریتم نمره‌دهی خطی، ضرایب دوره و رفع بن‌بست تساوی
# =====================================================================
def calculate_linear_scores(items_list):
    n = len(items_list)
    if n == 0:
        return {}
    if n == 1:
        return {items_list[0]: 10.0}
    scores = {}
    for rank_idx, item in enumerate(items_list):
        rank = rank_idx + 1 # 1 تا N
        score = 1.0 + ((n - rank) / (n - 1)) * 9.0
        scores[item] = round(score, 2)
    return scores

def detect_doreh_and_multiplier(row):
    d = str(row.get('دوره', '')).strip()
    u = str(row.get('دانشگاه قبولی', '')).strip()
    combined = f"{d} {u}".replace('ي', 'ی').replace('ك', 'ک')
    
    if any(k in combined for k in ['شهریه پرداز', 'شهریه‌پرداز', 'پردیس', 'خودگردان', 'مازاد']):
        return 'پردیس خودگردان / شهریه‌پرداز', 0.85
    elif any(k in combined for k in ['آزاد', 'دانشگاه آزاد', 'آزاداسلامی']):
        return 'دانشگاه آزاد اسلامی', 0.75
    elif any(k in combined for k in ['غیرانتفاعی', 'غیر دولتی', 'پیام نور']):
        return 'غیرانتفاعی / پیام‌نور', 0.70
    elif any(k in combined for k in ['نوبت دوم', 'شبانه']):
        return 'نوبت دوم (شبانه)', 0.95
    elif any(k in combined for k in ['تعهدی', 'مناطق محروم', 'محروم']):
        return 'تعهدی / مناطق محروم', 0.90
    else:
        return 'روزانه (دولتی رایگان)', 1.00

def parse_items_with_optional_scores(text, alias_dict):
    t = text.replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ')
    if any(k in t for k in ['همه', 'جامع', 'سراسر', 'کل کشور', 'تمام']):
        return ['همه'], {}
        
    tokens = re.split(r'[,،;\n]+', t)
    items = []
    scores = {}
    
    for token in tokens:
        sub = token.strip()
        if not sub:
            continue
        num_match = re.search(r'(10(?:\.0+)?|[1-9](?:\.\d+)?)', sub)
        score_val = None
        if num_match:
            try:
                score_val = float(num_match.group(1))
                sub_name = sub[:num_match.start()] + sub[num_match.end():]
            except Exception:
                sub_name = sub
        else:
            sub_name = sub
            
        matched_item = None
        for canon, aliases in alias_dict.items():
            if any(a in sub_name for a in aliases):
                if canon == 'پزشکی' and any(x in sub_name for x in ['دندان', 'دام', 'هسته']):
                    continue
                matched_item = canon
                break
                
        if matched_item and matched_item not in items:
            items.append(matched_item)
            if score_val is not None:
                scores[matched_item] = round(score_val, 2)
                
    if not items:
        for canon, aliases in alias_dict.items():
            for a in aliases:
                idx = t.find(a)
                if idx != -1:
                    if canon == 'پزشکی':
                        prefix = t[max(0, idx-10):idx]
                        suffix = t[idx:idx+15]
                        if any(x in prefix for x in ['دندان', 'دام']) or any(x in suffix for x in ['هسته']):
                            continue
                    if canon not in items:
                        items.append(canon)
                    break
                    
    return items, scores

bot = telebot.TeleBot(TOKEN)
user_state = {}

def to_persian_num(n):
    p_digits = '۰۱۲۳۴۵۶۷۸۹'
    res = ''
    for char in str(n):
        if char in p_digits:
            res += char
        elif char.isdigit():
            res += p_digits[int(char)]
        else:
            res += char
    return res
# =====================================================================
# ⌨️ کیبوردهای تعاملی اینلاین
# =====================================================================
def get_region_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("منطقه ۱", callback_data="reg_1"),
        types.InlineKeyboardButton("منطقه ۲", callback_data="reg_2"),
        types.InlineKeyboardButton("منطقه ۳", callback_data="reg_3")
    )
    return markup

def get_source_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🌐 همه با هم (پایگاه تجمیعی کامل)", callback_data="src_all"),
        types.InlineKeyboardButton("📋 کارنامه‌های قبولی (قلم‌چی و گزینه ۲)", callback_data="src_kanoon"),
        types.InlineKeyboardButton("📊 مرجع جامع کشوری (سنجش و دانشگاه‌ها)", callback_data="src_ref")
    )
    return markup

def build_majors_keyboard(selected_list):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🔍 همه رشته‌ها (جامع)", callback_data="maj_all"))
    
    buttons = []
    for idx, name in enumerate(TARGET_MAJORS):
        if name in selected_list:
            prio = selected_list.index(name) + 1
            btn_text = f"✅ {to_persian_num(prio)}. {name}"
        else:
            btn_text = name
        buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"maj_toggle_{idx}"))
        
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            markup.add(buttons[i], buttons[i+1])
        else:
            markup.add(buttons[i])
            
    cnt = len(selected_list)
    confirm_text = f"✅ تایید و مرحله بعد ({to_persian_num(cnt)} رشته)" if cnt > 0 else "✅ تایید رشته‌ها"
    markup.add(
        types.InlineKeyboardButton(confirm_text, callback_data="maj_confirm"),
        types.InlineKeyboardButton("🗑 پاک کردن انتخاب‌ها", callback_data="maj_clear")
    )
    return markup

def build_provinces_keyboard(selected_list):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🌐 سراسر کشور (تمام استان‌ها)", callback_data="prov_all"))
    
    buttons = []
    for idx, name in enumerate(PROVINCES_32):
        if name in selected_list:
            prio = selected_list.index(name) + 1
            btn_text = f"✅ {to_persian_num(prio)}. {name}"
        else:
            btn_text = name
        buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"prov_toggle_{idx}"))
        
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            markup.add(buttons[i], buttons[i+1])
        else:
            markup.add(buttons[i])
            
    cnt = len(selected_list)
    confirm_text = f"✅ محاسبه امتیاز و مشاهده نتایج ({to_persian_num(cnt)} استان)" if cnt > 0 else "✅ تایید و محاسبه نتایج"
    markup.add(
        types.InlineKeyboardButton(confirm_text, callback_data="prov_confirm"),
        types.InlineKeyboardButton("🗑 پاک کردن استان‌ها", callback_data="prov_clear")
    )
    return markup
# =====================================================================
# 🚀 هندلرهای رویدادها و کلیک‌ها
# =====================================================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    chat_id = message.chat.id
    user_state[chat_id] = {
        'step': 'select_region',
        'selected_majors': [],
        'major_scores': {},
        'selected_provinces': [],
        'prov_scores': {}
    }
    
    welcome_text = (
        "👋 **به ربات هوشمند انتخاب رشته تجربی خوش آمدید!**\n\n"
        "✨ **سیستم امتیازدهی و اولویت‌بندی اختصاصی:**\n"
        "▫️ **نمره‌دهی خطی (۱ تا ۱۰):** تبدیل خودکار اولویت رشته‌ها و شهرها به نمره دقیق ۱۰\n"
        "▫️ **فرمول ارزیابی جامع:** `(امتیاز رشته × ۱.۲) + (امتیاز شهر × ۱.۰)`\n"
        "▫️ **ضریب تعدیل دوره:** روزانه (۱.۰)، پردیس (۰.۸۵)، آزاد (۰.۷۵) و شبانه (۰.۹۵)\n"
        "▫️ **قانون رفع تساوی (Tie-Breaker):** در امتیازهای برابر، اولویت با رشته و سپس رتبه بهتر است.\n"
        "▫️ بازه تحلیلی: **۳۰٪ خوش‌بینانه** تا **۲۵٪ بدبینانه (حاشیه امن)**\n\n"
        "📍 **لطفاً سهمیه منطقه خود را انتخاب فرمایید:**"
    )
    bot.send_message(chat_id, welcome_text, parse_mode='Markdown', reply_markup=get_region_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith('reg_'))
def callback_region(call):
    chat_id = call.message.chat.id
    reg_num = int(call.data.split('_')[1])
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
    user_state[chat_id]['region'] = reg_num
    user_state[chat_id]['step'] = 'enter_rank'
    
    bot.answer_callback_query(call.id, f"منطقه {reg_num} انتخاب شد.")
    bot.edit_message_text(
        f"✅ سهمیه **منطقه {reg_num}** ثبت شد.\n\n"
        "🎯 لطفاً **رتبه در سهمیه** خود را به‌صورت عدد ارسال فرمایید (مثلاً: `6500`):",
        chat_id=chat_id,
        message_id=call.message.message_id,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('src_'))
def callback_source(call):
    chat_id = call.message.chat.id
    src_key = call.data.split('_')[1]
    
    source_map = {
        'all': ('همه', '🌐 همه با هم (پایگاه تجمیعی کامل)'),
        'kanoon': ('کارنامه', '📋 کارنامه‌های قبولی (قلم‌چی و گزینه ۲)'),
        'ref': ('مرجع جامع', '📊 مرجع جامع کشوری (سنجش و دانشگاه‌ها)')
    }
    src_code, src_label = source_map.get(src_key, ('همه', '🌐 همه با هم'))
    
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
    user_state[chat_id]['source'] = src_code
    user_state[chat_id]['source_label'] = src_label
    user_state[chat_id]['selected_majors'] = []
    user_state[chat_id]['major_scores'] = {}
    user_state[chat_id]['step'] = 'select_majors'
    
    bot.answer_callback_query(call.id, "منبع انتخاب شد.")
    send_majors_selection_prompt(chat_id, message_id=call.message.message_id)

def send_majors_selection_prompt(chat_id, message_id=None):
    selected = user_state[chat_id].get('selected_majors', [])
    manual_sc = user_state[chat_id].get('major_scores', {})
    if selected:
        calc_sc = manual_sc if manual_sc else calculate_linear_scores(selected)
        majors_txt = "\n".join([f"  {to_persian_num(i+1)}. {m}  *(نمره: {to_persian_num(calc_sc.get(m, 10.0))} از ۱۰)*" for i, m in enumerate(selected)])
        summary = f"\n\n📋 **رشته‌های انتخابی و نمرات محاسبه‌شده (۱ تا ۱۰):**\n{majors_txt}\n\n💡 برای افزودن/حذف کلیک کنید یا دکمه «تایید» را بزنید."
    else:
        summary = "\n\n📋 **رشته‌های انتخاب‌شده:** (هنوز رشته‌ای انتخاب نشده است)"
        
    msg_text = (
        f"✅ منبع استعلام: **{user_state[chat_id].get('source_label', 'همه')}**\n\n"
        "📚 **مرحله ۱: انتخاب رشته‌ها به ترتیب علاقه (از ۱ تا N):**\n"
        "▫️ روی رشته‌ها کلیک کنید تا به ترتیب اولویت تیک سبز بخورند.\n"
        "▫️ **سیستم خودکار نمره‌دهی خطی:** رتبه اول دقیقاً نمره ۱۰، رتبه آخر نمره ۱ و مابقی متناسب با ترتیب اولویت نمره‌گذاری می‌شوند.\n"
        "▫️ همچنین می‌توانید نام رشته‌ها را در چت تایپ فرمایید (یا به همراه نمره دستی، مثلاً: `پزشکی: 10، دندان: 8.5`)."
        f"{summary}"
    )
    keyboard = build_majors_keyboard(selected)
    if message_id:
        try:
            bot.edit_message_text(msg_text, chat_id=chat_id, message_id=message_id, parse_mode='Markdown', reply_markup=keyboard)
            return
        except Exception:
            try:
                bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
                return
            except Exception:
                pass
    bot.send_message(chat_id, msg_text, parse_mode='Markdown', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('maj_'))
def callback_major_action(call):
    chat_id = call.message.chat.id
    action = call.data[4:]
    
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
        
    selected = user_state[chat_id].get('selected_majors', [])
    
    if action == 'all':
        user_state[chat_id]['selected_majors'] = ['همه رشته‌ها']
        user_state[chat_id]['major_scores'] = {}
        bot.answer_callback_query(call.id, "همه رشته‌ها انتخاب شد.")
        proceed_to_provinces_step(chat_id, message_id=call.message.message_id)
        return
    elif action == 'clear':
        user_state[chat_id]['selected_majors'] = []
        user_state[chat_id]['major_scores'] = {}
        bot.answer_callback_query(call.id, "انتخاب‌ها پاک شد.")
        send_majors_selection_prompt(chat_id, message_id=call.message.message_id)
        return
    elif action == 'confirm':
        if not selected:
            user_state[chat_id]['selected_majors'] = ['همه رشته‌ها']
        bot.answer_callback_query(call.id, "رشته‌ها تایید شدند.")
        proceed_to_provinces_step(chat_id, message_id=call.message.message_id)
        return
    elif action.startswith('toggle_'):
        idx = int(action.split('_')[1])
        major_name = TARGET_MAJORS[idx]
        if major_name in selected:
            selected.remove(major_name)
            bot.answer_callback_query(call.id, f"حذف شد: {major_name}")
        else:
            selected.append(major_name)
            bot.answer_callback_query(call.id, f"اولویت {len(selected)}: {major_name}")
        user_state[chat_id]['selected_majors'] = selected
        user_state[chat_id]['major_scores'] = {}
        send_majors_selection_prompt(chat_id, message_id=call.message.message_id)

def proceed_to_provinces_step(chat_id, message_id=None):
    user_state[chat_id]['step'] = 'select_provinces'
    user_state[chat_id]['selected_provinces'] = []
    user_state[chat_id]['prov_scores'] = {}
    send_provinces_selection_prompt(chat_id, message_id=message_id)

def send_provinces_selection_prompt(chat_id, message_id=None):
    selected_majors = user_state[chat_id].get('selected_majors', ['همه رشته‌ها'])
    maj_summary = ", ".join(selected_majors[:4])
    if len(selected_majors) > 4:
        maj_summary += f" و {to_persian_num(len(selected_majors)-4)} رشته دیگر"
        
    selected = user_state[chat_id].get('selected_provinces', [])
    manual_sc = user_state[chat_id].get('prov_scores', {})
    if selected:
        calc_sc = manual_sc if manual_sc else calculate_linear_scores(selected)
        prov_txt = "\n".join([f"  {to_persian_num(i+1)}. {p}  *(نمره: {to_persian_num(calc_sc.get(p, 10.0))} از ۱۰)*" for i, p in enumerate(selected)])
        summary = f"\n\n🗺 **استان‌های انتخابی و نمرات محاسبه‌شده (۱ تا ۱۰):**\n{prov_txt}\n\n💡 برای ادامه دکمه «محاسبه امتیاز و مشاهده نتایج» را بزنید."
    else:
        summary = "\n\n🗺 **استان‌های انتخاب‌شده:** (هنوز استانی انتخاب نشده است)"
        
    msg_text = (
        f"🎯 **رشته‌های انتخابی:** {maj_summary}\n\n"
        "🗺 **مرحله ۲: اولویت‌بندی شهرها و استان‌ها (از ۱ تا M):**\n"
        "▫️ استان‌ها را به ترتیب ترجیح سکونت خود انتخاب کنید تا نمره خطی ۱ تا ۱۰ به آن‌ها تعلق گیرد.\n"
        "▫️ می‌توانید نام استان‌ها یا شهرها را در چت تایپ فرمایید (یا به همراه نمره دستی، مثلاً: `تهران: 10، مشهد: 8`).\n"
        "▫️ برای بررسی تمام استان‌ها، «سراسر کشور» را بزنید."
        f"{summary}"
    )
    keyboard = build_provinces_keyboard(selected)
    if message_id:
        try:
            bot.edit_message_text(msg_text, chat_id=chat_id, message_id=message_id, parse_mode='Markdown', reply_markup=keyboard)
            return
        except Exception:
            try:
                bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
                return
            except Exception:
                pass
    bot.send_message(chat_id, msg_text, parse_mode='Markdown', reply_markup=keyboard)

# =====================================================================
# 🗺 هندلر کلیک‌های استان‌ها (Province Callback Handlers)
# =====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('prov_'))
def callback_province_action(call):
    chat_id = call.message.chat.id
    action = call.data[5:]
    
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
        
    selected = user_state[chat_id].get('selected_provinces', [])
    
    if action == 'all':
        user_state[chat_id]['selected_provinces'] = ['سراسر کشور']
        user_state[chat_id]['prov_scores'] = {}
        bot.answer_callback_query(call.id, "سراسر کشور انتخاب شد.")
        execute_search_and_send(chat_id)
        return
    elif action == 'clear':
        user_state[chat_id]['selected_provinces'] = []
        user_state[chat_id]['prov_scores'] = {}
        bot.answer_callback_query(call.id, "استان‌ها پاک شدند.")
        send_provinces_selection_prompt(chat_id, message_id=call.message.message_id)
        return
    elif action == 'confirm':
        if not selected:
            user_state[chat_id]['selected_provinces'] = ['سراسر کشور']
        bot.answer_callback_query(call.id, "در حال محاسبه امتیازات...")
        execute_search_and_send(chat_id)
        return
    elif action.startswith('toggle_'):
        idx = int(action.split('_')[1])
        prov_name = PROVINCES_32[idx]
        if prov_name in selected:
            selected.remove(prov_name)
            bot.answer_callback_query(call.id, f"حذف شد: {prov_name}")
        else:
            selected.append(prov_name)
            bot.answer_callback_query(call.id, f"اولویت {len(selected)}: {prov_name}")
        user_state[chat_id]['selected_provinces'] = selected
        user_state[chat_id]['prov_scores'] = {}
        send_provinces_selection_prompt(chat_id, message_id=call.message.message_id)
# General Text Handler (Rank input or Typed Majors/Provinces with optional scores)
@bot.message_handler(func=lambda msg: True)
def text_input_handler(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    if chat_id not in user_state:
        user_state[chat_id] = {'step': 'select_region', 'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
        
    step = user_state[chat_id].get('step', 'select_region')
    
    if step == 'enter_rank':
        persian_digits = '۰۱۲۳۴۵۶۷۸۹'
        t_clean = text.replace(',', '')
        for i, p in enumerate(persian_digits):
            t_clean = t_clean.replace(p, str(i))
            
        if t_clean.isdigit():
            rank = int(t_clean)
            if 0 < rank <= 300000:
                user_state[chat_id]['rank'] = rank
                user_state[chat_id]['step'] = 'select_source'
                prompt_text = (
                    f"✅ رتبه **{rank:,}** (منطقه {user_state[chat_id].get('region', 2)}) ثبت گردید.\n\n"
                    "🔍 **مایلید استعلام قبولی‌ها بر اساس کدام پایگاه داده انجام شود؟**"
                )
                bot.send_message(chat_id, prompt_text, parse_mode='Markdown', reply_markup=get_source_keyboard())
                return
            else:
                bot.send_message(chat_id, "⚠️ رتبه وارد شده در محدوده معتبر نیست. لطفاً مجدداً رتبه را وارد فرمایید:")
                return
        else:
            bot.send_message(chat_id, "⚠️ لطفاً فقط مقدار عددی رتبه را ارسال فرمایید (مثلاً: 6500):")
            return
            
    if step == 'select_majors':
        parsed_m, manual_m_sc = parse_items_with_optional_scores(text, MAJOR_ALIASES)
        if parsed_m:
            user_state[chat_id]['selected_majors'] = parsed_m
            user_state[chat_id]['major_scores'] = manual_m_sc
            m_str = "، ".join(parsed_m)
            bot.send_message(chat_id, f"✅ **{to_persian_num(len(parsed_m))} رشته بر اساس اولویت ارسالی شما ثبت شد:**\n{m_str}")
            proceed_to_provinces_step(chat_id)
            return
        else:
            bot.send_message(chat_id, "⚠️ رشته‌ای از متن شما شناسایی نشد. لطفاً از دکمه‌های زیر انتخاب فرمایید:")
            send_majors_selection_prompt(chat_id)
            return
            
    if step == 'select_provinces':
        parsed_p, manual_p_sc = parse_items_with_optional_scores(text, PROVINCE_KEYWORDS)
        if parsed_p:
            user_state[chat_id]['selected_provinces'] = parsed_p
            user_state[chat_id]['prov_scores'] = manual_p_sc
            p_str = "، ".join(parsed_p)
            bot.send_message(chat_id, f"✅ **{to_persian_num(len(parsed_p))} استان بر اساس اولویت ارسالی شما ثبت شد:**\n{p_str}")
            execute_search_and_send(chat_id)
            return
        else:
            bot.send_message(chat_id, "⚠️ استانی از متن شما شناسایی نشد. لطفاً از دکمه‌های زیر انتخاب فرمایید:")
            send_provinces_selection_prompt(chat_id)
            return
            
    bot.send_message(chat_id, "💡 برای شروع استعلام انتخاب رشته، دستور /start را ارسال فرمایید.")

# =====================================================================
# 🔍 مرحله ۳: فرمول محاسباتی، شکستن تساوی و تولید فایل اکسل خروجی
# =====================================================================
def execute_search_and_send(chat_id):
    state = user_state.get(chat_id, {})
    rank = state.get('rank', 5000)
    region = state.get('region', 2)
    src_filter = state.get('source', 'همه')
    src_label = state.get('source_label', '🌐 همه با هم')
    selected_majors = state.get('selected_majors', ['همه رشته‌ها'])
    manual_major_scores = state.get('major_scores', {})
    selected_provinces = state.get('selected_provinces', ['سراسر کشور'])
    manual_prov_scores = state.get('prov_scores', {})
    
    min_rank = int(rank * 0.70)
    max_rank = int(rank * 1.25)
    
    sub_df = df.copy()
    if src_filter == 'مرجع جامع':
        sub_df = sub_df[sub_df['منبع'].str.contains('مرجع جامع', na=False)]
    elif src_filter == 'کارنامه':
        sub_df = sub_df[sub_df['منبع'].str.contains('کارنامه', na=False)]
        
    filtered = sub_df[
        (sub_df['سهمیه'] == region) & 
        (sub_df['رتبه در سهمیه'] >= min_rank) & 
        (sub_df['رتبه در سهمیه'] <= max_rank)
    ].copy()
    
    # 1. فیلتر رشته
    if selected_majors and 'همه رشته‌ها' not in selected_majors and 'همه' not in selected_majors:
        cond = False
        for m in selected_majors:
            cond = cond | filtered['رشته قبولی'].apply(lambda r: match_major_in_name(m, r))
        filtered = filtered[cond]
        
    # 2. فیلتر استان
    if selected_provinces and 'سراسر کشور' not in selected_provinces and 'همه' not in selected_provinces:
        filtered = filtered[filtered['استان'].isin(selected_provinces)]
        
    if filtered.empty:
        restart_markup = types.InlineKeyboardMarkup()
        restart_markup.add(types.InlineKeyboardButton("🔄 استعلام مجدد", callback_data="restart"))
        msg_text = (
            f"❌ در بازه رتبه‌ای **{min_rank:,}** الی **{max_rank:,}** (سهمیه منطقه {region})\n"
            f"قبولی متناسب با رشته‌ها و استان‌های انتخابی شما در این منبع یافت نشد.\n\n"
            "💡 پیشنهاد می‌شود تعداد استان‌ها یا رشته‌ها را گسترش دهید."
        )
        bot.send_message(chat_id, msg_text, parse_mode='Markdown', reply_markup=restart_markup)
        return

    # 3. محاسبه نمرات ۱ تا ۱۰ (دستی یا نرمال‌سازی خطی)
    major_scores = manual_major_scores if manual_major_scores else (
        calculate_linear_scores(selected_majors) if 'همه رشته‌ها' not in selected_majors and 'همه' not in selected_majors else {}
    )
    prov_scores = manual_prov_scores if manual_prov_scores else (
        calculate_linear_scores(selected_provinces) if 'سراسر کشور' not in selected_provinces and 'همه' not in selected_provinces else {}
    )
    
    def get_m_score(r_name):
        if not major_scores:
            for idx, tm in enumerate(TARGET_MAJORS):
                if match_major_in_name(tm, r_name):
                    return round(1.0 + ((len(TARGET_MAJORS) - (idx + 1)) / (len(TARGET_MAJORS) - 1)) * 9.0, 2)
            return 3.0
        for m, sc in major_scores.items():
            if match_major_in_name(m, r_name):
                return sc
        return 1.0
        
    def get_p_score(p_name):
        return prov_scores.get(p_name, 5.0)
        
    filtered['نمره_رشته'] = filtered['رشته قبولی'].apply(get_m_score)
    filtered['نمره_استان'] = filtered['استان'].apply(get_p_score)
    
    # 4. تشخیص دوره و ضریب تعدیل هزینه‌ای
    doreh_info = filtered.apply(detect_doreh_and_multiplier, axis=1)
    filtered['دوره_تطبیقی'] = [x[0] for x in doreh_info]
    filtered['ضریب_دوره'] = [x[1] for x in doreh_info]
    
    # 5. فرمول ارزیابی و امتیاز کل: (Major * 1.2 + City * 1.0) * Doreh_Multiplier
    filtered['نمره_پایه'] = (filtered['نمره_رشته'] * 1.2) + (filtered['نمره_استان'] * 1.0)
    filtered['امتیاز_کل'] = (filtered['نمره_پایه'] * filtered['ضریب_دوره']).round(2)
    
    # 6. شکستن تساوی (Tie-Breaking Rule) و مرتب‌سازی نهایی نزولی:
    filtered.sort_values(
        by=['امتیاز_کل', 'نمره_رشته', 'نمره_استان', 'رتبه در سهمیه'],
        ascending=[False, False, False, True],
        inplace=True
    )
    filtered.reset_index(drop=True, inplace=True)
    filtered['ترتیب_اولویت'] = range(1, len(filtered) + 1)
    
    total_count = len(filtered)
    majors_disp = "، ".join(selected_majors[:4]) + (f" و {to_persian_num(len(selected_majors)-4)} مورد دیگر" if len(selected_majors) > 4 else "")
    provs_disp = "، ".join(selected_provinces[:4]) + (f" و {to_persian_num(len(selected_provinces)-4)} مورد دیگر" if len(selected_provinces) > 4 else "")
    
    header_text = (
        f"📊 **لیست اولویت‌بندی شده انتخاب رشته بر اساس الگوریتم تصمیم‌گیری چندمعیاره:**\n"
        f"👤 **سهمیه:** منطقه {region} | **رتبه داوطلب:** {rank:,}\n"
        f"🎯 **بازه تحلیلی:** ۳۰٪ خوش‌بینانه ({min_rank:,}) تا ۲۵٪ بدبینانه ({max_rank:,})\n"
        f"📂 **منبع داده:** {src_label}\n"
        f"🎓 **رشته‌ها:** {majors_disp}\n"
        f"🗺 **استان‌ها:** {provs_disp}\n"
        f"📌 **تعداد کل گزینه‌های یافت‌شده:** {total_count:,} رشته‌محل\n"
        f"⚖️ **فرمول رتبه‌بندی:** `(نمره رشته × ۱.۲ + نمره شهر × ۱.۰) × ضریب دوره`\n"
        f"{'='*32}\n\n"
    )
    
    messages = []
    current_msg = header_text
    display_limit = 25
    
    for idx, (_, row) in enumerate(filtered.iterrows()):
        if idx >= display_limit:
            break
        r_val = int(row['رتبه در سهمیه'])
        if r_val < rank * 0.95:
            chance = "🎯 خوش‌بینانه"
        elif r_val <= rank * 1.05:
            chance = "⚖️ محتمل و منطقی"
        else:
            chance = "🛡️ شانس بالا"
            
        entry = (
            f"🏅 **رتبه اولویت {to_persian_num(row['ترتیب_اولویت'])}:** **{row['رشته قبولی']}** | {row['دوره_تطبیقی']}\n"
            f"🏛 {row['دانشگاه قبولی']} ({row['استان']})\n"
            f"⭐️ **امتیاز کل:** `{row['امتیاز_کل']}` *(رشته: {row['نمره_رشته']} | شهر: {row['نمره_استان']} | ضریب دوره: {row['ضریب_دوره']})*\n"
            f"📈 آخرین رتبه قبولی: `{r_val:,}` ({chance})\n"
            f"{'-'*28}\n"
        )
        if len(current_msg) + len(entry) > 3800:
            messages.append(current_msg)
            current_msg = entry
        else:
            current_msg += entry
            
    if current_msg:
        messages.append(current_msg)
        
    for msg in messages:
        bot.send_message(chat_id, msg, parse_mode='Markdown')
        
    if total_count > display_limit:
        bot.send_message(
            chat_id, 
            f"⚠️ جهت راحتی مطالعه، {display_limit} گزینه برتر در بالا نمایش داده شد.\n"
            f"⏳ در حال آماده‌سازی فایل اکسل کامل آماده پرینت و انتخاب رشته شامل تمام **{total_count:,}** کدرشته‌محل..."
        )
        
    excel_buffer = io.BytesIO()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "اولویت‌بندی انتخاب رشته"
    ws.views.sheetView[0].rightToLeft = True
    
    font_name = 'B Nazanin'
    h_font = Font(name=font_name, size=11, bold=True, color='FFFFFF')
    h_fill = PatternFill(start_color='002060', end_color='002060', fill_type='solid')
    d_font = Font(name=font_name, size=11, color='000000')
    d_bold_font = Font(name=font_name, size=11, bold=True, color='002060')
    alt_fill = PatternFill(start_color='F2F5F9', end_color='F2F5F9', fill_type='solid')
    t_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    al_center = Alignment(horizontal='center', vertical='center')
    al_right = Alignment(horizontal='right', vertical='center', indent=1)
    
    headers = [
        'اولویت پیشنهادی', 'رشته قبولی', 'دانشگاه قبولی', 'استان', 'دوره تحصیلی',
        'امتیاز کل اولویت', 'نمره رشته (۱-۱۰)', 'نمره شهر (۱-۱۰)', 'ضریب دوره',
        'رتبه در سهمیه', 'رتبه کشوری', 'منبع و سال', 'ارزیابی شانس'
    ]
    ws.append(headers)
    ws.row_dimensions[1].height = 28
    for col_idx in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col_idx)
        c.font = h_font
        c.fill = h_fill
        c.alignment = al_center
        c.border = t_border
        
    for r_idx, (_, r) in enumerate(filtered.iterrows(), 2):
        r_val = int(r['رتبه در سهمیه'])
        if r_val < rank * 0.95:
            chance_text = "خوش‌بینانه (تا ۳۰٪)"
        elif r_val <= rank * 1.05:
            chance_text = "محتمل و منطقی"
        else:
            chance_text = "شانس بالا (حاشیه امن)"
            
        row_data = [
            r['ترتیب_اولویت'],
            r['رشته قبولی'],
            r['دانشگاه قبولی'],
            r['استان'],
            r['دوره_تطبیقی'],
            r['امتیاز_کل'],
            r['نمره_رشته'],
            r['نمره_استان'],
            r['ضریب_دوره'],
            r_val,
            r.get('رتبه کشوری', '-'),
            r.get('منبع', '-'),
            chance_text
        ]
        ws.append(row_data)
        ws.row_dimensions[r_idx].height = 22
        fill = alt_fill if r_idx % 2 == 1 else None
        
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=r_idx, column=col_idx)
            cell.font = d_bold_font if col_idx == 6 else d_font
            cell.border = t_border
            if fill:
                cell.fill = fill
            h_name = headers[col_idx - 1]
            if h_name in ['اولویت پیشنهادی', 'استان', 'امتیاز کل اولویت', 'نمره رشته (۱-۱۰)', 'نمره شهر (۱-۱۰)', 'ضریب دوره', 'رتبه در سهمیه', 'رتبه کشوری', 'ارزیابی شانس']:
                cell.alignment = al_center
                if isinstance(val, (int, float)) and val > 0:
                    if isinstance(val, float):
                        cell.number_format = '0.00'
                    else:
                        cell.number_format = '#,##0'
            else:
                cell.alignment = al_right

    for col in ws.columns:
        max_l = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_l + 4, 13)
        
    wb.save(excel_buffer)
    excel_buffer.seek(0)
    
    file_title = f"اولویت_بندی_انتخاب_رشته_رتبه_{rank}_منطقه_{region}.xlsx"
    restart_markup = types.InlineKeyboardMarkup()
    restart_markup.add(types.InlineKeyboardButton("🔄 استعلام جدید", callback_data="restart"))
    
    bot.send_document(
        chat_id, 
        excel_buffer, 
        visible_file_name=file_title, 
        caption=f"📁 **فایل اکسل فرمول‌بندی شده انتخاب رشته رتبه {rank:,} (منطقه {region})**\n\n📌 شامل رتبه‌بندی دقیق از بالاترین نمره به پایین‌ترین نمره طبق فرمول اولویت، نمرات رشته، شهر و ضریب دوره.",
        parse_mode='Markdown'
    )
    bot.send_message(chat_id, "💡 برای ارزیابی رتبه یا اولویت‌های دیگر، دکمه زیر را لمس فرمایید:", reply_markup=restart_markup)

@bot.callback_query_handler(func=lambda call: call.data == "restart")
def callback_restart(call):
    chat_id = call.message.chat.id
    user_state[chat_id] = {
        'step': 'select_region',
        'selected_majors': [],
        'major_scores': {},
        'selected_provinces': [],
        'prov_scores': {}
    }
    bot.answer_callback_query(call.id, "شروع مجدد")
    bot.send_message(
        chat_id,
        "🔄 **استعلام جدید انتخاب رشته کنکور تجربی**\n\n"
        "📍 لطفاً سهمیه منطقه خود را انتخاب فرمایید:",
        parse_mode='Markdown',
        reply_markup=get_region_keyboard()
    )

if __name__ == '__main__':
    print("🚀 ربات با موفقیت و بر اساس سیستم نمره‌دهی خطی و فرمول اولویت آماده اجرا شد!")
    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=10)
    except Exception as e:
        print(f"\n⚠️ خطای اتصال به تلگرام: {e}")
        print("💡 راهنمای رفع مشکل:")
        print("۱. اگر در ایران هستید، تلگرام فیلتر است؛ لطفاً فیلترشکن (VPN) خود را روشن کنید.")
        print("۲. توصیه می‌شود در برنامه فیلترشکن خود حالت 'TUN Mode' را فعال کنید.")
