import os
import sys
import io
import re
import json
import socket
import textwrap
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

import time
import urllib.request
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import telebot
from telebot import types, apihelper

TOKEN = '8574451645:AAER4vkfOzip0KHolGmXqaeKfdmtN0f9bdk'
BOT_PASSWORD = '1381'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_FILE = os.path.join(BASE_DIR, 'auth_users.json')

# =====================================================================
# 🖋 تنظیم فونت پینار (Pinar) و سیستم چاپ PDF افقی فارسی
# =====================================================================
PINAR_FONT_PATH = os.path.join(BASE_DIR, 'Pinar-Regular.ttf')
if os.path.exists(PINAR_FONT_PATH):
    try:
        pdfmetrics.registerFont(TTFont('Pinar', PINAR_FONT_PATH))
        PDF_FONT_NAME = 'Pinar'
    except Exception as e:
        print(f"Error registering Pinar font in ReportLab: {e}")
        PDF_FONT_NAME = 'Helvetica'
else:
    PDF_FONT_NAME = 'Helvetica'

reshaper = arabic_reshaper.ArabicReshaper({
    'delete_harakat': False,
    'support_ligatures': True,
})

def fa_text(text, wrap_width=None):
    if text is None:
        return ''
    s = str(text).strip()
    if not s or s == '-':
        return '-'
    if wrap_width and len(s) > wrap_width:
        lines = textwrap.wrap(s, width=wrap_width)
        reshaped_lines = [get_display(reshaper.reshape(l)) for l in lines]
        return '<br/>'.join(reshaped_lines)
    try:
        return get_display(reshaper.reshape(s))
    except Exception:
        return s

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont(PDF_FONT_NAME, 8)
        self.setFillColor(colors.HexColor('#555555'))
        w, h = 841.89, 595.27
        # خط افقی بالای صفحه
        self.setStrokeColor(colors.HexColor('#002060'))
        self.setLineWidth(1)
        self.line(20, h - 22, w - 20, h - 22)
        top_txt = get_display(reshaper.reshape('سامانه هوشمند انتخاب رشته تجربی ۱۴۰۴ | نسخه رسمی چاپی افقی'))
        self.drawRightString(w - 20, h - 18, top_txt)
        
        # خط افقی پایین صفحه
        self.setStrokeColor(colors.HexColor('#D9D9D9'))
        self.setLineWidth(0.5)
        self.line(20, 20, w - 20, 20)
        page_str = get_display(reshaper.reshape(f'صفحه {self._pageNumber} از {page_count}'))
        self.drawString(25, 11, page_str)
        note_str = get_display(reshaper.reshape('تنظیم‌شده بر اساس بالاترین شانس قبولی و اولویت‌بندی علمی'))
        self.drawRightString(w - 20, 11, note_str)
        self.restoreState()

# =====================================================================
# 🔐 سیستم احراز هویت با رمز عبور و ذخیره‌سازی دائمی
# =====================================================================
def load_auth_users():
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                res = set()
                for item in data:
                    try:
                        res.add(int(item))
                    except Exception:
                        res.add(str(item))
                return res
        except Exception:
            return set()
    return set()

authenticated_users = load_auth_users()

def save_auth_user(chat_id):
    try:
        cid = int(chat_id)
    except Exception:
        cid = str(chat_id)
    authenticated_users.add(cid)
    users = load_auth_users()
    users.add(cid)
    try:
        with open(AUTH_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(users), f)
    except Exception as e:
        print(f"Error saving auth user: {e}")

def is_authenticated(chat_id):
    try:
        cid = int(chat_id)
    except Exception:
        cid = str(chat_id)
    if cid in authenticated_users or str(cid) in authenticated_users:
        return True
    if cid in load_auth_users():
        authenticated_users.add(cid)
        return True
    return False

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

# =====================================================================
# 📁 شناسایی هوشمند فایل اکسل پایگاه داده
# =====================================================================
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

print(f"📄 در حال خواندن شیت اصلی: {target_sheet}")
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
    'مازندران': ['مازندران', 'ساری', 'بابل', 'آمل', 'املی', 'آملی', 'تنکابن', 'رامسر', 'چالوس', 'نوشهر', 'بهشهر', 'بابلسر', 'قائمشهر', 'نور', 'محمودآباد', 'جویبار', 'سوادکوه'],
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
    'مناطق آزاد و سایر (کیش، قشم و...)': ['کیش', 'قشم', 'بین الملل', 'پردیس خودگردان کیش', 'پردیس بین الملل']
}

# 🗺 مرتب‌سازی کلیدواژه‌ها بر اساس طول نزولی (جلوگیری از تداخل کلمات کوتاه مانند کرمان با کرمانشاه یا ایران با ایرانشهر)
SORTED_PROVINCE_KEYWORDS = []
for prov, kws in PROVINCE_KEYWORDS.items():
    for kw in kws:
        SORTED_PROVINCE_KEYWORDS.append((kw, prov))
SORTED_PROVINCE_KEYWORDS.sort(key=lambda x: len(x[0]), reverse=True)

def get_province_of_uni(uni_str):
    u = str(uni_str).replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ')
    for kw, prov in SORTED_PROVINCE_KEYWORDS:
        if kw in u:
            return prov
    return 'سایر دانشگاه‌ها'

df['استان'] = df['دانشگاه قبولی'].apply(get_province_of_uni)
print(f"✅ تعداد {len(df):,} ردیف داده با موفقیت بارگذاری و نگاشت استانی شد.")

# =====================================================================
# 📚 دسته‌بندی و فهرست کامل رشته‌های تجربی (Complete Majors by Category)
# =====================================================================
MAJOR_CATEGORIES = {
    'doctor': '🩺 دکتری عمومی',
    'paramedical': '🧬 پیراپزشکی و توانبخشی',
    'health': '🔬 بهداشت، تغذیه و فوریت',
    'science': '🧪 علوم پایه و سایر'
}

TARGET_MAJORS_BY_CAT = {
    'doctor': [
        'پزشکی', 'دندانپزشکی', 'داروسازی', 'دامپزشکی', 'دکترای پیوسته بیوتکنولوژی'
    ],
    'paramedical': [
        'فیزیوتراپی', 'پرستاری', 'مامایی', 'تکنولوژی اتاق عمل', 'هوشبری',
        'تکنولوژی پرتوشناسی (رادیولوژی)', 'علوم آزمایشگاهی', 'بینایی سنجی',
        'شنوایی شناسی', 'گفتار درمانی', 'کار درمانی', 'اعضای مصنوعی (ارتوز و پروتز)',
        'تکنولوژی پرتودرمانی', 'تکنولوژی پزشکی هسته ای', 'ساخت پروتزهای دندانی'
    ],
    'health': [
        'علوم تغذیه', 'فوریت های پزشکی پیش بیمارستانی', 'بهداشت عمومی',
        'مهندسی بهداشت حرفه ای و ایمنی کار', 'مهندسی بهداشت محیط',
        'فناوری اطلاعات سلامت (HIT)', 'کتابداری و اطلاع رسانی پزشکی',
        'بهداشت مواد غذایی', 'بیولوژی و کنترل ناقلین بیماریها'
    ],
    'science': [
        'زیست شناسی سلولی مولکولی', 'زیست فناوری', 'میکروبیولوژی',
        'شیمی کاربردی', 'شیمی محض', 'زیست شناسی جانوری', 'زیست شناسی گیاهی',
        'علوم و صنایع غذایی', 'روانشناسی', 'حسابداری', 'مدیریت بازرگانی',
        'مدیریت مالی', 'مدیریت خدمات بهداشتی درمانی', 'علوم ورزشی',
        'مددکاری اجتماعی', 'علوم آزمایشگاهی دامپزشکی', 'مهندسی علوم دامی'
    ]
}

ALL_TARGET_MAJORS = []
for _m_list in TARGET_MAJORS_BY_CAT.values():
    ALL_TARGET_MAJORS.extend(_m_list)

MAJOR_ALIASES = {
    'پزشکی': ['پزشکی', 'پزشكی', 'دکتری عمومی'],
    'دندانپزشکی': ['دندانپزشکی', 'دندان‌پزشکی', 'دندان پزشکی', 'دندان'],
    'داروسازی': ['داروسازی', 'دارو‌سازی', 'دارو سازی', 'دارو'],
    'دامپزشکی': ['دامپزشکی', 'دام‌پزشکی', 'دام پزشکی', 'دامپزشک'],
    'دکترای پیوسته بیوتکنولوژی': ['پیوسته بیوتکنولوژی', 'دکترای بیوتکنولوژی'],
    'فیزیوتراپی': ['فیزیوتراپی', 'فیزیو تراپی', 'فیزیو'],
    'پرستاری': ['پرستاری', 'پرستار'],
    'مامایی': ['مامایی', 'ماما'],
    'تکنولوژی اتاق عمل': ['اتاق عمل', 'تکنولوژی اتاق عمل', 'اتاق‌عمل'],
    'هوشبری': ['هوشبری', 'بیهوشی'],
    'تکنولوژی پرتوشناسی (رادیولوژی)': ['رادیولوژی', 'پرتوشناسی', 'پرتو شناسی', 'تکنولوژی پرتوشناسی'],
    'علوم آزمایشگاهی': ['علوم آزمایشگاهی', 'علوم ازمایشگاهی', 'آزمایشگاه', 'ازمایشگاه'],
    'بینایی سنجی': ['بینایی سنجی', 'بینایی شناسی', 'بینایی', 'اپتومتری'],
    'شنوایی شناسی': ['شنوایی شناسی', 'شنوایی سنجی', 'شنوایی', 'شنواییسنجی'],
    'گفتار درمانی': ['گفتار درمانی', 'گفتاردرمانی', 'گفتار'],
    'کار درمانی': ['کار درمانی', 'کاردرمانی', 'کاردرمان'],
    'اعضای مصنوعی (ارتوز و پروتز)': ['اعضای مصنوعی', 'ارتوز و پروتز', 'پروتز', 'وسایل کمکی', 'ارتوز'],
    'تکنولوژی پرتودرمانی': ['پرتودرمانی', 'پرتو درمانی', 'تکنولوژی پرتودرمانی', 'رادیوتراپی'],
    'تکنولوژی پزشکی هسته ای': ['پزشکی هسته ای', 'پزشکی هسته‌ای', 'پزشکی هستهای', 'تکنولوژی پزشکی هسته ای', 'هسته ای'],
    'ساخت پروتزهای دندانی': ['پروتز دندان', 'پروتزهای دندانی', 'ساخت پروتز'],
    'علوم تغذیه': ['علوم تغذیه', 'تغذیه'],
    'فوریت های پزشکی پیش بیمارستانی': ['فوریت های پزشکی', 'فوریت‌های پزشکی', 'فوریتهای پزشکی', 'پیش بیمارستانی', 'فوریت', 'کاردانی فوریت'],
    'بهداشت عمومی': ['بهداشت عمومی'],
    'مهندسی بهداشت حرفه ای و ایمنی کار': ['بهداشت حرفه ای', 'بهداشت حرفه‌ای', 'بهداشت حرفهای', 'ایمنی کار', 'مهندسی بهداشت حرفه'],
    'مهندسی بهداشت محیط': ['بهداشت محیط', 'مهندسی بهداشت محیط'],
    'فناوری اطلاعات سلامت (HIT)': ['فناوری اطلاعات سلامت', 'اطلاعات سلامت', 'مدارک پزشکی', 'hit'],
    'کتابداری و اطلاع رسانی پزشکی': ['کتابداری و اطلاع رسانی پزشکی', 'کتابداری پزشکی', 'کتابداری'],
    'بهداشت مواد غذایی': ['بهداشت مواد غذایی'],
    'بیولوژی و کنترل ناقلین بیماریها': ['بیولوژی و کنترل ناقلین', 'ناقلین بیماری'],
    'زیست شناسی سلولی مولکولی': ['زیست سلولی', 'سلولی مولکولی', 'سلولی و مولکولی', 'سلولی', 'ژنتیک', 'زیست شناسی سلولی'],
    'زیست فناوری': ['زیست فناوری', 'بیوتکنولوژی'],
    'میکروبیولوژی': ['میکروبیولوژی', 'میکروب شناسی'],
    'شیمی کاربردی': ['شیمی کاربردی'],
    'شیمی محض': ['شیمی محض'],
    'زیست شناسی جانوری': ['زیست شناسی جانوری', 'زیست جانوری'],
    'زیست شناسی گیاهی': ['زیست شناسی گیاهی', 'زیست گیاهی'],
    'علوم و صنایع غذایی': ['علوم و صنایع غذایی', 'صنایع غذایی', 'مهندسی صنایع غذایی'],
    'روانشناسی': ['روانشناسی', 'روان شناسی'],
    'حسابداری': ['حسابداری'],
    'مدیریت بازرگانی': ['مدیریت بازرگانی'],
    'مدیریت مالی': ['مدیریت مالی'],
    'مدیریت خدمات بهداشتی درمانی': ['خدمات بهداشتی درمانی', 'مدیریت خدمات درمانی'],
    'علوم ورزشی': ['علوم ورزشی', 'تربیت بدنی'],
    'مددکاری اجتماعی': ['مددکاری اجتماعی', 'مددکاری'],
    'علوم آزمایشگاهی دامپزشکی': ['علوم آزمایشگاهی دامپزشکی', 'کاردانی دامپزشکی'],
    'مهندسی علوم دامی': ['علوم دامی', 'مهندسی علوم دامی', 'دامپروری', 'گیاه پزشکی']
}

def is_commitment_row(row):
    d = str(row.get('دوره', '')).strip()
    u = str(row.get('دانشگاه قبولی', '')).strip()
    return ('تعهد' in d or 'محروم' in d or 'عدالت' in d or 
            'مناطق محروم' in u or 'تعهد' in u or 'بومی' in d)

