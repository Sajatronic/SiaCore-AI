# NexusFlow Data Agent

Agent آلي يجلب بيانات الأسعار والمخزون من Nexar API ويزامنها مع Supabase
(جداول `distributer` و `stock`)، مع منع صارم لتكرار سجلات الموزعين عبر
تطبيع الأسماء (name normalization).

## 1. الإعداد

```bash
cd nexusflow-agent
python -m venv venv
source venv/bin/activate   # على ويندوز: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# افتح .env واملأ:
#   SUPABASE_URL, SUPABASE_SERVICE_KEY
#   NEXAR_CLIENT_ID, NEXAR_CLIENT_SECRET
```

## 2. التشغيل اليدوي

```bash
# قطعة واحدة (فورية، بدون أي منطق دفعات/checkpoint)
python main.py --mpn LM358 --type manual

# دفعة (يُقرأ كل أرقام القطع تلقائياً من جدول parts في Supabase) - يعالج
# تلقائياً MAX_PARTS_PER_RUN فقط
python main.py --batch --type manual

# تجاوز الحد الافتراضي لهذا التشغيل فقط
python main.py --batch --limit 20 --type manual

# تصفير نقطة التوقف والبدء من أول القائمة من جديد
python main.py --batch --reset-checkpoint
```

## 3. نظام الدفعات (Batch) وحل مشكلة حد Nexar API ⭐

بما أن Nexar API له حد للطلبات (rate limit)، الـ Agent **لا يعالج كل
القطع الموجودة في جدول `parts` دفعة واحدة**. بدلاً من ذلك:

- عند `--batch`، يُقرأ عمود `mpn` بالكامل من جدول `parts` في Supabase
  (مرتَّباً حسب `id` لثبات الترتيب بين التشغيلات)، **وليس** من أي ملف محلي.
- `MAX_PARTS_PER_RUN` (في `.env`, افتراضياً 50): أقصى عدد قطع يُعالَج في
  التشغيل الواحد.
- `NEXAR_REQUEST_DELAY_SECONDS` (افتراضياً 1.0): تأخير بالثواني بين كل
  طلب وطلب لـ Nexar داخل نفس التشغيل.
- `checkpoint.json`: ملف محلي (يُنشأ تلقائياً بجانب الكود) يحفظ آخر موضع
  توقّفنا عنده في القائمة. كل تشغيل جديد يكمل من هناك، ولمّا يوصل لآخر
  القائمة يرجع للبداية تلقائياً (دورة كاملة/round robin) — لا تكرار
  ولا فجوات.

مثال: لو عندك 500 قطعة في جدول `parts` و `MAX_PARTS_PER_RUN=50`، تحتاج 10
تشغيلات لتغطية القائمة كاملة مرة واحدة (مثلاً عبر الجدولة كل ساعة)، وبعدها
تبدأ الدورة التالية تلقائياً لتحديث الأسعار من جديد.

⚠️ ملف `checkpoint.json` محلي فقط (على القرص، ليس في Supabase). لو نشرت
الـ Agent على منصة بدون تخزين دائم (ephemeral)، تأكد إنه محفوظ في volume
دائم، وإلا سيرجع للبداية عند كل إعادة تشغيل للخدمة.

⚠️ إضافة/حذف قطع في جدول `parts` أثناء التشغيل قد يغيّر ترتيب القائمة
النسبي (`checkpoint.json` يحفظ مجرد رقم index وليس mpn نفسه) - تأثير
بسيط عملياً (بعض القطع قد تُعالَج مرتين أو تتخطى دورة، لا تكرار بيانات
خاطئة) لكن يستحق الانتباه له.

## 4. التشغيل المجدول (احتياطي)

```bash
python scheduler.py
```

يعمل كعملية دائمة (long-running)، ويشغّل دفعة واحدة (`run_batch_with_checkpoint`)
كل ساعة افتراضياً (عدّل `CronTrigger` داخل `scheduler.py` حسب باقة Nexar
عندك — كل ساعة، كل 15 دقيقة، يومياً... إلخ). يمكن أيضاً نشره كخدمة Docker
أو على Railway/Render بدل الاعتماد على cron الخاص بنظام التشغيل.

## 5. آلية منع تكرار الموزعين (الأهم في المشروع)

راجع `distributor_resolver.py`. الملخص:

1. أي اسم موزع قادم من Nexar يُطبَّع: أحرف صغيرة، حذف كلمات ضوضاء
   (Inc, Ltd, Electronics...)، حذف الرموز والمسافات.
