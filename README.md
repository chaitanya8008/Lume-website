# Lume — lume.co.in · Deployment Guide

Static site. No build step, no server, no database. Works on Vercel's free tier (or Netlify/Cloudflare Pages).

---

## 1. THE ONE THING YOU MUST DO — email delivery key (2 minutes)

Quote requests are emailed to you via Web3Forms (free: 250 submissions/month).

1. Go to https://web3forms.com
2. Enter **hello@lume.co.in** (or whichever inbox you want quotes in) → you get an **Access Key** instantly, no signup.
3. Open `js/lume.js`, line ~12:
   `var WEB3FORMS_KEY = 'YOUR_WEB3FORMS_ACCESS_KEY';`
   Replace with your key.

Until you do this, email sending is skipped — but the site still works, because every checkout also offers a one-tap **WhatsApp** button that opens the customer's WhatsApp with the full quote list pre-typed to **+91 62832 25517**. (WhatsApp always requires the customer's tap — no free service can silently message your WhatsApp; that needs the paid WhatsApp Business API.)

WhatsApp number lives on the next line of the same file if it ever changes.

**Second key — customer reference images (also 2 minutes):**
When someone uploads a sketch/photo on the Your Design page, the site hosts it on ImgBB (free) and puts the **link** inside the email and WhatsApp message — so customers upload once and never re-send.
1. https://api.imgbb.com → free account → get API key.
2. In `js/lume.js`, replace `YOUR_IMGBB_API_KEY` with it.
Without this key the form still works — it falls back to naming the file so the customer can share it in the WhatsApp chat. Note: hosted images are public to anyone with the link (fine for mirror sketches; keep it in mind).

## 2. Deploy on Vercel (free)

Option A — drag and drop:
1. https://vercel.com → sign up free → "Add New Project" → drag this whole folder in.
2. Project Settings → Domains → add `lume.co.in` and `www.lume.co.in`.
3. Vercel shows you two DNS records (an A record and a CNAME). Add them wherever you bought lume.co.in (GoDaddy/BigRock/etc). Done in ~10 min.

Option B — via GitHub: push this folder to a repo, import it in Vercel. Every push auto-deploys.

## 3. SEO — submit once, then it compounds

Already built in: per-page titles/descriptions, canonical URLs, Open Graph tags, JSON-LD structured data (LocalBusiness, FAQ, Services, Breadcrumbs), an image sitemap covering all 59 mirrors, robots.txt that explicitly allows GPTBot/ClaudeBot/PerplexityBot etc., and llms.txt describing the business for AI assistants.

After the domain is live:
1. **Google Search Console** (https://search.google.com/search-console) → add lume.co.in → verify via DNS → submit `https://lume.co.in/sitemap.xml`.
2. **Bing Webmaster Tools** — import from Search Console in one click (Bing feeds ChatGPT search).
3. Add the site link to your Google Business Profile, IndiaMART listing, and Instagram bio — early backlinks matter more than anything on-page for a new domain.

Honest expectation: page-1 rankings for "LED mirror manufacturer Panchkula" type queries are realistic within weeks; broad terms like "LED mirror India" take months and depend on backlinks, not code.

## 4. Placeholders to fill in later

- **IP rating & warranty**: search the codebase for `coming soon` — one badge row on `index.html` (features section) and one FAQ answer, plus a line in `llms.txt`.
- **Custom size presets / frame colours**: edit the `<select>` lists in the configurator (appears in `index.html` and `collections.html`) and in `custom.html`.

## 5. File map

- `index.html` — home: hero, two tracks, features, previews, FAQ, contact
- `collections.html` — all 59 designs, filterable, each with "Customise +"
- `custom.html` — bring-your-own-design form
- `trade.html` — B2B laser-frosting service
- `checkout.html` — quote list review + send (email + WhatsApp)
- `css/lume.css`, `js/lume.js` — shared styles and cart/checkout logic
- `robots.txt`, `sitemap.xml`, `llms.txt`, `vercel.json` — SEO & hosting config
- `images/` — all 59 catalogue photos, renamed for SEO, web-compressed
