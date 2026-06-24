// ── Constants ──────────────────────────────────────────────────────────────

const STORAGE_KEY = 'ai_otome_mira_v2';

const SCENES = {
  rain:    { label: 'Rainy Station',    line: 'Rain taps the glass roof. She notices you before you speak.', tint: 'rgba(100,140,220,.08)' },
  cafe:    { label: 'Late-Night Cafe',  line: 'A small table, warm lights, and two cups cooling too slowly.', tint: 'rgba(220,120,80,.07)' },
  library: { label: 'Moonlit Library',  line: 'Dust glows in the moonlight. Mira lowers her voice without meaning to.', tint: 'rgba(140,100,200,.08)' },
  rooftop: { label: 'Quiet Rooftop',   line: 'The city hums below. The night gives both of you room to be honest.', tint: 'rgba(80,160,120,.07)' },
};

const SCENE_IDS = Object.keys(SCENES);

const PORTRAITS = {
  default: 'assets/mira-happy.png',
  happy: 'assets/mira-happy.png', warm: 'assets/mira-happy.png',
  joyful: 'assets/mira-happy.png', excited: 'assets/mira-happy.png',
  pleased: 'assets/mira-happy.png', fond: 'assets/mira-happy.png',
  relieved: 'assets/mira-happy.png', curious: 'assets/mira-happy.png',
  neutral: 'assets/mira-happy.png', calm: 'assets/mira-happy.png',
  attentive: 'assets/mira-happy.png', pensive: 'assets/mira-happy.png',
  tender: 'assets/mira-shy.png', shy: 'assets/mira-shy.png',
  flushed: 'assets/mira-shy.png', bashful: 'assets/mira-shy.png',
  embarrassed: 'assets/mira-shy.png', touched: 'assets/mira-shy.png',
  moved: 'assets/mira-shy.png',
  sad: 'assets/mira-sad.png', hurt: 'assets/mira-sad.png',
  lonely: 'assets/mira-sad.png', wistful: 'assets/mira-sad.png',
  melancholy: 'assets/mira-sad.png',
  serious: 'assets/mira-serious.png', focused: 'assets/mira-serious.png',
  determined: 'assets/mira-serious.png', worried: 'assets/mira-serious.png',
  conflicted: 'assets/mira-serious.png',
  surprised: 'assets/mira-surprise.png', surprise: 'assets/mira-surprise.png',
  startled: 'assets/mira-surprise.png', stunned: 'assets/mira-surprise.png',
  blink: 'assets/mira-blink.png', amused: 'assets/mira-blink.png',
  teasing: 'assets/mira-blink.png', playful: 'assets/mira-blink.png',
};

const MOOD_ZH = {
  happy:'😊 开心', warm:'🌿 温柔', joyful:'✨ 雀跃', excited:'🌟 期待',
  pleased:'😌 满足', fond:'💜 喜欢', relieved:'😮‍💨 安心',
  curious:'🍃 好奇', neutral:'🌸 平静', calm:'🌿 平静',
  attentive:'👀 专注', pensive:'💭 若有所思',
  tender:'💜 心动', shy:'🌱 害羞', flushed:'🌸 脸红了',
  bashful:'🌱 有点不好意思', embarrassed:'😳 慌了',
  touched:'🥹 感动', moved:'💜 触动',
  sad:'🌧 有点难过', hurt:'💔 受伤了', lonely:'🌑 有点孤单',
  wistful:'🍂 惆怅', melancholy:'🌧 伤感',
  serious:'🌿 认真', focused:'🎯 专注', determined:'💪 下定决心',
  worried:'😟 担心', conflicted:'🌀 纠结',
  surprised:'😲 吃惊', startled:'！ 被吓到了', stunned:'😳 呆住了',
  blink:'😏 坏坏的', amused:'😄 被逗笑了',
  teasing:'😉 在捉弄你', playful:'🌿 活泼',
};