def match_major_in_name(major_target, r_name):
    target_clean = major_target.replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ').strip()
    name_clean = str(r_name).replace('ي', 'ی').replace('ك', 'ک').replace('‌', ' ').strip()
    
    if target_clean == 'پزشکی':
        if any(x in name_clean for x in ['دندان', 'دام', 'هسته', 'فوریت', 'کتابدار', 'گیاه', 'دامی']):
            return False
        return 'پزشکی' in name_clean
    elif target_clean == 'دندانپزشکی':
        return any(x in name_clean for x in ['دندانپزشکی', 'دندان پزشکی', 'دندان'])
    elif target_clean == 'دامپزشکی':
        if 'علوم آزمایشگاهی دامپزشکی' in name_clean:
            return False
        return any(x in name_clean for x in ['دامپزشکی', 'دام پزشکی', 'دامپزشک'])
    elif target_clean == 'داروسازی':
        return any(x in name_clean for x in ['داروسازی', 'دارو سازی', 'دارو'])
    elif target_clean in ['اعضای مصنوعی (ارتوز و پروتز)', 'اعضای مصنوعی', 'ارتوز و پروتز']:
        return any(x in name_clean for x in ['اعضای مصنوعی', 'ارتوز', 'پروتز و وسایل کمکی'])
    elif target_clean in ['تکنولوژی پرتوشناسی (رادیولوژی)', 'رادیولوژی']:
        return any(x in name_clean for x in ['رادیولوژی', 'پرتوشناسی', 'پرتو شناسی'])
    elif target_clean in ['تکنولوژی پرتودرمانی', 'پرتودرمانی']:
        return any(x in name_clean for x in ['پرتودرمانی', 'پرتو درمانی', 'رادیوتراپی'])
    elif target_clean in ['تکنولوژی پزشکی هسته ای', 'پزشکی هسته ای', 'پزشکی هسته‌ای']:
        return any(x in name_clean for x in ['پزشکی هسته', 'هسته ای', 'هسته‌ای'])
    elif target_clean in ['فوریت های پزشکی پیش بیمارستانی', 'فوریت های پزشکی', 'فوریتهای پزشکی']:
        return any(x in name_clean for x in ['فوریت', 'پیش بیمارستانی'])
    elif target_clean in ['علوم آزمایشگاهی']:
        if 'دامپزشکی' in name_clean:
            return False
        return 'علوم آزمایشگاهی' in name_clean or 'علوم ازمایشگاهی' in name_clean
    elif target_clean in ['کار درمانی', 'کاردرمانی']:
        return 'کار درمانی' in name_clean or 'کاردرمانی' in name_clean
    elif target_clean in ['گفتار درمانی', 'گفتاردرمانی']:
        return 'گفتار درمانی' in name_clean or 'گفتاردرمانی' in name_clean
    elif target_clean in ['بینایی سنجی', 'بیناییسنجی']:
        return any(x in name_clean for x in ['بینایی', 'اپتومتری'])
    elif target_clean in ['شنوایی شناسی', 'شنواییسنجی']:
        return any(x in name_clean for x in ['شنوایی'])
    elif target_clean in ['تکنولوژی اتاق عمل', 'اتاق عمل']:
        return 'اتاق عمل' in name_clean
    elif target_clean in ['فناوری اطلاعات سلامت (HIT)', 'فناوری اطلاعات سلامت']:
        return any(x in name_clean for x in ['فناوری اطلاعات سلامت', 'اطلاعات سلامت', 'مدارک پزشکی'])
    elif target_clean in ['زیست شناسی سلولی مولکولی', 'زیست سلولی-مولکولی']:
        return any(x in name_clean for x in ['سلولی مولکولی', 'سلولی و مولکولی', 'سلولی-مولکولی'])
    elif target_clean in ['زیست فناوری', 'بیوتکنولوژی']:
        return any(x in name_clean for x in ['زیست فناوری', 'بیوتکنولوژی'])
    elif target_clean in ['مهندسی بهداشت حرفه ای و ایمنی کار', 'بهداشت حرفه ای']:
        return any(x in name_clean for x in ['بهداشت حرفه ای', 'بهداشت حرفه‌ای', 'ایمنی کار'])
    elif target_clean in ['مهندسی بهداشت محیط', 'بهداشت محیط']:
        return 'بهداشت محیط' in name_clean
    elif target_clean in ['علوم و صنایع غذایی']:
        return 'صنایع غذایی' in name_clean
    elif target_clean in ['مدیریت بازرگانی']:
        return 'مدیریت بازرگانی' in name_clean
    elif target_clean in ['مدیریت مالی']:
        return 'مدیریت مالی' in name_clean
    elif target_clean in ['مدیریت خدمات بهداشتی درمانی']:
        return 'خدمات بهداشتی درمانی' in name_clean
    elif target_clean in ['علوم ورزشی']:
        return any(x in name_clean for x in ['علوم ورزشی', 'تربیت بدنی'])
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
    elif any(k in combined for k in ['تعهدی', 'مناطق محروم', 'محروم', 'عدالت']):
        return 'تعهدی (بومی استان)', 0.90
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
        num_match = re.search(r'[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*$', sub)
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
                if canon == 'پزشکی' and any(x in sub_name for x in ['دندان', 'دام', 'هسته', 'فوریت', 'کتابدار', 'گیاه']):
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
                        if any(x in prefix for x in ['دندان', 'دام', 'فوریت']) or any(x in suffix for x in ['هسته', 'پیش بیمارستانی', 'فوریت']):
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
    markup.row(
        types.InlineKeyboardButton("منطقه ۱", callback_data="reg_1"),
        types.InlineKeyboardButton("منطقه ۲", callback_data="reg_2"),
        types.InlineKeyboardButton("منطقه ۳", callback_data="reg_3")
    )
    markup.row(
        types.InlineKeyboardButton("🎖 سهمیه ۵ درصد ایثارگران", callback_data="reg_5")
    )
    return markup

def get_percentage_presets_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📊 استاندارد مشاوران (۳۰٪ خوش‌بینانه / ۲۵٪ بدبینانه)", callback_data="pct_p_30_25"),
        types.InlineKeyboardButton("⚖️ متوازن و منطقی (۱۵٪ خوش‌بینانه / ۱۵٪ بدبینانه)", callback_data="pct_p_15_15"),
        types.InlineKeyboardButton("🎯 دقیق و نزدیک (۱۰٪ خوش‌بینانه / ۱۰٪ بدبینانه)", callback_data="pct_p_10_10"),
        types.InlineKeyboardButton("🚀 بازه گسترده و حداکثری (۳۰٪ خوش‌بینانه / ۳۰٪ بدبینانه)", callback_data="pct_p_30_30"),
        types.InlineKeyboardButton("🛡️ حاشیه امن بالا (۱۰٪ خوش‌بینانه / ۳۰٪ بدبینانه)", callback_data="pct_p_10_30"),
        types.InlineKeyboardButton("⚙️ تنظیم دستی یا جداگانه درصدها (۵٪، ۱۰٪، ۲۵٪، ۳۰٪...)", callback_data="pct_custom_menu")
    )
    return markup

def get_custom_percentage_keyboard(opt_pct=30, pess_pct=25):
    markup = types.InlineKeyboardMarkup(row_width=6)
    
    markup.row(types.InlineKeyboardButton(f"📈 درصد خوش‌بینانه: {to_persian_num(opt_pct)}٪ (بهتر از رتبه شما)", callback_data="pct_info_opt"))
    opt_buttons = []
    for p in [5, 10, 15, 20, 25, 30]:
        label = f"✅{to_persian_num(p)}٪" if p == opt_pct else f"{to_persian_num(p)}٪"
        opt_buttons.append(types.InlineKeyboardButton(label, callback_data=f"pct_setopt_{p}"))
    markup.row(*opt_buttons)
    
    markup.row(types.InlineKeyboardButton(f"📉 درصد بدبینانه / حاشیه امن: {to_persian_num(pess_pct)}٪", callback_data="pct_info_pess"))
    pess_buttons = []
    for p in [5, 10, 15, 20, 25, 30]:
        label = f"✅{to_persian_num(p)}٪" if p == pess_pct else f"{to_persian_num(p)}٪"
        pess_buttons.append(types.InlineKeyboardButton(label, callback_data=f"pct_setpes_{p}"))
    markup.row(*pess_buttons)
    
    markup.row(
        types.InlineKeyboardButton(f"✅ تایید درصدها ({to_persian_num(opt_pct)}٪ خوش‌بینانه / {to_persian_num(pess_pct)}٪ بدبینانه) و ادامه ➡️", callback_data="pct_confirm")
    )
    return markup

AVAILABLE_SOURCES = {
    '1404': '🔥 اخرین قبولی تجربی 1404  (1)',
    '1403': '📋 اخرین قبولی تجربی 1403',
    '5pct': '🎖 آخرین رتبه های قبولی تجربی سهمیه 5 درصد 1404',
    'sanjesh': '📊 مرجع جامع کشوری سنجش و دانشگاه‌ها',
    'mehromaah': '📚 اخرین قبولی ها فایل مهر و ماه'
}

def get_sources_display_label(selected_sources):
    if not selected_sources or 'all' in selected_sources or len(selected_sources) == len(AVAILABLE_SOURCES):
        return '🌐 همه با هم (پایگاه تجمیعی کامل)'
    
    short_names = {
        '1404': '🔥 ۱۴۰۴',
        '1403': '📋 ۱۴۰۳',
        '5pct': '🎖 ۵ درصد',
        'sanjesh': '📊 سنجش',
        'mehromaah': '📚 مهروماه'
    }
    names = [short_names.get(k, k) for k in selected_sources if k in short_names]
    return ' + '.join(names) if names else '🌐 همه با هم'

def get_source_keyboard(selected_sources=None):
    if selected_sources is None:
        selected_sources = []
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # دکمه میانبر سریع انتخاب همه پایگاه‌ها باهم
    markup.add(
        types.InlineKeyboardButton("🌐 همه با هم (پایگاه تجمیعی کامل - ۱۷,۴۶۰ رکورد)", callback_data="src_all")
    )
    for src_key, src_title in AVAILABLE_SOURCES.items():
        is_sel = src_key in selected_sources
        prefix = "✅ " if is_sel else "◻️ "
        markup.add(
            types.InlineKeyboardButton(f"{prefix}{src_title}", callback_data=f"src_toggle_{src_key}")
        )
    
    cnt = len(selected_sources)
    if cnt > 0:
        confirm_text = f"✅ تایید منابع انتخابی ({to_persian_num(cnt)} منبع) و ادامه ➡️"
        markup.add(types.InlineKeyboardButton(confirm_text, callback_data="src_confirm"))
        markup.add(types.InlineKeyboardButton("🗑 پاک کردن انتخاب‌ها", callback_data="src_clear"))
    else:
        confirm_text = "✅ تایید همه منابع و ادامه ➡️"
        markup.add(types.InlineKeyboardButton(confirm_text, callback_data="src_all"))
        
    return markup

def build_majors_keyboard(selected_list, current_cat='doctor'):
    markup = types.InlineKeyboardMarkup()
    
    markup.row(
        types.InlineKeyboardButton("⚡️ انتخاب ۴ دکتری باهم", callback_data="maj_bulk_doctor"),
        types.InlineKeyboardButton("⚡️ انتخاب پیراپزشکی‌های اصلی", callback_data="maj_bulk_paramedical")
    )
    markup.row(
        types.InlineKeyboardButton("🔍 همه رشته‌ها (جامع و کامل)", callback_data="maj_all")
    )
    
    cat_buttons = []
    for cat_key, cat_title in MAJOR_CATEGORIES.items():
        prefix = "🔘 " if cat_key == current_cat else ""
        cat_buttons.append(types.InlineKeyboardButton(f"{prefix}{cat_title}", callback_data=f"maj_cat_{cat_key}"))
    markup.row(cat_buttons[0], cat_buttons[1])
    markup.row(cat_buttons[2], cat_buttons[3])
    
    majors_in_cat = TARGET_MAJORS_BY_CAT.get(current_cat, TARGET_MAJORS_BY_CAT['doctor'])
    major_buttons = []
    for m_name in majors_in_cat:
        if m_name in selected_list:
            prio = selected_list.index(m_name) + 1
            btn_text = f"✅ {to_persian_num(prio)}. {m_name}"
        else:
            btn_text = m_name
            
        m_idx = ALL_TARGET_MAJORS.index(m_name) if m_name in ALL_TARGET_MAJORS else 0
        major_buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"maj_tog_{m_idx}"))
        
    for i in range(0, len(major_buttons), 2):
        if i + 1 < len(major_buttons):
            markup.row(major_buttons[i], major_buttons[i+1])
        else:
            markup.row(major_buttons[i])
            
    cnt = len(selected_list)
    confirm_text = f"✅ تایید و مرحله بعد ({to_persian_num(cnt)} رشته) ➡️" if cnt > 0 else "✅ تایید همه رشته‌ها و مرحله بعد ➡️"
    markup.row(
        types.InlineKeyboardButton(confirm_text, callback_data="maj_confirm")
    )
    markup.row(
        types.InlineKeyboardButton("🗑 پاک کردن انتخاب‌ها", callback_data="maj_clear")
    )
    return markup

def build_native_province_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(types.InlineKeyboardButton("🚫 بدون کدرشته‌های تعهدی (فقط عادی و پردیس/آزاد)", callback_data="natprov_none"))
    
    buttons = []
    for idx, name in enumerate(PROVINCES_32):
        buttons.append(types.InlineKeyboardButton(name, callback_data=f"natprov_{idx}"))
    
    for i in range(0, len(buttons), 3):
        markup.row(*buttons[i:i+3])
    return markup

