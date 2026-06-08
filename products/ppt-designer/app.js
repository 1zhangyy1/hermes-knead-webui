/* PPT Designer — stage-driven canvas (Brief & Style → Outline → Slides). */
const $ = (id) => document.getElementById(id);

// ── Style presets (CSS-drawn swatches; map to ppt-skill style_refs) ──
const STYLES = [
  { id: 'minimal',   name: 'Minimal white',   bg: '#ffffff', ink: '#111111', accent: '#111111' },
  { id: 'dark-tech', name: 'Dark tech',       bg: '#0d1117', ink: '#e6edf3', accent: '#58a6ff' },
  { id: 'corporate', name: 'Corporate blue',  bg: '#f5f8ff', ink: '#1a2f5a', accent: '#2563eb' },
  { id: 'chinese',   name: 'Chinese elegant', bg: '#faf6ef', ink: '#2a211c', accent: '#b0532b' },
  { id: 'editorial', name: 'Editorial',       bg: '#fbfaf7', ink: '#1a1a1a', accent: '#c2410c' },
  { id: 'warm',      name: 'Warm clay',       bg: '#fffbf5', ink: '#1c1008', accent: '#c05c00' },
];

const STAGES = ['brief', 'outline', 'slides'];

const state = {
  stage: 'brief',
  deckName: '',
  title: 'Untitled deck',
  brief: { topic: '', audience: '', count: 8, style: 'minimal' },
  outline: [],            // [{title, points:[], notes}]
  slides: [],             // [{title, imgUrl, notes}]
  current: 0,
};

// ── Bridge helpers ──
const hasBridge = () => window.parent !== window && window.NextAI && window.NextAI.chat && window.NextAI.chat.send;
async function persist() {
  try {
    if (window.NextAI && window.NextAI.state) await window.NextAI.state.set('ppt', state, { scope: 'session' });
    else localStorage.setItem('ppt', JSON.stringify(state));
  } catch (_) {}
}
async function restore() {
  try {
    let saved = null;
    if (window.NextAI && window.NextAI.state) {
      // Never let a slow/absent host block the UI — race against a short timeout.
      saved = await Promise.race([
        window.NextAI.state.get('ppt', null, { scope: 'session' }),
        new Promise((r) => setTimeout(() => r(null), 1200)),
      ]);
    } else {
      saved = JSON.parse(localStorage.getItem('ppt') || 'null');
    }
    if (saved && typeof saved === 'object') Object.assign(state, saved);
  } catch (_) {}
}

function toast(msg) {
  const t = $('toast'); if (!t) return;
  t.textContent = msg; t.classList.add('show');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('show'), 2200);
}

// ── Stage switching ──
function setStage(stage) {
  if (!STAGES.includes(stage)) return;
  state.stage = stage;
  document.body.dataset.stage = stage;
  document.querySelectorAll('.stepper .step').forEach((b) => {
    b.classList.toggle('is-on', b.dataset.go === stage);
    const i = STAGES.indexOf(b.dataset.go);
    b.classList.toggle('is-done', i < STAGES.indexOf(stage));
  });
  $('falBar').hidden = stage !== 'slides';
  render();
  persist();
}

// ── Renders ──
function render() {
  $('deckTitle').textContent = state.title || 'Untitled deck';
  $('deckMeta').textContent = `${state.slides.length || state.outline.length || 0} slides`;
  if (state.stage === 'brief') renderBrief();
  if (state.stage === 'outline') renderOutline();
  if (state.stage === 'slides') renderSlides();
}