const PORTRAIT_PROMPT = `[half-body character art, anime otome game key visual]
Character: Mira, dark chestnut hair with soft side-swept bangs, warm violet eyes with gentle highlights, small floral hairpin, expression — shy and curious
Outfit: cozy modern romantic — cream turtleneck sweater, delicate necklace
Scene: misty rain station platform, bokeh streetlights, night
Mood: emotionally present, subtle warmth, soft longing
Style: clean visual novel character sprite, modern high-quality anime illustration, refined soft lighting, generous padding, no text, no watermark, no UI elements
Composition: centered half-body portrait, atmospheric depth`;

const DEFAULT_STATE = {
  scene: 'rain',
  mood: 'curious',
  bond: 18,
  chapter: 'Chapter 1',
  chapterTitle: 'A rain-soaked promise',
  objective: 'Make Mira feel that this meeting was not an accident.',
  portraitUrl: '',
  beats: ['Mira waited at the station longer than she admits.', 'The rain gives both of you an excuse to stay close.'],
  memories: ['You met Mira on a rainy evening.', 'She likes when you answer honestly.'],
  messages: [
    {
      role: 'assistant',
      content: '*Mira folds her umbrella and smiles like she was hoping you would arrive.*\n\n「你来了。我还以为今晚的雨会让你打退堂鼓。」',
    },
  ],
  choices: ['我想见你。', '雨让这一切像个秘密。', '你在等我吗？'],
};

// ── State ─────────────────────────────────────────────────────────────────

let state = cloneDefault();
let sending = false;

function cloneDefault() { return JSON.parse(JSON.stringify(DEFAULT_STATE)); }

async function loadState() {
  try {
    const useBridge = window.NextAI?.state && window.parent !== window;
    const saved = useBridge
      ? await window.NextAI.state.get(STORAGE_KEY, null)
      : JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    if (saved && Array.isArray(saved.messages)) state = normalizeState(saved);
  } catch { state = cloneDefault(); }
}

async function saveState() {
  const payload = normalizeState(state);
  if (window.NextAI?.state && window.parent !== window) {
    await window.NextAI.state.set(STORAGE_KEY, payload);
  } else {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }
}

function normalizeState(raw) {
  return {
    scene: SCENES[raw.scene] ? raw.scene : 'rain',
    mood: String(raw.mood || 'curious').slice(0, 32),
    bond: clamp(Number(raw.bond ?? 18), 0, 100),
    chapter: String(raw.chapter || 'Chapter 1').slice(0, 40),
    chapterTitle: String(raw.chapterTitle || DEFAULT_STATE.chapterTitle).slice(0, 80),
    objective: String(raw.objective || DEFAULT_STATE.objective).slice(0, 160),
    portraitUrl: normalizePortraitUrl(raw.portraitUrl),
    beats: Array.isArray(raw.beats) ? raw.beats.slice(-5).map(String) : cloneDefault().beats,
    memories: Array.isArray(raw.memories) ? raw.memories.slice(-8).map(String) : [],
    messages: Array.isArray(raw.messages)
      ? raw.messages.filter(m => m?.content).slice(-40).map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: String(m.content) }))
      : cloneDefault().messages,
    choices: Array.isArray(raw.choices) ? raw.choices.slice(0, 4).map(String) : [],
  };
}

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

function normalizePortraitUrl(v) {
  const u = String(v || '').trim();
  return u && !u.endsWith('assets/mira.svg') ? u : '';
}

// ── DOM refs ──────────────────────────────────────────────────────────────

