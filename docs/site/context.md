# КОНТЕКСТ — elektroschit.com.ua
> Єдиний консолідований довідник. Мова сайту: українська (+ російська
> версія під `/ru/`). Спілкуємось: російською.
> Актуально станом на: 2026-09-26 (повна ревізія за реальним кодом репозиторію)

---

## ПРО КОМПАНІЮ

- Виробництво силових електрощитів та щитів керування на замовлення
- Силові щити (ГРЩ, ВРЩ): до 630А
- Щити керування: насосами, вентиляцією, двигунами, засувками (ШУЗ), АВР, КРМ
- Досвід з 1999 року (25+ років)
- Компоненти основні: ETI, Hager, Schneider Electric, Eaton
- Компоненти економ: E-Next, Asko, Chint
- Гарантія 12 місяців, терміни від 2 тижнів
- Географія: Київ, Київська область, вся Україна
- Контакти: +38 (098) 152-75-55 | elektroschit.info@gmail.com | Київ, вул. Печенізька, 35/43, оф. 168
- НЕ наша аудиторія: житловий сектор, квартири, котеджі

---

## ТЕХНІЧНИЙ СТЕК

| Що | Як |
|---|---|
| Фреймворк | Astro 4.15, `output: 'static'` |
| Хостинг | Cloudflare Pages |
| Репо | GitHub: Vah509/elektro |
| Деплой | Ручне завантаження ZIP через GitHub UI → `ai-updates/` → GitHub Actions → автодеплой |
| CSS | Кастомна система, префікс `em-`, файли в `public/css/` |
| JS | Ваніла JS, `public/js/em-site.js` (+ `public/js/em-work-lightbox.js` для карток портфоліо) |
| Шрифти | Geologica (заголовки 700) + Manrope (текст 400/500/600) |
| Sitemap | Власний `src/pages/sitemap.xml.ts` (БЕЗ пакету `@astrojs/sitemap` — падав з помилкою `reduce` через динамічний роут) |
| Layouts | `BaseLayout.astro` (усі сторінки) + `ProductLayout.astro` (8 продуктових сторінок) — див. `docs/site/layouts.md` |

---

## СТРУКТУРА СТОРІНОК САЙТУ (актуальна, перевірено кодом репозиторію)

```
src/pages/
  index.astro                          → /
  kontakty.astro                       → /kontakty
  pro-nas.astro                        → /pro-nas
  admin_509.astro                      → /admin_509  (виключено з sitemap і robots.txt)
  sitemap.xml.ts                       → /sitemap.xml (службова, не сторінка)
  posluhy-ta-produktsiia/
    index.astro                        → /posluhy-ta-produktsiia/
    hrshch.astro                       → /posluhy-ta-produktsiia/hrshch    (ЕТАЛОН шаблону)
    dymovydalennia.astro
    dvyhuny.astro
    shuz.astro
    krm.astro
    zenitni-lihtari.astro
    ahro.astro
    plk.astro
    elektromontazh.astro               (НЕ використовує ProductLayout — інша структура)
  vykonani-roboty/
    index.astro                        → /vykonani-roboty/  (каталог з фільтрами)
    [slug].astro                       → /vykonani-roboty/[slug]/  (детальна картка)
  ru/
    index.astro                        → /ru/
    kontakty.astro                     → /ru/kontakty
    pro-nas.astro                      → /ru/pro-nas
    uslugi-i-produktsiya/
      index.astro                      → /ru/uslugi-i-produktsiya/
      grshch-i-vrshch.astro
      shchity-dymoudaleniya.astro
      shchity-upravleniya-dvigatelyami.astro
      shuz.astro
      krm.astro
      zenitnyye-fonari.astro
      elektroschity-dlya-agro.astro
      programmirovanie-plk.astro
      elektromontazh.astro
    vykonani-roboty/
      index.astro                      → /ru/vykonani-roboty/  (заглушка, див. розділ RU нижче)
```

**BaseLayout.astro тепер активно використовується всіма сторінками** (раніше
в проекті існував незадіяний файл з такою назвою — це виправлено введенням
`BaseLayout.astro` + `ProductLayout.astro`, див. `docs/site/layouts.md`).

