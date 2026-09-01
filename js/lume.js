/* ============================================================
   LUME — shared site logic
   Cart · Configurator · Checkout (email + WhatsApp) · UI
   ============================================================ */

(function () {
  'use strict';

  /* ------------------------------------------------------------
     CONFIG — fill these two values at deploy time
     ------------------------------------------------------------ */
  var WEB3FORMS_KEY = 'b2431694-f251-4a4e-a54e-59880995c42d'; // free key from https://web3forms.com — submissions arrive at your email
  var WHATSAPP_NUMBER = '916283225517';            // country code + number, no plus sign
  var IMGBB_KEY = '850b2baf56a789f76d14b75e1036a654';            // free key from https://api.imgbb.com — hosts customer reference images so a link travels in the quote

  /* ------------------------------------------------------------
     Cart storage — localStorage with safe in-memory fallback
     ------------------------------------------------------------ */
  var memCart = [];
  function loadCart() {
    try {
      var raw = window.localStorage.getItem('lume_cart');
      return raw ? JSON.parse(raw) : [];
    } catch (e) { return memCart; }
  }
  function saveCart(cart) {
    memCart = cart;
    try { window.localStorage.setItem('lume_cart', JSON.stringify(cart)); } catch (e) { /* in-memory only */ }
    renderCartCount();
    renderCartDrawer();
  }

  /* ------------------------------------------------------------
     Toast
     ------------------------------------------------------------ */
  var toastEl, toastTimer;
  function toast(msg) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.className = 'toast';
      toastEl.setAttribute('role', 'status');
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, 2600);
  }

  /* ------------------------------------------------------------
     Cart count badge
     ------------------------------------------------------------ */
  function renderCartCount() {
    var n = loadCart().length;
    document.querySelectorAll('.cart-count').forEach(function (el) {
      el.textContent = n;
      el.classList.toggle('show', n > 0);
    });
  }

  /* ------------------------------------------------------------
     Spec formatting
     ------------------------------------------------------------ */
  function specLines(item) {
    var lines = [];
    if (item.shape) lines.push('Shape: ' + item.shape);
    if (item.size) lines.push('Size: ' + item.size);
    if (item.light) lines.push('Light: ' + item.light);
    if (item.frame) lines.push('Frame: ' + item.frame);
    if (item.features && item.features.length) lines.push('Features: ' + item.features.join(', '));
    if (item.qty) lines.push('Qty: ' + item.qty);
    if (item.notes) lines.push('Notes: ' + item.notes);
    return lines;
  }

  function cartAsText() {
    var cart = loadCart();
    var out = [];
    cart.forEach(function (item, i) {
      out.push((i + 1) + '. ' + item.name);
      specLines(item).forEach(function (l) { out.push('   - ' + l); });
    });
    return out.join('\n');
  }

  /* ------------------------------------------------------------
     Cart drawer
     ------------------------------------------------------------ */
  function renderCartDrawer() {
    var list = document.getElementById('cartItems');
    if (!list) return;
    var cart = loadCart();
    if (cart.length === 0) {
      list.innerHTML = '<div class="cart-empty">Your quote list is empty.<br>Add any mirror from the collections — or describe your own design.</div>';
      return;
    }
    list.innerHTML = '';
    cart.forEach(function (item, idx) {
      var div = document.createElement('div');
      div.className = 'cart-item';
      var img = item.img ? '<img src="' + item.img + '" alt="' + item.name + '">' : '';
      div.innerHTML =
        img +
        '<div class="ci-body">' +
        '<div class="ci-name">' + item.name + '</div>' +
        '<div class="ci-spec">' + specLines(item).join('<br>') + '</div>' +
        '<button class="ci-remove" type="button" data-idx="' + idx + '">Remove</button>' +
        '</div>';
      list.appendChild(div);
    });
    list.querySelectorAll('.ci-remove').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var cart = loadCart();
        cart.splice(parseInt(btn.dataset.idx, 10), 1);
        saveCart(cart);
      });
    });
  }

  function openCart() {
    var d = document.getElementById('cartDrawer');
    if (d) { d.classList.add('open'); renderCartDrawer(); }
  }
  function closeCart() {
    var d = document.getElementById('cartDrawer');
    if (d) d.classList.remove('open');
  }

  /* ------------------------------------------------------------
     Configurator modal — opened from any gallery card
     ------------------------------------------------------------ */
  var currentProduct = null;

  function openConfigurator(name, img, shape) {
    currentProduct = { name: name, img: img, shape: shape };
    var m = document.getElementById('configModal');
    if (!m) return;
    document.getElementById('cfgName').textContent = name;
    document.getElementById('cfgImg').src = img;
    document.getElementById('cfgImg').alt = name + ' LED mirror';
    var shapeSel = document.getElementById('cfgShape');
    if (shapeSel && shape) shapeSel.value = shape;
    // reset form
    var form = document.getElementById('cfgForm');
    if (form) form.reset();
    if (shapeSel && shape) shapeSel.value = shape;
    m.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function closeConfigurator() {
    var m = document.getElementById('configModal');
    if (m) m.classList.remove('open');
    document.body.style.overflow = '';
  }

  function configuratorSubmit(e) {
    e.preventDefault();
    var f = e.target;
    var sizePreset = f.querySelector('[name="sizePreset"]').value;
    var sizeCustom = f.querySelector('[name="sizeCustom"]').value.trim();
    var size = sizeCustom ? sizeCustom + ' (custom)' : sizePreset;
    var feats = [];
    f.querySelectorAll('[name="feature"]:checked').forEach(function (c) { feats.push(c.value); });
    var item = {
      name: currentProduct ? currentProduct.name : 'Custom mirror',
      img: currentProduct ? currentProduct.img : '',
      shape: f.querySelector('[name="shape"]').value,
      size: size || 'To be discussed',
      light: f.querySelector('[name="light"]:checked') ? f.querySelector('[name="light"]:checked').value : 'Three-colour (switchable)',
      frame: f.querySelector('[name="frame"]').value,
      features: feats,
      qty: f.querySelector('[name="qty"]').value || '1',
      notes: f.querySelector('[name="notes"]').value.trim()
    };
    var cart = loadCart();
    cart.push(item);
    saveCart(cart);
    closeConfigurator();
    toast('Added to your quote list');
  }

  /* ------------------------------------------------------------
     Checkout — sends email via Web3Forms, then offers WhatsApp
     ------------------------------------------------------------ */
  function buildMessage(name, phone, email, city) {
    return (
      'NEW QUOTE REQUEST — lume.co.in\n' +
      '--------------------------------\n' +
      'Name: ' + name + '\n' +
      'Phone: ' + phone + '\n' +
      (email ? 'Email: ' + email + '\n' : '') +
      (city ? 'City: ' + city + '\n' : '') +
      '--------------------------------\n' +
      'ITEMS:\n' + cartAsText()
    );
  }

  function checkoutSubmit(e) {
    e.preventDefault();
    var cart = loadCart();
    if (cart.length === 0) { toast('Your quote list is empty'); return; }

    var f = e.target;
    var bot = f.querySelector('[name="botcheck"]');
    if (bot && bot.checked) { return; } // honeypot — humans never see this box
    var name = f.querySelector('[name="custName"]').value.trim();
    var phone = f.querySelector('[name="custPhone"]').value.trim();
    var email = f.querySelector('[name="custEmail"]').value.trim();
    var city = f.querySelector('[name="custCity"]').value.trim();
    var msg = buildMessage(name, phone, email, city);

    var btn = f.querySelector('button[type="submit"]');
    var original = btn.textContent;
    btn.textContent = 'Sending…';
    btn.disabled = true;

    var emailPromise = Promise.resolve({ ok: false });
    if (WEB3FORMS_KEY && WEB3FORMS_KEY !== 'YOUR_WEB3FORMS_ACCESS_KEY') {
      emailPromise = fetch('https://api.web3forms.com/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({
          access_key: WEB3FORMS_KEY,
          subject: 'Lume quote request — ' + name,
          from_name: 'lume.co.in',
          name: name,
          phone: phone,
          email: email || 'not-provided@lume.co.in',
          message: msg
        })
      }).then(function (r) { return r.json(); }).catch(function () { return { ok: false }; });
    }

    emailPromise.then(function (res) {
      btn.textContent = original;
      btn.disabled = false;
      var emailSent = res && (res.success === true || res.ok === true);
      // WhatsApp handoff — always offered, works with zero backend
      var waUrl = 'https://wa.me/' + WHATSAPP_NUMBER + '?text=' + encodeURIComponent(msg);
      var done = document.getElementById('checkoutDone');
      var formWrap = document.getElementById('checkoutFormWrap');
      if (done && formWrap) {
        formWrap.style.display = 'none';
        done.style.display = 'block';
        document.getElementById('waLink').href = waUrl;
        document.getElementById('emailStatus').textContent = emailSent
          ? 'Your request has been emailed to us. To reach us faster, also send it on WhatsApp:'
          : 'To make sure it reaches us instantly, send your request on WhatsApp:';
      } else {
        window.open(waUrl, '_blank');
      }
      if (emailSent) { saveCart([]); }
      toast(emailSent ? 'Request sent — we will get back with a quote' : 'One more tap — send it on WhatsApp');
    });
  }

  /* ------------------------------------------------------------
     Custom design form (custom.html) — adds a custom item to cart
     ------------------------------------------------------------ */
  function uploadReferenceImage(file) {
    // Hosts the customer's reference image on ImgBB so a link can travel
    // inside the email and WhatsApp message. Resolves to a URL string, or
    // null if no key is configured / the upload fails (caller falls back).
    if (!file) return Promise.resolve(null);
    if (!IMGBB_KEY || IMGBB_KEY === 'YOUR_IMGBB_API_KEY') return Promise.resolve(null);
    if (file.size > 20 * 1024 * 1024) return Promise.resolve(null); // keep well under ImgBB's cap
    var fd = new FormData();
    fd.append('image', file);
    return fetch('https://api.imgbb.com/1/upload?key=' + encodeURIComponent(IMGBB_KEY), {
      method: 'POST',
      body: fd
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        return (res && res.success && res.data && res.data.url) ? res.data.url : null;
      })
      .catch(function () { return null; });
  }

  function customSubmit(e) {
    e.preventDefault();
    var f = e.target;
    var feats = [];
    f.querySelectorAll('[name="feature"]:checked').forEach(function (c) { feats.push(c.value); });
    var fileInput = f.querySelector('[name="refImage"]');
    var file = (fileInput && fileInput.files.length) ? fileInput.files[0] : null;

    var btn = f.querySelector('button[type="submit"]');
    var original = btn.textContent;
    if (file) { btn.textContent = 'Uploading your reference…'; btn.disabled = true; }

    uploadReferenceImage(file).then(function (url) {
      btn.textContent = original;
      btn.disabled = false;
      var fileNote = '';
      if (url) {
        fileNote = 'Reference image: ' + url;
      } else if (file) {
        // Upload unavailable or failed — fall back to naming the file so it
        // can be shared when the conversation moves to WhatsApp or email.
        fileNote = 'Reference image: ' + file.name + ' (please attach it on WhatsApp or email)';
      }
      var userNotes = f.querySelector('[name="notes"]').value.trim();
      var combinedNotes = [userNotes, fileNote].filter(Boolean).join(' | ');
      var item = {
        name: 'Custom design — ' + (f.querySelector('[name="designName"]').value.trim() || 'my own idea'),
        img: url || 'images/irregular-led-mirror-14.jpg',
        shape: f.querySelector('[name="shape"]').value,
        size: f.querySelector('[name="size"]').value.trim() || 'To be discussed',
        light: f.querySelector('[name="light"]:checked') ? f.querySelector('[name="light"]:checked').value : 'Three-colour (switchable)',
        frame: f.querySelector('[name="frame"]').value,
        features: feats,
        qty: f.querySelector('[name="qty"]').value || '1',
        notes: combinedNotes
      };
      var cart = loadCart();
      cart.push(item);
      saveCart(cart);
      f.reset();
      toast(url ? 'Design added — reference image attached' : 'Custom design added to your quote list');
      openCart();
    });
  }

  /* ------------------------------------------------------------
     Gallery filter (collections.html)
     ------------------------------------------------------------ */
  function initFilters() {
    var bar = document.querySelector('.filter-bar');
    if (!bar) return;
    bar.addEventListener('click', function (e) {
      var btn = e.target.closest('button');
      if (!btn) return;
      bar.querySelectorAll('button').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      var cat = btn.dataset.filter;
      document.querySelectorAll('.g-card').forEach(function (card) {
        card.style.display = (cat === 'all' || card.dataset.cat === cat) ? '' : 'none';
      });
    });
  }

  /* ------------------------------------------------------------
     Reveal on scroll
     ------------------------------------------------------------ */
  function initReveal() {
    var els = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window)) {
      els.forEach(function (el) { el.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      });
    }, { threshold: 0.12 });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ------------------------------------------------------------
     Floating WhatsApp button — every page, one tap to chat
     ------------------------------------------------------------ */
  function initWhatsAppFloat() {
    if (document.querySelector('.wa-float')) return;
    var a = document.createElement('a');
    a.className = 'wa-float';
    a.href = 'https://wa.me/' + WHATSAPP_NUMBER + '?text=' +
      encodeURIComponent("Hi Lume! I'd like to talk about an LED mirror.");
    a.target = '_blank';
    a.rel = 'noopener';
    a.setAttribute('aria-label', 'Chat with Lume on WhatsApp');
    a.innerHTML = '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16.04 3C9.02 3 3.32 8.7 3.32 15.72c0 2.24.59 4.42 1.7 6.35L3.2 28.8l6.89-1.8a12.66 12.66 0 0 0 5.95 1.51h.01c7.01 0 12.72-5.7 12.72-12.72C28.77 8.7 23.06 3 16.04 3zm0 23.36h-.01a10.5 10.5 0 0 1-5.36-1.47l-.38-.23-3.98 1.04 1.06-3.88-.25-.4a10.53 10.53 0 0 1-1.62-5.62c0-5.83 4.75-10.57 10.58-10.57 2.83 0 5.48 1.1 7.48 3.1a10.5 10.5 0 0 1 3.1 7.48c0 5.83-4.75 10.57-10.57 10.57zm5.8-7.92c-.32-.16-1.88-.93-2.17-1.03-.29-.11-.5-.16-.72.16-.21.32-.82 1.03-1 1.24-.19.21-.37.24-.69.08-.32-.16-1.34-.5-2.55-1.58-.94-.84-1.58-1.87-1.77-2.19-.18-.32-.02-.49.14-.65.15-.14.32-.37.48-.56.16-.19.21-.32.32-.53.11-.21.05-.4-.03-.56-.08-.16-.72-1.72-.98-2.36-.26-.62-.52-.54-.72-.55l-.61-.01c-.21 0-.56.08-.85.4-.29.32-1.11 1.09-1.11 2.65 0 1.56 1.14 3.07 1.3 3.29.16.21 2.24 3.42 5.42 4.8.76.33 1.35.52 1.81.67.76.24 1.45.21 2 .13.61-.09 1.88-.77 2.14-1.5.26-.74.26-1.38.19-1.51-.08-.13-.29-.21-.61-.37z"/></svg>';
    document.body.appendChild(a);
  }

  /* ------------------------------------------------------------
     Gallery lightbox — tap any collection image to inspect it
     ------------------------------------------------------------ */
  var lbIndex = 0;
  function visibleCards() {
    return Array.prototype.filter.call(document.querySelectorAll('.g-card'), function (c) {
      return c.style.display !== 'none';
    });
  }

  function lightboxShow(idx) {
    var cards = visibleCards();
    if (!cards.length) return;
    lbIndex = (idx + cards.length) % cards.length;
    var card = cards[lbIndex];
    var img = card.querySelector('img');
    var btn = card.querySelector('[data-configure]');
    var lb = document.getElementById('lumeLightbox');
    lb.querySelector('.lb-img').src = img.src;
    lb.querySelector('.lb-img').alt = img.alt;
    lb.querySelector('.lb-name').textContent = btn ? btn.dataset.name : '';
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function lightboxClose() {
    var lb = document.getElementById('lumeLightbox');
    if (lb) { lb.classList.remove('open'); document.body.style.overflow = ''; }
  }

  function initLightbox() {
    var cards = document.querySelectorAll('.g-card');
    if (!cards.length) return;
    var lb = document.createElement('div');
    lb.id = 'lumeLightbox';
    lb.className = 'lightbox';
    lb.setAttribute('role', 'dialog');
    lb.setAttribute('aria-modal', 'true');
    lb.setAttribute('aria-label', 'Mirror photo viewer');
    lb.innerHTML =
      '<button type="button" class="lb-close" aria-label="Close viewer">✕</button>' +
      '<button type="button" class="lb-prev" aria-label="Previous mirror">‹</button>' +
      '<img class="lb-img" src="" alt="">' +
      '<div class="lb-bar"><span class="lb-name"></span>' +
      '<button type="button" class="btn btn-lit lb-configure">Customise +</button></div>' +
      '<button type="button" class="lb-next" aria-label="Next mirror">›</button>';
    document.body.appendChild(lb);

    cards.forEach(function (card) {
      card.querySelector('img').addEventListener('click', function () {
        lightboxShow(visibleCards().indexOf(card));
      });
    });
    lb.querySelector('.lb-close').addEventListener('click', lightboxClose);
    lb.querySelector('.lb-prev').addEventListener('click', function () { lightboxShow(lbIndex - 1); });
    lb.querySelector('.lb-next').addEventListener('click', function () { lightboxShow(lbIndex + 1); });
    lb.querySelector('.lb-configure').addEventListener('click', function () {
      var card = visibleCards()[lbIndex];
      var btn = card && card.querySelector('[data-configure]');
      lightboxClose();
      if (btn) openConfigurator(btn.dataset.name, btn.dataset.img, btn.dataset.shape);
    });
    lb.addEventListener('click', function (e) { if (e.target === lb) lightboxClose(); });
    document.addEventListener('keydown', function (e) {
      if (!lb.classList.contains('open')) return;
      if (e.key === 'Escape') lightboxClose();
      if (e.key === 'ArrowLeft') lightboxShow(lbIndex - 1);
      if (e.key === 'ArrowRight') lightboxShow(lbIndex + 1);
    });
  }

  /* ------------------------------------------------------------
     Wire up
     ------------------------------------------------------------ */
  document.addEventListener('DOMContentLoaded', function () {
    renderCartCount();
    renderCartDrawer();
    initFilters();
    initReveal();
    initWhatsAppFloat();
    initLightbox();

    // hero light demo — chips retint the hero glow
    var hero = document.querySelector('.hero');
    if (hero) {
      document.querySelectorAll('.ld-chip').forEach(function (chip) {
        chip.addEventListener('click', function () {
          hero.setAttribute('data-light', chip.dataset.lightmode);
          document.querySelectorAll('.ld-chip').forEach(function (c) {
            c.classList.toggle('active', c === chip);
            c.setAttribute('aria-pressed', c === chip ? 'true' : 'false');
          });
        });
      });
    }

    // nav burger
    var burger = document.querySelector('.nav-burger');
    if (burger) burger.addEventListener('click', function () {
      document.querySelector('.nav-links').classList.toggle('open');
    });
    // tapping a nav link closes the mobile menu (matters for same-page anchors)
    document.querySelectorAll('.nav-links a').forEach(function (a) {
      a.addEventListener('click', function () {
        document.querySelector('.nav-links').classList.remove('open');
      });
    });

    // cart open/close
    document.querySelectorAll('[data-open-cart]').forEach(function (b) {
      b.addEventListener('click', openCart);
    });
    document.querySelectorAll('[data-close-cart]').forEach(function (b) {
      b.addEventListener('click', closeCart);
    });

    // configure buttons on gallery cards
    document.querySelectorAll('[data-configure]').forEach(function (b) {
      b.addEventListener('click', function () {
        openConfigurator(b.dataset.name, b.dataset.img, b.dataset.shape);
      });
    });

    // configurator modal
    var cfgForm = document.getElementById('cfgForm');
    if (cfgForm) cfgForm.addEventListener('submit', configuratorSubmit);
    document.querySelectorAll('[data-close-config]').forEach(function (b) {
      b.addEventListener('click', closeConfigurator);
    });
    var overlay = document.getElementById('configModal');
    if (overlay) overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeConfigurator();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { closeConfigurator(); closeCart(); }
    });

    // checkout
    var checkoutForm = document.getElementById('checkoutForm');
    if (checkoutForm) checkoutForm.addEventListener('submit', checkoutSubmit);

    // custom design form
    var customForm = document.getElementById('customForm');
    if (customForm) customForm.addEventListener('submit', customSubmit);
  });
})();