def send_native_province_prompt(chat_id, message_id=None):
    msg_text = (
        "🏥 **مرحله انتخاب وضعیت تعهد خدمت (استان بومی):**\n\n"
        "▫️ کدرشته‌های **تعهد خدمت ۱.۵ برابر (مناطق محروم / عدالت آموزشی)** در پزشکی، دندانپزشکی، داروسازی و پیراپزشکی، **صرفاً مختص داوطلبان بومی همان استان** است.\n"
        "▫️ برای اینکه کدرشته‌های تعهدی دقیقاً متناسب با بومی‌گزینی شما پیشنهاد شوند، لطفاً **استان بومی** خود را انتخاب فرمایید:\n"
        "▫️ (یا در صورت عدم تمایل به دوره‌های تعهدی، گزینه «بدون کدرشته‌های تعهدی» را بزنید).\n\n"
        "💡 *همچنین می‌توانید نام استان بومی خود را در چت تایپ فرمایید.*"
    )
    keyboard = build_native_province_keyboard()
    if message_id:
        try:
            bot.edit_message_text(msg_text, chat_id=chat_id, message_id=message_id, parse_mode='Markdown', reply_markup=keyboard)
            return
        except Exception as e:
            if 'message is not modified' in str(e).lower():
                return
            try:
                bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
                return
            except Exception:
                pass
    bot.send_message(chat_id, msg_text, parse_mode='Markdown', reply_markup=keyboard)

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
    
    # 🔒 بررسی رمز عبور (Password Protection)
    if not is_authenticated(chat_id):
        user_state[chat_id] = {'step': 'enter_password'}
        bot.send_message(
            chat_id,
            "🔒 **به ربات هوشمند انتخاب رشته تجربی دکتر هاشمی خوش آمدید!**\n\n"
            "▫️ این ربات اختصاصی است. لطفاً جهت فعال‌سازی دسترسی خود، **رمز عبور** را ارسال فرمایید:\n\n"
            "*(رمز عبور تعیین شده را تایپ نمایید)*",
            parse_mode='Markdown'
        )
        return

    user_state[chat_id] = {
        'step': 'select_region',
        'opt_pct': 30,
        'pess_pct': 25,
        'current_major_cat': 'doctor',
        'selected_majors': [],
        'major_scores': {},
        'selected_provinces': [],
        'prov_scores': {},
        'native_province': None,
        'include_scores': True,
        'selected_sources': []
    }
    
    welcome_text = (
        "👋 **به ربات هوشمند انتخاب رشته تجربی خوش آمدید!**\n\n"
        "✨ **سیستم اولویت‌بندی اختصاصی و تصمیم‌گیری چندمعیاره:**\n"
        "▫️ پایگاه داده جامع ۱۷,۴۶۰ کارنامه قبولی (۱۴۰۴، ۱۴۰۳، سهمیه ۵ درصد، سنجش و مهروماه)\n"
        "▫️ نمره‌دهی خطی (۱ تا ۱۰) به ترتیب علاقه و ترجیح سکونت\n"
        "▫️ فرمول ارزیابی: `(نمره رشته × ۱.۲) + (نمره شهر × ۱.۰) × ضریب دوره`\n"
        "▫️ تفکیک دوره‌ها: روزانه (۱.۰)، پردیس (۰.۸۵)، تعهدی (۰.۹۰) و آزاد (۰.۷۵)\n"
        "▫️ بازه تحلیلی قابل تنظیم: از ۵٪ تا ۳۰٪ خوش‌بینانه و بدبینانه\n\n"
        "📍 **لطفاً سهمیه یا منطقه خود را انتخاب فرمایید:**"
    )
    bot.send_message(chat_id, welcome_text, parse_mode='Markdown', reply_markup=get_region_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith('reg_'))
def callback_region(call):
    chat_id = call.message.chat.id
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
        
    reg_val = int(call.data.split('_')[1])
    if chat_id not in user_state:
        user_state[chat_id] = {
            'opt_pct': 30, 'pess_pct': 25, 'current_major_cat': 'doctor',
            'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}
        }
    user_state[chat_id]['region'] = reg_val
    user_state[chat_id]['step'] = 'enter_rank'
    
    reg_name = f"منطقه {reg_val}" if reg_val in [1, 2, 3] else "سهمیه ۵ درصد ایثارگران"
    bot.answer_callback_query(call.id, f"{reg_name} انتخاب شد.")
    bot.edit_message_text(
        f"✅ سهمیه **{reg_name}** ثبت شد.\n\n"
        "🎯 لطفاً **رتبه در سهمیه** خود را به‌صورت عدد ارسال فرمایید (مثلاً: `6500`):",
        chat_id=chat_id,
        message_id=call.message.message_id,
        parse_mode='Markdown'
    )

# =====================================================================
# 🎯 هندلرهای انتخاب درصد خوش‌بینانه و بدبینانه (Percentages Handlers)
# =====================================================================
def send_percentage_selection_prompt(chat_id, message_id=None):
    rank = user_state[chat_id].get('rank', 5000)
    region = user_state[chat_id].get('region', 2)
    reg_name = f"منطقه {region}" if region in [1, 2, 3] else "سهمیه ۵ درصد ایثارگران"
    opt_p = user_state[chat_id].get('opt_pct', 30)
    pess_p = user_state[chat_id].get('pess_pct', 25)
    
    min_r = int(rank * (1 - opt_p / 100.0))
    max_r = int(rank * (1 + pess_p / 100.0))
    
    msg_text = (
        f"✅ رتبه **{rank:,}** ({reg_name}) ثبت گردید.\n\n"
        "🎯 **مرحله تنظیم بازه تحلیلی قبولی (درصد شانس):**\n"
        "▫️ **درصد خوش‌بینانه:** قبولی‌های نیازمند شانس و اقبال (رتبه‌های بهتر از شما)\n"
        "▫️ **درصد بدبینانه (حاشیه امن):** قبولی‌های بسیار مطمئن (رتبه‌های پایین‌تر از شما)\n\n"
        f"💡 بازه فعلی: از **{min_r:,}** ({opt_p}٪ خوش‌بینانه) تا **{max_r:,}** ({pess_p}٪ بدبینانه)\n\n"
        "👇 یکی از حالت‌های آماده زیر را لمس نمایید یا درصد دلخواه خود را تعیین کنید:"
    )
    keyboard = get_percentage_presets_keyboard()
    if message_id:
        try:
            bot.edit_message_text(msg_text, chat_id=chat_id, message_id=message_id, parse_mode='Markdown', reply_markup=keyboard)
            return
        except Exception:
            pass
    bot.send_message(chat_id, msg_text, parse_mode='Markdown', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('pct_p_'))
def callback_percentage_preset(call):
    chat_id = call.message.chat.id
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
        
    parts = call.data.split('_')
    opt_val = int(parts[2])
    pess_val = int(parts[3])
    
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
    user_state[chat_id]['opt_pct'] = opt_val
    user_state[chat_id]['pess_pct'] = pess_val
    
    bot.answer_callback_query(call.id, f"{opt_val}٪ خوش‌بینانه و {pess_val}٪ بدبینانه ثبت شد.")
    proceed_to_source_step(chat_id, message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'pct_custom_menu')
def callback_custom_percentage_menu(call):
    chat_id = call.message.chat.id
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
        
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
        
    opt_p = user_state[chat_id].get('opt_pct', 30)
    pess_p = user_state[chat_id].get('pess_pct', 25)
    rank = user_state[chat_id].get('rank', 5000)
    
    min_r = int(rank * (1 - opt_p / 100.0))
    max_r = int(rank * (1 + pess_p / 100.0))
    
    msg_text = (
        "⚙️ **تنظیم دقیق درصد خوش‌بینانه و بدبینانه:**\n\n"
        f"▫️ رتبه داوطلب: **{rank:,}**\n"
        f"▫️ درصد خوش‌بینانه: **{opt_p}٪** (از رتبه {min_r:,})\n"
        f"▫️ درصد بدبینانه (حاشیه امن): **{pess_p}٪** (تا رتبه {max_r:,})\n\n"
        "💡 برای تغییر روی درصدهای زیر کلیک فرمایید (یا دو عدد درصد را با فاصله در چت بفرستید، مثلاً `20 25`):"
    )
    keyboard = get_custom_percentage_keyboard(opt_p, pess_p)
    try:
        bot.edit_message_text(msg_text, chat_id=chat_id, message_id=call.message.message_id, parse_mode='Markdown', reply_markup=keyboard)
    except Exception:
        bot.send_message(chat_id, msg_text, parse_mode='Markdown', reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('pct_setopt_') or call.data.startswith('pct_setpes_'))
def callback_update_single_pct(call):
    chat_id = call.message.chat.id
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
        
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
        
    if call.data.startswith('pct_setopt_'):
        val = int(call.data.split('_')[2])
        user_state[chat_id]['opt_pct'] = val
        bot.answer_callback_query(call.id, f"خوش‌بینانه: {val}٪")
    else:
        val = int(call.data.split('_')[2])
        user_state[chat_id]['pess_pct'] = val
        bot.answer_callback_query(call.id, f"بدبینانه: {val}٪")
        
    callback_custom_percentage_menu(call)

@bot.callback_query_handler(func=lambda call: call.data == 'pct_confirm')
def callback_pct_confirm(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id, "درصدها تایید شدند.")
    proceed_to_source_step(chat_id, message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('pct_info_'))
def callback_pct_info(call):
    bot.answer_callback_query(call.id, "جهت تغییر، روی اعداد درصد زیر کلیک فرمایید.")

def proceed_to_source_step(chat_id, message_id=None):
    user_state[chat_id]['step'] = 'select_source'
    user_state[chat_id]['selected_sources'] = []
    opt_p = user_state[chat_id].get('opt_pct', 30)
    pess_p = user_state[chat_id].get('pess_pct', 25)
    rank = user_state[chat_id].get('rank', 5000)
    min_r = int(rank * (1 - opt_p / 100.0))
    max_r = int(rank * (1 + pess_p / 100.0))
    
    prompt_text = (
        f"🎯 **بازه استعلام فعال:** {opt_p}٪ خوش‌بینانه ({min_r:,}) تا {pess_p}٪ بدبینانه ({max_r:,})\n\n"
        "🔍 **مایلید استعلام قبولی‌ها بر اساس کدام پایگاه‌های داده انجام شود؟**\n"
        "💡 *می‌توانید یک یا چند منبع را به دلخواه انتخاب و سپس دکمه تایید را لمس فرمایید.*"
    )
    keyboard = get_source_keyboard([])
    if message_id:
        try:
            bot.edit_message_text(prompt_text, chat_id=chat_id, message_id=message_id, parse_mode='Markdown', reply_markup=keyboard)
            return
        except Exception:
            pass
    bot.send_message(chat_id, prompt_text, parse_mode='Markdown', reply_markup=keyboard)

# =====================================================================
# 📚 هندلر انتخاب منبع پایگاه داده (Data Source Callback Handler)
# =====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('src_'))
def callback_source(call):
    chat_id = call.message.chat.id
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
        
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
        
    data = call.data
    
    if data == "src_all":
        user_state[chat_id]['selected_sources'] = ['all']
        user_state[chat_id]['source'] = 'همه'
        user_state[chat_id]['source_label'] = '🌐 همه با هم (پایگاه تجمیعی کامل)'
        user_state[chat_id]['selected_majors'] = []
        user_state[chat_id]['major_scores'] = {}
        user_state[chat_id]['current_major_cat'] = 'doctor'
        user_state[chat_id]['step'] = 'select_majors'
        bot.answer_callback_query(call.id, "همه منابع انتخاب شدند.")
        send_majors_selection_prompt(chat_id, message_id=call.message.message_id)
        return

    elif data == "src_clear":
        user_state[chat_id]['selected_sources'] = []
        bot.answer_callback_query(call.id, "انتخاب‌ها پاک شدند.")
        keyboard = get_source_keyboard([])
        try:
            bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=keyboard)
        except Exception:
            pass
        return

    elif data == "src_confirm":
        selected_sources = user_state[chat_id].get('selected_sources', [])
        if not selected_sources:
            selected_sources = ['all']
            src_label = '🌐 همه با هم (پایگاه تجمیعی کامل)'
            src_code = 'همه'
        else:
            src_label = get_sources_display_label(selected_sources)
            src_code = '+'.join(selected_sources)
            
        user_state[chat_id]['selected_sources'] = selected_sources
        user_state[chat_id]['source'] = src_code
        user_state[chat_id]['source_label'] = src_label
        user_state[chat_id]['selected_majors'] = []
        user_state[chat_id]['major_scores'] = {}
        user_state[chat_id]['current_major_cat'] = 'doctor'
        user_state[chat_id]['step'] = 'select_majors'
        
        cnt = len(AVAILABLE_SOURCES) if 'all' in selected_sources else len(selected_sources)
        bot.answer_callback_query(call.id, f"{to_persian_num(cnt)} منبع تایید شد.")
        send_majors_selection_prompt(chat_id, message_id=call.message.message_id)
        return

    elif data.startswith("src_toggle_"):
        src_key = data.replace("src_toggle_", "")
        selected_sources = user_state[chat_id].get('selected_sources', [])
        if 'all' in selected_sources:
            selected_sources = []
            
        if src_key in selected_sources:
            selected_sources.remove(src_key)
            bot.answer_callback_query(call.id, "حذف شد")
        else:
            if src_key in AVAILABLE_SOURCES:
                selected_sources.append(src_key)
                bot.answer_callback_query(call.id, "انتخاب شد")
            else:
                bot.answer_callback_query(call.id)
                
        user_state[chat_id]['selected_sources'] = selected_sources
        keyboard = get_source_keyboard(selected_sources)
        try:
            bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=keyboard)
        except Exception:
            pass
        return

    else:
        # پشتیبانی از دکمه‌های تکی احتمالی
        src_key = data.split('_')[1]
        if src_key in AVAILABLE_SOURCES:
            selected_sources = [src_key]
            src_label = get_sources_display_label(selected_sources)
            user_state[chat_id]['selected_sources'] = selected_sources
            user_state[chat_id]['source'] = src_key
            user_state[chat_id]['source_label'] = src_label
            user_state[chat_id]['selected_majors'] = []
            user_state[chat_id]['major_scores'] = {}
            user_state[chat_id]['current_major_cat'] = 'doctor'
            user_state[chat_id]['step'] = 'select_majors'
            bot.answer_callback_query(call.id, f"منبع {src_label} انتخاب شد.")
            send_majors_selection_prompt(chat_id, message_id=call.message.message_id)
            return

