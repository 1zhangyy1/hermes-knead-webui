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
const resetBtn = document.getElementById('resetBtn');
const imageBtn = document.getElementById('imageBtn');
const imageDialog = document.getElementById('imageDialog');
const imagePrompt = document.getElementById('imagePrompt');
const copyPromptBtn = document.getElementById('copyPromptBtn');

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

function render() {
  const scene = SCENES[state.scene] || SCENES.rain;
  app.dataset.mood = state.mood.toLowerCase();
  app.dataset.scene = state.scene;
  app.style.setProperty('--scene-color', scene.color);
  moodLabel.textContent = titleCase(state.mood);
  bondValue.textContent = `${Math.round(state.bond)}%`;
  bondBar.style.width = `${clamp(state.bond, 0, 100)}%`;
  sceneChip.textContent = scene.label;
  sceneLine.textContent = scene.line;

  renderMessages();
  renderChoices();
  renderMemories();
  renderScenes();
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
  state.choices.forEach(choice => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = choice;
    btn.addEventListener('click', () => send(choice));
    choicesEl.appendChild(btn);
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
        memories: state.memories,
      },
      recent_messages: state.messages.slice(-12),
      response_contract: {
        text: 'Natural Chinese dialogue. Include short action lines in *asterisks*. Keep it emotionally vivid but concise.',
        json_last_line: {
          mood: 'one short English mood word',
          bond_delta: 'number from -3 to 6',
          scene: 'rain | cafe | library | rooftop',
          memory: 'one durable memory or empty string',
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
      choices: ['Ask what she noticed about you.', 'Move a little closer.', 'Invite her somewhere quieter.'],
    }),
  ].join('\n');
}

function applyAIReply(raw) {
  const parsed = parseStructuredReply(raw);
  state.messages.push({ role: 'assistant', content: parsed.text || raw || 'Mira smiles softly.' });
  state.mood = parsed.mood || state.mood;
  state.bond = clamp(state.bond + Number(parsed.bond_delta || 0), 0, 100);
  if (SCENES[parsed.scene]) state.scene = parsed.scene;
  if (parsed.memory && !state.memories.includes(parsed.memory)) {
    state.memories.push(parsed.memory);
    state.memories = state.memories.slice(-8);
  }
  state.choices = Array.isArray(parsed.choices) && parsed.choices.length
    ? parsed.choices.slice(0, 3)
    : ['Stay with her a little longer.', 'Ask what she is feeling.', 'Change the scene.'];
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
      choices: Array.isArray(data.choices) ? data.choices.map(String) : [],
    };
  } catch {
    return { text, choices: [] };
  }
}

resetBtn.addEventListener('click', async () => {
  state = cloneDefaultState();
  await saveState();
  render();
});

imageBtn.addEventListener('click', () => {
  imagePrompt.value = [
    'Create a polished otome game character portrait of Mira.',
    'Mira is a warm, perceptive young woman with soft expressive eyes, shoulder-length dark rose-brown hair, and a gentle modern romantic style.',
    'Mood: emotionally present, curious, slightly shy, comforting.',
    `Current scene: ${SCENES[state.scene].label}.`,
    'Composition: half-body character art, clean visual novel asset, subtle transparent or simple atmospheric background, no text, no watermark.',
    'Style: modern high-quality anime otome game key art, refined lighting, appealing but not explicit.',
  ].join('\n');
  imageDialog.showModal();
});

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