const appEl         = document.getElementById('app');
const stageBg       = document.getElementById('stageBg');
const sceneLabel    = document.getElementById('sceneLabel');
const portraitEl    = document.getElementById('portrait');
const portraitFb    = document.getElementById('portraitFallback');
const moodPill      = document.getElementById('moodPill');
const sceneDotsEl   = document.getElementById('sceneDots');
const bondFill      = document.getElementById('bondFill');
const bondPct       = document.getElementById('bondPct');
const bondBurst     = document.getElementById('bondBurst');
const chapterTag    = document.getElementById('chapterTag');
const chapterTitle  = document.getElementById('chapterTitle');
const objectiveText = document.getElementById('objectiveText');
const messagesEl    = document.getElementById('messages');
const choicesEl     = document.getElementById('choices');
const inputEl       = document.getElementById('input');
const composerEl    = document.getElementById('composer');
const sendBtn       = document.getElementById('sendBtn');
const memoryToggle  = document.getElementById('memoryToggle');
const memoryPanel   = document.getElementById('memoryPanel');
const panelClose    = document.getElementById('panelClose');
const beatList      = document.getElementById('beatList');
const memoryList    = document.getElementById('memoryList');
const sceneList     = document.getElementById('sceneList');
const resetBtn      = document.getElementById('resetBtn');
const imageBtn      = document.getElementById('imageBtn');
const imageDialog   = document.getElementById('imageDialog');
const imagePrompt   = document.getElementById('imagePrompt');
const copyPromptBtn = document.getElementById('copyPromptBtn');
const generatePortraitBtn = document.getElementById('generatePortraitBtn');
const imageResult   = document.getElementById('imageResult');

// Overlay for panel
const overlay = document.createElement('div');
overlay.className = 'overlay';
document.body.appendChild(overlay);

// ── Render ────────────────────────────────────────────────────────────────

function render() {
  const scene = SCENES[state.scene] || SCENES.rain;

  appEl.dataset.scene = state.scene;
  appEl.dataset.mood  = state.mood.toLowerCase();

  // Scene tint on stage bg
  stageBg.style.background = scene.tint;
  sceneLabel.textContent = scene.label;

  // Portrait
  const url = state.portraitUrl || portraitForMood(state.mood);
  if (url !== portraitEl.src.replace(location.origin + '/', '').replace(location.origin, '')) {
    portraitEl.src = url;
  }

  // Mood
  const mKey = state.mood.toLowerCase().trim();
  moodPill.textContent = MOOD_ZH[mKey] || ucFirst(state.mood);

  // Scene dots
  renderSceneDots();

  // Bond
  const b = clamp(state.bond, 0, 100);
  bondFill.style.width = b + '%';
  bondPct.textContent  = Math.round(b) + '%';

  // Chapter
  chapterTag.textContent   = state.chapter;
  chapterTitle.textContent = state.chapterTitle;
  objectiveText.textContent = state.objective;

  renderMessages();
  renderChoices();
  renderBeats();
  renderMemories();
  renderSceneList();
}

function renderSceneDots() {
  sceneDotsEl.innerHTML = '';
  SCENE_IDS.forEach(id => {
    const btn = document.createElement('button');
    btn.className = 'scene-dot' + (id === state.scene ? ' active' : '');
    btn.type = 'button';
    btn.title = SCENES[id].label;
    btn.addEventListener('click', () => switchScene(id));
    sceneDotsEl.appendChild(btn);
  });
}

function renderMessages() {
  messagesEl.innerHTML = '';
  state.messages.forEach(m => messagesEl.appendChild(buildMsgNode(m)));
  requestAnimationFrame(() => { messagesEl.scrollTop = messagesEl.scrollHeight; });
}

function buildMsgNode(msg, typing = false) {
  const art  = document.createElement('article');
  art.className = 'message ' + (msg.role === 'user' ? 'user' : 'ai');

  const spk  = document.createElement('span');
  spk.className = 'speaker';
  spk.textContent = msg.role === 'user' ? 'You' : 'Mira';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  if (typing) {
    const dots = document.createElement('div');
    dots.className = 'typing-dots';
    dots.innerHTML = '<span></span><span></span><span></span>';
    bubble.appendChild(dots);
  } else {
    parseSegments(msg.content).forEach(seg => {
      const p = document.createElement('p');
      p.className = seg.type;
      p.textContent = seg.text;
      bubble.appendChild(p);
    });
  }

  art.append(spk, bubble);
  return art;
}

