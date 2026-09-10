const API = 'api.php';
let POSTS = [];
let SCRIPTS = [];

// ============ Tab 切换 ============
document.querySelectorAll('.tab').forEach(t => {
  t.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.view').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('view-' + t.dataset.view).classList.add('active');
    if (t.dataset.view === 'flow' && !document.getElementById('flow-content').innerHTML) loadFlow();
    if (t.dataset.view === 'code' && !SCRIPTS.length) loadScripts();
  });
});

// ============ 统计 ============
fetch(API + '?action=stats').then(r => r.json()).then(d => {
  const s = document.getElementById('stats');
  const by = d.by_track || {};
  s.innerHTML = `
    <span>总成品 <b>${d.total}</b></span>
    <span class="stat-tut">教程 <b>${by.tutorial || 0}</b></span>
    <span class="stat-ski">Skill <b>${by.skill || 0}</b></span>
    <span class="stat-ppt">PPT <b>${by.ppt || 0}</b></span>
    <span>配图 <b>${d.total_images}</b></span>
    <span>MD模板 <b>${d.total_md}</b></span>
  `;
  document.getElementById('count-posts').textContent = d.total;
});

// ============ 作品列表 ============
const trackEmoji = {tutorial: '📖', skill: '🛠️', ppt: '📊'};
const trackLabel = {tutorial: '教程', skill: 'Skill', ppt: 'PPT'};

async function loadPosts() {
  const r = await fetch(API + '?action=list');
  const d = await r.json();
  POSTS = d.posts || [];
  renderPosts();
}