def send_majors_selection_prompt(chat_id, message_id=None):
    selected = user_state[chat_id].get('selected_majors', [])
    manual_sc = user_state[chat_id].get('major_scores', {})
    current_cat = user_state[chat_id].get('current_major_cat', 'doctor')
    
    if selected:
        calc_sc = manual_sc if manual_sc else calculate_linear_scores(selected)
        majors_txt = "\n".join([f"  {to_persian_num(i+1)}. {m}  *(نمره: {to_persian_num(calc_sc.get(m, 10.0))} از ۱۰)*" for i, m in enumerate(selected)])
        summary = f"\n\n📋 **رشته‌های انتخابی شما به ترتیب اولویت ({to_persian_num(len(selected))} رشته):**\n{majors_txt}\n\n💡 برای تایید، دکمه «تایید و مرحله بعد» را لمس فرمایید."
    else:
        summary = "\n\n📋 **رشته‌های انتخابی:** (هنوز رشته‌ای انتخاب نشده است)"
        
    cat_title = MAJOR_CATEGORIES.get(current_cat, 'رشته‌ها')
    msg_text = (
        f"✅ منبع استعلام: **{user_state[chat_id].get('source_label', 'همه')}**\n\n"
        f"📚 **مرحله انتخاب رشته‌ها (دسته: {cat_title}):**\n"
        "▫️ روی رشته‌ها کلیک کنید تا با تیک سبز به لیست اضافه و اولویت‌بندی شوند.\n"
        "▫️ از دکمه‌های «انتخاب ۴ دکتری» یا «پیراپزشکی‌های اصلی» می‌توانید برای انتخاب یکجای رشته‌ها استفاده کنید.\n"
        "▫️ همچنین می‌توانید نام چند رشته را در چت بفرستید (مثلاً: `پزشکی، دندان، داروسازی، فیزیوتراپی`)."
        f"{summary}"
    )
    keyboard = build_majors_keyboard(selected, current_cat=current_cat)
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
# 📚 هندلر کلیک‌های رشته‌ها (Major Callback Handlers)
# =====================================================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('maj_'))
def callback_major_action(call):
    chat_id = call.message.chat.id
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
        
    action = call.data[4:]
    
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
        
    selected = user_state[chat_id].get('selected_majors', [])
    
    if action == 'all':
        user_state[chat_id]['selected_majors'] = ['همه رشته‌ها']
        user_state[chat_id]['major_scores'] = {}
        bot.answer_callback_query(call.id, "همه رشته‌ها انتخاب شد.")
        proceed_to_native_province_step(chat_id, message_id=call.message.message_id)
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
        proceed_to_native_province_step(chat_id, message_id=call.message.message_id)
        return
        
    elif action.startswith('cat_'):
        cat_key = action.split('_')[1]
        user_state[chat_id]['current_major_cat'] = cat_key
        bot.answer_callback_query(call.id, MAJOR_CATEGORIES.get(cat_key, 'دسته'))
        send_majors_selection_prompt(chat_id, message_id=call.message.message_id)
        return
        
    elif action == 'bulk_doctor':
        doc_majors = ['پزشکی', 'دندانپزشکی', 'داروسازی', 'دامپزشکی']
        for dm in doc_majors:
            if dm not in selected:
                selected.append(dm)
        user_state[chat_id]['selected_majors'] = selected
        user_state[chat_id]['major_scores'] = {}
        bot.answer_callback_query(call.id, "۴ رشته دکتری افزوده شد.")
        send_majors_selection_prompt(chat_id, message_id=call.message.message_id)
        return
        
    elif action == 'bulk_paramedical':
        paramed_majors = ['فیزیوتراپی', 'پرستاری', 'مامایی', 'تکنولوژی اتاق عمل', 'هوشبری', 'تکنولوژی پرتوشناسی (رادیولوژی)', 'علوم آزمایشگاهی']
        for pm in paramed_majors:
            if pm not in selected:
                selected.append(pm)
        user_state[chat_id]['selected_majors'] = selected
        user_state[chat_id]['major_scores'] = {}
        bot.answer_callback_query(call.id, "پیراپزشکی‌های اصلی افزوده شدند.")
        send_majors_selection_prompt(chat_id, message_id=call.message.message_id)
        return
        
    elif action.startswith('tog_'):
        idx = int(action.split('_')[1])
        if idx < len(ALL_TARGET_MAJORS):
            major_name = ALL_TARGET_MAJORS[idx]
            if major_name in selected:
                selected.remove(major_name)
                bot.answer_callback_query(call.id, f"حذف شد: {major_name}")
            else:
                selected.append(major_name)
                bot.answer_callback_query(call.id, f"اولویت {len(selected)}: {major_name}")
            user_state[chat_id]['selected_majors'] = selected
            user_state[chat_id]['major_scores'] = {}
            send_majors_selection_prompt(chat_id, message_id=call.message.message_id)
        return

def proceed_to_native_province_step(chat_id, message_id=None):
    user_state[chat_id]['step'] = 'select_native_prov'
    send_native_province_prompt(chat_id, message_id=message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('natprov_'))
def callback_native_province(call):
    chat_id = call.message.chat.id
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
        
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
        
    data = call.data[8:]
    if data == 'none':
        user_state[chat_id]['native_province'] = 'بدون تعهدی'
        bot.answer_callback_query(call.id, "بدون کدرشته‌های تعهدی")
    else:
        idx = int(data)
        prov_name = PROVINCES_32[idx]
        user_state[chat_id]['native_province'] = prov_name
        bot.answer_callback_query(call.id, f"استان بومی: {prov_name}")
        
    user_state[chat_id]['step'] = 'select_provinces'
    send_provinces_selection_prompt(chat_id, message_id=call.message.message_id)

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
        "🗺 **مرحله اولویت‌بندی شهرها و استان‌ها (از ۱ تا M):**\n"
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
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
        
    action = call.data[5:]
    
    if chat_id not in user_state:
        user_state[chat_id] = {'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {}}
        
    selected = user_state[chat_id].get('selected_provinces', [])
    
    if action == 'all':
        user_state[chat_id]['selected_provinces'] = ['سراسر کشور']
        user_state[chat_id]['prov_scores'] = {}
        bot.answer_callback_query(call.id, "سراسر کشور انتخاب شد.")
        proceed_to_score_columns_prompt(chat_id, message_id=call.message.message_id)
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
        bot.answer_callback_query(call.id, "تنظیمات گزارش خروجی...")
        proceed_to_score_columns_prompt(chat_id, message_id=call.message.message_id)
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

# =====================================================================
# ⚙️ مرحله انتخاب فعال بودن ستون‌های امتیازدهی در فایل خروجی
# =====================================================================
def proceed_to_score_columns_prompt(chat_id, message_id=None):
    user_state[chat_id]['step'] = 'select_score_columns'
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_yes_pdf = types.InlineKeyboardButton("📑 نسخه کامل اکسل + فایل‌های PDF چاپی (افقی A4)", callback_data="scoreopt_yes_pdf")
    btn_yes = types.InlineKeyboardButton("📊 نسخه کامل اکسل (همراه با ستون‌های نمره‌دهی)", callback_data="scoreopt_yes")
    btn_no_pdf = types.InlineKeyboardButton("📑 نسخه ساده اکسل + فایل‌های PDF چاپی (افقی A4)", callback_data="scoreopt_no_pdf")
    btn_no = types.InlineKeyboardButton("📋 نسخه ساده اکسل (بدون ستون‌های نمره‌دهی)", callback_data="scoreopt_no")
    markup.add(btn_yes_pdf, btn_yes, btn_no_pdf, btn_no)
    
    msg_text = (
        "⚙️ **تنظیمات نهایی فایل‌های خروجی (اکسل و PDF):**\n\n"
        "آیا مایلید ستون‌های نمره‌دهی و فرمول اولویت‌بندی در گزارش‌ها درج شوند؟\n\n"
        "▫️ **📊 نسخه کامل:** نمایش تمام ستون‌های محاسباتی، نمرات ۱ تا ۱۰ رشته و شهر، ضریب دوره و امتیاز کل اولویت.\n"
        "▫️ **📋 نسخه ساده:** فایل‌های شیک و رسمی بدون ستون‌های نمره‌دهی (شامل رشته، دانشگاه، رتبه قبولی، استان، دوره، شانس قبولی و رتبه کشوری).\n\n"
        "🖨 **نسخه چاپی PDF:** هر دو فایل با چیدمان افقی استاندارد (Landscape A4) و فونت شکیل پینار (Pinar) بدون به‌هم‌ریختگی ستون‌ها و مناسب پرینت مستقیم آماده می‌شوند.\n\n"
        "💡 *در تمام حالت‌ها، کدرشته‌ها بر اساس بالاترین اولویت و شانس دقیق شما چینش می‌گردند.*"
    )
    
    if message_id:
        try:
            bot.edit_message_text(msg_text, chat_id=chat_id, message_id=message_id, parse_mode='Markdown', reply_markup=markup)
            return
        except Exception as e:
            if 'message is not modified' in str(e).lower():
                return
            try:
                bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=markup)
                return
            except Exception:
                pass
    bot.send_message(chat_id, msg_text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('scoreopt_'))
def callback_score_option(call):
    chat_id = call.message.chat.id
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
        
    opt_type = call.data[9:]
    user_state[chat_id]['export_pdf'] = ('pdf' in opt_type)
    if opt_type.startswith('yes'):
        user_state[chat_id]['include_scores'] = True
        bot.answer_callback_query(call.id, "نسخه با ستون‌های نمره‌دهی انتخاب شد.")
    else:
        user_state[chat_id]['include_scores'] = False
        bot.answer_callback_query(call.id, "نسخه ساده بدون نمره‌دهی انتخاب شد.")
        
    execute_search_and_send(chat_id)