---

## КОМПОНЕНТИ (src/components/) — АКТУАЛЬНИЙ СПИСОК

### Загальні (є на кожній сторінці)

| Файл | Пропси | Призначення |
|---|---|---|
| `Header.astro` | `activePage` ('produktsiia' / 'posluhy' / 'vykonani-roboty' / 'pro-nas' / 'kontakty') | Шапка з навігацією. Імпортує `PHONE`, `PHONE_DISPLAY` з config |
| `Footer.astro` | — | Футер. Імпортує `PHONE`, `PHONE_DISPLAY`, `EMAIL` з config |
| `Breadcrumbs.astro` | `current`, `parentLabel?`, `parentHref?`, `simple?` | Хлібні крихти (schema.org). `simple=true` → 2 рівні, без — 3 рівні |
| `FaqAccordion.astro` | `items: {q,a}[]`, `sectionTitle?` | FAQ акордеон, FAQPage JSON-LD |
| `AlsoMake.astro` | `currentSlug` | Блок «Також виготовляємо» — показує всі продукти крім поточного |
| `ContactBlock.astro` | `title?` | Контакти + месенджери. Імпортує ВСЕ з config |
| `Lightbox.astro` | — | Лайтбокс для галереї продуктових сторінок (листання ←/→, свайп, нескінченний цикл) |

### Компоненти для карток «Виконані роботи» (перевірено кодом, з реальними пропсами)

| Файл | Пропси | Призначення |
|---|---|---|
| `WorkPhotos.astro` | `photos: {src, caption}[]`, `title` | Головне фото (клік → лайтбокс `em-work-lightbox.js` через `window.emOpenWorkLightbox`) + мініатюри. Десктоп (901px+): фото зліва `object-fit:contain`/`max-height:70vh`, мініатюри сіткою 2 колонки справа зі своїм скролом. Мобільна: фото зверху 4:3 cover, мініатюри стрічкою знизу |
| `WorkDescription.astro` | `title`, `types: string[]`, `tags: string[]`, `properties: string[]`, + slot для тексту | Теги (types+tags) + H1 + властивості (properties, окремим рядом, не фільтруються) + опис через `<Content />`. **Увага:** пропс `properties` є в реальному компоненті, хоч і не згадувався в ранніх версіях цієї документації |
| `WorkSpecs.astro` | `specs: {label, value}[]` | Таблиця технічних характеристик, обгорнута у власну `em-section-alt` секцію (не потребує зовнішньої обгортки) |
| `WorkBrands.astro` | `brands: string[]` | Прості пігулки брендів, без поділу на групи основні/економ. Обгорнутий у власну `em-section` |
| `WorkSimilar.astro` | `relatedTop: Work[]`, `moreWorks: Work[]`, `currentTypeLabel?` | «Схожі роботи» — **ЧИСТО ВІДОБРАЖЕННЯ**, весь підрахунок винесено в `src/utils/similarWorksGraph.ts`. Ряд 1 (relatedTop) — картки з фото/тегами/брендами; Ряд 2 (moreWorks) — компактні картки; якщо обидва ряди порожні — fallback-кнопка «Всі виконані роботи →» |

**Важливе виправлення:** `WorkSimilar` НЕ приймає `currentSlug`/`types`/`tags`
напряму (як помилково вказувалося раніше) — весь скоринг рахується заздалегідь
у `getStaticPaths()` сторінки `[slug].astro` через `getGlobalSimilarWorksMap()`,
і в компонент передаються вже готові списки `relatedTop`/`moreWorks`.

### Алгоритм «Схожих робіт» (src/utils/similarWorksGraph.ts)

Рахується **один раз на весь білд** (усередині `getStaticPaths()`), а не
окремо для кожної картки — це дає глобальну картину і виключає картки-сироти.

**Ряд 1 (`relatedTop`, за замовчуванням до 4 карток):**
- Скоринг між парою карток: `+2` за кожен спільний `type`, `+1` за кожен
  спільний `tag` (ваги — `typeWeight`/`tagWeight`, налаштовуються)
