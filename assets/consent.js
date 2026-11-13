// still() 쿠키 동의 배너 — GA4 는 수락한 방문자에게만 로드한다. 측정 ID 는 scripts/site_common.py 와 여기 두 곳에만 있다.
(function () {
  var GA_ID = 'G-XG4BH800J0';
  var KEY = 'still_ga_consent';
  var T = {
    en: ['We use Google Analytics to understand how this site is used. It loads only if you accept.', 'Accept', 'Decline', 'Privacy policy'],
    ko: ['사이트 이용 현황을 파악하려고 Google Analytics(GA4)를 씁니다. 수락하실 때만 로드됩니다.', '수락', '거절', '개인정보처리방침'],
    ja: ['サイトの利用状況を把握するため Google Analytics（GA4）を使用します。同意いただいた場合のみ読み込みます。', '同意する', '拒否', 'プライバシーポリシー'],
    'zh-Hant': ['為了解網站使用情況，本站使用 Google Analytics（GA4）。只有您同意後才會載入。', '同意', '拒絕', '隱私權政策'],
    es: ['Usamos Google Analytics (GA4) para entender cómo se usa este sitio. Solo se carga si lo aceptas.', 'Aceptar', 'Rechazar', 'Política de privacidad'],
    'pt-BR': ['Usamos o Google Analytics (GA4) para entender como o site é usado. Ele só é carregado se você aceitar.', 'Aceitar', 'Recusar', 'Política de privacidade'],
    fr: ["Nous utilisons Google Analytics (GA4) pour comprendre l'usage du site. Il n'est chargé que si vous acceptez.", 'Accepter', 'Refuser', 'Politique de confidentialité'],
    de: ['Wir nutzen Google Analytics (GA4), um die Nutzung der Website zu verstehen. Es wird nur geladen, wenn Sie zustimmen.', 'Akzeptieren', 'Ablehnen', 'Datenschutzerklärung'],
    id: ['Kami menggunakan Google Analytics (GA4) untuk memahami cara situs ini digunakan. Analitik hanya dimuat jika Anda menerima.', 'Terima', 'Tolak', 'Kebijakan privasi'],
    th: ['เราใช้ Google Analytics (GA4) เพื่อทำความเข้าใจการใช้งานเว็บไซต์นี้ จะโหลดก็ต่อเมื่อคุณยอมรับเท่านั้น', 'ยอมรับ', 'ปฏิเสธ', 'นโยบายความเป็นส่วนตัว'],
    vi: ['Chúng tôi dùng Google Analytics (GA4) để hiểu cách trang này được sử dụng. Chỉ tải khi bạn đồng ý.', 'Đồng ý', 'Từ chối', 'Chính sách bảo mật'],
    tr: ['Bu sitenin nasıl kullanıldığını anlamak için Google Analytics (GA4) kullanıyoruz. Yalnızca kabul ederseniz yüklenir.', 'Kabul et', 'Reddet', 'Gizlilik politikası']
  };
  var lang = document.documentElement.getAttribute('lang') || 'en';
  var t = T[lang] || (/^zh(-|$)/.test(lang) ? T['zh-Hant'] : T.en);
  var privacy = lang === 'ko' ? 'https://ipe.rest/ko/legal/privacy/' : 'https://ipe.rest/en/legal/privacy/';
  // a local preview must not count as a visit: the banner still shows there, GA4 never loads
  var LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  function store(v) {
    try { localStorage.setItem(KEY, v); } catch (e) { /* 저장 실패 = 다음 방문에 다시 묻는다 */ }
  }

  function outbound(e) {
    if (e.type === 'auxclick' && e.button !== 1) return;
    var a = e.target.closest && e.target.closest('a[href^="http"]');
    if (!a) return;
    var h = a.hostname;
    if (h === location.hostname || h === 'ipe.rest' || /\.ipe\.rest$/.test(h)) return;
    window.gtag('event', 'outbound_click', {link_url: a.href, link_domain: h, transport_type: 'beacon'});
  }

  function load() {
    if (LOCAL) return;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag('consent', 'default', {analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied'});
    window.gtag('consent', 'update', {analytics_storage: 'granted'});
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + GA_ID;
    document.head.appendChild(s);
    window.gtag('js', new Date());
    window.gtag('config', GA_ID);
    document.addEventListener('click', outbound);
    document.addEventListener('auxclick', outbound);
  }

  function button(label, onClick) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'consent-btn';
    b.textContent = label;
    b.onclick = onClick;
    return b;
  }

  function banner() {
    var box = document.createElement('section');
    box.className = 'consent';
    box.setAttribute('aria-label', t[0]);
    var text = document.createElement('p');
    text.appendChild(document.createTextNode(t[0] + ' '));
    var link = document.createElement('a');
    link.href = privacy;
    link.textContent = t[3];
    text.appendChild(link);
    var row = document.createElement('div');
    row.className = 'consent-actions';
    row.appendChild(button(t[1], function () { store('granted'); box.remove(); load(); }));
    row.appendChild(button(t[2], function () { store('denied'); box.remove(); }));
    box.appendChild(text);
    box.appendChild(row);
    document.body.appendChild(box);
  }

  var saved = stored();
  if (saved === 'granted') load();
  else if (saved !== 'denied') banner();
})();