# =====================================================================
# ✍️ هندلر ورودی‌های متنی چت (Password, Rank, Percentages, Majors, Provinces)
# =====================================================================
@bot.message_handler(func=lambda msg: True)
def text_input_handler(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    # 🔒 بررسی رمز عبور ربات (پشتیبانی از اعداد فارسی و انگلیسی در هر مرحله)
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    t_clean = text
    for i, p in enumerate(persian_digits):
        t_clean = t_clean.replace(p, str(i))
    t_clean = t_clean.strip()
    
    if t_clean == BOT_PASSWORD:
        save_auth_user(chat_id)
        current_step = user_state.get(chat_id, {}).get('step')
        if current_step and current_step not in ['enter_password', 'select_region']:
            bot.send_message(
                chat_id,
                "🔓 **رمز عبور با موفقیت تایید شد.**\nدسترسی شما فعال است و انتخاب‌های قبلی شما با موفقیت حفظ شده‌اند.",
                parse_mode='Markdown'
            )
            # هدایت کاربر به آخرین مرحله فعلی بدون ریست شدن یا باگ خوردن
            if current_step == 'enter_rank':
                bot.send_message(chat_id, "🎯 لطفاً **رتبه در سهمیه** خود را ارسال فرمایید (مثلاً: `6500`):", parse_mode='Markdown')
            elif current_step == 'select_percentages':
                send_percentage_selection_prompt(chat_id)
            elif current_step == 'select_source':
                proceed_to_source_step(chat_id)
            elif current_step == 'select_majors':
                send_majors_selection_prompt(chat_id)
            elif current_step == 'select_native_prov':
                proceed_to_native_province_step(chat_id)
            elif current_step == 'select_provinces':
                send_provinces_selection_prompt(chat_id)
            elif current_step == 'select_score_columns':
                proceed_to_score_columns_prompt(chat_id)
            return
        else:
            bot.send_message(
                chat_id, 
                "🔓 **رمز عبور با موفقیت تایید شد. دسترسی شما با موفقیت فعال گردید!**\n\nدر حال آماده‌سازی منوی اصلی انتخاب رشته...",
                parse_mode='Markdown'
            )
            send_welcome(message)
            return

    # اگر کاربر احراز هویت نشده باشد و چیز دیگری ارسال کرده باشد
    if not is_authenticated(chat_id):
        bot.send_message(
            chat_id,
            "❌ **رمز عبور وارد شده نادرست است.**\n\n"
            "🔒 لطفاً جهت ورود، رمز عبور صحیح ربات را ارسال فرمایید:",
            parse_mode='Markdown'
        )
        return
            
    if chat_id not in user_state:
        user_state[chat_id] = {
            'step': 'select_region', 'opt_pct': 30, 'pess_pct': 25,
            'selected_majors': [], 'major_scores': {}, 'selected_provinces': [], 'prov_scores': {},
            'include_scores': True
        }
        
    step = user_state[chat_id].get('step', 'select_region')
    
    # 1. ورود رتبه در سهمیه
    if step == 'enter_rank':
        persian_digits = '۰۱۲۳۴۵۶۷۸۹'
        t_clean = text.replace(',', '')
        for i, p in enumerate(persian_digits):
            t_clean = t_clean.replace(p, str(i))
            
        if t_clean.isdigit():
            rank = int(t_clean)
            if 0 < rank <= 300000:
                user_state[chat_id]['rank'] = rank
                user_state[chat_id]['step'] = 'select_percentages'
                send_percentage_selection_prompt(chat_id)
                return
            else:
                bot.send_message(chat_id, "⚠️ رتبه وارد شده در محدوده معتبر نیست. لطفاً مجدداً رتبه را وارد فرمایید:")
                return
        else:
            bot.send_message(chat_id, "⚠️ لطفاً فقط مقدار عددی رتبه را ارسال فرمایید (مثلاً: 6500):")
            return

    # 2. تنظیم دستی درصدهای خوش‌بینانه و بدبینانه
    if step == 'select_percentages':
        nums = re.findall(r'[0-9]+', text.replace('٪', '').replace('%', ''))
        if len(nums) >= 2:
            opt_val = max(1, min(50, int(nums[0])))
            pess_val = max(1, min(50, int(nums[1])))
            user_state[chat_id]['opt_pct'] = opt_val
            user_state[chat_id]['pess_pct'] = pess_val
            bot.send_message(chat_id, f"✅ بازه تحلیلی: **{opt_val}٪ خوش‌بینانه** و **{pess_val}٪ بدبینانه** با موفقیت ثبت شد.")
            proceed_to_source_step(chat_id)
            return
        elif len(nums) == 1:
            val = max(1, min(50, int(nums[0])))
            user_state[chat_id]['opt_pct'] = val
            user_state[chat_id]['pess_pct'] = val
            bot.send_message(chat_id, f"✅ بازه تحلیلی: **{val}٪ خوش‌بینانه و بدبینانه** ثبت شد.")
            proceed_to_source_step(chat_id)
            return
        else:
            bot.send_message(chat_id, "⚠️ لطفاً درصدها را به صورت عددی ارسال فرمایید (مثلاً: `20 25`) یا از دکمه‌های زیر انتخاب کنید:")
            send_percentage_selection_prompt(chat_id)
            return

    # 3. تایپ رشته‌ها در چت
    if step == 'select_majors':
        parsed_m, manual_m_sc = parse_items_with_optional_scores(text, MAJOR_ALIASES)
        if parsed_m:
            user_state[chat_id]['selected_majors'] = parsed_m
            user_state[chat_id]['major_scores'] = manual_m_sc
            m_str = "، ".join(parsed_m)
            bot.send_message(chat_id, f"✅ **{to_persian_num(len(parsed_m))} رشته بر اساس اولویت ارسالی شما ثبت شد:**\n{m_str}")
            proceed_to_native_province_step(chat_id)
            return
        else:
            bot.send_message(chat_id, "⚠️ رشته‌ای از متن شما شناسایی نشد. لطفاً از دکمه‌های زیر انتخاب فرمایید:")
            send_majors_selection_prompt(chat_id)
            return
            
    # 4. استان بومی (تعهدی)
    if step == 'select_native_prov':
        t_clean = text.replace('ي', 'ی').replace('ك', 'ک').strip()
        if any(x in t_clean for x in ['بدون', 'خیر', 'نه', 'هیچ']):
            user_state[chat_id]['native_province'] = 'بدون تعهدی'
            bot.send_message(chat_id, "✅ وضعیت کدرشته‌های تعهدی: **غیرفعال** ثبت شد.")
        else:
            found_p = None
            for p in PROVINCES_32:
                if p in t_clean:
                    found_p = p
                    break
            if not found_p:
                for p, kws in PROVINCE_KEYWORDS.items():
                    if any(kw in t_clean for kw in kws):
                        found_p = p
                        break
            user_state[chat_id]['native_province'] = found_p if found_p else 'بدون تعهدی'
            if found_p:
                bot.send_message(chat_id, f"✅ استان بومی شما: **{found_p}** ثبت شد.\n(کدرشته‌های تعهد خدمت منحصراً برای این استان فعال شدند)")
            else:
                bot.send_message(chat_id, "✅ کدرشته‌های تعهدی برای شما لحاظ نشد.")
                
        user_state[chat_id]['step'] = 'select_provinces'
        send_provinces_selection_prompt(chat_id)
        return

    # 5. استان‌ها در چت
    if step == 'select_provinces':
        parsed_p, manual_p_sc = parse_items_with_optional_scores(text, PROVINCE_KEYWORDS)
        if parsed_p:
            user_state[chat_id]['selected_provinces'] = parsed_p
            user_state[chat_id]['prov_scores'] = manual_p_sc
            p_str = "، ".join(parsed_p)
            bot.send_message(chat_id, f"✅ **{to_persian_num(len(parsed_p))} استان بر اساس اولویت ارسالی شما ثبت شد:**\n{p_str}")
            proceed_to_score_columns_prompt(chat_id)
            return
        else:
            bot.send_message(chat_id, "⚠️ استانی از متن شما شناسایی نشد. لطفاً از دکمه‌های زیر انتخاب فرمایید:")
            send_provinces_selection_prompt(chat_id)
            return

    # 6. انتخاب ستون‌های امتیازدهی در چت
    if step == 'select_score_columns':
        t_low = text.lower()
        if any(w in t_low for w in ['بله', 'کامل', 'امتیاز', 'با امتیاز', '۱', '1', 'اره', 'آره', 'yes', 'y']):
            user_state[chat_id]['include_scores'] = True
            bot.send_message(chat_id, "✅ گزارش همراه با ستون‌های نمره‌دهی انتخاب شد.")
            execute_search_and_send(chat_id)
            return
        elif any(w in t_low for w in ['خیر', 'نه', 'ساده', 'بدون', 'بدون امتیاز', '۲', '2', 'no', 'n']):
            user_state[chat_id]['include_scores'] = False
            bot.send_message(chat_id, "✅ گزارش ساده بدون ستون‌های نمره‌دهی انتخاب شد.")
            execute_search_and_send(chat_id)
            return
        else:
            bot.send_message(chat_id, "⚠️ لطفاً یکی از گزینه‌های زیر را لمس فرمایید:")
            proceed_to_score_columns_prompt(chat_id)
            return
            
    bot.send_message(chat_id, "💡 برای شروع استعلام انتخاب رشته، دستور /start را ارسال فرمایید.")

# =====================================================================
# 🔍 توابع کمکی دسته‌بندی رشته‌ها و تولید دو فایل اکسل خروجی
# =====================================================================
def get_primary_target_major(r_name, selected_majors=None):
    if selected_majors and 'همه رشته‌ها' not in selected_majors and 'همه' not in selected_majors:
        for m in selected_majors:
            if match_major_in_name(m, r_name):
                return m
    for m in ALL_TARGET_MAJORS:
        if match_major_in_name(m, r_name):
            return m
    return str(r_name).strip()

def get_chance_text(r_val, rank, opt_p, pess_p):
    if r_val < rank * 0.95:
        return f"خوش‌بینانه (تا {opt_p}٪)"
    elif r_val <= rank * 1.05:
        return "محتمل و منطقی"
    else:
        return f"شانس بالا (تا {pess_p}٪)"

def add_native_checklist_sheet(wb, filtered, selected_majors, native_prov):
    if not native_prov or native_prov == 'بدون تعهدی':
        return
        
    font_name = 'Pinar'
    h_font = Font(name=font_name, size=11, bold=True, color='FFFFFF')
    h_fill = PatternFill(start_color='002060', end_color='002060', fill_type='solid')
    d_font = Font(name=font_name, size=11, color='000000')
    t_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    ws2 = wb.create_sheet(title="چک‌لیست تعهد خدمت بومی")
    ws2.views.sheetView[0].rightToLeft = True
    
    headers2 = [
        'ردیف', 'رشته تحصیلی انتخابی', 'استان بومی تعهدی', 
        'وضعیت در سوابق سال‌های گذشته', 'دستورالعمل و اقدام الزامی مشاور برای دفترچه کنکور امسال'
    ]
    ws2.append(headers2)
    ws2.row_dimensions[1].height = 28
    for c_idx in range(1, len(headers2) + 1):
        c = ws2.cell(row=1, column=c_idx)
        c.font = h_font
        c.fill = h_fill
        c.alignment = Alignment(horizontal='center', vertical='center')
        c.border = t_border

    check_majors = selected_majors if ('همه رشته‌ها' not in selected_majors and 'همه' not in selected_majors) else ALL_TARGET_MAJORS[:15]
    
    existing_tahad_majors = set()
    for _, r in filtered.iterrows():
        if 'تعهدی' in str(r.get('دوره_تطبیقی', '')):
            for m in check_majors:
                if match_major_in_name(m, r.get('رشته قبولی', '')):
                    existing_tahad_majors.add(m)

    for idx, m in enumerate(check_majors, 1):
        has_t = m in existing_tahad_majors
        status_text = "✅ موجود در سوابق رتبه‌های قبولی (در شیت ۱ درج شد)" if has_t else "⚠️ در سوابق این بازه رتبه ثبت نشده است"
        instr_text = (
            f"کدرشته‌های تعهدی {m} در علوم پزشکی {native_prov} از دفترچه امسال تطبیق و اولویت‌بندی شود."
            if has_t else
            f"⚠️ بررسی الزامی در دفترچه کنکور امسال: مشاور حتماً بررسی کند اگر برای {m} در دانشگاه‌های علوم پزشکی استان {native_prov} ظرفیت تعهد خدمت اعلام شده، فوراً به فرم انتخاب رشته افزوده شود (ظرفیت سالانه متغیر است)."
        )
        row_vals = [idx, m, native_prov, status_text, instr_text]
        ws2.append(row_vals)
        r_idx = ws2.max_row
        ws2.row_dimensions[r_idx].height = 25
        
        fill2 = PatternFill(start_color='FEF9E7', end_color='FEF9E7', fill_type='solid') if not has_t else PatternFill(start_color='E8F8F5', end_color='E8F8F5', fill_type='solid')
        for c_idx, val in enumerate(row_vals, 1):
            cell = ws2.cell(row=r_idx, column=c_idx)
            cell.font = d_font
            cell.border = t_border
            cell.fill = fill2
            if c_idx in [1, 3]:
                cell.alignment = Alignment(horizontal='center', vertical='center')
            else:
                cell.alignment = Alignment(horizontal='right', vertical='center')

    for col in ws2.columns:
        max_l = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws2.column_dimensions[col_letter].width = max(max_l + 3, 14)

def build_excel_by_priority(filtered, rank, opt_p, pess_p, native_prov, reg_title, selected_majors, include_scores=True):
    font_name = 'Pinar'
    h_font = Font(name=font_name, size=11, bold=True, color='FFFFFF')
    h_fill = PatternFill(start_color='002060', end_color='002060', fill_type='solid')
    d_font = Font(name=font_name, size=11, color='000000')
    d_bold_font = Font(name=font_name, size=11, bold=True, color='002060')
    alt_fill = PatternFill(start_color='F2F5F9', end_color='F2F5F9', fill_type='solid')
    tahad_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    t_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    al_center = Alignment(horizontal='center', vertical='center')
    al_right = Alignment(horizontal='right', vertical='center', indent=1)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "اولویت‌بندی بر اساس امتیاز"
    ws.views.sheetView[0].rightToLeft = True

    # ترتیب ستون‌ها: اولویت پیشنهادی -> رشته قبولی -> دانشگاه قبولی -> رتبه در سهمیه -> استان -> دوره تحصیلی -> شانس قبولی -> رتبه کشوری -> (امتیازها) -> منبع و سال
    headers = [
        'اولویت پیشنهادی', 'رشته قبولی', 'دانشگاه قبولی',
        'رتبه در سهمیه', 'استان', 'دوره تحصیلی', 'شانس قبولی', 'رتبه کشوری'
    ]
    if include_scores:
        headers.extend(['امتیاز کل اولویت', 'نمره رشته (۱-۱۰)', 'نمره شهر (۱-۱۰)', 'ضریب دوره'])
    headers.append('منبع و سال')

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
        chance_text = get_chance_text(r_val, rank, opt_p, pess_p)
        row_data = [
            r['ترتیب_اولویت'],
            r['رشته قبولی'],
            r['دانشگاه قبولی'],
            r_val,
            r['استان'],
            r.get('دوره_تطبیقی', r.get('دوره', '-')),
            chance_text,
            r.get('رتبه کشوری', '-')
        ]
        if include_scores:
            row_data.extend([
                r['امتیاز_کل'],
                r['نمره_رشته'],
                r['نمره_استان'],
                r['ضریب_دوره']
            ])
        row_data.append(r.get('منبع', '-'))

        ws.append(row_data)
        ws.row_dimensions[r_idx].height = 22
        is_row_tahad = 'تعهدی' in str(r.get('دوره_تطبیقی', ''))
        fill = tahad_fill if is_row_tahad else (alt_fill if r_idx % 2 == 1 else None)

        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=r_idx, column=col_idx)
            h_name = headers[col_idx - 1]
            
            is_bold = (h_name in ['اولویت پیشنهادی', 'رتبه در سهمیه', 'امتیاز کل اولویت'])
            cell.font = d_bold_font if is_bold else d_font
            cell.border = t_border
            if fill:
                cell.fill = fill
                
            if h_name in ['رشته قبولی', 'دانشگاه قبولی']:
                cell.alignment = al_right
            else:
                cell.alignment = al_center

            if h_name in ['اولویت پیشنهادی', 'رتبه در سهمیه', 'رتبه کشوری']:
                if isinstance(val, (int, float)) and val > 0:
                    cell.number_format = '#,##0'
            elif h_name in ['امتیاز کل اولویت', 'نمره رشته (۱-۱۰)', 'نمره شهر (۱-۱۰)', 'ضریب دوره']:
                if isinstance(val, (int, float)) and val > 0:
                    cell.number_format = '0.00'

    if native_prov and native_prov != 'بدون تعهدی':
        ws.append([])
        b_idx = ws.max_row + 1
        ws.merge_cells(start_row=b_idx, start_column=1, end_row=b_idx, end_column=len(headers))
        b_cell = ws.cell(row=b_idx, column=1)
        b_cell.value = (
            f"💡 یادآوری مهم مشاور درباره کدرشته‌های تعهد خدمت استان {native_prov}: "
            f"کدرشته‌های تعهد خدمت ۱.۵ برابر (مناطق محروم / عدالت آموزشی) منحصراً متعلق به داوطلبان بومی استان {native_prov} است. "
            f"با توجه به متغیر بودن ظرفیت‌ها در هر سال، حتماً کدرشته‌های تعهدی دانشگاه‌های علوم پزشکی استان خود را در دفترچه انتخاب رشته امسال بررسی و در لیست نهایی درج فرمایید."
        )
        b_cell.font = Font(name=font_name, size=11, bold=True, color='9C6500')
        b_cell.fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
        b_cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        b_cell.border = t_border
        ws.row_dimensions[b_idx].height = 42

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        cell_lengths = []
        for cell in col:
            val_str = str(cell.value or '')
            if len(val_str) < 55:
                cell_lengths.append(len(val_str))
        max_l = max(cell_lengths) if cell_lengths else 10
        ws.column_dimensions[col_letter].width = max(max_l + 4, 13)

    add_native_checklist_sheet(wb, filtered, selected_majors, native_prov)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

