const STORAGE_KEY = 'ai_otome_mira_v1';

const SCENES = {
  rain: {
    label: 'Rainy station',
    line: 'Rain taps the glass roof. She notices you before you speak.',
    color: '#6d8fbd',
  },
  cafe: {
    label: 'Late cafe',
    line: 'A small table, warm lights, and two cups cooling too slowly.',
    color: '#d1846f',
  },
  library: {
    label: 'Moonlit library',
    line: 'Dust glows in the moonlight. Mira lowers her voice without meaning to.',
    color: '#8c75bb',
  },
  rooftop: {
    label: 'Quiet rooftop',
    line: 'The city hums below. The night gives both of you room to be honest.',
    color: '#74a88c',
  },
};

const DEFAULT_STATE = {
  scene: 'rain',
  mood: 'curious',
  bond: 18,
  chapter: 'Chapter 1',
  chapterTitle: 'A rain-soaked promise',
  objective: 'Make Mira feel that this meeting was not an accident.',
  portraitUrl: '',
  beats: [
    'Mira waited at the station longer than she admits.',
    'The rain gives both of you an excuse to stay close.',
  ],
  memories: [
    'You met Mira on a rainy evening.',
    'She likes when you answer honestly.',
  ],
  messages: [
    {
      role: 'assistant',
      content: '*Mira folds her umbrella and smiles like she was hoping you would arrive.*\n\n"You came. I was wondering whether the rain would keep you away."',
    },
  ],
  choices: [
    'I wanted to see you.',
    'The rain makes this feel secret.',
    'Were you waiting for me?',
  ],
};

let state = structuredClone(DEFAULT_STATE);
let sending = false;

const app = document.querySelector('.otome-app');
const messagesEl = document.getElementById('messages');
const choicesEl = document.getElementById('choices');
const inputEl = document.getElementById('input');
const composerEl = document.getElementById('composer');
const sendBtn = document.getElementById('sendBtn');
const moodLabel = document.getElementById('moodLabel');
const bondValue = document.getElementById('bondValue');
const bondBar = document.getElementById('bondBar');
const memoryList = document.getElementById('memoryList');
const sceneChip = document.getElementById('sceneChip');
const sceneLine = document.getElementById('sceneLine');
const sceneList = document.getElementById('sceneList');
const beatList = document.getElementById('beatList');
const chapterLabel = document.getElementById('chapterLabel');
const chapterTitle = document.getElementById('chapterTitle');
const objectiveText = document.getElementById('objectiveText');
const bondBurst = document.getElementById('bondBurst');
const resetBtn = document.getElementById('resetBtn');
const imageBtn = document.getElementById('imageBtn');
const imageDialog = document.getElementById('imageDialog');
const imagePrompt = document.getElementById('imagePrompt');
const copyPromptBtn = document.getElementById('copyPromptBtn');
const generatePortraitBtn = document.getElementById('generatePortraitBtn');
const imageResult = document.getElementById('imageResult');
const portraitEls = Array.from(document.querySelectorAll('.portrait, .portrait-small'));
// Mood → portrait file. Add more entries as new assets are added.
// Each key is a lowercase English mood word the AI might return.
const PORTRAITS = {
  default:    'assets/mira-happy.png',
  // ── happy / warm family
  happy:      'assets/mira-happy.png',
  warm:       'assets/mira-happy.png',
  joyful:     'assets/mira-happy.png',
  excited:    'assets/mira-happy.png',
  pleased:    'assets/mira-happy.png',
  fond:       'assets/mira-happy.png',
  relieved:   'assets/mira-happy.png',
  // ── curious / neutral
  curious:    'assets/mira-happy.png',
  neutral:    'assets/mira-happy.png',
  calm:       'assets/mira-happy.png',
  attentive:  'assets/mira-happy.png',
  pensive:    'assets/mira-happy.png',
  // ── shy / tender family
  tender:     'assets/mira-shy.png',
  shy:        'assets/mira-shy.png',
  flushed:    'assets/mira-shy.png',
  bashful:    'assets/mira-shy.png',
  embarrassed:'assets/mira-shy.png',
  touched:    'assets/mira-shy.png',
  moved:      'assets/mira-shy.png',
  // ── sad / hurt family
  sad:        'assets/mira-sad.png',
  hurt:       'assets/mira-sad.png',
  lonely:     'assets/mira-sad.png',
  wistful:    'assets/mira-sad.png',
  melancholy: 'assets/mira-sad.png',
  // ── serious / focused family
  serious:    'assets/mira-serious.png',
  focused:    'assets/mira-serious.png',
  determined: 'assets/mira-serious.png',
  worried:    'assets/mira-serious.png',
  conflicted: 'assets/mira-serious.png',
  // ── surprised / alert family
  surprised:  'assets/mira-surprise.png',
  surprise:   'assets/mira-surprise.png',
  startled:   'assets/mira-surprise.png',
  stunned:    'assets/mira-surprise.png',
  // ── blink / amused
  blink:      'assets/mira-blink.png',
  amused:     'assets/mira-blink.png',
  teasing:    'assets/mira-blink.png',
  playful:    'assets/mira-blink.png',
};

