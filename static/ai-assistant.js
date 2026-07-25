(() => {
  const root = document.querySelector('[data-ai-assistant]');
  if (!root) return;
  root.innerHTML = '<section class="ai-assistant-panel" aria-label="AI 搜索助手"><button class="ai-assistant-close" type="button" aria-label="关闭 AI 搜索助手">×</button><h2>AI 搜索助手</h2><p>描述你想找的资源、帖子或失物信息。</p><form class="ai-assistant-form"><input name="query" maxlength="100" placeholder="例如：想找 Python 教材" required><button class="btn btn-primary">搜索</button></form><div class="ai-result-list" aria-live="polite"></div></section><button class="ai-assistant-toggle" type="button" aria-label="打开 AI 搜索助手" aria-expanded="false">✦</button>';
  const toggle = root.querySelector('.ai-assistant-toggle');
  const form = root.querySelector('form');
  const list = root.querySelector('.ai-result-list');
  const input = form.elements.query;
  const close = () => { root.classList.remove('open'); toggle.setAttribute('aria-expanded', 'false'); };
  const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  toggle.addEventListener('click', () => {
    const open = root.classList.toggle('open');
    toggle.setAttribute('aria-expanded', open);
    if (open) input.focus();
  });
  root.querySelector('.ai-assistant-close').addEventListener('click', close);
  document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
  document.addEventListener('click', event => { if (root.classList.contains('open') && !root.contains(event.target)) close(); });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const query = input.value.trim();
    if (!query) return;
    list.innerHTML = '<div class="ai-loading"></div><div class="ai-loading"></div>';
    try {
      const response = await fetch('/api/ai/search', {
        method: 'POST',
        headers: {'Content-Type':'application/json', 'X-CSRF-Token': root.dataset.csrfToken},
        body: JSON.stringify({query}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.description || '搜索失败，请稍后重试。');
      list.innerHTML = data.results.length ? data.results.map(result => '<a class="ai-result" href="' + escapeHtml(result.url) + '"><span class="ai-result-type">' + escapeHtml(result.type) + '</span><h3>' + escapeHtml(result.title) + '</h3><p>' + escapeHtml(result.reason || result.summary) + '</p></a>').join('') : '<p class="ai-empty">没有找到相关内容。</p>';
    } catch (error) {
      list.innerHTML = '<p class="ai-empty">' + escapeHtml(error.message) + '</p>';
    }
  });
})();