def build_excel_by_major(filtered, rank, opt_p, pess_p, native_prov, reg_title, selected_majors, include_scores=True):
    font_name = 'Pinar'
    h_font = Font(name=font_name, size=11, bold=True, color='FFFFFF')
    h_fill = PatternFill(start_color='002060', end_color='002060', fill_type='solid')
    d_font = Font(name=font_name, size=11, color='000000')
    d_bold_font = Font(name=font_name, size=11, bold=True, color='002060')
    alt_fill = PatternFill(start_color='F2F5F9', end_color='F2F5F9', fill_type='solid')
    tahad_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
    major_banners_fill = PatternFill(start_color='1F497D', end_color='1F497D', fill_type='solid')
    major_banners_font = Font(name=font_name, size=12, bold=True, color='FFFFFF')
    t_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    al_center = Alignment(horizontal='center', vertical='center')
    al_right = Alignment(horizontal='right', vertical='center', indent=1)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تفکیک بر اساس رشته"
    ws.views.sheetView[0].rightToLeft = True

    # ترتیب ستون‌ها: اولویت در رشته -> اولویت کل پیشنهادی -> رشته قبولی -> دانشگاه قبولی -> رتبه در سهمیه -> استان -> دوره تحصیلی -> شانس قبولی -> رتبه کشوری -> (امتیازها) -> منبع و سال
    headers = [
        'اولویت در رشته', 'اولویت کل پیشنهادی', 'رشته قبولی', 'دانشگاه قبولی',
        'رتبه در سهمیه', 'استان', 'دوره تحصیلی', 'شانس قبولی', 'رتبه کشوری'
    ]
    if include_scores:
        headers.extend(['امتیاز کل اولویت', 'نمره رشته (۱-۱۰)', 'نمره شهر (۱-۱۰)', 'ضریب دوره'])
    headers.append('منبع و سال')

    ws.append(headers)
    ws.row_dimensions[1].height = 28

    for col_idx in range(1, len(headers) + 1):
        c = ws.cell(row=1, column=col_idx)
        c.font = h_font
        c.fill = h_fill
        c.alignment = al_center
        c.border = t_border

    # دسته‌بندی رکوردها بر اساس گروه رشته
    grouped_rows = {}
    for _, r in filtered.iterrows():
        m_name = r.get('گروه_رشته', r['رشته قبولی'])
        if m_name not in grouped_rows:
            grouped_rows[m_name] = []
        grouped_rows[m_name].append(r)

    # ترتیب دسته‌ها: اول بر اساس ترتیب رشته‌های انتخابی کاربر، سپس سایر رشته‌ها
    major_order = selected_majors if (selected_majors and 'همه رشته‌ها' not in selected_majors and 'همه' not in selected_majors) else ALL_TARGET_MAJORS
    ordered_keys = []
    for mo in major_order:
        if mo in grouped_rows and mo not in ordered_keys:
            ordered_keys.append(mo)
    for k in grouped_rows:
        if k not in ordered_keys:
            ordered_keys.append(k)

    current_row_idx = 2
    for major_name in ordered_keys:
        rows_in_major = grouped_rows[major_name]
        # مرتب‌سازی گزینه‌های درون رشته بر اساس امتیاز کل نزولی، سپس نمره استان نزولی، سپس رتبه صعودی
        rows_in_major.sort(key=lambda x: (-x['امتیاز_کل'], -x['نمره_استان'], x['رتبه در سهمیه']))

        # ردیف هدر متمایز گروه رشته
        ws.row_dimensions[current_row_idx].height = 26
        ws.merge_cells(start_row=current_row_idx, start_column=1, end_row=current_row_idx, end_column=len(headers))
        m_cell = ws.cell(row=current_row_idx, column=1)
        m_cell.value = f"📌 کدرشته‌های قبولی: {major_name} (شامل {len(rows_in_major):,} کدرشته‌محل — مرتب‌شده بر اساس بالاترین امتیاز)"
        m_cell.font = major_banners_font
        m_cell.fill = major_banners_fill
        m_cell.alignment = Alignment(horizontal='right', vertical='center', indent=1)
        for c_idx in range(1, len(headers) + 1):
            ws.cell(row=current_row_idx, column=c_idx).border = t_border
        current_row_idx += 1

        for in_major_idx, r in enumerate(rows_in_major, 1):
            r_val = int(r['رتبه در سهمیه'])
            chance_text = get_chance_text(r_val, rank, opt_p, pess_p)
            row_data = [
                in_major_idx,
                r['ترتیب_اولویت'],
                r['رشته قبولی'],
                r['دانشگاه قبولی'],
                r_val,
                r['استان'],
                r.get('دوره_تطبیقی', r.get('دوره', '-')),
                chance_text,
                r.get('رتبه کشوری', '-')
            ]
            if include_scores:
                row_data.extend([
                    r['امتیاز_کل'],
                    r['نمره_رشته'],
                    r['نمره_استان'],
                    r['ضریب_دوره']
                ])
            row_data.append(r.get('منبع', '-'))

            ws.append(row_data)
            ws.row_dimensions[current_row_idx].height = 22
            is_row_tahad = 'تعهدی' in str(r.get('دوره_تطبیقی', ''))
            fill = tahad_fill if is_row_tahad else (alt_fill if in_major_idx % 2 == 1 else None)

            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=current_row_idx, column=col_idx)
                h_name = headers[col_idx - 1]

                is_bold = (h_name in ['اولویت در رشته', 'اولویت کل پیشنهادی', 'رتبه در سهمیه', 'امتیاز کل اولویت'])
                cell.font = d_bold_font if is_bold else d_font
                cell.border = t_border
                if fill:
                    cell.fill = fill

                if h_name in ['رشته قبولی', 'دانشگاه قبولی']:
                    cell.alignment = al_right
                else:
                    cell.alignment = al_center

                if h_name in ['اولویت در رشته', 'اولویت کل پیشنهادی', 'رتبه در سهمیه', 'رتبه کشوری']:
                    if isinstance(val, (int, float)) and val > 0:
                        cell.number_format = '#,##0'
                elif h_name in ['امتیاز کل اولویت', 'نمره رشته (۱-۱۰)', 'نمره شهر (۱-۱۰)', 'ضریب دوره']:
                    if isinstance(val, (int, float)) and val > 0:
                        cell.number_format = '0.00'

            current_row_idx += 1

        # ردیف فاصله ظریف بین گروه‌های رشته
        ws.append([])
        ws.row_dimensions[current_row_idx].height = 10
        current_row_idx += 1

    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        cell_lengths = []
        for cell in col:
            val_str = str(cell.value or '')
            if len(val_str) < 55:
                cell_lengths.append(len(val_str))
        max_l = max(cell_lengths) if cell_lengths else 10
        ws.column_dimensions[col_letter].width = max(max_l + 4, 13)

    add_native_checklist_sheet(wb, filtered, selected_majors, native_prov)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

# =====================================================================
# 📄 توابع ساخت و رندر فایل‌های PDF با چیدمان افقی و فونت پینار
# =====================================================================
def build_pdf_by_priority(filtered, rank, opt_p, pess_p, native_prov, reg_title, selected_majors, include_scores=True):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=20,
        rightMargin=20,
        topMargin=26,
        bottomMargin=26
    )
    story = []

    # عنوان سند
    title_style = ParagraphStyle(
        'DocTitle',
        fontName=PDF_FONT_NAME,
        fontSize=12,
        leading=15,
        alignment=1,
        textColor=colors.HexColor('#002060'),
        spaceAfter=5
    )
    story.append(Paragraph(fa_text('📋 گزارش رسمی اولویت‌بندی انتخاب رشته تجربی (چیدمان کلی بر اساس شانس و امتیاز)'), title_style))

    # مشخصات داوطلب در کادر بالا
    min_rank = max(1, int(rank * (1 - opt_p / 100.0)))
    max_rank = int(rank * (1 + pess_p / 100.0))
    tahad_status = f"بومی استان {native_prov}" if (native_prov and native_prov != 'بدون تعهدی') else "بدون کدرشته‌های تعهدی"
    format_label = "نسخه کامل (همراه با ستون‌های نمره‌دهی)" if include_scores else "نسخه ساده (بدون ستون‌های نمره‌دهی)"
    
    meta_p1 = f"سهمیه: {reg_title}  |  رتبه در سهمیه: {rank:,}  |  بازه تحلیلی: {opt_p}٪ خوش‌بینانه ({min_rank:,}) تا {pess_p}٪ بدبینانه ({max_rank:,})"
    meta_p2 = f"وضعیت تعهد خدمت: {tahad_status}  |  تعداد کدرشته‌های استخراج‌شده: {len(filtered):,} رشته‌محل  |  قالب گزارش: {format_label}"

    meta_style = ParagraphStyle(
        'MetaStyle',
        fontName=PDF_FONT_NAME,
        fontSize=7.5,
        leading=10,
        alignment=1,
        textColor=colors.HexColor('#222222')
    )
    meta_table = Table(
        [
            [Paragraph(fa_text(meta_p1), meta_style)],
            [Paragraph(fa_text(meta_p2), meta_style)]
        ],
        colWidths=[800]
    )
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F2F5F9')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#B0C4DE')),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 5))

    # تعریف استایل‌های سلول‌های جدول
    style_h = ParagraphStyle('Head', fontName=PDF_FONT_NAME, fontSize=7.5, leading=9.5, alignment=1, textColor=colors.white)
    style_cell_c = ParagraphStyle('CellC', fontName=PDF_FONT_NAME, fontSize=7, leading=9, alignment=1, textColor=colors.HexColor('#111111'))
    style_cell_r = ParagraphStyle('CellR', fontName=PDF_FONT_NAME, fontSize=7, leading=9, alignment=2, textColor=colors.HexColor('#111111'))
    style_cell_bold = ParagraphStyle('CellB', fontName=PDF_FONT_NAME, fontSize=7, leading=9, alignment=1, textColor=colors.HexColor('#002060'))

    if include_scores:
        headers = [
            'منبع و سال', 'ضریب دوره', 'نمره شهر', 'نمره رشته', 'امتیاز کل',
            'رتبه کشوری', 'شانس قبولی', 'دوره تحصیلی', 'استان', 'رتبه در سهمیه',
            'دانشگاه قبولی', 'رشته قبولی', 'اولویت'
        ]
        col_widths = [70, 35, 35, 35, 45, 45, 70, 60, 50, 50, 165, 110, 30]
    else:
        headers = [
            'منبع و سال', 'رتبه کشوری', 'شانس قبولی', 'دوره تحصیلی', 'استان',
            'رتبه در سهمیه', 'دانشگاه قبولی', 'رشته قبولی', 'اولویت'
        ]
        col_widths = [90, 55, 85, 70, 65, 65, 200, 135, 35]

    table_data = []
    # ردیف هدر
    table_data.append([Paragraph(fa_text(h), style_h) for h in headers])

    for _, r in filtered.iterrows():
        r_val = int(r['رتبه در سهمیه'])
        chance_text = get_chance_text(r_val, rank, opt_p, pess_p)
        r_keshvari_val = r.get('رتبه کشوری', '-')
        if str(r_keshvari_val).isdigit() and int(r_keshvari_val) > 0:
            k_disp = f"{int(r_keshvari_val):,}"
        else:
            k_disp = str(r_keshvari_val)

        if include_scores:
            row = [
                Paragraph(fa_text(str(r.get('منبع', '-'))[:35], wrap_width=16), style_cell_c),
                Paragraph(fa_text(f"{float(r.get('ضریب_دوره', 1.0)):.2f}"), style_cell_c),
                Paragraph(fa_text(f"{float(r.get('نمره_استان', 5.0)):.1f}"), style_cell_c),
                Paragraph(fa_text(f"{float(r.get('نمره_رشته', 5.0)):.1f}"), style_cell_c),
                Paragraph(fa_text(f"{float(r.get('امتیاز_کل', 0.0)):.2f}"), style_cell_bold),
                Paragraph(fa_text(k_disp), style_cell_c),
                Paragraph(fa_text(chance_text), style_cell_c),
                Paragraph(fa_text(str(r.get('دوره_تطبیقی', r.get('دوره', '-')))), style_cell_c),
                Paragraph(fa_text(str(r.get('استان', '-'))), style_cell_c),
                Paragraph(fa_text(f"{r_val:,}"), style_cell_bold),
                Paragraph(fa_text(str(r['دانشگاه قبولی']), wrap_width=25), style_cell_r),
                Paragraph(fa_text(str(r['رشته قبولی']), wrap_width=18), style_cell_r),
                Paragraph(fa_text(str(r['ترتیب_اولویت'])), style_cell_bold)
            ]
        else:
            row = [
                Paragraph(fa_text(str(r.get('منبع', '-'))[:40], wrap_width=20), style_cell_c),
                Paragraph(fa_text(k_disp), style_cell_c),
                Paragraph(fa_text(chance_text), style_cell_c),
                Paragraph(fa_text(str(r.get('دوره_تطبیقی', r.get('دوره', '-')))), style_cell_c),
                Paragraph(fa_text(str(r.get('استان', '-'))), style_cell_c),
                Paragraph(fa_text(f"{r_val:,}"), style_cell_bold),
                Paragraph(fa_text(str(r['دانشگاه قبولی']), wrap_width=30), style_cell_r),
                Paragraph(fa_text(str(r['رشته قبولی']), wrap_width=22), style_cell_r),
                Paragraph(fa_text(str(r['ترتیب_اولویت'])), style_cell_bold)
            ]
        table_data.append(row)

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    ts = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#002060')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
        ('TOPPADDING', (0,0), (-1,-1), 1.5),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D9D9D9')),
    ]
    for idx, (_, r) in enumerate(filtered.iterrows(), 1):
        is_row_tahad = 'تعهدی' in str(r.get('دوره_تطبیقی', ''))
        if is_row_tahad:
            ts.append(('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#FFF2CC')))
        elif idx % 2 == 1:
            ts.append(('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#F2F5F9')))
    t.setStyle(TableStyle(ts))
    story.append(t)

    # باکس یادآوری کدرشته‌های تعهد خدمت
    if native_prov and native_prov != 'بدون تعهدی':
        story.append(Spacer(1, 6))
        warn_style = ParagraphStyle(
            'Warn',
            fontName=PDF_FONT_NAME,
            fontSize=7.5,
            leading=10,
            alignment=1,
            textColor=colors.HexColor('#9C6500')
        )
        warn_msg = (
            f"💡 یادآوری مهم مشاور درباره کدرشته‌های تعهد خدمت استان {native_prov}: "
            f"کدرشته‌های تعهد خدمت ۱.۵ برابر (مناطق محروم / عدالت آموزشی) منحصراً متعلق به داوطلبان بومی استان {native_prov} است. "
            f"با توجه به متغیر بودن ظرفیت‌ها در هر سال، حتماً کدرشته‌های تعهدی دانشگاه‌های علوم پزشکی استان خود را در دفترچه انتخاب رشته امسال بررسی و در لیست نهایی درج فرمایید."
        )
        warn_table = Table([[Paragraph(fa_text(warn_msg), warn_style)]], colWidths=[800])
        warn_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#FFF2CC')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#E0B86C')),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        story.append(warn_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    buf.seek(0)
    return buf