2. يُقارَن بنفس الأسماء المطبَّعة لكل الموزعين الموجودين في `distributer`.
3. تطابق تام → استخدام `D_code` الموجود، لا إنشاء جديد أبداً.
4. لا تطابق → إنشاء موزع جديد بكود جديد (`SUPxxx`) وقيم افتراضية آمنة
   (`D_status = Pending Review`, `vetting_status = Unverified`, ...) بدل NULL.

## 6. آلية التسجيل في `agent_logs`

الجدول الفعلي هو سجل **ملخّص لكل تشغيل** (صف واحد لكل run)، وليس سجل أحداث
تفصيلية:

```
id, run_timestamp, source_name, records_fetched, records_updated,
status, error_message, records_skipped
```

`logger.py` يعمل كالتالي:
1. عند بدء التشغيل: يُنشئ صفاً واحداً بحالة `status = 'running'` فوراً
   (تقدر تشوفه في القاعدة أثناء التشغيل الفعلي).
2. أثناء التشغيل: كل الرسائل (معلومات/تحذيرات/أخطاء) تُطبع على الطرفية
   فقط وتُجمَّع داخلياً في عدادات.
3. عند الانتهاء: يُحدَّث نفس الصف بالنتائج النهائية:
   - `records_fetched` = عدد القطع (MPN) التي تمت معالجتها
   - `records_updated` = عدد صفوف `stock` التي تم إدراجها/تحديثها
   - `records_skipped` = عدد الموزعين الذين احتاجوا مراجعة يدوية
   - `status` = `success` / `partial_success` / `failed`
   - `error_message` = ملخّص نصي لأي أخطاء أو ملاحظات (بما فيها عدد
     الموزعين الجدد والمطابَقين، لعدم وجود أعمدة مخصصة لها حالياً)

لو حبيت لاحقاً تفصيل أدق (مثلاً عمود منفصل لعدد الموزعين الجدد)، أقدر أضيفه
بسهولة بمجرد ما تضيف الأعمدة في Supabase.

## 7. نقاط أخرى تحتاج تأكيدك قبل أول تشغيل حقيقي ⚠️

- **استعلام Nexar GraphQL** في `nexar_client.py` (`supSearchMpn`) تم اختباره
  فعلياً وأثبت نجاحه على قطعتين حقيقيتين (`LM358`, `ATTINY13ASSUR`). تمت
  إضافة `clickUrl` (-> `product_url`)، `factoryLeadDays` (-> `lead_time_days`)،
  و`specs` (-> `Lifecycle_Status`، عبر البحث عن `attribute.shortname ==
  "lifecyclestatus"`) بناءً على التوثيق الرسمي لـ Nexar.
- **`original_source_name`**: لا يوجد له مصدر مباشر من Nexar، فيُثبَّت دائماً
  كنص `"Nexar API"` لتوثيق مصدر البيانات.
- **مطابقة سطور `stock`**: اعتمدتُ مفتاحاً منطقياً للـ upsert هو
  `(mpn, distributor_code, Supplier_SKU, Price_Break_Qty)`. إذا كان عندك
  تعريف مختلف لما يجعل صف السعر "نفسه" (مثلاً تجاهل `Price_Break_Qty`)،
  أخبرني لأعدّل المنطق.

## 8. سجل تعديلات (Migration Log) — الدفعة الحالية

### قاعدة البيانات (`migration_001.sql`)
- إضافة قيد `UNIQUE (mpn, distributer_code, "Supplier_SKU", "Price_Break_Qty")`
  على `stock` لمنع التكرار الهائل على مستوى قاعدة البيانات نفسها.
- إضافة عمود `"Manufacturer_Lifecycle_Status"` (نص) على `stock`. العمود
  القديم `Lifecycle_Status` **لم يُحذف ولم يُعدَّل** ويبقى كما هو لحين
  إعادة المسح الشامل والتأكد من امتلاء العمود الجديد.
- تفعيل RLS على `stock` و `distributer` + سياسة `authenticated`. لا يؤثر
  على الـ Agent لأنه يتصل بـ service_role key الذي يتجاوز RLS تلقائياً.

### `stock_sync.py`
- **تحقق MPN صارم**: لو `results[0]["part"]["mpn"]` (بعد `strip()`) لا
  يطابق الـ mpn المطلوب حرفياً، تتم مقاطعة معالجة القطعة بالكامل (لا يُنشأ
  سجل parts ولا stock) مع تحذير واضح في اللوج.