// Mood → Chinese display label shown on the mood-card
const MOOD_LABELS = {
  happy:      '😊 开心',
  warm:       '🌿 温柔',
  joyful:     '✨ 雀跃',
  excited:    '🌟 期待',
  pleased:    '😌 满足',
  fond:       '💚 喜欢',
  relieved:   '😮‍💨 安心',
  curious:    '🍃 好奇',
  neutral:    '🌸 平静',
  calm:       '🌿 平静',
  attentive:  '👀 专注',
  pensive:    '💭 若有所思',
  tender:     '💚 心动',
  shy:        '🌱 害羞',
  flushed:    '🍃 脸红了',
  bashful:    '🌱 有点不好意思',
  embarrassed:'😳 慌了',
  touched:    '🥹 感动',
  moved:      '💚 触动',
  sad:        '🌧 有点难过',
  hurt:       '💔 受伤了',
  lonely:     '🌑 有点孤单',
  wistful:    '🍂 惆怅',
  melancholy: '🌧 伤感',
  serious:    '🌿 认真',
  focused:    '🎯 专注',
  determined: '💪 下定决心',
  worried:    '😟 担心',
  conflicted: '🌀 纠结',
  surprised:  '😲 吃惊',
  startled:   '！ 被吓到了',
  stunned:    '😳 呆住了',
  blink:      '😏 有点坏坏的',
  amused:     '😄 被逗笑了',
  teasing:    '😉 在捉弄你',
  playful:    '🌿 活泼',
};

function cloneDefaultState() {
  return JSON.parse(JSON.stringify(DEFAULT_STATE));
}

async function loadState() {
  try {
    const useBridgeState = window.NextAI?.state && window.parent !== window;
    const saved = useBridgeState
      ? await window.NextAI.state.get(STORAGE_KEY, null)
      : JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    if (saved && Array.isArray(saved.messages)) state = normalizeState(saved);
  } catch {
    state = cloneDefaultState();
  }
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
    chapterTitle: String(raw.chapterTitle || 'A rain-soaked promise').slice(0, 80),
    objective: String(raw.objective || 'Make Mira feel that this meeting was not an accident.').slice(0, 160),
    portraitUrl: normalizePortraitUrl(raw.portraitUrl),
    beats: Array.isArray(raw.beats) ? raw.beats.slice(-5).map(String) : cloneDefaultState().beats,
    memories: Array.isArray(raw.memories) ? raw.memories.slice(-8).map(String) : [],
    messages: Array.isArray(raw.messages)
      ? raw.messages.filter(item => item && item.content).slice(-40).map(item => ({
          role: item.role === 'user' ? 'user' : 'assistant',
          content: String(item.content),
        }))
      : cloneDefaultState().messages,
    choices: Array.isArray(raw.choices) ? raw.choices.slice(0, 4).map(String) : [],
  };
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function normalizePortraitUrl(value) {
  const url = String(value || '').trim();
  return url && !url.endsWith('assets/mira.svg') ? url : '';
}

function portraitForMood(mood) {
  const key = String(mood || '').toLowerCase().trim();
  if (PORTRAITS[key]) return PORTRAITS[key];
  // Fuzzy: find first portrait key that appears inside the mood string
  const fuzzy = Object.keys(PORTRAITS).find(k => k !== 'default' && key.includes(k));
  return fuzzy ? PORTRAITS[fuzzy] : PORTRAITS.default;
}