def build_pdf_by_major(filtered, rank, opt_p, pess_p, native_prov, reg_title, selected_majors, include_scores=True):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=20,
        rightMargin=20,
        topMargin=26,
        bottomMargin=26
    )
    story = []

    # عنوان سند
    title_style = ParagraphStyle(
        'DocTitle2',
        fontName=PDF_FONT_NAME,
        fontSize=12,
        leading=15,
        alignment=1,
        textColor=colors.HexColor('#002060'),
        spaceAfter=5
    )
    story.append(Paragraph(fa_text('📋 گزارش رسمی تفکیک موضوعی بر اساس رشته (چیدمان رشته‌ها پشت‌سرهم)'), title_style))

    min_rank = max(1, int(rank * (1 - opt_p / 100.0)))
    max_rank = int(rank * (1 + pess_p / 100.0))
    tahad_status = f"بومی استان {native_prov}" if (native_prov and native_prov != 'بدون تعهدی') else "بدون کدرشته‌های تعهدی"
    format_label = "نسخه کامل (همراه با ستون‌های نمره‌دهی)" if include_scores else "نسخه ساده (بدون ستون‌های نمره‌دهی)"
    
    meta_p1 = f"سهمیه: {reg_title}  |  رتبه در سهمیه: {rank:,}  |  بازه تحلیلی: {opt_p}٪ خوش‌بینانه ({min_rank:,}) تا {pess_p}٪ بدبینانه ({max_rank:,})"
    meta_p2 = f"وضعیت تعهد خدمت: {tahad_status}  |  تعداد کدرشته‌های استخراج‌شده: {len(filtered):,} رشته‌محل  |  قالب گزارش: {format_label}"

    meta_style = ParagraphStyle(
        'MetaStyle2',
        fontName=PDF_FONT_NAME,
        fontSize=7.5,
        leading=10,
        alignment=1,
        textColor=colors.HexColor('#222222')
    )
    meta_table = Table(
        [
            [Paragraph(fa_text(meta_p1), meta_style)],
            [Paragraph(fa_text(meta_p2), meta_style)]
        ],
        colWidths=[800]
    )
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F2F5F9')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#B0C4DE')),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 5))

    style_h = ParagraphStyle('Head2', fontName=PDF_FONT_NAME, fontSize=7.5, leading=9.5, alignment=1, textColor=colors.white)
    style_banner = ParagraphStyle('Banner2', fontName=PDF_FONT_NAME, fontSize=8, leading=10, alignment=2, textColor=colors.white)
    style_cell_c = ParagraphStyle('CellC2', fontName=PDF_FONT_NAME, fontSize=7, leading=9, alignment=1, textColor=colors.HexColor('#111111'))
    style_cell_r = ParagraphStyle('CellR2', fontName=PDF_FONT_NAME, fontSize=7, leading=9, alignment=2, textColor=colors.HexColor('#111111'))
    style_cell_bold = ParagraphStyle('CellB2', fontName=PDF_FONT_NAME, fontSize=7, leading=9, alignment=1, textColor=colors.HexColor('#002060'))

    if include_scores:
        headers = [
            'منبع و سال', 'ضریب دوره', 'نمره شهر', 'نمره رشته', 'امتیاز کل',
            'رتبه کشوری', 'شانس قبولی', 'دوره تحصیلی', 'استان', 'رتبه در سهمیه',
            'دانشگاه قبولی', 'رشته قبولی', 'اولویت کل', 'اولویت رشته'
        ]
        col_widths = [65, 32, 32, 32, 42, 42, 65, 55, 45, 45, 155, 105, 42, 43]
    else:
        headers = [
            'منبع و سال', 'رتبه کشوری', 'شانس قبولی', 'دوره تحصیلی', 'استان',
            'رتبه در سهمیه', 'دانشگاه قبولی', 'رشته قبولی', 'اولویت کل', 'اولویت رشته'
        ]
        col_widths = [80, 50, 80, 65, 60, 60, 195, 130, 40, 40]

    num_cols = len(headers)
    table_data = []
    table_data.append([Paragraph(fa_text(h), style_h) for h in headers])

    ts = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#002060')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1.5),
        ('TOPPADDING', (0,0), (-1,-1), 1.5),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
        ('RIGHTPADDING', (0,0), (-1,-1), 2),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D9D9D9')),
    ]

    # دسته‌بندی رکوردها بر اساس گروه رشته
    grouped_rows = {}
    for _, r in filtered.iterrows():
        m_name = r.get('گروه_رشته', r['رشته قبولی'])
        if m_name not in grouped_rows:
            grouped_rows[m_name] = []
        grouped_rows[m_name].append(r)

    major_order = selected_majors if (selected_majors and 'همه رشته‌ها' not in selected_majors and 'همه' not in selected_majors) else ALL_TARGET_MAJORS
    ordered_keys = []
    for mo in major_order:
        if mo in grouped_rows and mo not in ordered_keys:
            ordered_keys.append(mo)
    for k in grouped_rows:
        if k not in ordered_keys:
            ordered_keys.append(k)

    for major_name in ordered_keys:
        rows_in_major = grouped_rows[major_name]
        rows_in_major.sort(key=lambda x: (-x['امتیاز_کل'], -x['نمره_استان'], x['رتبه در سهمیه']))

        banner_row_idx = len(table_data)
        banner_text = f"📌 کدرشته‌های قبولی: {major_name} (شامل {len(rows_in_major):,} کدرشته‌محل — مرتب‌شده بر اساس بالاترین امتیاز)"
        banner_p = Paragraph(fa_text(banner_text), style_banner)
        table_data.append([banner_p] + [''] * (num_cols - 1))
        ts.append(('SPAN', (0, banner_row_idx), (-1, banner_row_idx)))
        ts.append(('BACKGROUND', (0, banner_row_idx), (-1, banner_row_idx), colors.HexColor('#1F497D')))

        for in_major_idx, r in enumerate(rows_in_major, 1):
            curr_row_idx = len(table_data)
            r_val = int(r['رتبه در سهمیه'])
            chance_text = get_chance_text(r_val, rank, opt_p, pess_p)
            r_keshvari_val = r.get('رتبه کشوری', '-')
            if str(r_keshvari_val).isdigit() and int(r_keshvari_val) > 0:
                k_disp = f"{int(r_keshvari_val):,}"
            else:
                k_disp = str(r_keshvari_val)

            if include_scores:
                row = [
                    Paragraph(fa_text(str(r.get('منبع', '-'))[:35], wrap_width=16), style_cell_c),
                    Paragraph(fa_text(f"{float(r.get('ضریب_دوره', 1.0)):.2f}"), style_cell_c),
                    Paragraph(fa_text(f"{float(r.get('نمره_استان', 5.0)):.1f}"), style_cell_c),
                    Paragraph(fa_text(f"{float(r.get('نمره_رشته', 5.0)):.1f}"), style_cell_c),
                    Paragraph(fa_text(f"{float(r.get('امتیاز_کل', 0.0)):.2f}"), style_cell_bold),
                    Paragraph(fa_text(k_disp), style_cell_c),
                    Paragraph(fa_text(chance_text), style_cell_c),
                    Paragraph(fa_text(str(r.get('دوره_تطبیقی', r.get('دوره', '-')))), style_cell_c),
                    Paragraph(fa_text(str(r.get('استان', '-'))), style_cell_c),
                    Paragraph(fa_text(f"{r_val:,}"), style_cell_bold),
                    Paragraph(fa_text(str(r['دانشگاه قبولی']), wrap_width=24), style_cell_r),
                    Paragraph(fa_text(str(r['رشته قبولی']), wrap_width=16), style_cell_r),
                    Paragraph(fa_text(str(r['ترتیب_اولویت'])), style_cell_bold),
                    Paragraph(fa_text(str(in_major_idx)), style_cell_bold)
                ]
            else:
                row = [
                    Paragraph(fa_text(str(r.get('منبع', '-'))[:40], wrap_width=18), style_cell_c),
                    Paragraph(fa_text(k_disp), style_cell_c),
                    Paragraph(fa_text(chance_text), style_cell_c),
                    Paragraph(fa_text(str(r.get('دوره_تطبیقی', r.get('دوره', '-')))), style_cell_c),
                    Paragraph(fa_text(str(r.get('استان', '-'))), style_cell_c),
                    Paragraph(fa_text(f"{r_val:,}"), style_cell_bold),
                    Paragraph(fa_text(str(r['دانشگاه قبولی']), wrap_width=28), style_cell_r),
                    Paragraph(fa_text(str(r['رشته قبولی']), wrap_width=20), style_cell_r),
                    Paragraph(fa_text(str(r['ترتیب_اولویت'])), style_cell_bold),
                    Paragraph(fa_text(str(in_major_idx)), style_cell_bold)
                ]
            table_data.append(row)
            is_row_tahad = 'تعهدی' in str(r.get('دوره_تطبیقی', ''))
            if is_row_tahad:
                ts.append(('BACKGROUND', (0, curr_row_idx), (-1, curr_row_idx), colors.HexColor('#FFF2CC')))
            elif in_major_idx % 2 == 1:
                ts.append(('BACKGROUND', (0, curr_row_idx), (-1, curr_row_idx), colors.HexColor('#F2F5F9')))

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(ts))
    story.append(t)

    # باکس یادآوری کدرشته‌های تعهد خدمت
    if native_prov and native_prov != 'بدون تعهدی':
        story.append(Spacer(1, 6))
        warn_style = ParagraphStyle(
            'Warn2',
            fontName=PDF_FONT_NAME,
            fontSize=7.5,
            leading=10,
            alignment=1,
            textColor=colors.HexColor('#9C6500')
        )
        warn_msg = (
            f"💡 یادآوری مهم مشاور درباره کدرشته‌های تعهد خدمت استان {native_prov}: "
            f"کدرشته‌های تعهد خدمت ۱.۵ برابر (مناطق محروم / عدالت آموزشی) منحصراً متعلق به داوطلبان بومی استان {native_prov} است. "
            f"با توجه به متغیر بودن ظرفیت‌ها در هر سال، حتماً کدرشته‌های تعهدی دانشگاه‌های علوم پزشکی استان خود را در دفترچه انتخاب رشته امسال بررسی و در لیست نهایی درج فرمایید."
        )
        warn_table = Table([[Paragraph(fa_text(warn_msg), warn_style)]], colWidths=[800])
        warn_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#FFF2CC')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#E0B86C')),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        story.append(warn_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    buf.seek(0)
    return buf

def send_pdf_results(chat_id):
    state = user_state.get(chat_id, {})
    filtered = state.get('last_filtered')
    if filtered is None or filtered.empty:
        bot.send_message(chat_id, "⚠️ داده‌ای برای تولید PDF یافت نشد. لطفاً ابتدا یک استعلام انجام دهید.")
        return
        
    rank = state.get('rank', 5000)
    region = state.get('region', 2)
    reg_title = f"منطقه {region}" if region in [1, 2, 3] else "سهمیه ۵ درصد ایثارگران"
    opt_p = state.get('opt_pct', 30)
    pess_p = state.get('pess_pct', 25)
    native_prov = state.get('native_province', None)
    selected_majors = state.get('selected_majors', ['همه رشته‌ها'])
    include_scores = state.get('include_scores', True)
    clean_reg_name = reg_title.replace(' ', '_')
    total_count = len(filtered)
    format_label = "📊 نسخه کامل (همراه با ستون‌های نمره‌دهی و فرمول)" if include_scores else "📋 نسخه ساده (بدون ستون‌های نمره‌دهی)"

    status_msg = bot.send_message(chat_id, "⏳ در حال ساخت فایل‌های PDF با چیدمان افقی A4 و فونت پینار... لطفاً چند لحظه شکیبا باشید.")
    
    try:
        # فایل PDF ۱: اولویت‌بندی کلی
        file_title_pdf1 = f"۱_اولویت_بندی_انتخاب_رشته_رتبه_{rank}_{clean_reg_name}.pdf"
        buf_pdf1 = build_pdf_by_priority(filtered, rank, opt_p, pess_p, native_prov, reg_title, selected_majors, include_scores=include_scores)
        
        bot.send_document(
            chat_id,
            buf_pdf1,
            visible_file_name=file_title_pdf1,
            caption=(
                f"📄 **نسخه چاپی PDF (فایل اول: اولویت‌بندی کلی)**\n\n"
                f"👤 رتبه: **{rank:,}** ({reg_title}) | تعداد: **{total_count:,}** رشته‌محل\n"
                f"📐 **چیدمان:** افقی (Landscape A4) مناسب پرینت مستقیم\n"
                f"🖋 **فونت:** پینار (Pinar) خوانا و استاندارد\n"
                f"⚙️ **قالب:** {format_label}"
            ),
            parse_mode='Markdown'
        )

        # فایل PDF ۲: تفکیک بر اساس رشته
        file_title_pdf2 = f"۲_تفکیک_بر_اساس_رشته_رتبه_{rank}_{clean_reg_name}.pdf"
        buf_pdf2 = build_pdf_by_major(filtered, rank, opt_p, pess_p, native_prov, reg_title, selected_majors, include_scores=include_scores)

        bot.send_document(
            chat_id,
            buf_pdf2,
            visible_file_name=file_title_pdf2,
            caption=(
                f"📄 **نسخه چاپی PDF (فایل دوم: تفکیک بر اساس رشته)**\n\n"
                f"👤 رتبه: **{rank:,}** ({reg_title}) | تعداد: **{total_count:,}** رشته‌محل\n"
                f"📐 **چیدمان:** افقی (Landscape A4) با بنرهای تفکیک هر رشته\n"
                f"🖋 **فونت:** پینار (Pinar) خوانا و استاندارد\n"
                f"⚙️ **قالب:** {format_label}"
            ),
            parse_mode='Markdown'
        )
        
        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass

    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا در تولید فایل PDF: {e}")