- Сортування: спочатку за очками (спадання), потім за датою (новіші вище)
- Fallback: якщо після types+tags назбиралось менше 4 — добираються картки з
  тим самим основним `type` (без урахування tags), від найновіших

**Ряд 2 (`moreWorks`, за замовчуванням до 4 карток) — захист від сиріт:**
- Обробка карток іде від найстарішої до найновішої (`byDateAsc`)
- Для кожної картки рахується `inboundCount` — скільки вхідних посилань з
  Ряду 1 вона вже отримала від інших карток
- Кандидати в Ряд 2 сортуються за зростанням `inboundCount` (менше вхідних
  посилань — вищий пріоритет потрапити хоч кудись), при рівності — новіші вище
- Лічильник `inboundCount` оновлюється одразу під час проходу, тож наступні
  картки в тому ж проході вже бачать, кого щойно «врятували»

Виклик у `[slug].astro`:
```typescript
const similarMap = await getGlobalSimilarWorksMap({
  row1Count: 4, row2Count: 4, typeWeight: 2, tagWeight: 1,
  fallbackToSameType: true,
});
```

---

## ФАЙЛ КОНФІГУРАЦІЇ — src/config.ts

**Єдине місце для всіх контактів та домену.** При зміні контактів — правити тільки цей файл.

```typescript
export const SITE_PREVIEW    = 'https://elektro-4a1.pages.dev';
export const SITE_CANONICAL  = 'https://elektroschit.com.ua';
export const GITHUB_CONTENT_BASE = 'https://github.com/Vah509/elektro/edit/main/src/content/vykonani-roboty';

export const PHONE         = '+380981527555';
export const PHONE_DISPLAY = '+38 (098) 152-75-55';
export const EMAIL         = 'elektroschit.info@gmail.com';
export const ADDRESS       = 'Київ, вул. Печенізька, 35/43, оф. 168';
export const MAPS_URL      = 'https://www.google.com/maps/search/?api=1&query=Київ,+вул.+Печенізька,+35/43';
export const VIBER         = 'viber://chat?number=%2B380981527555';
export const TELEGRAM      = 'https://t.me/+380981527555';
export const WHATSAPP      = 'https://wa.me/380981527555';
export const WORK_HOURS    = 'робочі дні з 9:00 до 17:00';
export const GTM_ID        = 'GTM-PZSRTZ2T';
export const CLARITY_ID    = '';   // порожньо — Clarity ще не підключено
```

### Правила імпорту (перевірено, працює у всіх файлах):

```astro
// Компоненти (src/components/) → ../config
import { PHONE, PHONE_DISPLAY, EMAIL } from '../config';

// Сторінки верхнього рівня (src/pages/) → ../config
import { SITE_CANONICAL, PHONE, PHONE_DISPLAY } from '../config';

// Сторінки у підпапках (src/pages/posluhy-ta-produktsiia/, vykonani-roboty/, ru/) → ../../config
import { SITE_CANONICAL, PHONE, PHONE_DISPLAY } from '../../config';

// Сторінки у ru/uslugi-i-produktsiya/ (третій рівень вкладеності) → ../../../config
import { SITE_CANONICAL } from '../../../config';
```

**Правило без винятків:** жодна сторінка чи компонент не повинні містити
телефон/email/адресу/домен прямим текстом у робочих посиланнях (`tel:`,
`mailto:`, `canonical`, месенджери). Виняток — природний текст у
meta-description (описова фраза, не посилання) можна лишати як є.

---

## ТАКСОНОМІЯ ПРОДУКТІВ — src/data/tags-registry.ts (ПЕРЕВІРЕНО КОДОМ)

**Єдине джерело істини** для типів, тегів та властивостей. При додаванні
нового значення — редагувати ТІЛЬКИ цей файл.

### Розділи (types) — 10 значень
Відповідають розділам продукції на сайті:
`hrshch` (ГРЩ / ВРЩ) · `dymovydalennia` (Димовидалення) · `dvyhuny`
(Керування двигунами) · `shuz` (ШУЗ) · `krm` (КРМ) · `zenitni-lihtari`
(Зенітні ліхтарі) · `ahro` (Агро) · `plk` (ПЛК) · `elektromontazh`
(Електромонтаж) · `shafi-keruvannia` (Шафи керування)