function renderPosts() {
  const grid = document.getElementById('post-grid');
  const track = document.querySelector('.filter-btn.active')?.dataset.track || '';
  const q = document.getElementById('search').value.toLowerCase();
  const list = POSTS.filter(p => {
    if (track && p.track !== track) return false;
    if (q && !p.title.toLowerCase().includes(q) && !(p.tags || []).join(' ').toLowerCase().includes(q)) return false;
    return true;
  });
  document.getElementById('post-empty').style.display = list.length ? 'none' : 'block';
  grid.innerHTML = list.map(p => {
    const cover = p.cover_url || '';
    const coverHtml = cover
      ? `<img src="${cover}" loading="lazy" onerror="this.parentNode.innerHTML='<div class=&quot;thumb-fallback&quot;>${trackEmoji[p.track]||'📄'}</div>'">`
      : `<div class="thumb-fallback">${trackEmoji[p.track] || '📄'}</div>`;
    const badges = [];
    if (p.has_md) badges.push('<span class="badge-ico">MD</span>');
    if (p.has_skill_script) badges.push('<span class="badge-ico">CODE</span>');
    return `
      <div class="post-card track-${p.track}" onclick="loadDetail('${p.topic_id}')">
        <div class="thumb">
          ${coverHtml}
          <span class="track-tag">${trackLabel[p.track] || p.track}</span>
          <div class="badges">${badges.join('')}</div>
        </div>
        <div class="body">
          <div class="title">${esc(p.title)}</div>
          <div class="meta">
            <span class="chip">📷 ${p.image_count}</span>
            <span class="chip">📝 ${p.body_len}</span>
            ${(p.tags || []).slice(0, 2).map(t => `<span class="chip">${esc(t)}</span>`).join('')}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// ============ Filter ============
document.querySelectorAll('.filter-btn').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    renderPosts();
  });
});
document.getElementById('search').addEventListener('input', renderPosts);

// ============ 详情 ============
async function loadDetail(id) {
  const r = await fetch(API + `?action=post&id=${encodeURIComponent(id)}`);
  const d = await r.json();
  const p = d.post;
  if (!p) return;
  const modal = document.getElementById('detail-modal');
  const images = (p.image_urls || []).map((u, i) => `
    <div class="img-wrap">
      <img src="${u}" loading="lazy" onclick="window.open('${u}')">
      <span class="img-label">图 ${i + 1}</span>
    </div>
  `).join('');

  let extra = '';
  // Skill 代码
  if (p.skill_script_content) {
    extra += `
      <div class="detail-section">
        <h3>Skill 脚本</h3>
        <pre class="code-block"><span class="lang">${p.skill_script_path.split('/').pop()}</span>${esc(p.skill_script_content)}</pre>
      </div>
      <div class="detail-section">
        <h3>演示</h3>
        <div class="demo-row">
          <div class="demo-box"><h4>输入</h4><pre>${esc(p.demo_input || '')}</pre></div>
          <div class="demo-box"><h4>输出</h4><pre>${esc(p.demo_output || '')}</pre></div>
        </div>
      </div>
    `;
  }
  // Markdown 完整文案模板
  if (p.md_content) {
    extra += `
      <div class="detail-section">
        <h3>完整文案模板 (Markdown)</h3>
        <div class="md-actions">
          ${p.md_download_url ? `<a href="${p.md_download_url}" class="md-download">⬇ 下载 .md 文件</a>` : ''}
          <button class="md-toggle active" onclick="toggleMdView(this,'rendered')">排版预览</button>
          <button class="md-toggle" onclick="toggleMdView(this,'raw')">Markdown 原文</button>
        </div>
        <div class="md-doc md-view-rendered">${renderMarkdown(p.md_content)}</div>
        <pre class="md-raw md-view-raw" style="display:none">${esc(p.md_content)}</pre>
      </div>
    `;
  }

  modal.innerHTML = `
    <div class="detail-header">
      <button class="detail-close" onclick="closeDetail()">×</button>
      <div class="detail-title">${esc(p.title)}</div>
      <div class="detail-tags">
        ${(p.tags || []).map(t => `<span class="tag">#${esc(t)}</span>`).join('')}
      </div>
    </div>
    <div class="detail-body">
      <div class="detail-section">
        <h3>正文</h3>
        <div class="detail-body-text">${esc(p.body)}</div>
      </div>
      ${images ? `<div class="detail-section"><h3>配图 (${p.image_urls.length})</h3><div class="detail-images">${images}</div></div>` : ''}
      ${extra}
    </div>
  `;
  document.getElementById('detail-overlay').classList.add('show');
}

function closeDetail() {
  document.getElementById('detail-overlay').classList.remove('show');
}
document.getElementById('detail-overlay').addEventListener('click', e => {
  if (e.target.id === 'detail-overlay') closeDetail();
});

// ============ 流程 ============
async function loadFlow() {
  const r = await fetch(API + '?action=flow');
  const d = await r.json();
  const c = document.getElementById('flow-content');
  const steps = d.steps || [];
  c.innerHTML = steps.map((s, i) => `
    <div class="flow-step">
      <div class="flow-num">${s.id}</div>
      <div class="flow-step-content">
        <h3>${s.name}</h3>
        <div>脚本 <span class="script">${s.script || ''}</span></div>
        <div class="meta-row">
          <span>输入: <b>${s.input || ''}</b></span>
          <span>输出: <b>${s.output || ''}</b></span>
        </div>
        <div class="stats-row">
          ${Object.entries(s.stats || {}).map(([k, v]) => `<span class="stat-pill">${k}: ${v}</span>`).join('')}
        </div>
        <div class="purpose">${esc(s.purpose || '')}</div>
      </div>
    </div>
    ${i < steps.length - 1 ? '<div class="flow-arrow">↓</div>' : ''}
  `).join('') + `
    <div style="margin-top:24px;padding:16px;background:#fef3c7;border-radius:8px;color:#92400e;font-size:13px">
      <b>反馈闭环:</b> ${esc(d.feedback_loop || '')}
    </div>
  `;
}

// ============ 源代码 ============
async function loadScripts() {
  const r = await fetch(API + '?action=scripts');
  const d = await r.json();
  SCRIPTS = d.scripts || [];
  const list = document.getElementById('script-list');
  list.innerHTML = SCRIPTS.map((s, i) => `
    <div class="script-item ${i === 0 ? 'active' : ''}" onclick="loadScript('${s.name}', this)">
      ${s.name}
      <span class="size">${(s.size / 1024).toFixed(1)}K</span>
    </div>
  `).join('');
  if (SCRIPTS[0]) loadScript(SCRIPTS[0].name);
}

async function loadScript(name, el) {
  document.querySelectorAll('.script-item').forEach(x => x.classList.remove('active'));
  if (el) el.classList.add('active');
  const r = await fetch(API + `?action=script&name=${encodeURIComponent(name)}`);
  const d = await r.json();
  document.getElementById('code-file').textContent = name + ' · ' + (d.size || 0) + ' bytes';
  document.getElementById('code-content').textContent = d.content || '';
}

// ============ Markdown 渲染(轻量,支持标题/段落/引用/嵌套列表/分割线/行内格式) ============
function mdInline(s) {
  s = s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}

function mdBuildList(items) {
  // items: [{depth, type, text}] 构建嵌套树并渲染
  const root = { depth: -1, children: [] };
  const stack = [root];
  for (const it of items) {
    while (stack.length > 1 && stack[stack.length - 1].depth >= it.depth) stack.pop();
    const node = { depth: it.depth, type: it.type, text: it.text, children: [] };
    stack[stack.length - 1].children.push(node);
    stack.push(node);
  }
  const renderNodes = (nodes) => {
    let out = '';
    let i = 0;
    while (i < nodes.length) {
      const type = nodes[i].type;
      let j = i;
      while (j < nodes.length && nodes[j].type === type) j++;
      out += `<${type}>`;
      for (let k = i; k < j; k++) {
        out += `<li>${mdInline(nodes[k].text)}${nodes[k].children.length ? renderNodes(nodes[k].children) : ''}</li>`;
      }
      out += `</${type}>`;
      i = j;
    }
    return out;
  };
  return renderNodes(root.children);
}

function renderMarkdown(src) {
  if (!src) return '';
  const lines = src.replace(/\r\n/g, '\n').split('\n');
  let html = '';
  let para = [];
  let quote = [];
  let listItems = null;

  const flushPara = () => {
    if (para.length) { html += '<p>' + mdInline(para.join(' ')) + '</p>'; para = []; }
  };
  const flushQuote = () => {
    if (quote.length) {
      html += '<blockquote>' + quote.map(l => '<p>' + mdInline(l) + '</p>').join('') + '</blockquote>';
      quote = [];
    }
  };
  const flushList = () => {
    if (listItems) { html += mdBuildList(listItems); listItems = null; }
  };
  const flushAll = () => { flushPara(); flushQuote(); flushList(); };

  for (let raw of lines) {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) { flushAll(); continue; }
    if (/^-{3,}$/.test(line.trim())) {
      flushAll(); html += '<hr>'; continue;
    }
    const hm = line.match(/^(#{1,4})\s+(.*)$/);
    if (hm) {
      flushAll();
      html += `<h${hm[1].length}>${mdInline(hm[2])}</h${hm[1].length}>`;
      continue;
    }
    const qm = line.match(/^>\s?(.*)$/);
    if (qm) { flushPara(); flushList(); quote.push(qm[1]); continue; }
    flushQuote();
    const lm = line.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
    if (lm) {
      flushPara();
      const indent = lm[1].replace(/\t/g, '  ').length;
      const depth = Math.floor(indent / 2);
      const type = /\d+\./.test(lm[2]) ? 'ol' : 'ul';
      if (!listItems) listItems = [];
      listItems.push({ depth, type, text: lm[3] });
      continue;
    }
    flushList();
    para.push(line.trim());
  }
  flushAll();
  return html;
}

function toggleMdView(btn, view) {
  const section = btn.closest('.detail-section');
  section.querySelectorAll('.md-toggle').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  section.querySelector('.md-view-rendered').style.display = view === 'rendered' ? '' : 'none';
  section.querySelector('.md-view-raw').style.display = view === 'raw' ? '' : 'none';
}

// ============ 工具 ============
function esc(s) {
  return (s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

// 初始化
loadPosts();