function render() {
  const scene = SCENES[state.scene] || SCENES.rain;
  app.dataset.mood = state.mood.toLowerCase();
  app.dataset.scene = state.scene;
  app.style.setProperty('--scene-color', scene.color);
  const moodKey = String(state.mood || '').toLowerCase().trim();
  moodLabel.textContent = MOOD_LABELS[moodKey] || titleCase(state.mood);
  bondValue.textContent = `${Math.round(state.bond)}%`;
  bondBar.style.width = `${clamp(state.bond, 0, 100)}%`;
  sceneChip.textContent = scene.label;
  sceneLine.textContent = scene.line;
  chapterLabel.textContent = state.chapter;
  chapterTitle.textContent = state.chapterTitle;
  objectiveText.textContent = state.objective;
  const portraitUrl = state.portraitUrl || portraitForMood(state.mood);
  portraitEls.forEach(img => { img.src = portraitUrl; });

  renderMessages();
  renderChoices();
  renderMemories();
  renderScenes();
  renderBeats();
}

function renderMessages() {
  messagesEl.innerHTML = '';
  state.messages.forEach(message => messagesEl.appendChild(messageNode(message)));
  requestAnimationFrame(() => {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  });
}

function messageNode(message) {
  const node = document.createElement('article');
  node.className = `message ${message.role}`;
  const label = document.createElement('span');
  label.className = 'speaker';
  label.textContent = message.role === 'user' ? 'You' : 'Mira';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  parseSegments(message.content).forEach(segment => {
    const line = document.createElement('p');
    line.className = segment.type;
    line.textContent = segment.text;
    bubble.appendChild(line);
  });
  node.append(label, bubble);
  return node;
}

function parseSegments(text) {
  const parts = String(text || '').split(/(\*[^*]+\*)/g).filter(part => part.trim());
  const segments = [];
  parts.forEach(part => {
    if (part.startsWith('*') && part.endsWith('*')) {
      segments.push({ type: 'action', text: part.slice(1, -1).trim() });
      return;
    }
    part.split('\n').filter(line => line.trim()).forEach(line => {
      segments.push({ type: 'speech', text: line.trim() });
    });
  });
  return segments.length ? segments : [{ type: 'speech', text }];
}

function renderChoices() {
  choicesEl.innerHTML = '';
  state.choices.forEach((choice, index) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    const tag = document.createElement('span');
    tag.className = 'choice-tag';
    tag.textContent = ['Heart', 'Courage', 'Trust', 'Spark'][index] || 'Choice';
    const label = document.createElement('strong');
    label.textContent = choice;
    btn.append(tag, label);
    btn.addEventListener('click', () => send(choice));
    choicesEl.appendChild(btn);
  });
}

function renderBeats() {
  beatList.innerHTML = '';
  const beats = state.beats.length ? state.beats : ['The story has just begun.'];
  beats.slice(-5).forEach((beat, index) => {
    const item = document.createElement('li');
    item.innerHTML = `<span>${String(index + 1).padStart(2, '0')}</span><p></p>`;
    item.querySelector('p').textContent = beat;
    beatList.appendChild(item);
  });
}

function renderMemories() {
  memoryList.innerHTML = '';
  const memories = state.memories.length ? state.memories : ['Mira is still learning what matters to you.'];
  memories.slice(-6).forEach(memory => {
    const item = document.createElement('li');
    item.textContent = memory;
    memoryList.appendChild(item);
  });
}

function renderScenes() {
  sceneList.innerHTML = '';
  Object.entries(SCENES).forEach(([id, scene]) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = id === state.scene ? 'active' : '';
    btn.textContent = scene.label;
    btn.addEventListener('click', async () => {
      state.scene = id;
      state.messages.push({
        role: 'assistant',
        content: `*The moment shifts into ${scene.label.toLowerCase()}.*`,
      });
      await saveState();
      render();
    });
    sceneList.appendChild(btn);
  });
}

composerEl.addEventListener('submit', event => {
  event.preventDefault();
  send(inputEl.value);
});

inputEl.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    send(inputEl.value);
  }
});

inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 132)}px`;
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
  render();
  await saveState();

  const typing = { role: 'assistant', content: '*Mira is thinking about what you said...*' };
  state.messages.push(typing);
  render();

  try {
    const reply = await callMira(text);
    state.messages.pop();
    applyAIReply(reply);
  } catch (error) {
    state.messages.pop();
    state.messages.push({
      role: 'assistant',
      content: '*Mira glances down at her phone, then back to you with an apologetic smile.*\n\n"I lost the thread for a second. Tell me again?"',
    });
    state.choices = ['I will say it again.', 'Let us slow down.', 'Can you stay with me?'];
  } finally {
    sending = false;
    sendBtn.disabled = false;
    await saveState();
    render();
  }
}

async function callMira(text) {
  if (!window.NextAI?.chat?.send || window.parent === window) {
    return localMiraReply(text);
  }
  const response = await window.NextAI.chat.send({
    action: 'otome_companion_turn',
    text,
    context: {
      mode: 'ai_otome_companion',
      product: 'AI Otome',
      character: {
        name: 'Mira',
        premise: 'A warm, perceptive AI companion in a gentle otome story. She is emotionally present, playful when safe, and never explicit.',
      },
      state: {
        scene: SCENES[state.scene].label,
        mood: state.mood,
        bond: state.bond,
        chapter: state.chapter,
        objective: state.objective,
        beats: state.beats,
        memories: state.memories,
      },
      recent_messages: state.messages.slice(-12),
      response_contract: {
        text: 'Natural Chinese dialogue. Include short action lines in *asterisks*. Keep it emotionally vivid but concise.',
        json_last_line: {
          mood: 'one English mood word from: happy, warm, joyful, excited, pleased, fond, relieved, curious, calm, attentive, pensive, tender, shy, flushed, bashful, embarrassed, touched, moved, sad, hurt, lonely, wistful, melancholy, serious, focused, determined, worried, conflicted, surprised, startled, stunned, blink, amused, teasing, playful',
          bond_delta: 'number from -3 to 6',
          scene: 'rain | cafe | library | rooftop',
          memory: 'one durable memory or empty string',
          beat: 'one short story beat that just happened',
          chapter_title: 'current chapter title if it should change',
          objective: 'next emotional objective for the player',
          choices: '2 or 3 Chinese next-step choices',
        },
        required_format: 'Put a single JSON object on the last line after the prose. No markdown fence.',
      },
    },
  });
  return response?.content || '';
}

function localMiraReply(text) {
  const lower = String(text || '').toLowerCase();
  const scene = lower.includes('coffee') || lower.includes('cafe') || lower.includes('tea')
    ? 'cafe'
    : lower.includes('book') || lower.includes('library')
    ? 'library'
    : lower.includes('roof') || lower.includes('night')
    ? 'rooftop'
    : state.scene;
  const mood = lower.includes('miss') || lower.includes('like') || lower.includes('see you')
    ? 'warm'
    : lower.includes('sorry') || lower.includes('sad')
    ? 'tender'
    : 'curious';
  return [
    '*Mira listens closely, her expression softening before she answers.*',
    '',
    '"I like when you say it in your own words. It makes this feel less like a script, and more like us."',
    '',
    JSON.stringify({
      mood,
      bond_delta: 2,
      scene,
      memory: text.length > 10 ? `You told Mira: ${text.slice(0, 72)}` : '',
      beat: 'Mira reacted to your honesty instead of treating it like a normal chat message.',
      chapter_title: state.chapterTitle,
      objective: 'Decide whether to tease her gently or say something sincere.',
      choices: ['问她刚才注意到了什么', '靠近一点，陪她听雨', '邀请她去更安静的地方'],
    }),
  ].join('\n');
}

function applyAIReply(raw) {
  const parsed = parseStructuredReply(raw);
  const prevBond = state.bond;
  state.messages.push({ role: 'assistant', content: parsed.text || raw || 'Mira smiles softly.' });
  state.mood = parsed.mood || state.mood;
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
  if (state.bond !== prevBond) {
    showBondBurst(state.bond - prevBond);
  }
  state.choices = Array.isArray(parsed.choices) && parsed.choices.length
    ? parsed.choices.slice(0, 3)
    : ['陪她多待一会儿', '问她现在的心情', '换一个更适合说真话的场景'];
}

function parseStructuredReply(raw) {
  const text = String(raw || '').trim();
  const match = text.match(/\{[\s\S]*\}\s*$/);
  if (!match) return { text, choices: [] };
  try {
    const data = JSON.parse(match[0]);
    return {
      text: text.slice(0, match.index).trim(),
      mood: typeof data.mood === 'string' ? data.mood.slice(0, 32) : '',
      bond_delta: Number(data.bond_delta || 0),
      scene: typeof data.scene === 'string' ? data.scene : '',
      memory: typeof data.memory === 'string' ? data.memory.trim().slice(0, 140) : '',
      beat: typeof data.beat === 'string' ? data.beat.trim().slice(0, 140) : '',
      chapter_title: typeof data.chapter_title === 'string' ? data.chapter_title.trim().slice(0, 80) : '',
      objective: typeof data.objective === 'string' ? data.objective.trim().slice(0, 160) : '',
      choices: Array.isArray(data.choices) ? data.choices.map(String) : [],
    };
  } catch {
    return { text, choices: [] };
  }
}

function showBondBurst(delta) {
  const value = Number(delta);
  if (!value || !bondBurst) return;
  bondBurst.textContent = value > 0 ? `Bond +${value}` : `Bond ${value}`;
  bondBurst.classList.remove('show');
  void bondBurst.offsetWidth;
  bondBurst.classList.add('show');
}

resetBtn.addEventListener('click', async () => {
  state = cloneDefaultState();
  await saveState();
  render();
});

imageBtn.addEventListener('click', () => {
  imagePrompt.value = buildPortraitPrompt();
  imageResult.textContent = 'Uses GPT Image 2 when opened inside Knead.';
  imageResult.className = 'image-result';
  imageDialog.showModal();
});

function buildPortraitPrompt() {
  return [
    'Create a polished otome game character portrait of Mira.',
    'Mira is a visually memorable AI otome heroine with soft expressive eyes, shoulder-length dark rose-brown hair, tiny rain-drop hairpin, and a warm modern romantic outfit.',
    'Make her cute, emotionally attractive, and instantly recognizable as the main companion character of a premium AI romance game.',
    'Mood: emotionally present, curious, slightly shy, comforting, with subtle playful confidence.',
    `Current scene: ${SCENES[state.scene].label}.`,
    'Composition: half-body character art, clean visual novel asset, generous padding, simple atmospheric background, no text, no watermark.',
    'Style: modern high-quality anime otome game key art, refined lighting, appealing but not explicit, suitable for an in-app character sprite.',
  ].join('\n');
}

generatePortraitBtn.addEventListener('click', generatePortrait);

async function generatePortrait() {
  if (!window.NextAI?.chat?.send || window.parent === window) {
    imageResult.className = 'image-result error';
    imageResult.textContent = 'Open this product inside Knead to generate with GPT Image 2. Direct preview can only copy the prompt.';
    return;
  }

  generatePortraitBtn.disabled = true;
  imageResult.className = 'image-result loading';
  imageResult.textContent = 'Generating Mira with GPT Image 2...';

  try {
    const res = await window.NextAI.chat.send({
      action: 'image_generate',
      text: imagePrompt.value || buildPortraitPrompt(),
      context: {
        mode: 'otome_character_image_generation',
        tool: 'image_generate',
        provider: 'image two',
        model: 'fal-ai/gpt-image-2',
        preferred_image_model: 'fal-ai/gpt-image-2',
        aspect_ratio: 'portrait',
        character: { name: 'Mira', product: 'AI Otome' },
      },
    });
    const content = res?.content || '';
    const raw = res?.raw || {};
    const imageUrl = raw.image || raw.url || raw.media || content.match(/https?:\/\/\S+/)?.[0];
    if (!imageUrl) {
      throw new Error('No image URL returned');
    }
    state.portraitUrl = imageUrl;
    await saveState();
    render();
    imageResult.className = 'image-result';
    imageResult.innerHTML = `<img src="${imageUrl}" alt="Generated Mira portrait"><p>Mira portrait updated.</p>`;
  } catch (error) {
    imageResult.className = 'image-result error';
    imageResult.textContent = 'Image generation failed. Copy the prompt and try again from the host chat.';
  } finally {
    generatePortraitBtn.disabled = false;
  }
}

copyPromptBtn.addEventListener('click', async () => {
  await navigator.clipboard?.writeText(imagePrompt.value);
  copyPromptBtn.textContent = 'Copied';
  setTimeout(() => { copyPromptBtn.textContent = 'Copy prompt'; }, 1200);
});

function titleCase(value) {
  const text = String(value || '');
  return text ? text[0].toUpperCase() + text.slice(1) : 'Curious';
}

loadState().then(() => {
  render();
});