function renderBrief() {
  $('topicInput').value = state.brief.topic || '';
  $('audienceInput').value = state.brief.audience || '';
  document.querySelectorAll('#countChips .chip').forEach((c) =>
    c.classList.toggle('is-on', Number(c.dataset.count) === Number(state.brief.count)));
  // style cards
  const grid = $('styleGrid');
  grid.innerHTML = STYLES.map((s) => `
    <button class="style-card ${s.id === state.brief.style ? 'is-on' : ''}" data-style="${s.id}">
      <span class="sw" style="background:${s.bg}">
        <span class="sw-bar" style="background:${s.accent}"></span>
        <span class="sw-l1" style="background:${s.ink}"></span>
        <span class="sw-l2" style="background:${s.ink}55"></span>
      </span>
      <span class="style-name">${s.name}</span>
    </button>`).join('');
  grid.querySelectorAll('.style-card').forEach((b) => b.onclick = () => {
    state.brief.style = b.dataset.style; renderBrief(); persist();
    // Picking a style is part of the conversation: tell the AI.
    const name = (STYLES.find((s) => s.id === b.dataset.style) || {}).name || b.dataset.style;
    if (hasBridge()) send('style', `把这个 PPT 的视觉风格定为「${name}」。据此继续(已有大纲就更新视觉风格)。`);
    else toast(`Style: ${name}`);
  });
}

function renderOutline() {
  const empty = $('outlineEmpty'), list = $('outlineList');
  $('outlineSub').textContent = state.outline.length
    ? 'Edit any title or point inline. Then generate slides.'
    : 'No outline yet.';
  if (!state.outline.length) { empty.hidden = false; list.hidden = true; return; }
  empty.hidden = true; list.hidden = false;
  list.innerHTML = state.outline.map((s, i) => `
    <li class="ol-item" data-i="${i}">
      <div class="ol-num">${String(i + 1).padStart(2, '0')}</div>
      <div class="ol-body">
        <input class="ol-title" data-i="${i}" value="${escAttr(s.title || '')}" placeholder="Slide title">
        <textarea class="ol-points" data-i="${i}" rows="3" placeholder="One point per line">${esc((s.points || []).join('\n'))}</textarea>
      </div>
      <button class="ol-del" data-i="${i}" title="Remove">✕</button>
    </li>`).join('');
  list.querySelectorAll('.ol-title').forEach((el) => el.oninput = () => { state.outline[+el.dataset.i].title = el.value; persistDeb(); });
  list.querySelectorAll('.ol-points').forEach((el) => el.oninput = () => {
    state.outline[+el.dataset.i].points = el.value.split('\n').map(s => s.trim()).filter(Boolean); persistDeb();
  });
  list.querySelectorAll('.ol-del').forEach((el) => el.onclick = () => { state.outline.splice(+el.dataset.i, 1); renderOutline(); render(); persist(); });
}

function renderSlides() {
  const has = state.slides.length > 0;
  $('viewerEmpty').hidden = has;
  $('viewerStage').hidden = !has;
  $('viewerBar').hidden = !has;
  $('thumbStrip').hidden = !has;
  if (!has) return;
  state.current = Math.max(0, Math.min(state.current, state.slides.length - 1));
  const s = state.slides[state.current];
  const img = $('viewerImg'), html = $('viewerHtml');
  if (s.imgUrl) { img.src = s.imgUrl; img.hidden = false; html.hidden = true; }
  else { html.innerHTML = slideHtml(s); html.hidden = false; img.hidden = true; }
  $('navLabel').textContent = `${state.current + 1} / ${state.slides.length}`;
  $('thumbStrip').innerHTML = state.slides.map((sl, i) => `
    <button class="thumb ${i === state.current ? 'is-on' : ''}" data-i="${i}">
      ${sl.imgUrl ? `<img src="${sl.imgUrl}" alt="">` : `<span class="thumb-html">${esc(sl.title || ('Slide ' + (i + 1)))}</span>`}
      <span class="thumb-n">${i + 1}</span>
    </button>`).join('');
  $('thumbStrip').querySelectorAll('.thumb').forEach((b) => b.onclick = () => { state.current = +b.dataset.i; renderSlides(); });
}

function slideHtml(s) {
  const pts = (s.points || []).map(p => `<li>${esc(p)}</li>`).join('');
  return `<div class="slide-render"><h3>${esc(s.title || '')}</h3>${pts ? `<ul>${pts}</ul>` : ''}</div>`;
}