- **تنظيف SKU**: `Supplier_SKU` يُنظَّف بـ `.strip()`. لو فارغ/غائب، يُستبدل
  بقيمة صناعية `NOSKU-{mpn}-{distributor_code}` لضمان أن قيد الـ UNIQUE
  الجديد يعمل فعلياً (لأن `NULL != NULL` في SQL ولن يمنع التكرار وحده).
- **Full update عبر upsert**: استُبدل منطق `SELECT` ثم `INSERT`/`UPDATE`
  اليدوي بـ `upsert(..., on_conflict="mpn,distributer_code,Supplier_SKU,
  Price_Break_Qty")` مباشرة على القيد الجديد. هذا يحل مشكلة الـ race
  condition المحتملة بين تشغيلين متزامنين (مثلاً manual + scheduled)
  ويضمن تحديث كل الحقول المتاحة معاً بدل تحديث جزئي.
- **توجيه lifecycle الجديد**: قيمة `lifecycle_status` المستخرجة من Nexar
  تُكتب الآن في `Manufacturer_Lifecycle_Status` فقط، وليس في العمود القديم.
- إزالة متغير `distributor_name` غير المستخدم في `sync_part`.
- لا يزال Lead Time لا يُخمَّن أبداً عند RFQ: يُترك `NULL` ويُسجَّل تحذير.

### `distributor_resolver.py`
- عند إنشاء موزع جديد: تم **تجنّب** القراءة الديناميكية لأعمدة الجدول
  وملء المجهول منها بـ `"Unknown"` (قرار مرفوض عمداً — راجع التعليق في
  الكود لسبب الرفض: خطر type mismatch على أعمدة boolean/integer/date).
  بدلاً من ذلك: union آمن نوعياً بين `extra_fields` (من Nexar، بعد حذف
  القيم `None`) و `config.NEW_DISTRIBUTOR_DEFAULTS`. أي عمود جديد يُضاف
  للجدول مستقبلاً يُفعَّل بإضافته صراحة في `config.py`.

### `nexar_client.py`
- `search_part` أصبحت تُعيد المحاولة تلقائياً حتى 3 مرات، وبانتظار متزايد
  (1s, 2s, 4s)، **فقط** عند: أخطاء شبكة/timeout، أو استجابة HTTP بحالة
  `429`/`500`/`502`/`503`/`504`. أي خطأ آخر (401 مصادقة، 400 query غلط،
  خطأ GraphQL منطقي) يُرفَع فوراً بدون إعادة محاولة، لأنه سيفشل بنفس الشكل
  في كل مرة ولا فائدة من الانتظار.
- بعد استنفاد المحاولات الثلاث تُرفع `NexarRetryExhaustedError`.

### خطوة تشغيلية مطلوبة بعد هذه الدفعة
شغّل إعادة مسح شامل لتحديث `Manufacturer_Lifecycle_Status` لكل القطع:
```bash
python main.py --batch parts.txt --reset-checkpoint
```
ثم تحقق يدوياً أن العمود الجديد ممتلئ وأن `stock` خالٍ من التكرارات.

## 9. تحديث لاحق: اكتشاف "تعدد النتائج لنفس MPN" وإصلاحه

أثناء تشخيص سبب ظهور `lead_time_days = NULL` لقطعة معينة رغم أن موقع
الموزع (Arrow) كان يعرض "Lead time: 8 weeks"، تم فحص استجابة Nexar الخام
كاملة، وظهر اكتشافان مهمان:

1. **Arrow نفسه لم يظهر إطلاقاً** ضمن الموزعين اللي رجّعهم Nexar لهذا
   الاستعلام (من أصل ~28 موزع عبر كل النتائج). القيمة `8 weeks` المعروضة
   على موقع Arrow غير قابلة للسحب من Nexar لهذا الاستعلام تحديداً - على
   الأغلب لأن `factoryLeadDays` يعكس lead time المصنّع نفسه (Microchip)
   وظهر مصادفة بنفس القيمة (`56` يوم) مع موزعين آخرين (Onlinecomponents.com،
   Microchip direct) يسحبون من نفس خط الإنتاج.
2. **اكتشاف أهم**: Nexar رجّع نفس الـ `mpn` الحرفي (`EQCO30R5.D`) كـ`part`
   منفصل **مرتين** في نفس الاستجابة، بمجموعتيّ موزعين مختلفتين تماماً في كل
   مرة (بالإضافة لنتيجة ثالثة لـ variant مختلف `EQCO30R5.D-TRAY`). الكود
   القديم (`results[0]["part"]` فقط) كان يُسقط بصمت تام أي موزعين ظهروا في
   `part` مطابق آخر غير الأول - حتى لو كان `mpn` بتاعه مطابق 100% للمطلوب.
   هذا خلل اكتمال بيانات (data completeness)، مش مجرد مسألة lead time.

