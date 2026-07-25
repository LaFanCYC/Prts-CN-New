const category = document.querySelector('[data-category]');
const condition = document.querySelector('[data-condition]');
const mode = document.querySelector('[data-mode]');
if (category && condition && mode) {
  const sync = () => {
    const skill = category.value === '技能服务';
    [...condition.options].forEach(o => o.hidden = skill ? o.value !== '不适用' : o.value === '不适用');
    [...mode.options].forEach(o => o.hidden = skill ? !['free_help','skill_exchange'].includes(o.value) : ['free_help','skill_exchange'].includes(o.value));
    condition.value = skill ? '不适用' : (condition.value === '不适用' ? '全新' : condition.value);
    if (mode.selectedOptions[0]?.hidden) mode.value = skill ? 'free_help' : 'borrow';
  };
  category.addEventListener('change', sync); sync();
}

const sidebarToggle = document.querySelector('[data-toggle-sidebar]');
const sidebar = document.querySelector('[data-sidebar]');
if (sidebarToggle && sidebar) {
  sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    sidebarToggle.setAttribute('aria-expanded', sidebar.classList.contains('open'));
  });
}

document.querySelectorAll('[data-close-flash]').forEach(button => {
  button.addEventListener('click', () => button.parentElement.remove());
});

document.querySelectorAll('[data-dropdown-trigger]').forEach(trigger => {
  trigger.addEventListener('click', () => trigger.closest('[data-dropdown]').classList.toggle('open'));
});

document.addEventListener('click', event => {
  if (!event.target.closest('[data-dropdown]')) {
    document.querySelectorAll('[data-dropdown].open').forEach(dropdown => dropdown.classList.remove('open'));
  }
});

// Flask 表单通常重定向回当前页；保留阅读位置，避免交互后跳回页首。
if ('scrollRestoration' in history) {
  history.scrollRestoration = 'manual';
}
const scrollKey = `campus-scroll:${location.pathname}`;
const savedScroll = sessionStorage.getItem(scrollKey);
if (!location.hash && savedScroll !== null) {
  requestAnimationFrame(() => window.scrollTo(0, Number(savedScroll)));
}
window.addEventListener('pagehide', () => {
  sessionStorage.setItem(scrollKey, String(window.scrollY));
});