// ── Agent round-trip ──
function agentSpecPrompt() {
  const b = state.brief;
  return [
    `请按这个 brief 规划 PPT 大纲。`,
    `主题：${b.topic || '(未填)'}`,
    `受众：${b.audience || 'general'}`,
    `页数：${b.count}`,
    `风格：${b.style}`,
    `参考 ppt-skill/SKILL.md。先只做大纲规划，不要生成图片。`,
    `在回复末尾用代码块给出结构化大纲(画布会自动读取并展示)：`,
    '```outline.json',
    '{"title":"演示标题","slides":[{"title":"第1页标题","points":["要点1","要点2"],"notes":"讲稿"}]}',
    '```',
  ].join('\n');
}
function agentGeneratePrompt() {
  const b = state.brief, deck = state.deckName || slug(b.topic) || 'deck';
  state.deckName = deck;
  return [
    `确认大纲，用 ppt-skill(GPT Image 2) 生成 PPT。`,
    `在产品根目录运行：python ppt-skill/ppt.py gen ${deck} "<每页prompt>" --quality high`,
    `风格：${b.style}。产物落 outputs/${deck}/(slide-NN.png)。`,
    `缺 fal 密钥(ppt-skill/.env)或依赖就直说,别假装生成。`,
    `当前大纲：\n${state.outline.map((s, i) => `${i + 1}. ${s.title} — ${(s.points || []).join('; ')}`).join('\n')}`,
    `生成完在回复末尾附(按实际页数)：`,
    '```js',
    `window.PPT.loadImages("${(state.title || deck)}", "${deck}", [`,
    `  {slot:1, imgUrl:"/api/products/ppt-designer/preview/outputs/${deck}/slide-01.png", title:"第1页标题"},`,
    `]);`,
    '```',
  ].join('\n');
}

async function send(kind, prompt, btn) {
  if (!hasBridge()) { try { await navigator.clipboard.writeText(prompt); } catch (_) {} toast('Prompt copied — paste into chat'); return; }
  const old = btn && btn.textContent; if (btn) { btn.disabled = true; btn.textContent = 'Sent…'; }
  try {
    // The reply is handled uniformly via the broadcast → onAgentMessage (one path,
    // whether the turn came from a canvas button or the user typing in chat).
    await window.NextAI.chat.send({ text: prompt, action: `ppt:${kind}`, context: { ppt: state.brief } });
  } catch (e) { toast((e && e.message) || 'Send failed'); }
  finally { if (btn) { btn.disabled = false; btn.textContent = old; } }
}

function applyReply(kind, content) {
  if (kind === 'spec') {
    const o = parseOutlineReply(content);
    if (!o) { toast('Outline coming in chat…'); return; }
    state.title = o.title || state.title;
    state.outline = o.slides || [];
    setStage('outline'); toast('Outline ready');
  } else if (kind === 'generate') {
    const d = parseLoadImages(content);
    if (!d) { toast('Generating… check chat'); return; }
    window.PPT.loadImages(d.title, d.deckName, d.entries);
  }
}

function parseOutlineReply(text) {
  const s = String(text || '');
  const m = s.match(/```(?:outline\.json|json)?\s*(\{[\s\S]*?\})\s*```/);
  if (!m) return null;
  try { const o = JSON.parse(m[1]); if (Array.isArray(o.slides)) return o; } catch (_) {}
  return null;
}
function parseLoadImages(text) {
  const s = String(text || ''); if (s.indexOf('loadImages') === -1) return null;
  const head = s.match(/loadImages\(\s*"([^"]*)"\s*,\s*"([^"]*)"/); if (!head) return null;
  const entries = []; const re = /\{\s*slot\s*:\s*(\d+)\s*,\s*imgUrl\s*:\s*"([^"]+)"\s*(?:,\s*title\s*:\s*"([^"]*)")?\s*\}/g; let m;
  while ((m = re.exec(s))) entries.push({ slot: +m[1], imgUrl: m[2], title: m[3] || '' });
  return entries.length ? { title: head[1], deckName: head[2], entries } : null;
}