function parseSegments(text) {
  const parts = String(text || '').split(/(\*[^*]+\*)/g).filter(p => p.trim());
  const segs  = [];
  parts.forEach(p => {
    if (p.startsWith('*') && p.endsWith('*')) {
      segs.push({ type: 'action', text: p.slice(1, -1).trim() });
    } else {
      p.split('\n').filter(l => l.trim()).forEach(l => segs.push({ type: 'speech', text: l.trim() }));
    }
  });
  return segs.length ? segs : [{ type: 'speech', text }];
}

function renderChoices() {
  choicesEl.innerHTML = '';
  state.choices.forEach(c => {
    const btn = document.createElement('button');
    btn.className = 'choice-btn';
    btn.type = 'button';
    btn.textContent = c;
    btn.addEventListener('click', () => send(c));
    choicesEl.appendChild(btn);
  });
}

function renderBeats() {
  beatList.innerHTML = '';
  const beats = state.beats.length ? state.beats : ['The story has just begun.'];
  beats.slice(-5).forEach((beat, i) => {
    const li  = document.createElement('li');
    const num = document.createElement('span');
    num.className = 'beat-num';
    num.textContent = String(i + 1).padStart(2, '0');
    const txt = document.createElement('span');
    txt.textContent = beat;
    li.append(num, txt);
    beatList.appendChild(li);
  });
}

function renderMemories() {
  memoryList.innerHTML = '';
  const mems = state.memories.length ? state.memories : ['Mira is still learning what matters to you.'];
  mems.slice(-6).forEach(m => {
    const li = document.createElement('li');
    li.textContent = m;
    memoryList.appendChild(li);
  });
}

function renderSceneList() {
  sceneList.innerHTML = '';
  SCENE_IDS.forEach(id => {
    const btn = document.createElement('button');
    btn.className = 'scene-btn' + (id === state.scene ? ' active' : '');
    btn.type = 'button';
    btn.textContent = SCENES[id].label;
    btn.addEventListener('click', () => {
      closePanel();
      switchScene(id);
    });
    sceneList.appendChild(btn);
  });
}

async function switchScene(id) {
  if (!SCENES[id] || id === state.scene) return;
  state.scene = id;
  state.messages.push({ role: 'assistant', content: `*画面一转，来到了${SCENES[id].label}。*` });
  await saveState();
  render();
}

// ── Bond burst ────────────────────────────────────────────────────────────

function showBondBurst(delta) {
  bondBurst.textContent = delta > 0 ? `Bond +${delta} ♡` : `Bond ${delta}`;
  bondBurst.classList.remove('show');
  void bondBurst.offsetWidth;
  bondBurst.classList.add('show');
  bondBurst.addEventListener('animationend', () => bondBurst.classList.remove('show'), { once: true });
}

// ── Portrait helpers ───────────────────────────────────────────────────────

function portraitForMood(mood) {
  const k = String(mood || '').toLowerCase().trim();
  if (PORTRAITS[k]) return PORTRAITS[k];
  const fuzzy = Object.keys(PORTRAITS).find(p => p !== 'default' && k.includes(p));
  return PORTRAITS[fuzzy] || PORTRAITS.default;
}

function ucFirst(s) { return String(s).charAt(0).toUpperCase() + String(s).slice(1); }

// ── Send / AI call ────────────────────────────────────────────────────────

composerEl.addEventListener('submit', e => { e.preventDefault(); send(inputEl.value); });

inputEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(inputEl.value); }
});

inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
});