### Теги (tags) — 3 значення, беруть участь у фільтрації каталогу
`avr` (Шафа з АВР) · `sylova-shafa` (Силова шафа) ·
`upravlinnia-osvitlenniiam` (Управління освітленням)

### Властивості (properties) — 8 значень, інформаційні, НЕ фільтруються
`pryamyi-pusk` (Прямий пуск) · `zirka-trykutnyk` (Зірка-трикутник) ·
`chastotnyy-peretvoryuvach` (Частотний перетворювач) · `kontrol-faz`
(Контроль фаз) · `plavnyi-pusk` (Плавний пуск) · `avr-na-kontaktorakh`
(АВР на контакторах) · `avr-na-peremykachakh` (АВР на перемикачах) ·
`try-vvody` (Три вводи)

> ⚠️ Ці списки зростають з часом — перед використанням значення в новому
> контенті звіряй з актуальним `tags-registry.ts` у репозиторії, ця таблиця
> лише знімок стану на дату ревізії.

---

## СХЕМА КОЛЕКЦІЇ «ВИКОНАНІ РОБОТИ» (src/content/config.ts)

```typescript
const vykonaniRoboty = defineCollection({
  type: 'content',
  schema: z.object({
    id: z.number(),                                    // YYMMDDHHMMSS або YYMMDDN
    title: z.string(),
    date: z.date(),
    types: z.array(z.enum(validTypes)).min(1),
    tags: z.array(z.enum(validTags)).default([]),
    properties: z.array(z.enum(validProperties)).default([]),
    description: z.string(),
    specs: z.array(z.object({ label: z.string(), value: z.string() })).default([]),
    brands: z.array(z.string()).default([]),
    photos: z.array(z.object({ src: z.string(), caption: z.string() })).min(1),
    seoTitle: z.string().optional(),
  }),
});
```

`types`, `tags`, `properties` валідуються по `src/data/tags-registry.ts`.

**URL картки:** `work.slug`, формується як
`https://elektroschit.com.ua/vykonani-roboty/${work.slug}/` (з завершальним слешем).

---

## SLUGS ПРОДУКТІВ (для AlsoMake.currentSlug та Header activePage)

`hrshch` | `dymovydalennia` | `dvyhuny` | `shuz` | `krm` | `zenitni-lihtari` | `ahro` | `plk` | `elektromontazh`

---

## СТРУКТУРА СТОРІНКИ ПРОДУКТУ

Див. `docs/site/layouts.md` — з переходом на `ProductLayout.astro` уся
структура блоків (Hero → Галерея → Застосування → Характеристики →
Компоненти → Як ми працюємо → Переваги → FAQ → ContactBlock → AlsoMake)
та чергування фонів (зелений → білий → зелений → ...) реалізовані
всередині лейауту, а не в кожній сторінці окремо.

---

## СТРУКТУРА КАРТКИ ПОРТФОЛІО (vykonani-roboty/[slug].astro) — ЗВІРЕНО З КОДОМ

```astro
export async function getStaticPaths() {
  const works = await getCollection('vykonani-roboty');
  const similarMap = await getGlobalSimilarWorksMap({
    row1Count: 4, row2Count: 4, typeWeight: 2, tagWeight: 1,
    fallbackToSameType: true,
  });
  return works.map(work => ({
    params: { slug: work.slug },
    props:  { work, similar: similarMap.get(work.slug) ?? { relatedTop: [], moreWorks: [] } },
  }));
}
```

```
<BaseLayout page={{ section: 'vykonani-roboty', ogType: 'article', lang: 'uk', ...crumbs }}>
  <WorkPhotos photos={data.photos} title={data.title} />
  <WorkDescription title={data.title} types={data.types} tags={data.tags} properties={data.properties}>
    <Content />
  </WorkDescription>
  <WorkSpecs specs={data.specs} />
  <WorkBrands brands={data.brands} />
  <WorkSimilar relatedTop={similar.relatedTop} moreWorks={similar.moreWorks} currentTypeLabel={currentTypeLabel} />
  <ContactBlock title="Хочете такий щит? Зв'яжіться з нами" />
  <AlsoMake currentSlug="" />
  <Lightbox />
</BaseLayout>
```