// ── React to the live conversation: the canvas is a surface FOR the chat ──
// When the agent (in the host chat) produces an outline or generated slides,
// the right canvas auto-expands to that stage. No buttons required.
// Easiest, most reliable AI→GUI channel: the agent writes deck state to a workspace
// file (state.json); the canvas reads it. The canvas is served from the workspace,
// so a relative fetch hits that file. Chat-block parsing stays as a fallback.
function applyDeckState(d) {
  if (!d || typeof d !== 'object') return false;
  if (d.title) state.title = d.title;
  if (d.deckName) state.deckName = d.deckName;
  if (d.style) state.brief.style = d.style;
  if (d.brief && typeof d.brief === 'object') Object.assign(state.brief, d.brief);
  if (Array.isArray(d.outline)) state.outline = d.outline.map((s) => ({ title: s.title || '', points: s.points || s.bullets || [], notes: s.notes || '' }));
  if (Array.isArray(d.slides)) state.slides = d.slides.map((s, i) => ({ title: s.title || `Slide ${i + 1}`, imgUrl: s.imgUrl || s.img || '', notes: s.notes || '' }));
  const stage = d.stage || (state.slides.length ? 'slides' : state.outline.length ? 'outline' : state.stage);
  setStage(stage);
  return true;
}
async function fetchStateFile() {
  try {
    const r = await fetch('state.json?cb=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) return false;
    return applyDeckState(await r.json());
  } catch (_) { return false; }
}

function onAgentMessage(content) {
  const o = parseOutlineReply(content);
  if (o) { state.title = o.title || state.title; state.outline = o.slides || []; setStage('outline'); toast('Outline updated'); return; }
  const d = parseLoadImages(content);
  if (d) { window.PPT.loadImages(d.title, d.deckName, d.entries); return; }
  if (/style\.pick|\[\[pick[_-]?style\]\]/i.test(String(content || ''))) { setStage('brief'); toast('Pick a style →'); }
}
window.addEventListener('nextai:agent', async (e) => {
  // Prefer the file the agent wrote this turn; fall back to parsing the chat reply.
  const got = await fetchStateFile();
  if (!got) { try { onAgentMessage(e.detail && e.detail.content); } catch (_) {} }
});

// ── window.PPT API (agent callbacks) ──
window.PPT = {
  loadOutline(title, slides) {
    state.title = title || state.title; state.outline = slides || [];
    setStage('outline'); toast(`Outline · ${state.outline.length} slides`);
  },
  loadImages(title, deckName, entries) {
    state.title = title || state.title; if (deckName) state.deckName = deckName;
    state.slides = (entries || []).map((e, i) => ({ title: e.title || `Slide ${i + 1}`, imgUrl: e.imgUrl || '', notes: e.notes || '' }));
    state.current = 0; setStage('slides'); toast(`Loaded ${state.slides.length} slides`);
  },
  load(title, slideData) { // back-compat: treat as outline-style slides
    state.title = title || state.title;
    state.outline = (slideData || []).map(s => ({ title: s.title || '', points: s.bullets || s.points || [], notes: s.notes || '' }));
    setStage('outline');
  },
  get() { return { ...state }; },
};

// ── utils ──
function esc(s) { return String(s ?? '').replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
function escAttr(s) { return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
function slug(s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 32); }
let _pt; function persistDeb() { clearTimeout(_pt); _pt = setTimeout(persist, 400); }

// ── wire up ──
function collectBriefFromInputs() {
  state.brief.topic = $('topicInput').value.trim();
  state.brief.audience = $('audienceInput').value.trim();
}
function init() {
  // stepper
  document.querySelectorAll('.stepper .step').forEach((b) => b.onclick = () => setStage(b.dataset.go));
  // brief inputs
  $('topicInput').oninput = () => { state.brief.topic = $('topicInput').value; persistDeb(); };
  $('audienceInput').oninput = () => { state.brief.audience = $('audienceInput').value; persistDeb(); };
  $('countChips').onclick = (e) => { const c = e.target.closest('.chip'); if (!c) return; state.brief.count = +c.dataset.count; renderBrief(); persist(); };
  // actions
  $('shapeOutlineBtn').onclick = (e) => { collectBriefFromInputs(); send('spec', agentSpecPrompt(), e.currentTarget); };
  $('generateBtn').onclick = (e) => send('generate', agentGeneratePrompt(), e.currentTarget);
  $('exportBtn').onclick = (e) => send('pack', `用 ppt-skill 打包 deck ${state.deckName || 'deck'}：python ppt-skill/ppt.py pack ${state.deckName || 'deck'}，完成后给我 deck.pptx 路径。`, e.currentTarget);
  $('addSlideBtn').onclick = () => { state.outline.push({ title: '', points: [], notes: '' }); renderOutline(); render(); persist(); };
  $('prevBtn').onclick = () => { state.current = Math.max(0, state.current - 1); renderSlides(); };
  $('nextBtn').onclick = () => { state.current = Math.min(state.slides.length - 1, state.current + 1); renderSlides(); };
  $('falConfigBtn').onclick = () => toast('Set FAL key in ppt-skill/.env');
}

function seedDemo(stage) {
  state.title = 'Q2 AI Tooling Review';
  state.brief = { topic: 'Q2 AI tooling — results & next steps', audience: 'engineering leadership', count: 8, style: 'minimal' };
  state.outline = [
    { title: 'Q2 AI Tooling — Results & Next Steps', points: ['8 weeks · 12 engineers', 'Review + Q3 plan'], notes: '' },
    { title: 'The bet', points: ['AI in code review + test generation', 'Target: +20% delivery, flat headcount'], notes: '' },
    { title: 'What we rolled out', points: ['Copilot — completion', 'Codex — bug fix & tests', 'Claude — docs & API notes'], notes: '' },
    { title: 'Results', points: ['Review time −31%', 'Test coverage +18pt', 'Satisfaction 4.4 / 5'], notes: '' },
    { title: 'Risks & watch-items', points: ['Over-reliance on suggestions', 'Prompt hygiene'], notes: '' },
    { title: 'Roadmap — Q3', points: ['Expand to QA', 'Shared prompt library'], notes: '' },
  ];
  if (stage === 'slides') { state.slides = state.outline.map((s) => ({ title: s.title, points: s.points, imgUrl: '', notes: '' })); state.current = 0; }
  state.stage = stage === 'slides' ? 'slides' : 'outline';
}

// ── 喜茶发展史：当前已生成的 deck 数据，优先级最高 ──
const HEYTEA_DECK = {
  title: '喜茶发展史',
  deckName: 'deck',
  stage: 'slides',
  brief: {
    topic: '喜茶发展史 — 从江门18㎡小店到全球消费茶饮第一品牌',
    audience: '品牌爱好者 / 商业讲演',
    count: 8,
    style: 'minimal',
  },
  outline: [
    { title: '封面：一杯茶的野心',       points: ['大字「喜茶」居中，高对比衬线字体', '副标题：一杯茶的野心', '喜茶 IP 小人（线描，头顶茶杯）占右下角', '时间范围：2012 — 2025'], notes: '封面建立整体调性：喜茶极简线描插画风，米白底，茶棕点缀' },
    { title: '起点：一间 18㎡ 的小店',   points: ['2012 年广东江门，10 万元起家', '主打天然芝士茶，奶精时代的破局者', '左侧大号「2012」锚定时间'], notes: '创始人聂云宸在江门创业，彼时大部分茶饮还在用奶精' },
    { title: '爆红：排队 4 小时',        points: ['2016 年深圳万象城，日均排队时长 4 小时', '黄牛炒茶，30 元茶有人出 150 元代购', '深墨绿底反白，大号「4小时」占满画面中心'], notes: '深圳是喜茶真正出圈的起点，排队文化让品牌成为全国话题' },
    { title: '融资：四轮，估值 600 亿',  points: ['2016 天使轮 IDG 领投', '2018 A轮 美团龙珠·黑蚁资本', '2020 C轮 估值 160 亿', '2022 D轮 估值 600 亿'], notes: '横向时间轴，四个里程碑节点' },
    { title: '进化：从茶饮到生活方式',   points: ['2012：18㎡小店 / 手写招牌 / 一款芝士茶', '2024：全球 900+ 门店 / 12 个海外城市 / 联名 100+ 品牌'], notes: '左右对比卡片' },
    { title: '联名：跨界是另一种语言',   points: ['FENDI — 高奢破次元，引发抢购潮', '藤原浩 — 街头文化入侵茶饮圈', '梦华录 — 古装剧联名 3 天售 100 万杯', '原神 — 二次元用户首次大规模破圈', 'Nike — 运动生活方式人群拓展', 'LINE FRIENDS — 少女心与悦己经济'], notes: '3×2 卡片网格' },
    { title: '出海：12 个城市的版图',    points: ['2023—2025，从华人聚居区走向主流市场', '新加坡·伦敦·纽约·洛杉矶·东京·首尔·多伦多·悉尼·巴黎·迪拜·曼谷·吉隆坡'], notes: '极简线描世界地图，茶棕圆点标注城市' },
    { title: '结语：重新定义中国消费',   points: ['极致产品力 × 品牌美学 × 文化联结', '喜茶证明：一个品类可以从头开始被重新定义'], notes: '超大留白，右下角举杯小人收尾' },
  ],
  slides: [
    { title: '封面：一杯茶的野心',       imgUrl: 'outputs/deck/slide-01.png', notes: '封面：建立调性。喜茶极简线描风，米白底，茶棕点缀。' },
    { title: '起点：江门18㎡小店',       imgUrl: 'outputs/deck/slide-02.png', notes: '2012年，10万元起步，天然芝士茶破局奶精时代。' },
    { title: '爆红：排队4小时',          imgUrl: 'outputs/deck/slide-03.png', notes: '2016深圳，日均排队4小时，黄牛炒茶现象级出圈。' },
    { title: '融资：估值600亿',          imgUrl: 'outputs/deck/slide-04.png', notes: '四轮融资时间轴：2016天使→2018A→2020C→2022D轮600亿。' },
    { title: '进化：从茶饮到生活方式',   imgUrl: 'outputs/deck/slide-05.png', notes: '2012 vs 2024 对比：从小店到全球900+门店，100+联名。' },
    { title: '联名：跨界是另一种语言',   imgUrl: 'outputs/deck/slide-06.png', notes: 'FENDI·藤原浩·梦华录·原神·Nike·LINE FRIENDS，6大联名。' },
    { title: '出海：12个城市版图',       imgUrl: 'outputs/deck/slide-07.png', notes: '12个海外城市，从华人区走向本地化主流市场。' },
    { title: '结语：重新定义中国消费',   imgUrl: 'outputs/deck/slide-08.png', notes: '极致产品力×品牌美学×文化联结，喜茶重新定义一个品类。' },
  ],
  current: 0,
};

(async function start() {
  init();
  const demo = new URLSearchParams(location.search).get('demo');
  if (demo) { seedDemo(demo); setStage(state.stage); return; }
  setStage(state.stage || 'brief');   // paint immediately with defaults
  await restore();                    // then load saved session state (timeout-guarded)
  await fetchStateFile();             // workspace state.json (what the agent wrote) wins
  // 最终：把当前已生成的喜茶 deck 强制写入，覆盖一切旧状态
  applyDeckState(HEYTEA_DECK);
})();