async function send(rawText) {
  const text = String(rawText || '').trim();
  if (!text || sending) return;

  sending = true;
  sendBtn.disabled = true;
  inputEl.value = '';
  inputEl.style.height = 'auto';
  state.choices = [];
  state.messages.push({ role: 'user', content: text });
  renderMessages();
  renderChoices();
  await saveState();

  // Typing indicator
  const typingNode = buildMsgNode({ role: 'assistant', content: '' }, true);
  messagesEl.appendChild(typingNode);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  try {
    const raw = await callMira(text);
    typingNode.remove();
    applyAIReply(raw);
  } catch {
    typingNode.remove();
    state.messages.push({
      role: 'assistant',
      content: '*Mira 低头看了看手机，随后抬起头，带着一点歉意微笑。*\n\n「刚才走神了一秒——你说什么来着？」',
    });
    state.choices = ['我再说一遍。', '没关系，慢慢来。', '你还好吗？'];
  } finally {
    sending = false;
    sendBtn.disabled = false;
    await saveState();
    render();
  }
}

async function callMira(text) {
  if (!window.NextAI?.chat?.send || window.parent === window) {
    return localFallback(text);
  }
  const res = await window.NextAI.chat.send({
    action: 'otome_companion_turn',
    text,
    context: {
      mode: 'ai_otome_companion',
      product: 'AI Otome',
      character: {
        name: 'Mira',
        system: `You are Mira, a warm, emotionally present AI companion in a gentle otome romance game. You respond in Chinese. Include short atmospheric action lines in *asterisks* to set the mood. At the very end of each reply (on its own last line), output exactly ONE JSON object (no markdown) with these keys:
- mood: one English word from: happy warm joyful excited pleased fond relieved curious calm attentive pensive tender shy flushed bashful embarrassed touched moved sad hurt lonely wistful melancholy serious focused determined worried conflicted surprised startled stunned blink amused teasing playful
- bond_delta: integer from -3 to 6
- scene: rain | cafe | library | rooftop
- memory: one durable memory string, or empty string
- beat: one short story beat that just happened
- chapter_title: current chapter title or empty string
- objective: next emotional objective for the player
- choices: array of 2-3 Chinese next-step player choices`,
      },
      game_state: {
        scene: SCENES[state.scene].label,
        mood: state.mood,
        bond: state.bond,
        chapter: state.chapter,
        objective: state.objective,
        beats: state.beats.slice(-3),
        memories: state.memories.slice(-5),
      },
      history: state.messages.slice(-12),
    },
  });
  return res?.content || '';
}

function localFallback(text) {
  const lo = text.toLowerCase();
  const scene = lo.includes('咖啡') || lo.includes('cafe') ? 'cafe'
              : lo.includes('图书馆') || lo.includes('library') ? 'library'
              : lo.includes('屋顶') || lo.includes('roof') ? 'rooftop'
              : state.scene;
  const mood = lo.includes('想你') || lo.includes('喜欢') ? 'warm'
             : lo.includes('对不起') || lo.includes('难过') ? 'tender'
             : 'curious';
  return [
    '*Mira 静静听你说完，眼神里多了一丝柔软。*',
    '',
    '「听你这么说……我觉得今晚的雨下得刚刚好。」',
    '',
    JSON.stringify({
      mood,
      bond_delta: 2,
      scene,
      memory: text.length > 8 ? `你对 Mira 说：${text.slice(0, 60)}` : '',
      beat: 'Mira 感受到了你话语里的真诚。',
      chapter_title: state.chapterTitle,
      objective: '决定是温柔地逗她，还是说一句真心话。',
      choices: ['问她刚才注意到了什么', '靠近一点，陪她听雨', '邀请她去更安静的地方'],
    }),
  ].join('\n');
}

function applyAIReply(raw) {
  const parsed = parseStructuredReply(raw);
  const prevBond = state.bond;

  state.messages.push({ role: 'assistant', content: parsed.text || raw || 'Mira 温柔地微笑。' });
  if (parsed.mood) state.mood = parsed.mood;
  state.bond = clamp(state.bond + Number(parsed.bond_delta || 0), 0, 100);
  if (SCENES[parsed.scene]) state.scene = parsed.scene;
  if (parsed.chapter_title) state.chapterTitle = parsed.chapter_title;
  if (parsed.objective) state.objective = parsed.objective;
  if (parsed.beat && !state.beats.includes(parsed.beat)) {
    state.beats.push(parsed.beat);
    state.beats = state.beats.slice(-5);
  }
  if (parsed.memory && !state.memories.includes(parsed.memory)) {
    state.memories.push(parsed.memory);
    state.memories = state.memories.slice(-8);
  }
  state.choices = Array.isArray(parsed.choices) ? parsed.choices.slice(0, 4).map(String) : [];

  const delta = Math.round(state.bond - prevBond);
  if (delta !== 0) showBondBurst(delta);
}