`seoTitle` з frontmatter (якщо є) використовується як `<title>`, інакше —
`${data.title} | elektroschit.com.ua`.

---

## РОСІЙСЬКА ВЕРСІЯ САЙТУ (/ru/) — ПОВНИЙ РОЗДІЛ (звірено з кодом, раніше не документувалося)

### Загальний принцип

Продуктові сторінки та довідкові сторінки (головна, контакти, про нас)
мають повноцінний дубль під `/ru/`, з власним російським slug. Розділ
«Виконані роботи» (`vykonani-roboty`) — **українською мовою only**,
`/ru/vykonani-roboty/` це навмисна заглушка, а не список карток.

### Мапа slug'ів UA → RU

| UA slug (`posluhy-ta-produktsiia/`) | RU slug (`ru/uslugi-i-produktsiya/`) |
|---|---|
| `hrshch` | `grshch-i-vrshch` |
| `dymovydalennia` | `shchity-dymoudaleniya` |
| `dvyhuny` | `shchity-upravleniya-dvigatelyami` |
| `shuz` | `shuz` |
| `krm` | `krm` |
| `zenitni-lihtari` | `zenitnyye-fonari` |
| `ahro` | `elektroschity-dlya-agro` |
| `plk` | `programmirovanie-plk` |
| `elektromontazh` | `elektromontazh` |

RU-слуги використовують ту саму `ProductLayout.astro`, що і UA-версія —
різняться лише мовою контенту, `page.lang`, `page.altUrl` і canonical.

### Додаткові поля `page` для RU-сторінок (не описані в layouts.md)

RU-сторінки (і фактично всі сторінки після впровадження hreflang) передають
у `page` два додаткових поля поверх базових з `docs/site/layouts.md`:

| Поле | Тип | Опис |
|---|---|---|
| `lang` | `'uk' \| 'ru'` | Мова конкретної сторінки — використовується для `<html lang>` та hreflang-розмітки в BaseLayout |
| `altUrl` | string | Repo-relative шлях до альтернативної мовної версії цієї ж сторінки (напр. RU-сторінка ГРЩ вказує `altUrl: '/posluhy-ta-produktsiia/hrshch/'`) |

Приклад (RU-сторінка продукту):
```typescript
const page = {
  lang:        'ru' as const,
  altUrl:      '/posluhy-ta-produktsiia/hrshch/',
  section:     'produktsiia',
  title:       'Изготовление ГРЩ и ВРЩ до 630А | elektroschit.com.ua',
  canonical:   `${SITE_CANONICAL}/ru/uslugi-i-produktsiya/grshch-i-vrshch/`,
  crumbs: [ /* ... */ ],
};
```

### `/ru/vykonani-roboty/` — заглушка (не каталог)

Сторінка `src/pages/ru/vykonani-roboty/index.astro` не рендерить жодних
карток. Показує повідомлення «Раздел недоступен на русском языке» з
іконкою та кнопкою-посиланням на українську версію (`/vykonani-roboty/`).
Немає жодних RU-карток портфоліо, і не планується.

**У sitemap.xml.ts шлях `ru/vykonani-roboty` явно виключений** через
константу `EXCLUDED_PATHS` — тобто сама заглушка в sitemap не потрапляє,
хоча технічно існує і доступна за URL.

---

## ФОТОГРАФІЇ — ПРАВИЛА РОБОТИ

**⚠️ Виправлення давньої помилки в документації:** оптимізація фото в
пайплайні деплою виконується **Node.js-скриптом на бібліотеці `sharp`**
(`scripts/lib/optimize-photos.js`), а НЕ Python/Pillow. Раніше в цій
документації помилково вказувався Pillow — можливо, це стосувалося якогось
локального/ручного процесу підготовки фото перед завантаженням у ZIP, а не
автоматичного пайплайну на GitHub Actions.

### Автоматична оптимізація в process-update.js (реальна логіка коду)
- Обробляються тільки `.jpg`/`.jpeg` файли зі списку архіву
- Якщо ширина фото ≤ 1200px — вважається вже оптимізованим, лишається без змін
- Якщо ширина > 1200px — стискається до ширини 1200px (`withoutEnlargement: true`),
  JPEG якість **85** (не 82, як вказувалося раніше)
