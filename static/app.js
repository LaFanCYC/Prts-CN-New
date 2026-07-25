(function(){
'use strict';
/* Resource form category/mode sync */
var cat = document.querySelector('[data-category]');
var cond = document.querySelector('[data-condition]');
var mod = document.querySelector('[data-mode]');
if (cat && cond && mod) {
  var sync = function(){
    var sk = cat.value === '技能服务';
    [].forEach.call(cond.options, function(o){ o.hidden = sk ? o.value !== '不适用' : o.value === '不适用'; });
    [].forEach.call(mod.options, function(o){ o.hidden = sk ? ['free_help','skill_exchange'].indexOf(o.value) === -1 : ['free_help','skill_exchange'].indexOf(o.value) > -1; });
    cond.value = sk ? '不适用' : (cond.value === '不适用' ? '全新' : cond.value);
    if (mod.selectedOptions[0] && mod.selectedOptions[0].hidden) mod.value = sk ? 'free_help' : 'borrow';
  };
  cat.addEventListener('change', sync); sync();
}

/* Tab switching */
var tabs = document.querySelectorAll('.tab-btn');
var panels = document.querySelectorAll('.tab-content');
if (tabs.length && panels.length) {
  [].forEach.call(tabs, function(btn){
    btn.addEventListener('click', function(){
      var target = this.getAttribute('data-tab');
      [].forEach.call(tabs, function(b){ b.classList.remove('active'); b.setAttribute('aria-selected','false'); });
      [].forEach.call(panels, function(p){ p.classList.remove('active'); });
      this.classList.add('active'); this.setAttribute('aria-selected','true');
      var panel = document.getElementById('tab-' + target);
      if (panel) panel.classList.add('active');
    });
  });
}

/* Mobile sidebar toggle */
var toggle = document.querySelector('[data-toggle-sidebar]');
var sidebar = document.querySelector('[data-sidebar]');
var overlay = null;
if (toggle && sidebar) {
  toggle.addEventListener('click', function(){
    if (sidebar.classList.contains('open')) { closeSidebar(); return; }
    overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';
    overlay.addEventListener('click', closeSidebar);
    document.body.appendChild(overlay);
    sidebar.classList.add('open');
    toggle.setAttribute('aria-expanded','true');
  });
  function closeSidebar(){
    sidebar.classList.remove('open');
    toggle.setAttribute('aria-expanded','false');
    if (overlay) { overlay.remove(); overlay = null; }
  }
}

/* Flash message dismiss */
[].forEach.call(document.querySelectorAll('[data-close-flash]'), function(btn){
  btn.addEventListener('click', function(){
    var flash = this.parentNode;
    flash.style.opacity = '0';
    flash.style.transition = 'opacity .2s';
    setTimeout(function(){ if (flash.parentNode) flash.remove(); }, 200);
  });
});

/* Dropdown toggle */
[].forEach.call(document.querySelectorAll('[data-dropdown-trigger]'), function(trigger){
  trigger.addEventListener('click', function(e){
    e.preventDefault();
    this.closest('[data-dropdown]').classList.toggle('open');
  });
});
document.addEventListener('click', function(e){ if (!e.target.closest('[data-dropdown]')) { [].forEach.call(document.querySelectorAll('[data-dropdown].open'), function(d){ d.classList.remove('open'); }); } });
})();
