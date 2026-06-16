/* ============================================================
   0731本地生活圈 - 全局交互脚本
   ============================================================ */

// ---------- Toast 提示 ----------
function showToast(message, type = 'success', duration = 2000) {
  const toast = document.getElementById('toast') || createToastElement();
  toast.textContent = message;
  toast.className = `toast ${type}`;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.className = 'toast';
  }, duration);
}

function createToastElement() {
  const toast = document.createElement('div');
  toast.id = 'toast';
  toast.className = 'toast';
  document.body.appendChild(toast);
  return toast;
}

// ---------- 认证状态模拟 ----------
let authState = {
  isLoggedIn: false,
  level: null, // 'basic' | 'standard' | 'advanced' | 'business'
  phone: null,
};

function getAuthState() {
  const stored = localStorage.getItem('auth_state');
  if (stored) {
    authState = JSON.parse(stored);
  }
  return authState;
}

function setAuthState(state) {
  authState = { ...authState, ...state };
  localStorage.setItem('auth_state', JSON.stringify(authState));
  updateAuthUI();
}

function updateAuthUI() {
  const state = getAuthState();
  const authBtns = document.querySelectorAll('[data-auth-action]');
  const authBadges = document.querySelectorAll('[data-auth-badge]');
  const authRequired = document.querySelectorAll('[data-auth-required]');

  authBtns.forEach(btn => {
    if (state.isLoggedIn) {
      btn.textContent = '已认证';
      btn.classList.remove('btn-primary');
      btn.classList.add('btn-outline');
      if (state.level) {
        const labels = { basic: '基础认证', standard: '标准认证', advanced: '高级认证', business: '商家认证' };
        btn.textContent = labels[state.level];
      }
    }
  });

  authBadges.forEach(badge => {
    if (state.isLoggedIn && state.level) {
      badge.textContent = { basic: '基础', standard: '标准', advanced: '高级', business: '商家' }[state.level];
      badge.className = `auth-badge ${state.level}`;
    }
  });

  authRequired.forEach(el => {
    if (state.isLoggedIn && state.level) {
      el.style.display = 'none';
    }
  });
}

// ---------- 点赞动画 ----------
function animateLike(btn) {
  const heart = btn.querySelector('.like-icon') || btn;
  heart.style.transition = 'transform 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
  heart.style.transform = 'scale(1.3)';
  setTimeout(() => {
    heart.style.transform = 'scale(1)';
  }, 150);

  const countEl = btn.querySelector('.like-count');
  if (countEl) {
    const current = parseInt(countEl.textContent) || 0;
    countEl.textContent = btn.classList.contains('liked') ? current - 1 : current + 1;
  }
  btn.classList.toggle('liked');
}

// ---------- 搜索 ----------
function handleSearch(event) {
  event.preventDefault();
  const input = event.target.querySelector('input[name="q"]') || event.target.querySelector('input');
  const query = input?.value?.trim();
  if (query) {
    window.location.href = `/search?q=${encodeURIComponent(query)}`;
  }
}

// ---------- 时间格式化 ----------
function formatTime(date) {
  const now = new Date();
  const d = new Date(date);
  const diff = now - d;
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  if (hours < 24) return `${hours}小时前`;
  if (days < 7) return `${days}天前`;
  return d.toLocaleDateString('zh-CN');
}

// ---------- 签到 ----------
async function doCheckin() {
  const widget = document.getElementById('checkinWidget');
  if (!widget || widget.classList.contains('checked-in')) return;

  try {
    const resp = await fetch('/api/checkin', { method: 'POST' });
    const data = await resp.json();
    if (data.ok) {
      widget.classList.add('checked-in');
      document.getElementById('coinBalance').textContent = data.total_coins + ' 论坛币';
      document.getElementById('coinHint').textContent = `🎉 签到成功！获得 ${data.coins_earned} 论坛币（价值${data.yuan_value}元）`;
      document.getElementById('checkinIcon').textContent = '✅';
      showToast(`签到成功！+${data.coins_earned} 论坛币 🪙`);
    } else {
      showToast(data.detail || '签到失败', 'error');
    }
  } catch (err) {
    showToast('签到失败，请重试', 'error');
  }
}

async function initCheckinStatus() {
  try {
    const resp = await fetch('/api/checkin/status');
    const data = await resp.json();
    const widget = document.getElementById('checkinWidget');
    if (!widget) return;

    if (data.checked_in) {
      widget.classList.add('checked-in');
      document.getElementById('checkinIcon').textContent = '✅';
      document.getElementById('coinHint').textContent = '今日已签到，明天再来！';
    }
    if (document.getElementById('coinBalance')) {
      document.getElementById('coinBalance').textContent = (data.total_coins || 0) + ' 论坛币';
    }
  } catch (err) {
    // 静默处理
  }
}

// ---------- 在线人数 ----------
async function fetchOnlineCount() {
  try {
    const resp = await fetch('/api/online_count');
    const data = await resp.json();
    const el = document.getElementById('onlineCount');
    if (el) {
      el.textContent = data.count;
    }
  } catch (err) {
    // 静默处理
  }
}

// ---------- 置顶帖子 ----------
async function loadPinnedPosts() {
  const section = document.getElementById('pinnedSection');
  const list = document.getElementById('pinnedPostsList');
  if (!section || !list) return;

  try {
    // 使用搜索API获取置顶帖子（通过前端过滤最新帖子中is_pinned的）
    const resp = await fetch('/api/online_count');
    // 置顶帖子通过首页服务端渲染已包含，这里做客户端补充
    // 如果服务端已渲染置顶帖子则不需重复加载
  } catch (err) {
    // 静默处理
  }
}

// ---------- Toast ----------
document.addEventListener('DOMContentLoaded', () => {
  updateAuthUI();
  fetchOnlineCount();
  initCheckinStatus();
  loadPinnedPosts();

  // 搜索框提交
  document.querySelectorAll('.search-bar').forEach(bar => {
    bar.addEventListener('submit', handleSearch);
  });
});