function parseStructuredReply(raw) {
  const s = String(raw || '');
  const lastLine = s.split('\n').filter(l => l.trim()).pop() || '';
  let json = null;
  try { json = JSON.parse(lastLine); } catch { /* ignore */ }
  if (!json) {
    const m = s.match(/\{[\s\S]*\}(?=[^}]*$)/);
    if (m) try { json = JSON.parse(m[0]); } catch { /* ignore */ }
  }
  const text = json ? s.slice(0, s.lastIndexOf(lastLine.trim())).trim() : s.trim();
  return {
    text,
    mood: json?.mood || '',
    bond_delta: Number(json?.bond_delta || 0),
    scene: json?.scene || '',
    memory: String(json?.memory || ''),
    beat: String(json?.beat || ''),
    chapter_title: String(json?.chapter_title || ''),
    objective: String(json?.objective || ''),
    choices: Array.isArray(json?.choices) ? json.choices : [],
  };
}

// ── Memory panel ──────────────────────────────────────────────────────────

function openPanel()  { memoryPanel.classList.add('open'); overlay.classList.add('open'); }
function closePanel() { memoryPanel.classList.remove('open'); overlay.classList.remove('open'); }

memoryToggle.addEventListener('click', () => {
  memoryPanel.classList.contains('open') ? closePanel() : openPanel();
});
panelClose.addEventListener('click', closePanel);
overlay.addEventListener('click', closePanel);

// ── Reset ─────────────────────────────────────────────────────────────────

resetBtn.addEventListener('click', async () => {
  if (!confirm('重置故事进度？（Bond、记忆、对话记录会全部清除）')) return;
  state = cloneDefault();
  await saveState();
  closePanel();
  render();
});

// ── Image dialog ──────────────────────────────────────────────────────────

imageBtn.addEventListener('click', () => {
  imagePrompt.value = PORTRAIT_PROMPT;
  imageResult.textContent = '在 Knead 中运行时可直接生成立绘。';
  closePanel();
  imageDialog.showModal();
});

copyPromptBtn.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(imagePrompt.value);
    copyPromptBtn.textContent = '已复制！';
    setTimeout(() => { copyPromptBtn.textContent = '复制提示词'; }, 1600);
  } catch { /* ignore */ }
});

generatePortraitBtn.addEventListener('click', async () => {
  if (!window.NextAI?.chat?.send) {
    imageResult.textContent = '需要在 Knead 环境中运行才能生成图片。';
    return;
  }
  imageResult.textContent = '正在生成 Mira 立绘，请稍候…';
  try {
    const res = await window.NextAI.chat.send({
      action: 'generate_portrait',
      text: '请根据以下提示词生成 Mira 的立绘图片：\n\n' + PORTRAIT_PROMPT,
      context: { product_action: 'image_generate', save_as: 'assets/mira-portrait.png' },
    });
    const url = res?.image_url || res?.content_url;
    if (url) {
      portraitEl.src = url;
      state.portraitUrl = url;
      await saveState();
      imageResult.textContent = '立绘已生成并应用到游戏中 ♡';
    } else {
      imageResult.textContent = res?.content || '生成完成，但未返回图片 URL。';
    }
  } catch (e) {
    imageResult.textContent = '生成失败：' + (e?.message || '未知错误');
  }
});

// ── Boot ──────────────────────────────────────────────────────────────────

(async () => {
  await loadState();
  render();
})();