# =====================================================================
# 🔍 مرحله محاسباتی، شکستن تساوی و تولید دو فایل اکسل خروجی
# =====================================================================
def execute_search_and_send(chat_id):
    state = user_state.get(chat_id, {})
    rank = state.get('rank', 5000)
    region = state.get('region', 2)
    reg_title = f"منطقه {region}" if region in [1, 2, 3] else "سهمیه ۵ درصد ایثارگران"
    opt_p = state.get('opt_pct', 30)
    pess_p = state.get('pess_pct', 25)
    selected_sources = state.get('selected_sources', [])
    src_filter = state.get('source', 'همه')
    src_label = state.get('source_label', '🌐 همه با هم')
    selected_majors = state.get('selected_majors', ['همه رشته‌ها'])
    manual_major_scores = state.get('major_scores', {})
    selected_provinces = state.get('selected_provinces', ['سراسر کشور'])
    manual_prov_scores = state.get('prov_scores', {})
    
    min_rank = max(1, int(rank * (1 - opt_p / 100.0)))
    max_rank = int(rank * (1 + pess_p / 100.0))
    
    # فیلتر پایگاه داده (تک‌منبع یا چندمنبع همزمان)
    if not selected_sources or 'all' in selected_sources or len(selected_sources) == len(AVAILABLE_SOURCES):
        if region == 5:
            sub_df = df[df['سهمیه'] == 5].copy()
        else:
            sub_df = df.copy()
    else:
        cond_src = pd.Series(False, index=df.index)
        for k in selected_sources:
            if k == '1404' or k == '۱۴۰۴':
                cond_src = cond_src | (df['منبع'].astype(str).str.contains('1404', na=False) & ~df['منبع'].astype(str).str.contains('5 درصد|۵ درصد', na=False))
            elif k == '1403' or k == '۱۴۰۳':
                cond_src = cond_src | df['منبع'].astype(str).str.contains('1403', na=False)
            elif k == '5pct' or k == '۵درصد':
                cond_src = cond_src | (df['سهمیه'] == 5)
            elif k == 'sanjesh' or k == 'سنجش':
                cond_src = cond_src | df['منبع'].astype(str).str.contains('سنجش|جامع', na=False)
            elif k == 'mehromaah' or k == 'مهروماه':
                cond_src = cond_src | df['منبع'].astype(str).str.contains('مهر و ماه|مهروماه', na=False)
        sub_df = df[cond_src].copy()

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
        
    # 2.5. فیلتر کدرشته‌های تعهد خدمت (بومی‌گزینی اختصاصی)
    native_prov = state.get('native_province', None)
    def filter_commitment_seats(row):
        is_comm = is_commitment_row(row)
        if not is_comm:
            return True
        if not native_prov or native_prov == 'بدون تعهدی':
            return False
        return row.get('استان', '') == native_prov
        
    filtered = filtered[filtered.apply(filter_commitment_seats, axis=1)]
    
    if filtered.empty:
        # بررسی تشخیصی هوشمند: آیا در سراسر کشور یا با بازه گسترده‌تر قبولی وجود دارد؟
        check_wider = sub_df[
            (sub_df['سهمیه'] == region) & 
            (sub_df['رتبه در سهمیه'] >= max(1, int(rank * 0.5))) & 
            (sub_df['رتبه در سهمیه'] <= int(rank * 1.5))
        ]
        if selected_majors and 'همه رشته‌ها' not in selected_majors and 'همه' not in selected_majors:
            cond_m = False
            for m in selected_majors:
                cond_m = cond_m | check_wider['رشته قبولی'].apply(lambda r: match_major_in_name(m, r))
            check_wider = check_wider[cond_m]
            
        hint_text = ""
        if len(check_wider) > 0 and selected_provinces and 'سراسر کشور' not in selected_provinces:
            hint_text = f"\n\n💡 **نکته مشاور:** در استان‌های انتخابی شما در این بازه قبولی ثبت نشده، اما در **سایر استان‌های کشور تعداد {len(check_wider):,} قبولی** برای این رشته‌ها وجود دارد! پیشنهاد می‌شود گزینه «سراسر کشور» را انتخاب فرمایید."
        else:
            hint_text = "\n\n💡 **راهنمای مشاور:** پیشنهاد می‌شود بازه درصدی (خوش‌بینانه / بدبینانه) را افزایش دهید یا تعداد رشته‌ها و استان‌های انتخابی را گسترش دهید."

        restart_markup = types.InlineKeyboardMarkup()
        restart_markup.add(types.InlineKeyboardButton("🔄 استعلام مجدد", callback_data="restart"))
        msg_text = (
            f"❌ در بازه رتبه‌ای **{min_rank:,}** الی **{max_rank:,}** ({reg_title})\n"
            f"قبولی متناسب با رشته‌ها و استان‌های انتخابی شما در این منبع یافت نشد."
            f"{hint_text}"
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
            for idx, tm in enumerate(ALL_TARGET_MAJORS):
                if match_major_in_name(tm, r_name):
                    return round(1.0 + ((len(ALL_TARGET_MAJORS) - (idx + 1)) / (len(ALL_TARGET_MAJORS) - 1)) * 9.0, 2)
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
    filtered['گروه_رشته'] = filtered['رشته قبولی'].apply(lambda r: get_primary_target_major(r, selected_majors))
    
    # 6. شکستن تساوی و مرتب‌سازی نزولی بر اساس اولویت کل
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
    
    export_pdf = state.get('export_pdf', False)
    format_label = "📊 نسخه کامل (همراه با ستون‌های نمره‌دهی و فرمول)" if include_scores else "📋 نسخه ساده (بدون ستون‌های نمره‌دهی)"
    
    # ذخیره در state کاربر برای امکان دانلود مستقیم PDF در هر لحظه
    user_state[chat_id]['last_filtered'] = filtered.copy()

    # -------------------------------------------------------------
    # 💬 پیام خلاصه نهایی
    # -------------------------------------------------------------
    summary_msg = (
        f"🎯 **محاسبات اولویت‌بندی انتخاب رشته تجربی با موفقیت انجام شد!**\n\n"
        f"👤 **سهمیه:** {reg_title} | **رتبه داوطلب:** {rank:,}\n"
        f"📈 **بازه تحلیلی:** {opt_p}٪ خوش‌بینانه ({min_rank:,}) تا {pess_p}٪ بدبینانه ({max_rank:,})\n"
        f"📂 **منبع آماری:** {src_label}\n"
        f"🎓 **رشته‌های انتخابی:** {majors_disp}\n"
        f"🗺 **استان‌های انتخابی:** {provs_disp}\n"
        f"🏥 **وضعیت تعهد خدمت:** {'بومی ' + native_prov if (native_prov and native_prov != 'بدون تعهدی') else 'بدون کدرشته‌های تعهدی'}\n"
        f"⚙️ **قالب گزارش‌ها:** {format_label}\n"
        f"📌 **تعداد کل کدرشته‌محل‌های یافت‌شده:** **{total_count:,} رشته‌محل**\n\n"
        f"⚖️ **فرمول رتبه‌بندی:** `(نمره رشته × ۱.۲ + نمره شهر × ۱.۰) × ضریب دوره`\n\n"
        f"📁 **فایل‌های اکسل و PDF اختصاصی آماده پرینت در ادامه ارسال می‌گردد:**\n"
        f"  1️⃣ **فایل ۱ (اولویت‌بندی کلی):** چیدمان از بالاترین امتیاز به پایین‌ترین شانس\n"
        f"  2️⃣ **فایل ۲ (تفکیک رشته‌ها):** چیدمان موضوعی پشت‌سرهم (همه پرستاری‌ها پشت هم، همه پزشکی‌ها پشت هم و...) به همراه اولویت درون‌رشته‌ای"
    )
    bot.send_message(chat_id, summary_msg, parse_mode='Markdown')

    # ارسال پیام راهنمای چک‌لیست تعهد خدمت در تلگرام
    if native_prov and native_prov != 'بدون تعهدی':
        check_majors_tg = selected_majors if ('همه رشته‌ها' not in selected_majors and 'همه' not in selected_majors) else ALL_TARGET_MAJORS[:10]
        existing_tahad_majors_tg = set()
        for _, r in filtered.iterrows():
            if 'تعهدی' in str(r.get('دوره_تطبیقی', '')):
                for m in check_majors_tg:
                    if match_major_in_name(m, r.get('رشته قبولی', '')):
                        existing_tahad_majors_tg.add(m)
                        
        checklist_lines = []
        for m in check_majors_tg:
            if m in existing_tahad_majors_tg:
                checklist_lines.append(f"▫️ ✅ **{m}:** دارای قبولی تعهدی در سوابق.")
            else:
                checklist_lines.append(f"▫️ ⚠️ **{m}:** در سوابق نبود؛ *حتماً دفترچه امسال بررسی و در صورت داشتن تعهدی، به فرم انتخاب رشته اضافه گردد.*")
                
        checklist_text = (
            f"🏥 **چک‌لیست کدرشته‌های تعهد خدمت ۱.۵ برابر (بومی استان {native_prov}):**\n"
            f"با توجه به اینکه کدرشته‌های تعهد خدمت صرفاً به داوطلبان بومی استان **{native_prov}** تعلق دارد و ظرفیت‌ها هر سال تغییر می‌کند:\n\n"
            + "\n".join(checklist_lines) +
            f"\n\n💡 *شیت دوم هر دو فایل اکسل نیز به این چک‌لیست اختصاص یافته است.*"
        )
        bot.send_message(chat_id, checklist_text, parse_mode='Markdown')

    # -------------------------------------------------------------
    # 📑 تولید و ارسال فایل اکسل ۱: اولویت‌بندی بر اساس امتیاز کل
    # -------------------------------------------------------------
    clean_reg_name = reg_title.replace(' ', '_')
    file_title_prio = f"۱_اولویت_بندی_بر_اساس_امتیاز_رتبه_{rank}_{clean_reg_name}.xlsx" if include_scores else f"۱_اولویت_بندی_انتخاب_رشته_رتبه_{rank}_{clean_reg_name}.xlsx"
    buf_prio = build_excel_by_priority(filtered, rank, opt_p, pess_p, native_prov, reg_title, selected_majors, include_scores=include_scores)
    
    bot.send_document(
        chat_id, 
        buf_prio, 
        visible_file_name=file_title_prio, 
        caption=(
            f"📁 **فایل اکسل اول: اولویت‌بندی کلی بر اساس امتیاز و شانس قبولی**\n\n"
            f"👤 رتبه: **{rank:,}** ({reg_title}) | تعداد: **{total_count:,}** رشته‌محل\n"
            f"📌 چیدمان جامع بر اساس فرمول اولویت، نمرات رشته، شهر و ضریب دوره.\n"
            f"🖋 فونت: پینار (Pinar)\n"
            f"⚙️ **قالب:** {format_label}"
        ),
        parse_mode='Markdown'
    )

    # -------------------------------------------------------------
    # 📑 تولید و ارسال فایل اکسل ۲: تفکیک بر اساس رشته‌ها پشت‌سرهم
    # -------------------------------------------------------------
    file_title_major = f"۲_تفکیک_بر_اساس_رشته_رتبه_{rank}_{clean_reg_name}.xlsx"
    buf_major = build_excel_by_major(filtered, rank, opt_p, pess_p, native_prov, reg_title, selected_majors, include_scores=include_scores)
    
    bot.send_document(
        chat_id, 
        buf_major, 
        visible_file_name=file_title_major, 
        caption=(
            f"📁 **فایل اکسل دوم: تفکیک موضوعی بر اساس رشته**\n\n"
            f"👤 رتبه: **{rank:,}** ({reg_title}) | تعداد: **{total_count:,}** رشته‌محل\n"
            f"📌 چیدمان رشته‌ها پشت‌سرهم (پرستاری، پزشکی، دندانپزشکی و...) به همراه اولویت درون‌رشته‌ای.\n"
            f"🖋 فونت: پینار (Pinar)\n"
            f"⚙️ **قالب:** {format_label}"
        ),
        parse_mode='Markdown'
    )
    
    # -------------------------------------------------------------
    # 📄 ارسال فایل‌های PDF چاپی (در صورت درخواست در منو)
    # -------------------------------------------------------------
    if export_pdf:
        send_pdf_results(chat_id)
        
    action_markup = types.InlineKeyboardMarkup(row_width=1)
    if not export_pdf:
        action_markup.add(types.InlineKeyboardButton("📄 دریافت هر دو فایل به صورت PDF چاپی (افقی A4)", callback_data="dl_pdf_both"))
    action_markup.add(types.InlineKeyboardButton("🔄 استعلام جدید", callback_data="restart"))
    
    bot.send_message(chat_id, "💡 برای دریافت نسخه چاپی PDF یا استعلام جدید، گزینه‌های زیر را لمس فرمایید:", reply_markup=action_markup)

@bot.callback_query_handler(func=lambda call: call.data == "dl_pdf_both")
def callback_dl_pdf_both(call):
    chat_id = call.message.chat.id
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
    bot.answer_callback_query(call.id, "در حال تولید فایل‌های PDF چاپی...")
    send_pdf_results(chat_id)

@bot.callback_query_handler(func=lambda call: call.data == "restart")
def callback_restart(call):
    chat_id = call.message.chat.id
    if not is_authenticated(chat_id):
        save_auth_user(chat_id)
        
    user_state[chat_id] = {
        'step': 'select_region',
        'opt_pct': 30,
        'pess_pct': 25,
        'current_major_cat': 'doctor',
        'selected_majors': [],
        'major_scores': {},
        'selected_provinces': [],
        'prov_scores': {},
        'native_province': None,
        'include_scores': True,
        'selected_sources': []
    }
    bot.answer_callback_query(call.id, "شروع مجدد")
    bot.send_message(
        chat_id,
        "🔄 **استعلام جدید انتخاب رشته کنکور تجربی**\n\n"
        "📍 لطفاً سهمیه یا منطقه خود را انتخاب فرمایید:",
        parse_mode='Markdown',
        reply_markup=get_region_keyboard()
    )

# =====================================================================
# 🌐 وب‌سرور داخلی و پینگر خودکار Render (ضد خواب زمستانی ۲۴ ساعته)
# =====================================================================
HTML_STATUS_PAGE = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>ربات انتخاب رشته کنکور - وضعیت ۲۴ ساعته</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; text-align: center; padding-top: 60px; margin: 0; }
        .card { background: #1e293b; max-width: 520px; margin: 0 auto; padding: 30px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border: 1px solid #334155; }
        .status-badge { display: inline-block; background: #10b981; color: white; padding: 6px 16px; border-radius: 20px; font-weight: bold; margin-bottom: 20px; font-size: 14px; }
        h1 { color: #38bdf8; font-size: 22px; margin-bottom: 12px; }
        p { color: #94a3b8; font-size: 14px; line-height: 1.6; }
        .tag { font-family: monospace; background: #334155; padding: 2px 6px; border-radius: 4px; color: #f1f5f9; }
    </style>
</head>
<body>
    <div class="card">
        <div class="status-badge">● ۲۴ ساعته آنلاین و فعال (Active 24/7)</div>
        <h1>ربات تلگرام انتخاب رشته کنکور</h1>
        <p>وب‌سرور پایدارساز و سیستم ضد خاموشی خودکار (<span class="tag">Keep-Alive</span>) با موفقیت در حال اجرا است.</p>
        <p style="margin-top: 15px; font-size: 12px; color: #64748b;">Render Sleep Preventer & Health Monitor Active</p>
    </div>
</body>
</html>"""

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(HTML_STATUS_PAGE.strip().encode('utf-8'))
        
    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()

    def log_message(self, format, *args):
        return

def auto_pinger_loop():
    """حلقه پینگ خودکار جهت جلوگیری از به خواب رفتن سرور رندر در پلان رایگان"""
    time.sleep(25)  # فرصت برای بالا آمدن وب‌سرور
    default_url = "https://konkur-bot-1.onrender.com"
    while True:
        url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("APP_URL") or default_url
        now_str = time.strftime("%H:%M:%S")
        try:
            if not url.startswith("http"):
                url = "https://" + url
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (RenderKeepAlive/1.0)"}
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                if response.status == 200:
                    print(f"💓 [Keep-Alive] پینگ خودکار موفق به {url} در {now_str} (سرور بیدار نگه‌داشته شد)")
        except Exception as e:
            print(f"⚠️ [Keep-Alive] وضعیت پینگ خودکار: {e}")
        time.sleep(480)  # هر ۸ دقیقه یک‌بار پینگ می‌زند (قبل از مهلت ۱۵ دقیقه‌ای رندر)

def run_bot_polling():
    print("🚀 پردازشگر تلگرام با سیستم رمز عبور، تفکیک سهمیه ۵ درصد و منابع جدید آماده اتصال شد...")
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=20, restart_on_change=False, skip_pending=True)
        except Exception as e:
            err_str = str(e)
            print(f"⚠️ پیام سرور تلگرام: {err_str}")
            if "409" in err_str or "Conflict" in err_str:
                print("⏳ تداخل موقت توکن با اتصال قبلی؛ ۱۰ ثانیه صبر برای آزادسازی نشست تلگرام...")
                time.sleep(10)
            else:
                time.sleep(10)

if __name__ == '__main__':
    # 1. اجرای پولینگ تلگرام در ترد پس‌زمینه با قابلیت اتصال مجدد خودکار
    t_bot = threading.Thread(target=run_bot_polling, daemon=True)
    t_bot.start()

    # 2. اجرای پینگر خودکار در پس‌زمینه برای بیدار نگه‌داشتن دائمی رندر (ضد خواب زمستانی)
    t_pinger = threading.Thread(target=auto_pinger_loop, daemon=True)
    t_pinger.start()
    
    # 3. اجرای وب‌سرور روی ترد اصلی جهت باز بودن قطعی پورت شبکه برای رندر
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 وب‌سرور رندر با موفقیت روی پورت {port} فعال شد.")
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
