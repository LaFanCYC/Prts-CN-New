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