### الإصلاح المطبَّق في `stock_sync.py`
- `sync_part` الآن تجمع **كل** الأجزاء (`parts`) اللي `mpn` بتاعها مطابق
  حرفياً للمطلوب (مش بس أول واحد)، وتدمج قوائم موزعيها (`sellers`) معاً
  قبل المعالجة.
- بيانات القطعة نفسها (الوصف، `ensure_exists`) تُؤخذ من أول جزء مطابق فقط.
- `lifecycle_status` يُستخرج من أول جزء عنده قيمة فعلية (لأن بعض الأجزاء
  ممكن يكون `specs` فاضي عندها).
- لا حاجة لإزالة تكرار الموزعين يدوياً عند الدمج: `DistributorResolver`
  أصلاً يطابق بالاسم المطبَّع فيرجع نفس `D_code`، وقيد `stock_unique_offer`
  في قاعدة البيانات يحمي من أي تكرار على مستوى صفوف `stock` نفسها.

### أداة التشخيص (`debug_lead_time.py`)
تم تحديثها لعرض **كل** النتائج (parts) المرجَّعة، مش بس الأولى، مع تمييز
واضح لأيها يطابق الـ mpn حرفياً (`--exact-only` لعرض المطابقة فقط - بنفس
منطق `sync_part` الفعلي).

## 10. عمود `is_preferred_supplier` في `stock` (`migration_004.sql`)

عمود `boolean` جديد على `stock`، يُشتق تلقائياً من `dealt_with` الحقيقي
للموزع في `distributer` وقت المزامنة:
- `dealt_with = "Yes"` → `is_preferred_supplier = true`
- `dealt_with = "No"` → `is_preferred_supplier = false`
- `dealt_with` غير معروف (سجل قديم لسه ما اتعملهاش backfill) →
  `is_preferred_supplier = NULL` (بدون تخمين).

`DistributorResolver` بيحمّل `dealt_with` مع كل موزع (سواء موجود مسبقاً أو
جديد) ويمرّره في `DistributorMatch.dealt_with`، و`stock_sync.py` بيشتق
منه القيمة النهائية في `_upsert_offer`.

⚠️ اسم العمود الفعلي في القاعدة **lowercase** (`is_preferred_supplier`)
لأن الـ migration اتنفّذ من غير quotes فحوّله PostgreSQL تلقائياً.

## 11. تطبيع مقارنة الـ MPN (حتمي، ليس fuzzy)

اكتُشف أن بعض المصنّعين (مثال حقيقي: Microchip مع `ATTINY13ASSUR` مقابل
`ATTINY13A-SSUR`) يوثّقون نفس القطعة بأكثر من صيغة نصية (فروق شرطات/
مسافات فقط)، وفحص التطابق الصارم كان يرفضها كـ"قطعة مختلفة" بالخطأ.

الحل في `stock_sync.py`: دالة `_normalize_mpn()` تزيل أي رمز غير حرف/رقم
وتوحّد الحالة (uppercase) **للمقارنة فقط** - القيمة المخزَّنة في `stock`
تبقى كما طلبها المستخدم حرفياً، بدون أي تعديل. هذا لا يزال حتمياً 100%:
`EQCO30R5.D` لا يزال مرفوضاً مقابل `EQCO30R5.D-TRAY` (حروف إضافية حقيقية
= قطعة مختلفة فعلاً)، بينما `ATTINY13ASSUR` يُقبل مقابل `ATTINY13A-SSUR`
(فرق شكلي بحت).

## 12. إصلاح عمود `id` في جدول `parts` (`migration_005.sql`)

اكتُشف أن عمود `id` في `parts` من نوع `double precision`، `NOT NULL`،
بدون أي `default` تلقائي - أي `INSERT` لقطعة جديدة (عبر `parts_resolver.py`)
كان يفشل بخطأ `null value in column "id"`. تم الإصلاح عبر `sequence` مخصص
(`parts_id_seq`) مربوط كـ `DEFAULT` على العمود، مضبوط ليبدأ من أكبر `id`
موجود + 1 (بدون التصادم مع أي بيانات موجودة).

## 13. إثراء `NEW_DISTRIBUTOR_DEFAULTS` بقيم حقيقية إضافية

في `config.py`، تمت إضافة قيم افتراضية حقيقية (وليست تخميناً) لأي موزع
جديد يُنشأ تلقائياً:
- `vetting_status = "Not Vetted"` (بدل `"Unverified"`)
- `relationship_tier = "Not Engaged"`
- `years_relationship = 0.0`
- `quality_issues_l12m = 0`