- Звіт по кожному файлу (розмір до/після, статус ОК/ОПТ/помилка) йде в перше
  Telegram-повідомлення

### Ручні конвенції найменування (незалежно від автоматичного пайплайна)
- Колаж hero: суфікс `-c1`…`-c4`, перші 2 — `loading="eager"`, решта — `lazy`
- Галерея: суфікс `-01` (велике) … `-08` (малі)
- SEO назва: `[slug]-[дескриптор]-kyiv-2026-06-[номер або c1-c4].jpg`
- Лайтбокс несумісний з `src/assets/` (Astro хешує імена файлів) —
  залишатись на `public/images/` до повної скриптованої міграції

---

## РОБОТА З ВИХІДНИМИ МАТЕРІАЛАМИ (MD + HTML)

1. Читати обидва файли — MD і HTML з WordPress
2. HTML має пріоритет над MD при розбіжностях
3. Порівнювати і обговорювати розбіжності перед генерацією
4. Типові розбіжності: кількість карток, питань FAQ, унікальні блоки

---

## ПРАВИЛА ДОСТАВКИ ЗМІН (ZIP)

- Формат: ZIP-архів, без кореневої папки — файли лежать одразу в корені
- Шляхи: repo-relative (напр. `src/pages/posluhy-ta-produktsiia/dvyhuny.astro`)
- Завантаження: через GitHub UI в `ai-updates/` → GitHub Actions
  (`scripts/process-update.js`) → автодеплой Cloudflare Pages
- **Workflow:** обговорення структури → явне підтвердження → генерація
  ZIP. Ніколи не будувати ZIP до підтвердження
- `delete.txt`: строго це ім'я, строго в корені ZIP, один шлях на рядок від
  кореня проекту, без лапок/пробілів/слешу на початку/коментарів
- Детальний покроковий опис самого скрипту обробки — `docs/site/deploy-and-sitemap.md`

---

## БРЕЙКПОІНТИ

| Назва | Значення |
|---|---|
| Десктоп | 900px+ (де саме зазначено 901px+ у CSS-медіа-запитах — це той самий поріг) |
| Планшет | 600px – 899px |
| Мобільний | < 600px |

---

## SEO ШАБЛОН

- **Title:** `Виготовлення [назва] на замовлення — [ампераж або особливість] | elektroschit.com.ua`
- **Description:** 150–160 символів
- **H1:** обов'язково починається з «Виготовлення» (або «Програмування» для ПЛК)
- **canonical:** через `SITE_CANONICAL` з config.ts, завжди
- Для RU-сторінок: title/description російською, canonical на `/ru/...`,
  `altUrl` вказує на UA-відповідник для hreflang

---

## SITEMAP ТА ROBOTS.TXT (перевірено кодом sitemap.xml.ts)

- Власний файл `src/pages/sitemap.xml.ts` — без пакету `@astrojs/sitemap`
- Автоматично сканує через `import.meta.glob`:
  `src/pages/*.astro`, `src/pages/posluhy-ta-produktsiia/*.astro`,
  `src/pages/vykonani-roboty/index.astro`, `src/pages/ru/**/*.astro`
- Виключає за іменем файлу: `admin_509`; за повним шляхом: `ru/vykonani-roboty`
- Виключає динамічні роути (файли, що починаються з `[`)
- Картки портфоліо підтягуються автоматично через `getCollection('vykonani-roboty')`
- Дедублікація за `urlPath` — лишається перше входження
- `lastmod` для кожного URL береться з `src/data/lastmod-map.json` (не з
  git log напряму — див. `docs/site/deploy-and-sitemap.md`), з фолбеком на
  дату білду, якщо запису в мапі немає
- `public/robots.txt` містить `Sitemap: https://elektroschit.com.ua/sitemap.xml`
- URL: `https://elektroschit.com.ua/sitemap.xml`

---

*Проект: elektroschit.com.ua | context v4.0 (повна ревізія за кодом) | 2026-09-26*