بينما `on_time_delivery_rate` عمداً **غير موجود** في `NEW_DISTRIBUTOR_DEFAULTS`
ويبقى `NULL` - لأنه معدّل محسوب من `0` طلبات (`0/0` غير معرَّف رياضياً)،
مش حقيقة بسيطة زي "لسه محصلش أي تعامل".

## 14. `backfill_distributors.py` - تحديثات إضافية

### `--scrape-founded-year`
Flag جديد يحاول استخراج `company_founded_year` من `D_website`:
1. **أولوية أولى**: بيانات JSON-LD منظَّمة (`foundingDate`) - أدق مصدر،
   الموقع نفسه يعلنها صراحة لمحركات البحث.
2. **fallback**: بحث نصي بكلمات مفتاحية صريحة فقط (`Founded`, `Established`,
   `Since`, `Est.`) ملتصقة مباشرة بسنة رباعية، مع فحص منطقي (السنة بين
   1900 والسنة الحالية) لاستبعاد نتائج مستحيلة.
3. **بقرار صريح من صاحب المشروع**: النتيجة تُكتب **مباشرة** في
   `company_founded_year` (وليس كمرشّح في `research_notes` فقط، خلافاً
   لمعيار `--scrape-headquarters`)، + سطر توثيق للمصدر/الاقتباس في
   `research_notes` للمرجعية.
4. لو فشل الاستخراج تماماً (مفيش موقع، أو الموقع مالوش أي إشارة واضحة)،
   يُكتب النص الحرفي `"Not found"` في `company_founded_year` - **بقرار
   صريح من صاحب المشروع** ليتوافق مع شكل البيانات الموجود بالفعل في
   الجدول. ⚠️ ملحوظة: بما إن `"Not found"` مش `NULL`، أي تشغيلة قادمة لن
   تُعيد المحاولة لنفس الموزع تلقائياً - يحتاج تصفير يدوي لـ `NULL` أولاً
   لو حابين إعادة المحاولة بعد تحديث الموقع.

### إصلاح: روابط `D_website` بدون scheme
بعض قيم `D_website` مخزَّنة بدون `http://`/`https://` (مثال حقيقي:
`tomark.co.uk`)، وكانت تفشل بخطأ `Invalid URL: No scheme supplied` قبل
حتى محاولة فحص الصفحة. تم إضافة `_ensure_url_scheme()` تضيف `https://`
تلقائياً لو غائبة - تطبيع رابط بسيط وحتمي، وليس تخميناً في المحتوى.
(`migration_007.sql` بيصفّر الصفوف اللي اتأثرت بهذا الباج تحديداً قبل
الإصلاح، عشان تُعاد محاولتها).

## 15. سجل ملفات الـ Migration الكامل (بالترتيب)

| الملف | الغرض |
|---|---|
| `migration_001.sql` | قيد `UNIQUE` على `stock` + عمود `Manufacturer_Lifecycle_Status` + تفعيل RLS |
| `migration_002.sql` | دمج عمودي lifecycle القديم والجديد |
| `migration_003.sql` | تصفير `Manufacturer_Lifecycle_Status` (تصحيح بيانات قديمة خاطئة قبل الإصلاح) |
| `migration_004.sql` | إضافة عمود `is_preferred_supplier` لجدول `stock` |
| `migration_005.sql` | إصلاح عمود `id` في `parts` (sequence + default) |
| `migration_006.sql` | *(اختياري/لم يعد مطلوباً)* تصفير قيم "Not found" الحرفية |
| `migration_007.sql` | تصفير `company_founded_year` للصفوف المتأثرة ببق روابط بدون scheme |

⚠️ لازم تُنفَّذ **بالترتيب الرقمي** لإنها مبنية فوق بعض، وبعد كل migration
يمس بيانات `stock` يُفضَّل تشغيل إعادة مسح شامل:
```bash
python main.py --batch --reset-checkpoint
```

## 16. مصدر أرقام القطع (MPN): جدول `parts` بدل ملف محلي

تم إلغاء الاعتماد على ملف `parts.txt` المحلي بالكامل. `--batch` دلوقتي
يقرأ عمود `mpn` مباشرة من جدول `parts` في Supabase (مرتَّباً حسب `id`)،
عبر `get_all_mpns_from_parts_table()` في `main.py`. باقي منطق الدفعات
والـ checkpoint لم يتغيّر - لسه بيعالج جزء محدود فقط في كل تشغيل.

`scheduler.py` تم تحديثه بالمثل (لم يعد يشير لأي مسار ملف).