/**
 * JJ Invest Web Trading Platform - Frontend Controller
 * Chart.js Integration, REST API Communication, Account Management, and Backtest Engine
 */

// 전역 상태
const state = {
  user: null,
  token: null,
  currentTab: 'dashboard',
  portfolio: null,
  accounts: [],
  activeAccountDetail: null,
  activeDetailSubTab: 'orders',
  serverStatus: null,
  backtestResults: null,
  charts: {
    equity: null,
    drawdown: null,
    allocation: null
  }
};

// 통화/숫자 포맷터
const fmt = {
  usd: (v) => '$' + (Number(v) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  usdk: (v) => '$' + (Number(v) || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }),
  pct: (v) => (v >= 0 ? '+' : '') + (Number(v) || 0).toFixed(2) + '%',
  num: (v) => (Number(v) || 0).toLocaleString(),
};

// 주문 정보 정규화 헬퍼 (영문/한글 필드 호환)
function parseOrderItem(o, defaultMemo = '') {
  if (!o) return { p: 0, q: 0, a: 0, m: defaultMemo };
  const p = o.price !== undefined ? Number(o.price) : (parseFloat(String(o['주문단가'] || '0').replace(/[^0-9.]/g, '')) || 0);
  const q = o.qty !== undefined ? Number(o.qty) : (o.shares !== undefined ? Number(o.shares) : (parseInt(String(o['주문수량'] || '0').replace(/[^0-9]/g, '')) || 0));
  const a = o.amount !== undefined ? Number(o.amount) : (parseFloat(String(o['예상금액'] || '0').replace(/[^0-9.]/g, '')) || (p * q));
  const m = o.비고 || o.memo || o['체결조건'] || o['구분'] || o['호가단계'] || defaultMemo;
  return { p, q, a, m };
}
window.parseOrderItem = parseOrderItem;

// -------------------------------------------------------------------
// 사용자 인증 및 세션 제어
// -------------------------------------------------------------------
let appInitialized = false;
let pollingInterval = null;

// 공통 인증 헤더 Fetch 유틸리티
function authFetch(url, options = {}) {
  const opts = { ...options };
  opts.headers = { ...(options.headers || {}) };
  if (state.token) {
    opts.headers['Authorization'] = `Bearer ${state.token}`;
  }
  return fetch(url, opts).then(async (res) => {
    if (res.status === 401) {
      console.warn('세션이 만료되었거나 인증되지 않았습니다.');
      handleLogout();
      throw new Error('로그인이 필요합니다.');
    }
    return res;
  });
}

document.addEventListener('DOMContentLoaded', () => {
  checkAuthAndInit();
});

async function checkAuthAndInit() {
  const savedUser = localStorage.getItem('jj_auth_user') || sessionStorage.getItem('jj_auth_user');
  const savedToken = localStorage.getItem('jj_auth_token') || sessionStorage.getItem('jj_auth_token');

  if (savedUser && savedToken) {
    try {
      state.user = JSON.parse(savedUser);
      state.token = savedToken;

      // 서버에 세션 유효성 검증
      const meRes = await fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${savedToken}` }
      });
      const meData = await meRes.json();
      if (meData.authenticated && meData.user) {
        state.user = meData.user;
        showAppView();
        initApp();
        return;
      }
    } catch (e) {
      console.warn('세션 검증 실패:', e);
    }
    // 유효하지 않은 세션 정리
    localStorage.removeItem('jj_auth_user');
    localStorage.removeItem('jj_auth_token');
    sessionStorage.removeItem('jj_auth_user');
    sessionStorage.removeItem('jj_auth_token');
  }

  showLoginView();
}

function showLoginView() {
  const loginView = document.getElementById('login-view');
  const appView = document.getElementById('app-view');
  if (loginView) loginView.style.display = 'flex';
  if (appView) appView.style.display = 'none';

  // 아이디/비밀번호 고정 없이 빈 값으로 초기화
  const unameInput = document.getElementById('login-username');
  if (unameInput) unameInput.value = '';
  const pwdInput = document.getElementById('login-password');
  if (pwdInput) pwdInput.value = '';

  switchAuthMode('login');
}

function switchAuthMode(mode) {
  const loginForm = document.getElementById('login-form');
  const regForm = document.getElementById('register-form');
  const btnLogin = document.getElementById('btn-show-login');
  const btnReg = document.getElementById('btn-show-register');
  const alertBox = document.getElementById('auth-alert-box');

  if (alertBox) alertBox.style.display = 'none';

  if (mode === 'login') {
    if (loginForm) loginForm.style.display = 'block';
    if (regForm) regForm.style.display = 'none';
    if (btnLogin) btnLogin.classList.add('active');
    if (btnReg) btnReg.classList.remove('active');
  } else {
    if (loginForm) loginForm.style.display = 'none';
    if (regForm) regForm.style.display = 'block';
    if (btnLogin) btnLogin.classList.remove('active');
    if (btnReg) btnReg.classList.add('active');
  }
}

function showAppView() {
  const loginView = document.getElementById('login-view');
  const appView = document.getElementById('app-view');
  if (loginView) loginView.style.display = 'none';
  if (appView) appView.style.display = 'block';

  // 헤더 사용자 정보 갱신
  if (state.user) {
    const nameEl = document.getElementById('user-display-name');
    if (nameEl) nameEl.textContent = state.user.name || state.user.username;

    // 관리자(Admin) 전용 회원 관리 설정 탭 노출 여부 제어
    const adminSettingBtn = document.getElementById('btn-setting-tab-admin');
    if (adminSettingBtn) {
      adminSettingBtn.style.display = (state.user && state.user.role === 'admin') ? 'inline-flex' : 'none';
    }
  }
}

function initApp() {
  if (appInitialized) return;
  appInitialized = true;

  initTabs();
  initTickerRibbon();
  loadServerStatus();
  loadAccounts();
  initBacktestPresets();

  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(() => {
    if (state.user) {
      loadServerStatus();
      loadAccounts(true);
    }
  }, 15000);
}

// 1. 로그인 요청
async function handleLoginSubmit(event) {
  if (event) event.preventDefault();

  const uname = document.getElementById('login-username').value.trim();
  const pwd = document.getElementById('login-password').value.trim();
  const remember = document.getElementById('login-remember').checked;
  const alertBox = document.getElementById('auth-alert-box');
  const btnText = document.getElementById('btn-login-text');
  const btnSpinner = document.getElementById('btn-login-spinner');
  const submitBtn = document.getElementById('btn-login-submit');

  if (!uname || !pwd) {
    showAuthAlert('아이디와 비밀번호를 모두 입력해주세요.', 'error');
    return;
  }

  if (alertBox) alertBox.style.display = 'none';
  btnText.style.display = 'none';
  btnSpinner.style.display = 'inline';
  submitBtn.disabled = true;

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: uname, password: pwd })
    });

    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.detail || '아이디 또는 비밀번호가 일치하지 않습니다.');
    }

    state.user = data.user;
    state.token = data.token;

    if (remember) {
      localStorage.setItem('jj_auth_user', JSON.stringify(data.user));
      localStorage.setItem('jj_auth_token', data.token);
    } else {
      sessionStorage.setItem('jj_auth_user', JSON.stringify(data.user));
      sessionStorage.setItem('jj_auth_token', data.token);
    }

    showAppView();
    initApp();
    showToast(`환영합니다, ${data.user.name || uname}님! 나만의 투자 현황을 불러옵니다.`, 'success');
  } catch (err) {
    showAuthAlert(err.message, 'error');
  } finally {
    btnText.style.display = 'inline';
    btnSpinner.style.display = 'none';
    submitBtn.disabled = false;
  }
}

// 2. 회원가입 요청
async function handleRegisterSubmit(event) {
  if (event) event.preventDefault();

  const email = document.getElementById('reg-email').value.trim();
  const uname = document.getElementById('reg-username').value.trim();
  const pwd = document.getElementById('reg-password').value.trim();
  const pwdConfirm = document.getElementById('reg-password-confirm').value.trim();
  const btnText = document.getElementById('btn-reg-text');
  const btnSpinner = document.getElementById('btn-reg-spinner');
  const submitBtn = document.getElementById('btn-register-submit');

  if (!email || !uname || !pwd) {
    showAuthAlert('모든 필수 항목을 입력해주세요.', 'error');
    return;
  }

  if (pwd !== pwdConfirm) {
    showAuthAlert('비밀번호 확인이 일치하지 않습니다.', 'error');
    return;
  }

  btnText.style.display = 'none';
  btnSpinner.style.display = 'inline';
  submitBtn.disabled = true;

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, username: uname, password: pwd })
    });

    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.detail || '회원가입에 실패했습니다.');
    }

    state.user = data.user;
    state.token = data.token;
    localStorage.setItem('jj_auth_user', JSON.stringify(data.user));
    localStorage.setItem('jj_auth_token', data.token);

    showAppView();
    initApp();
    showToast(`회원가입 완료! 환영합니다, ${data.user.name || uname}님!`, 'success');
  } catch (err) {
    showAuthAlert(err.message, 'error');
  } finally {
    btnText.style.display = 'inline';
    btnSpinner.style.display = 'none';
    submitBtn.disabled = false;
  }
}

function showAuthAlert(msg, type = 'error') {
  const alertBox = document.getElementById('auth-alert-box');
  if (!alertBox) return;
  alertBox.textContent = (type === 'error' ? '⚠️ ' : '✅ ') + msg;
  alertBox.style.display = 'flex';
}

function togglePasswordVisibility(inputId) {
  const el = document.getElementById(inputId);
  if (!el) return;
  el.type = el.type === 'password' ? 'text' : 'password';
}

async function handleLogout() {
  try {
    if (state.token) {
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${state.token}` }
      });
    }
  } catch (e) {}
  localStorage.removeItem('jj_auth_user');
  localStorage.removeItem('jj_auth_token');
  sessionStorage.removeItem('jj_auth_user');
  sessionStorage.removeItem('jj_auth_token');
  state.user = null;
  state.token = null;
  appInitialized = false;
  if (pollingInterval) clearInterval(pollingInterval);
  showLoginView();
  showToast('안전하게 로그아웃되었습니다.');
}


function initTabs() {
  document.querySelectorAll('.nav-tabs .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;
      if (target) switchTab(target);
    });
  });
}

function switchTab(tabId) {
  if (!tabId) return;
  state.currentTab = tabId;
  document.querySelectorAll('.nav-tabs .tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tabId);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === `tab-${tabId}`);
  });

  // '계좌 현황' 탭 선택 시 기본적으로 계좌 목록(카드 그리드) 화면 표시
  if (tabId === 'accounts') {
    closeAccountDetailView(false);
  }

  if (tabId === 'admin') {
    loadAdminUsers();
  }

  if (tabId === 'backtest' && !state.backtestResults) {
    // 백테스트 탭 처음 열릴 때 빠른 실행 제안
  }

  if (tabId === 'dashboard' && state.charts.allocation) {
    state.charts.allocation.resize();
  }
}

// -------------------------------------------------------------------
// 시세 리본 바
// -------------------------------------------------------------------
const WATCH_TICKERS = ['SOXL', 'TQQQ', 'QLD', 'UPRO', 'NVDA', 'TSLA'];

async function initTickerRibbon() {
  // Removed top ticker bar per user request
  return;
}

function quickFillBacktest(sym) {
  switchTab('backtest');
  const input = document.getElementById('bt-ticker');
  if (input) input.value = sym;
  showToast(`${sym} 종목이 백테스트에 설정되었습니다.`);
}

// -------------------------------------------------------------------
// 서버 상태 로드
// -------------------------------------------------------------------
async function loadServerStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    state.serverStatus = data;

    // 미국 증시 상태 뱃지 업데이트
    const market = data.market;
    const badgeEl = document.getElementById('market-badge');
    if (badgeEl && market) {
      badgeEl.innerHTML = `
        <span class="status-dot ${market.badge}"></span>
        <span>${market.status}</span>
      `;
    }

    // 자동매매 카드 업데이트
    const botStatusEl = document.getElementById('bot-status-text');
    const botToggleBtn = document.getElementById('btn-bot-toggle');
    if (botStatusEl && data.autotrade) {
      botStatusEl.textContent = data.autotrade.status;
      botStatusEl.style.color = data.autotrade.enabled ? 'var(--profit-green)' : 'var(--text-muted)';
      if (botToggleBtn) {
        botToggleBtn.textContent = data.autotrade.enabled ? '자동매매 중지' : '자동매매 시작';
        botToggleBtn.className = `btn ${data.autotrade.enabled ? 'btn-danger' : 'btn-success'}`;
      }
    }
  } catch (e) {
    console.error('서버 상태 조회 실패', e);
  }
}

// -------------------------------------------------------------------
// 계좌 목록 및 대시보드 로드
// -------------------------------------------------------------------
async function loadAccounts(isSilent = false) {
  try {
    const res = await authFetch('/api/accounts');
    const data = await res.json();
    state.portfolio = data.portfolio;
    state.accounts = data.accounts;

    renderDashboardKPIs(data.portfolio);
    renderAccountsGrid(data.accounts);
    renderAssetTrendChart(data.portfolio);
    renderAllocationDonut(data.accounts);

  } catch (e) {
    if (!isSilent) showToast('계좌 데이터를 불러오는 중 오류가 발생했습니다.', 'error');
  }
}

function renderDashboardKPIs(p) {
  if (!p) return;
  document.getElementById('kpi-total-asset').textContent = fmt.usd(p.total_asset);
  document.getElementById('kpi-total-profit').textContent = fmt.usd(p.total_profit);
  const retEl = document.getElementById('kpi-total-return');
  retEl.textContent = fmt.pct(p.return_pct);
  retEl.className = p.return_pct >= 0 ? 'pos' : 'neg';

  document.getElementById('kpi-total-cash').textContent = fmt.usd(p.total_cash);
  const cashRatio = p.total_asset > 0 ? ((p.total_cash / p.total_asset) * 100).toFixed(1) : 0;
  document.getElementById('kpi-cash-ratio').textContent = `현금 비중 ${cashRatio}%`;

  document.getElementById('kpi-total-seed').textContent = fmt.usd(p.total_seed);
  document.getElementById('kpi-account-count').textContent = `${p.account_count}개 운용 중`;
}

function renderAccountsGrid(accounts) {
  const container = document.getElementById('accounts-grid');
  if (!container) return;

  if (!accounts || accounts.length === 0) {
    const userName = state.user ? (state.user.name || state.user.username) : '';
    container.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 3.5rem 2rem; background: var(--bg-card); border-radius: var(--radius-md); border: 1px dashed var(--border-subtle);">
        <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">💼</div>
        <h3 style="color: var(--text-primary); margin-bottom: 0.5rem;">${userName ? userName + '님의 ' : ''}등록된 투자 계좌가 없습니다.</h3>
        <p style="color: var(--text-secondary); margin-bottom: 1.5rem; font-size: 0.9rem;">종종이 3단계 LOC 또는 라오어 무한매수법 계좌를 개설하여 나만의 자동투자를 시작해보세요.</p>
        <button class="btn btn-primary btn-lg" onclick="openNewAccountModal()">+ 첫 투자 계좌 개설하기</button>
      </div>
    `;
    return;
  }

  container.innerHTML = accounts.map(acc => {
    const modeClass = acc.mode === 'Safe' ? 'badge-mode-safe' : (acc.mode === 'Riskoff' ? 'badge-mode-riskoff' : 'badge-mode-normal');
    const stateClass = acc.operational_state === 'WAITING_FOR_FILL' ? 'badge-state-waiting' : 'badge-state-done';
    const stateText = acc.operational_state === 'WAITING_FOR_FILL' ? '장전 대기' : '정산 완료';
    const retClass = acc.return_pct >= 0 ? 'color: var(--profit-green);' : 'color: var(--loss-red);';
    const isAutoOn = acc.auto_trade && acc.auto_trade.enabled;
    const autoTradeBadge = isAutoOn
      ? `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);">🤖 자동 ON (${acc.auto_trade.broker || 'meritz'})</span>`
      : `<span class="badge" style="background: rgba(148, 163, 184, 0.1); color: var(--text-muted); border: 1px solid rgba(148, 163, 184, 0.2);">⚪ 자동 OFF</span>`;

    return `
      <div class="account-card" onclick="openAccountDetailModal('${acc.id}')">
        <div>
          <div class="card-top">
            <div class="card-title">
              <h3>${acc.name}</h3>
              <div style="margin-top: 4px; display: flex; gap: 6px; flex-wrap: wrap;">
                ${autoTradeBadge}
                <span class="badge badge-ticker">${acc.ticker}</span>
                <span class="badge ${modeClass}">${acc.mode}</span>
                <span class="badge ${stateClass}">${stateText}</span>
              </div>
            </div>
            <div style="text-align: right;">
              <div style="font-size: 1.15rem; font-weight: 700; ${retClass}">${fmt.pct(acc.return_pct)}</div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">${fmt.usd(acc.total_profit)}</div>
            </div>
          </div>

          <div class="account-metrics" style="margin-top: 1rem;">
            <div class="metric-item">
              <div class="lbl">총 평가자산</div>
              <div class="val">${fmt.usd(acc.total_asset)}</div>
            </div>
            <div class="metric-item">
              <div class="lbl">보유 현금</div>
              <div class="val">${fmt.usd(acc.current_cash)}</div>
            </div>
            <div class="metric-item">
              <div class="lbl">보유 주식수</div>
              <div class="val">${fmt.num(acc.current_holdings)}주 (${fmt.usd(acc.current_price)})</div>
            </div>
            <div class="metric-item">
              <div class="lbl">초기 원금</div>
              <div class="val">${fmt.usd(acc.initial_seed)}</div>
            </div>
          </div>
        </div>

        <div class="card-footer">
          <span>${acc.strategy}</span>
          <span style="color: var(--accent-cyan); font-weight: 600;">상세보기 & 주문표 →</span>
        </div>
      </div>
    `;
  }).join('');
}



// -------------------------------------------------------------------
// 대시보드 일자별 총 자산 현황 꺾은선 차트 (X축: 거래일자, Y축: 총자산)
// -------------------------------------------------------------------
function renderAssetTrendChart(portfolio) {
  const canvas = document.getElementById('assetTrendLineChart');
  if (!canvas) return;

  const trendData = (portfolio && portfolio.daily_trend) ? portfolio.daily_trend : [];
  const latestAssetEl = document.getElementById('trend-latest-asset');
  if (latestAssetEl && portfolio) {
    latestAssetEl.textContent = `현재 총 자산: ${fmt.usd(portfolio.total_asset)}`;
  }

  if (trendData.length === 0) {
    if (state.charts.assetTrend) {
      state.charts.assetTrend.destroy();
      state.charts.assetTrend = null;
    }
    return;
  }

  const labels = trendData.map(item => item.date);
  const dataVals = trendData.map(item => item.asset);

  if (state.charts.assetTrend) {
    state.charts.assetTrend.destroy();
  }

  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 240);
  gradient.addColorStop(0, 'rgba(16, 185, 129, 0.3)');
  gradient.addColorStop(1, 'rgba(16, 185, 129, 0.0)');

  state.charts.assetTrend = new Chart(canvas, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: '일자별 총 자산 ($)',
        data: dataVals,
        borderColor: '#10b981',
        backgroundColor: gradient,
        borderWidth: 2.2,
        pointRadius: labels.length > 50 ? 0 : 2.5,
        pointHoverRadius: 5,
        pointBackgroundColor: '#10b981',
        pointBorderColor: '#ffffff',
        pointBorderWidth: 1.5,
        fill: true,
        tension: 0.2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#94a3b8',
          bodyColor: '#34d399',
          bodyFont: { weight: 'bold', size: 13 },
          borderColor: 'rgba(52, 211, 153, 0.3)',
          borderWidth: 1,
          padding: 10,
          displayColors: false,
          callbacks: {
            title: function(items) {
              return `📅 거래일: ${items[0].label}`;
            },
            label: function(ctx) {
              return `💰 총 자산: $${Number(ctx.raw).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: {
            color: '#94a3b8',
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 7
          }
        },
        y: {
          position: 'right',
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: {
            color: '#94a3b8',
            callback: function(val) {
              return '$' + (val >= 1000 ? (val / 1000).toFixed(0) + 'k' : val);
            }
          }
        }
      }
    }
  });
}


// -------------------------------------------------------------------
// 자산 배분 도넛 차트
// -------------------------------------------------------------------
function renderAllocationDonut(accounts) {
  const canvas = document.getElementById('allocationDonutChart');
  if (!canvas || !accounts || accounts.length === 0) return;

  const labels = accounts.map(a => a.name);
  const dataVals = accounts.map(a => a.total_asset);

  if (state.charts.allocation) {
    state.charts.allocation.destroy();
  }

  state.charts.allocation = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: dataVals,
        backgroundColor: [
          '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899'
        ],
        borderColor: '#111827',
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: { color: '#94a3b8', font: { size: 11 } }
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${fmt.usd(ctx.raw)}`
          }
        }
      }
    }
  });
}

// -------------------------------------------------------------------
// 계좌 상세 인페이지 뷰 & 뒤로가기 제어
// -------------------------------------------------------------------
async function openAccountDetailModal(accId, pushHistory = true) {
  try {
    const res = await authFetch(`/api/accounts/${accId}`);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: 계좌 데이터를 불러오지 못했습니다.`);
    }
    const data = await res.json();
    if (!data || !data.account) {
      throw new Error('계좌 응답 데이터가 비어 있습니다.');
    }
    state.activeAccountDetail = data;

    // 메인화면 내 계좌 상세 뷰로 전환 (모달 팝업 대신 인페이지)
    const listView = document.getElementById('account-list-view');
    const detailView = document.getElementById('account-detail-view');
    if (listView) listView.style.display = 'none';
    if (detailView) detailView.style.display = 'block';

    const headerTitle = document.getElementById('modal-acc-title');
    const subTitleEl = document.getElementById('modal-acc-subtitle');
    const actionsEl = document.getElementById('detail-header-actions');
    const acc = data.account;

    if (headerTitle) {
      headerTitle.innerHTML = `
        <span id="header-acc-name-text">${acc.name}</span>
        <span style="font-size: 1.1rem; color: var(--text-muted); font-weight: 500;">(${acc.ticker})</span>
        <button type="button" class="btn btn-secondary btn-xs" onclick="openRenameAccountModal('${acc.id}', '${acc.name.replace(/'/g, "\\'")}')" title="계좌명 변경" style="margin-left: 0.6rem; padding: 3px 8px; font-size: 0.775rem; border-color: rgba(56, 189, 248, 0.4); background: rgba(56, 189, 248, 0.1); color: var(--accent-cyan); font-weight: 600; cursor: pointer; border-radius: 4px; display: inline-flex; align-items: center; gap: 0.25rem;">
          <span>✏️</span> 계좌명 변경
        </button>
      `;
    }

    if (subTitleEl) {
      const modeText = acc.mode || (data.summary && data.summary.mode) || 'Normal';
      const modeClass = modeText === 'Safe' ? 'badge-mode-safe' : (modeText === 'Riskoff' ? 'badge-mode-riskoff' : 'badge-mode-normal');
      subTitleEl.innerHTML = `
        <span class="badge badge-ticker">${acc.ticker}</span>
        <span class="badge ${modeClass}">${modeText}</span>
        <span style="color: var(--text-secondary); margin-left: 6px;">${acc.strategy}</span>
        <span style="color: var(--text-muted); margin-left: 8px;">| 운용 기준일: <strong>${acc.current_date}</strong></span>
      `;
    }

    if (actionsEl) {
      actionsEl.innerHTML = `
        <button class="btn btn-secondary btn-sm" onclick="advanceAccountDay('${acc.id}')" title="다음 거래일로 진행">
          <span>⏩</span> Next Day
        </button>
        <button class="btn btn-primary btn-sm" onclick="openSettlementModal('${acc.id}')" title="당일 종가 및 체결 정산">
          <span>📝</span> 종가 정산
        </button>
        <button class="btn btn-secondary btn-sm" onclick="openAdjustmentModal('${acc.id}')" title="입금 또는 출금 기록">
          <span>💰</span> 입출금
        </button>
        <button class="btn btn-secondary btn-sm" onclick="openAccountBrokerModal('${acc.id}')" title="계좌별 자동매매 및 증권사 API 연동 설정" style="border-color: rgba(56, 189, 248, 0.4); background: rgba(56, 189, 248, 0.1); color: var(--accent-cyan); font-weight: 600;">
          <span>🤖</span> 자동매매 설정
        </button>
      `;
    }

    // 서브 탭 렌더링 및 첫 서브탭 활성화
    renderDetailSubTabs(data);
    switchDetailSubTab(state.activeDetailSubTab || 'orders');

    // 브라우저 뒤로가기(popstate) 연동
    if (pushHistory) {
      try {
        history.pushState({ view: 'account-detail', accId: accId }, '', `#account-${accId}`);
      } catch (e) {}
    }

    // 화면 상단으로 스크롤 이동
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } catch (e) {
    console.error('계좌 상세 로드 실패:', e);
    const msg = (e && e.message) ? e.message : String(e);
    showToast(`계좌 상세 정보를 불러오지 못했습니다: ${msg}`, 'error');
  }
}

function closeAccountDetailView(triggerHistoryBack = true) {
  const listView = document.getElementById('account-list-view');
  const detailView = document.getElementById('account-detail-view');
  if (listView) listView.style.display = 'block';
  if (detailView) detailView.style.display = 'none';

  state.activeAccountDetail = null;

  if (triggerHistoryBack && window.history.state && window.history.state.view === 'account-detail') {
    window.history.back();
    return;
  }

  // 계좌 목록 갱신 (정산/입출금 내역 반영)
  loadAccounts(true);
}

// 브라우저 뒤로가기(popstate) 이벤트 핸들러
window.addEventListener('popstate', (e) => {
  const st = e.state;
  if (st && st.view === 'account-detail' && st.accId) {
    openAccountDetailModal(st.accId, false);
  } else {
    const detailView = document.getElementById('account-detail-view');
    if (detailView && detailView.style.display !== 'none') {
      closeAccountDetailView(false);
    }
  }
});

function switchDetailSubTab(subTabId) {
  state.activeDetailSubTab = subTabId;
  document.querySelectorAll('.detail-subtab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.subtab === subTabId);
    if (b.dataset.subtab !== subTabId) b.blur();
  });
  document.querySelectorAll('.detail-subtab-pane').forEach(p => {
    p.classList.toggle('active', p.id === `subtab-${subTabId}`);
  });
}

function renderDetailSubTabs(data) {
  if (!data) return;
  const acc = data.account || {};
  const sum = data.summary || {};
  const orders = data.orders || {};
  const unsold = data.unsold_lots || [];
  const records = data.trade_records || [];
  const adjustments = data.adjustments || [];
  const parseFn = typeof parseOrderItem === 'function' ? parseOrderItem : (window.parseOrderItem || ((o, m = '') => ({ p: 0, q: 0, a: 0, m })));

  // 1. 주문표 서브탭
  const ordersPane = document.getElementById('subtab-orders');
  if (ordersPane) {
    const buyList = orders.buy_orders || [];
    const sellList = orders.sell_orders || [];

    let ordersContent = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;flex-wrap:wrap;gap:0.5rem;">
        <div>
          <span class="badge ${acc.operational_state === 'WAITING_FOR_FILL' ? 'badge-state-waiting' : 'badge-state-done'}">
            ${acc.operational_state === 'WAITING_FOR_FILL' ? '장전 주문 대기' : '당일 마감 정산 완료'}
          </span>
          <span style="font-size:0.85rem;color:var(--text-secondary);margin-left:8px;">운용 기준일: <strong>${acc.current_date}</strong></span>
        </div>
        <div style="display:flex;gap:0.5rem;">
          <button class="btn btn-secondary btn-sm" onclick="advanceAccountDay('${acc.id}')">⏩ 다음 거래일 진행 (Next Day)</button>
          <button class="btn btn-primary btn-sm" onclick="openSettlementModal('${acc.id}')">📝 당일 종가 & 체결 정산</button>
        </div>
      </div>
    `;

    if (buyList.length > 0 || sellList.length > 0) {
      ordersContent += `
        <table class="custom-table">
          <thead>
            <tr>
              <th>구분</th>
              <th>주문 단가</th>
              <th>주문 수량</th>
              <th>주문 금액</th>
              <th>메모</th>
            </tr>
          </thead>
          <tbody>
            ${sellList.map(o => {
              const { p, q, a, m } = parseFn(o);
              const typeStr = o['주문유형'] || 'LOC 매도';
              return `
              <tr>
                <td><span class="tag-sell">${typeStr}</span></td>
                <td>${fmt.usd(p)}</td>
                <td>${fmt.num(q)}주</td>
                <td>${fmt.usd(a)}</td>
                <td><span style="font-size:0.75rem;color:var(--text-muted);">${m}</span></td>
              </tr>
            `;}).join('')}
            ${buyList.map(o => {
              const { p, q, a, m } = parseFn(o);
              const typeStr = o['주문유형'] || 'LOC 매수';
              return `
              <tr>
                <td><span class="tag-buy">${typeStr}</span></td>
                <td>${fmt.usd(p)}</td>
                <td>${fmt.num(q)}주</td>
                <td>${fmt.usd(a)}</td>
                <td><span style="font-size:0.75rem;color:var(--text-muted);">${m}</span></td>
              </tr>
            `;}).join('')}
          </tbody>
        </table>
      `;
    } else {
      ordersContent += `
        <div style="padding:2rem;text-align:center;color:var(--text-muted);background:rgba(15,23,42,0.5);border-radius:var(--radius-sm);">
          현재 산출된 대기 주문이 없습니다. (Next Day 진행 후 장전 주문표가 자동 갱신됩니다)
        </div>
      `;
    }
    ordersPane.innerHTML = ordersContent;
  }

  // 2. 미매도 슬롯 서브탭
  const unsoldPane = document.getElementById('subtab-unsold');
  if (unsoldPane) {
    if (unsold.length > 0) {
      unsoldPane.innerHTML = `
        <table class="custom-table">
          <thead>
            <tr>
              <th>매수 일자</th>
              <th>보유 수량</th>
              <th>목표 매도가 (U)</th>
              <th>보유 일수</th>
            </tr>
          </thead>
          <tbody>
            ${unsold.map(u => `
              <tr>
                <td>${u.date}</td>
                <td><strong>${fmt.num(u.R)}주</strong></td>
                <td style="color:var(--accent-cyan);font-weight:700;">${fmt.usd(u.U)}</td>
                <td><span class="badge badge-mode-normal">${u.hold_days}일차</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      `;
    } else {
      unsoldPane.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text-muted);">현재 미매도 보유 슬롯이 없습니다 (현금 100%).</div>';
    }
  }

  // 3. 매매 일지 서브탭 (스크린샷 그룹 색상 및 12개 컬럼 완벽 일치)
  const recordsPane = document.getElementById('subtab-records');
  if (recordsPane) {
    if (records.length > 0) {
      let cumProfit = 0;
      const enrichedRecords = records.map((r, i) => {
        const isSold = Boolean(r.Sold);
        const profit = (r.Profit !== null && r.Profit !== undefined) ? Number(r.Profit) : null;
        if (isSold && profit !== null) {
          cumProfit += profit;
        }

        // 보유일수 계산 (미매도 슬롯의 경우 최신 데이터 기준 경과 거래일)
        const holdDays = (records.length - 1) - i;

        // 수익률 계산
        const buyPrice = Number(r.BuyPrice || r.Close || 1);
        const sellPrice = Number(r.X || 0);
        let yieldPct = null;
        if (isSold && sellPrice > 0) {
          yieldPct = ((sellPrice - buyPrice) / buyPrice) * 100;
        }

        const chgVal = (r.Chg !== null && r.Chg !== undefined) ? Number(r.Chg) : null;

        return {
          ...r,
          isSold,
          profit,
          cumProfit: isSold ? cumProfit : null,
          yieldPct,
          holdDays,
          chgVal
        };
      });

      const reversed = [...enrichedRecords].reverse();

      recordsPane.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">
          <div style="font-size:0.8rem;color:var(--text-secondary);">
            총 <strong>${records.length}</strong>건의 매매일지 (최신순 정렬)
          </div>
          <button class="btn btn-danger btn-sm" onclick="undoLastTradeRecord('${acc.id}')">↩ 마지막 기록 취소 (Undo)</button>
        </div>
        <div class="jj-journal-wrapper">
          <table class="jj-journal-table">
            <thead>
              <tr>
                <th class="jj-th-grp1">거래일자</th>
                <th class="jj-th-grp1">종가</th>
                <th class="jj-th-grp1">변동률</th>
                <th class="jj-th-grp1">모드</th>
                <th class="jj-th-grp2">매수량</th>
                <th class="jj-th-grp2">목표가</th>
                <th class="jj-th-grp3">매도일</th>
                <th class="jj-th-grp3">매도가</th>
                <th class="jj-th-grp4">손익금액</th>
                <th class="jj-th-grp4">손익률</th>
                <th class="jj-th-grp4">누적손익</th>
                <th class="jj-th-grp5">수정</th>
              </tr>
            </thead>
            <tbody>
              ${reversed.map(r => {
                const dateFmt = formatTradeDate(r.Date);
                const closeFmt = fmt.usd(r.Close);

                // 변동률
                let chgHtml = '<span style="color:#64748b;">-</span>';
                if (r.chgVal !== null && !isNaN(r.chgVal) && Math.abs(r.chgVal) > 0.00001) {
                  const pctStr = (r.chgVal * 100).toFixed(2);
                  if (r.chgVal > 0) {
                    chgHtml = `<span style="color:#f87171;font-weight:700;">+${pctStr}%</span>`;
                  } else {
                    chgHtml = `<span style="color:#60a5fa;font-weight:700;">${pctStr}%</span>`;
                  }
                }

                // 모드
                const modeStr = String(r.Mode || 'Normal').toLowerCase();
                let modeBadge = '<span class="badge-mode-normal-pill">Normal</span>';
                if (modeStr === 'safe') {
                  modeBadge = '<span class="badge-mode-safe-pill">Safe</span>';
                } else if (modeStr === 'riskoff' || modeStr === 'risk-off') {
                  modeBadge = '<span class="badge-mode-risk-pill">Risk-off</span>';
                }

                // 매수량 & 목표가
                const buyQty = Number(r.BuyQty || r.R || 0);
                const buyQtyHtml = buyQty > 0 ? `<span style="color:#00e699;font-weight:700;">${fmt.num(buyQty)}주</span>` : '<span style="color:#64748b;">-</span>';
                const targetU = r.U ? fmt.usd(r.U) : fmt.usd(r.Close * 1.0275);

                // 매도일 & 매도가
                let sellDateHtml = `<span class="badge-holding-pill">보유중(${r.holdDays}d)</span>`;
                let sellPriceHtml = '<span style="color:#64748b;">-</span>';
                if (r.isSold) {
                  sellDateHtml = `<span>${formatTradeDate(r.W || r.Date)}</span>`;
                  sellPriceHtml = `<span>${fmt.usd(r.X || r.SellPrice || 0)}</span>`;
                }

                // 손익금액, 손익률, 누적손익
                let profitHtml = '<span style="color:#64748b;">-</span>';
                let yieldHtml = '<span style="color:#64748b;">-</span>';
                let cumProfitHtml = '<span style="color:#64748b;">-</span>';
                if (r.isSold && r.profit !== null) {
                  const pRound = Math.round(r.profit);
                  profitHtml = pRound >= 0 
                    ? `<span style="color:#00e699;font-weight:700;">+${pRound.toLocaleString()}$</span>`
                    : `<span style="color:#ef4444;font-weight:700;">-${Math.abs(pRound).toLocaleString()}$</span>`;
                  
                  if (r.yieldPct !== null) {
                    yieldHtml = r.yieldPct >= 0
                      ? `<span style="color:#00e699;font-weight:700;">+${r.yieldPct.toFixed(1)}%</span>`
                      : `<span style="color:#ef4444;font-weight:700;">${r.yieldPct.toFixed(1)}%</span>`;
                  }

                  if (r.cumProfit !== null) {
                    const cRound = Math.round(r.cumProfit);
                    cumProfitHtml = cRound >= 0
                      ? `<span style="color:#00e699;font-weight:700;">+${cRound.toLocaleString()}$</span>`
                      : `<span style="color:#ef4444;font-weight:700;">-${Math.abs(cRound).toLocaleString()}$</span>`;
                  }
                }

                const safeMemo = (r.Memo || '').replace(/'/g, "\\'");
                const editIconBtn = `
                  <button class="btn-table-edit" onclick="openEditTradeModal('${acc.id}', '${r.Date}', ${r.Close || 0}, ${buyQty}, ${r.SellQty || 0}, '${r.Mode || 'Normal'}', '${safeMemo}')" title="기록 수정">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"></path>
                    </svg>
                  </button>
                `;

                return `
                  <tr>
                    <td><strong>${dateFmt}</strong></td>
                    <td><strong>${closeFmt}</strong></td>
                    <td>${chgHtml}</td>
                    <td>${modeBadge}</td>
                    <td>${buyQtyHtml}</td>
                    <td>${targetU}</td>
                    <td>${sellDateHtml}</td>
                    <td>${sellPriceHtml}</td>
                    <td>${profitHtml}</td>
                    <td>${yieldHtml}</td>
                    <td>${cumProfitHtml}</td>
                    <td style="text-align:center;">${editIconBtn}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    } else {
      recordsPane.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--text-muted);">아직 기록된 일별 매매일지가 없습니다.</div>';
    }
  }

  // 4. 입출금 서브탭
  const adjPane = document.getElementById('subtab-adjustments');
  if (adjPane) {
    adjPane.innerHTML = `
      <div style="display:flex;justify-content:flex-end;margin-bottom:0.75rem;">
        <button class="btn btn-primary btn-sm" onclick="openAdjustmentModal('${acc.id}')">+ 입출금 기록 추가</button>
      </div>
      ${adjustments.length > 0 ? `
        <table class="custom-table">
          <thead>
            <tr>
              <th>일자</th>
              <th>구분</th>
              <th>금액</th>
              <th>사유</th>
            </tr>
          </thead>
          <tbody>
            ${adjustments.map(a => `
              <tr>
                <td>${a.date}</td>
                <td><span class="badge ${a.type === 'DEPOSIT' ? 'badge-mode-normal' : 'badge-mode-riskoff'}">${a.type === 'DEPOSIT' ? '입금' : '출금 (세금 등)'}</span></td>
                <td><strong>${fmt.usd(a.amount)}</strong></td>
                <td>${a.reason || '-'}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      ` : '<div style="padding:2rem;text-align:center;color:var(--text-muted);">입출금 이력이 없습니다.</div>'}
    `;
  }

  // 5. 전략 운용 변수 설정 서브탭 (모드별 익절률 & 분할수, 보유일수, 위기준비, 수수료율)
  const stratPane = document.getElementById('subtab-strategy-settings');
  if (stratPane) {
    const params = acc.strategy_params || {
      max_hold_days: 10,
      reserve_ratio: acc.reserve_ratio || 0.05,
      fee_rate: 0.0,
      normal_target_yield: 0.0275,
      normal_splits: 8.0,
      safe_target_yield: 0.0025,
      safe_splits: 7.0,
      riskoff_target_yield: 0.0070,
      riskoff_splits: 5.0
    };

    const maxHoldDays = params.max_hold_days || 10;
    const reserveRatioPct = ((params.reserve_ratio !== undefined ? params.reserve_ratio : 0.05) * 100).toFixed(2);
    const feeRatePct = ((params.fee_rate !== undefined ? params.fee_rate : 0.0) * 100).toFixed(3);
    const normalYieldPct = ((params.normal_target_yield !== undefined ? params.normal_target_yield : 0.0275) * 100).toFixed(2);
    const normalSplits = params.normal_splits !== undefined ? params.normal_splits : 8;
    const safeYieldPct = ((params.safe_target_yield !== undefined ? params.safe_target_yield : 0.0025) * 100).toFixed(2);
    const safeSplits = params.safe_splits !== undefined ? params.safe_splits : 7;
    const riskoffYieldPct = ((params.riskoff_target_yield !== undefined ? params.riskoff_target_yield : 0.0070) * 100).toFixed(2);
    const riskoffSplits = params.riskoff_splits !== undefined ? params.riskoff_splits : 5;

    stratPane.innerHTML = `
      <div style="background: rgba(15, 23, 42, 0.4); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 1.5rem; max-width: 900px; margin: 0 auto;">
        <!-- 상단 헤더 -->
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem; border-bottom: 1px solid var(--border-subtle); padding-bottom: 0.75rem; flex-wrap: wrap; gap: 0.5rem;">
          <div>
            <h3 style="margin: 0; font-size: 1.15rem; color: var(--text-primary); display: flex; align-items: center; gap: 0.5rem;">
              <span>⚙️</span> 계좌별 맞춤 전략 운용 변수 설정
            </h3>
            <p style="margin: 4px 0 0 0; font-size: 0.82rem; color: var(--text-muted);">
              각 시장 모드(Normal / Safe / Riskoff)별 목표 익절률 및 분할수, 보유일수, 위기준비율을 자유롭게 맞춤 설정합니다.
            </p>
          </div>
          <span class="badge badge-ticker">${acc.name}</span>
        </div>

        <!-- 1. 기본 기간 & 위기준비금 & 수수료율 (3분할 상단 카드) -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1.25rem; margin-bottom: 1.25rem;">
          <!-- 계좌 기본 정보 -->
          <div style="background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(255,255,255,0.06); border-radius: var(--radius-sm); padding: 1.1rem;">
            <div style="font-weight: 700; color: var(--accent-cyan); margin-bottom: 0.85rem; display: flex; align-items: center; gap: 0.4rem; font-size: 0.95rem;">
              <span>🏷️</span> 계좌 기본 정보
            </div>
            <div class="form-group">
              <label style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px; display: flex; justify-content: space-between;">
                <span>계좌명 (별칭)</span>
                <span style="color: var(--accent-cyan); font-size: 0.72rem;">수정 가능</span>
              </label>
              <input type="text" id="sp-account-name" class="form-input" value="${acc.name}" placeholder="계좌명 입력" style="font-weight: 700; color: var(--accent-cyan); width: 100%; min-width: 0; box-sizing: border-box; padding: 0.45rem 0.6rem;">
            </div>
          </div>

          <!-- 기간 & 자산 배분 -->
          <div style="background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(255,255,255,0.06); border-radius: var(--radius-sm); padding: 1.1rem;">
            <div style="font-weight: 700; color: #f59e0b; margin-bottom: 0.85rem; display: flex; align-items: center; gap: 0.4rem; font-size: 0.95rem;">
              <span>⏳</span> 기간 & 자산 배분
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.85rem;">
              <div class="form-group">
                <label style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px; display: flex; justify-content: space-between;">
                  <span>보유일수</span>
                  <span style="color: var(--text-muted); font-size: 0.72rem;">기준 10일</span>
                </label>
                <div style="display: flex; align-items: center; gap: 0.4rem;">
                  <input type="number" id="sp-max-hold-days" class="form-input" value="${maxHoldDays}" min="1" max="60" step="1" style="font-weight: 700; text-align: right; width: 100%; min-width: 0; box-sizing: border-box; padding: 0.45rem 0.6rem;">
                  <span style="color: var(--text-muted); font-size: 0.82rem; white-space: nowrap;">일</span>
                </div>
              </div>

              <div class="form-group">
                <label style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px; display: flex; justify-content: space-between;">
                  <span>위기준비금</span>
                  <span style="color: var(--text-muted); font-size: 0.72rem;">기준 5.00%</span>
                </label>
                <div style="display: flex; align-items: center; gap: 0.4rem;">
                  <input type="number" id="sp-reserve-ratio" class="form-input" value="${reserveRatioPct}" min="0" max="50" step="0.25" style="font-weight: 700; text-align: right; width: 100%; min-width: 0; box-sizing: border-box; padding: 0.45rem 0.6rem;">
                  <span style="color: var(--text-muted); font-size: 0.82rem; white-space: nowrap;">%</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 거래 수수료 -->
          <div style="background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(255,255,255,0.06); border-radius: var(--radius-sm); padding: 1.1rem;">
            <div style="font-weight: 700; color: #a78bfa; margin-bottom: 0.85rem; display: flex; align-items: center; gap: 0.4rem; font-size: 0.95rem;">
              <span>💳</span> 거래 수수료율
            </div>
            <div class="form-group">
              <label style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px; display: flex; justify-content: space-between;">
                <span>수수료율</span>
                <span style="color: var(--text-muted); font-size: 0.72rem;">기준 0.000% (매매 체결 시)</span>
              </label>
              <div style="display: flex; align-items: center; gap: 0.4rem; max-width: 200px;">
                <input type="number" id="sp-fee-rate" class="form-input" value="${feeRatePct}" min="0" max="5" step="0.005" style="font-weight: 700; text-align: right; width: 100%; min-width: 0; box-sizing: border-box; padding: 0.45rem 0.6rem;">
                <span style="color: var(--text-muted); font-size: 0.82rem; white-space: nowrap;">%</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 2. 시장 모드별 매도 & 분할수 (표 테이블 형태로 넉넉하고 깨짐 없는 레이아웃) -->
        <div style="background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(255,255,255,0.06); border-radius: var(--radius-sm); padding: 1.25rem; margin-bottom: 1.25rem;">
          <div style="font-weight: 700; color: var(--accent-cyan); margin-bottom: 0.85rem; display: flex; align-items: center; gap: 0.4rem; font-size: 0.95rem;">
            <span>🎯</span> 시장 모드별 매도 목표수익률 & 분할 매수 조각수
          </div>

          <div style="overflow-x: auto;">
            <table class="custom-table" style="width: 100%; margin: 0; border-collapse: collapse;">
              <thead>
                <tr style="background: rgba(15, 23, 42, 0.7);">
                  <th style="padding: 0.75rem 1rem; text-align: left; width: 34%; font-size: 0.85rem;">시장 구분 모드</th>
                  <th style="padding: 0.75rem 1rem; text-align: center; width: 33%; font-size: 0.85rem;">매도 목표수익률 (%)</th>
                  <th style="padding: 0.75rem 1rem; text-align: center; width: 33%; font-size: 0.85rem;">분할 조각수 (조각)</th>
                </tr>
              </thead>
              <tbody>
                <!-- Normal -->
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); background: rgba(16, 185, 129, 0.05);">
                  <td style="padding: 0.85rem 1rem;">
                    <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                      <span class="badge badge-mode-normal" style="font-size: 0.82rem; padding: 4px 10px; font-weight: 700;">Normal</span>
                      <span style="font-size: 0.8rem; color: #10b981;">상승장 / 평상시</span>
                    </div>
                  </td>
                  <td style="padding: 0.85rem 1rem; text-align: center;">
                    <div style="display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem; width: 100%; max-width: 150px;">
                      <input type="number" id="sp-normal-yield" class="form-input" value="${normalYieldPct}" step="0.05" style="text-align: right; font-weight: 700; color: #10b981; width: 100%; min-width: 0; box-sizing: border-box; padding: 0.45rem 0.6rem;">
                      <span style="color: var(--text-muted); font-size: 0.85rem; white-space: nowrap;">%</span>
                    </div>
                  </td>
                  <td style="padding: 0.85rem 1rem; text-align: center;">
                    <div style="display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem; width: 100%; max-width: 150px;">
                      <input type="number" id="sp-normal-splits" class="form-input" value="${normalSplits}" step="1" min="1" max="50" style="text-align: right; font-weight: 700; width: 100%; min-width: 0; box-sizing: border-box; padding: 0.45rem 0.6rem;">
                      <span style="color: var(--text-muted); font-size: 0.85rem; white-space: nowrap;">조각</span>
                    </div>
                  </td>
                </tr>

                <!-- Safe -->
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); background: rgba(56, 189, 248, 0.05);">
                  <td style="padding: 0.85rem 1rem;">
                    <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                      <span class="badge badge-mode-safe" style="font-size: 0.82rem; padding: 4px 10px; font-weight: 700;">Safe</span>
                      <span style="font-size: 0.8rem; color: #38bdf8;">주의 / 보수 모드</span>
                    </div>
                  </td>
                  <td style="padding: 0.85rem 1rem; text-align: center;">
                    <div style="display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem; width: 100%; max-width: 150px;">
                      <input type="number" id="sp-safe-yield" class="form-input" value="${safeYieldPct}" step="0.05" style="text-align: right; font-weight: 700; color: #38bdf8; width: 100%; min-width: 0; box-sizing: border-box; padding: 0.45rem 0.6rem;">
                      <span style="color: var(--text-muted); font-size: 0.85rem; white-space: nowrap;">%</span>
                    </div>
                  </td>
                  <td style="padding: 0.85rem 1rem; text-align: center;">
                    <div style="display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem; width: 100%; max-width: 150px;">
                      <input type="number" id="sp-safe-splits" class="form-input" value="${safeSplits}" step="1" min="1" max="50" style="text-align: right; font-weight: 700; width: 100%; min-width: 0; box-sizing: border-box; padding: 0.45rem 0.6rem;">
                      <span style="color: var(--text-muted); font-size: 0.85rem; white-space: nowrap;">조각</span>
                    </div>
                  </td>
                </tr>

                <!-- Riskoff -->
                <tr style="background: rgba(239, 68, 68, 0.05);">
                  <td style="padding: 0.85rem 1rem;">
                    <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                      <span class="badge badge-mode-riskoff" style="font-size: 0.82rem; padding: 4px 10px; font-weight: 700;">Riskoff</span>
                      <span style="font-size: 0.8rem; color: #ef4444;">위기 / 폭락장 탈출</span>
                    </div>
                  </td>
                  <td style="padding: 0.85rem 1rem; text-align: center;">
                    <div style="display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem; width: 100%; max-width: 150px;">
                      <input type="number" id="sp-riskoff-yield" class="form-input" value="${riskoffYieldPct}" step="0.05" style="text-align: right; font-weight: 700; color: #ef4444; width: 100%; min-width: 0; box-sizing: border-box; padding: 0.45rem 0.6rem;">
                      <span style="color: var(--text-muted); font-size: 0.85rem; white-space: nowrap;">%</span>
                    </div>
                  </td>
                  <td style="padding: 0.85rem 1rem; text-align: center;">
                    <div style="display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem; width: 100%; max-width: 150px;">
                      <input type="number" id="sp-riskoff-splits" class="form-input" value="${riskoffSplits}" step="1" min="1" max="50" style="text-align: right; font-weight: 700; width: 100%; min-width: 0; box-sizing: border-box; padding: 0.45rem 0.6rem;">
                      <span style="color: var(--text-muted); font-size: 0.85rem; white-space: nowrap;">조각</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- 3. 하단 안내문구 & 저장 버튼 바 -->
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; padding: 1.1rem; background: rgba(30, 41, 59, 0.4); border-radius: var(--radius-sm); border: 1px solid rgba(255,255,255,0.06);">
          <div style="font-size: 0.775rem; color: var(--text-muted); line-height: 1.5; max-width: 580px;">
            💡 <strong>안내:</strong> 최초원금, SEC Fee, 수수료합은 시스템 자동 산출되므로 별도 설정할 필요가 없습니다.<br>
            설정 저장 시 즉시 해당 계좌의 당일 LOC 주문표 및 매수/매도 수량이 자동 재계산됩니다.
          </div>
          <button type="button" class="btn btn-primary" onclick="saveAccountStrategyParams('${acc.id}')" style="padding: 0.75rem 1.75rem; font-weight: 700; font-size: 0.95rem; display: flex; align-items: center; gap: 0.5rem; box-shadow: 0 4px 14px rgba(6, 182, 212, 0.3);">
            <span>💾</span> 전략 운용 설정 저장
          </button>
        </div>
      </div>
    `;
  }
}

async function saveAccountStrategyParams(accId) {
  const newName = (document.getElementById('sp-account-name')?.value || '').trim();
  const maxHold = parseInt(document.getElementById('sp-max-hold-days').value, 10);
  const reserveRatioPct = parseFloat(document.getElementById('sp-reserve-ratio').value);
  const feeRatePct = parseFloat(document.getElementById('sp-fee-rate').value);
  const normalYieldPct = parseFloat(document.getElementById('sp-normal-yield').value);
  const normalSplits = parseFloat(document.getElementById('sp-normal-splits').value);
  const safeYieldPct = parseFloat(document.getElementById('sp-safe-yield').value);
  const safeSplits = parseFloat(document.getElementById('sp-safe-splits').value);
  const riskoffYieldPct = parseFloat(document.getElementById('sp-riskoff-yield').value);
  const riskoffSplits = parseFloat(document.getElementById('sp-riskoff-splits').value);

  if (isNaN(maxHold) || isNaN(normalSplits) || isNaN(safeSplits) || isNaN(riskoffSplits)) {
    showToast('모든 숫자 항목을 올바르게 입력해주세요.', 'error');
    return;
  }

  // 1. 계좌명이 입력되어 있으면 계좌 기본 정보 업데이트
  if (newName) {
    try {
      await authFetch(`/api/accounts/${accId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName })
      });
    } catch (err) {
      console.warn('Account name update error:', err);
    }
  }

  const payload = {
    max_hold_days: maxHold,
    reserve_ratio: (reserveRatioPct || 0) / 100.0,
    fee_rate: (feeRatePct || 0) / 100.0,
    normal_target_yield: (normalYieldPct || 0) / 100.0,
    normal_splits: normalSplits,
    safe_target_yield: (safeYieldPct || 0) / 100.0,
    safe_splits: safeSplits,
    riskoff_target_yield: (riskoffYieldPct || 0) / 100.0,
    riskoff_splits: riskoffSplits
  };

  try {
    const res = await authFetch(`/api/accounts/${accId}/strategy-params`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast('계좌 정보 및 전략 운용 변수가 성공적으로 저장되었습니다.', 'success');
      await openAccountDetailModal(accId, false);
      loadAccounts(true);
    } else {
      showToast(data.detail || '설정 저장에 실패했습니다.', 'error');
    }
  } catch (e) {
    showToast('설정 저장 중 오류가 발생했습니다.', 'error');
  }
}
window.saveAccountStrategyParams = saveAccountStrategyParams;

// -------------------------------------------------------------------
// 계좌명 변경 전용 모달 (헤더 1클릭 변경용)
// -------------------------------------------------------------------
function openRenameAccountModal(accId, curName) {
  const modal = document.getElementById('renameAccountModal');
  if (!modal) return;
  document.getElementById('rename-acc-id').value = accId;
  const input = document.getElementById('rename-acc-name-input');
  if (input) {
    input.value = curName || '';
  }
  modal.classList.add('active');
  modal.style.display = 'flex';
  setTimeout(() => { if (input) input.focus(); }, 50);
}
window.openRenameAccountModal = openRenameAccountModal;

async function submitRenameAccount() {
  const accId = document.getElementById('rename-acc-id').value;
  const newName = (document.getElementById('rename-acc-name-input').value || '').trim();
  if (!newName) {
    showToast('변경할 새 계좌명을 입력해주세요.', 'error');
    return;
  }
  try {
    const res = await authFetch(`/api/accounts/${accId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName })
    });
    const data = await res.json();
    if (data.success) {
      showToast('계좌명이 성공적으로 변경되었습니다.', 'success');
      closeModal('renameAccountModal');
      await openAccountDetailModal(accId, false);
      loadAccounts(true);
    } else {
      showToast(data.detail || '계좌명 변경에 실패했습니다.', 'error');
    }
  } catch (e) {
    showToast('계좌명 변경 중 오류가 발생했습니다.', 'error');
  }
}
window.submitRenameAccount = submitRenameAccount;

// -------------------------------------------------------------------
// 계좌 관련 제어 액션들
// -------------------------------------------------------------------
async function advanceAccountDay(accId) {
  try {
    const res = await authFetch(`/api/accounts/${accId}/advance-day`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('다음 거래일로 진행되었습니다.');
      await openAccountDetailModal(accId);
      loadAccounts(true);
    }
  } catch (e) {
    showToast('거래일 진행 실패', 'error');
  }
}

async function undoLastTradeRecord(accId) {
  if (!confirm('마지막 날짜의 거래 기록을 삭제하고 이전 상태로 되돌리시겠습니까?')) return;
  try {
    const res = await authFetch(`/api/accounts/${accId}/undo`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast('마지막 기록이 정상 취소되었습니다.');
      await openAccountDetailModal(accId);
      loadAccounts(true);
    }
  } catch (e) {
    showToast('취소 작업 실패', 'error');
  }
}

function openSettlementModal(accId) {
  const modal = document.getElementById('settlementModal');
  document.getElementById('settle-acc-id').value = accId;
  modal.classList.add('active');
}

async function submitSettlement() {
  const accId = document.getElementById('settle-acc-id').value;
  const closePrice = parseFloat(document.getElementById('settle-close-price').value);
  const buyQty = parseInt(document.getElementById('settle-buy-qty').value) || 0;
  const sellQty = parseInt(document.getElementById('settle-sell-qty').value) || 0;
  const memo = document.getElementById('settle-memo').value;

  if (isNaN(closePrice) || closePrice <= 0) {
    showToast('당일 종가를 올바르게 입력해주세요.', 'error');
    return;
  }

  try {
    const res = await authFetch(`/api/accounts/${accId}/close-settlement`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        close_price: closePrice,
        buy_qty: buyQty,
        sell_qty: sellQty,
        memo: memo
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast('당일 마감 정산이 완료되었습니다.');
      closeModal('settlementModal');
      await openAccountDetailModal(accId);
      loadAccounts(true);
    }
  } catch (e) {
    showToast('정산 기록 중 오류가 발생했습니다.', 'error');
  }
}

// -------------------------------------------------------------------
// 매매 일지 날짜 포맷 및 수정 모달
// -------------------------------------------------------------------
function formatTradeDate(dateStr) {
  if (!dateStr) return '-';
  const clean = String(dateStr).substring(0, 10);
  const parts = clean.split('-');
  if (parts.length === 3) {
    const y = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    const d = parseInt(parts[2], 10);
    const dt = new Date(y, m - 1, d);
    const days = ['일', '월', '화', '수', '목', '금', '토'];
    const dayName = days[dt.getDay()];
    const mm = String(m).padStart(2, '0');
    const dd = String(d).padStart(2, '0');
    return `${mm}.${dd}.(${dayName})`;
  }
  return dateStr;
}

function openEditTradeModal(accId, dateStr, close, buyQty, sellQty, mode, memo) {
  const modal = document.getElementById('editTradeModal');
  if (!modal) return;
  document.getElementById('edit-trade-acc-id').value = accId;
  document.getElementById('edit-trade-date').value = dateStr;
  document.getElementById('edit-trade-date-display').value = `${dateStr} [${formatTradeDate(dateStr)}]`;
  document.getElementById('edit-trade-close').value = close || '';
  document.getElementById('edit-trade-buy-qty').value = buyQty || 0;
  document.getElementById('edit-trade-sell-qty').value = sellQty || 0;
  const mLower = (mode || '').toLowerCase();
  document.getElementById('edit-trade-mode').value = mLower === 'safe' ? 'Safe' : (mLower.includes('risk') ? 'Riskoff' : 'Normal');
  document.getElementById('edit-trade-memo').value = memo || '';

  modal.classList.add('active');
  modal.style.display = 'flex';
}

async function submitEditTradeRecord() {
  const accId = document.getElementById('edit-trade-acc-id').value;
  const dateStr = document.getElementById('edit-trade-date').value;
  const closePrice = parseFloat(document.getElementById('edit-trade-close').value);
  const buyQty = parseInt(document.getElementById('edit-trade-buy-qty').value) || 0;
  const sellQty = parseInt(document.getElementById('edit-trade-sell-qty').value) || 0;
  const mode = document.getElementById('edit-trade-mode').value;
  const memo = document.getElementById('edit-trade-memo').value;

  if (isNaN(closePrice) || closePrice <= 0) {
    showToast('종가를 올바르게 입력해주세요.', 'error');
    return;
  }

  try {
    const res = await authFetch(`/api/accounts/${accId}/trade-records/edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: dateStr,
        close_price: closePrice,
        buy_qty: buyQty,
        sell_qty: sellQty,
        mode: mode,
        memo: memo
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast('매매 기록이 성공적으로 수정되었습니다.');
      closeModal('editTradeModal');
      await openAccountDetailModal(accId);
      loadAccounts(true);
    } else {
      showToast(data.detail || '수정에 실패했습니다.', 'error');
    }
  } catch (e) {
    showToast('수정 요청 중 오류가 발생했습니다.', 'error');
  }
}

function openAdjustmentModal(accId) {
  const modal = document.getElementById('adjustmentModal');
  document.getElementById('adj-acc-id').value = accId;
  document.getElementById('adj-date').value = new Date().toISOString().substring(0, 10);
  modal.classList.add('active');
}

async function submitAdjustment() {
  const accId = document.getElementById('adj-acc-id').value;
  const type = document.getElementById('adj-type').value;
  const amount = parseFloat(document.getElementById('adj-amount').value);
  const dateStr = document.getElementById('adj-date').value;
  const reason = document.getElementById('adj-reason').value;

  if (isNaN(amount) || amount <= 0) {
    showToast('입출금 금액을 올바르게 입력해주세요.', 'error');
    return;
  }

  try {
    const res = await authFetch(`/api/accounts/${accId}/adjustment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, amount, date: dateStr, reason })
    });
    const data = await res.json();
    if (data.success) {
      showToast('입출금 내역이 저장되었습니다.');
      closeModal('adjustmentModal');
      await openAccountDetailModal(accId);
      loadAccounts(true);
    }
  } catch (e) {
    showToast('입출금 처리 실패', 'error');
  }
}

function openNewAccountModal() {
  document.getElementById('new-acc-start-date').value = new Date().toISOString().substring(0, 10);
  document.getElementById('newAccountModal').classList.add('active');
}

async function submitNewAccount() {
  const name = document.getElementById('new-acc-name').value;
  const ticker = document.getElementById('new-acc-ticker').value;
  const strategy = document.getElementById('new-acc-strategy').value;
  const seed = parseFloat(document.getElementById('new-acc-seed').value);
  const startDate = document.getElementById('new-acc-start-date').value;
  const reserveRatio = parseFloat(document.getElementById('new-acc-reserve').value) || 0.05;
  const memo = document.getElementById('new-acc-memo').value;

  if (!name || !ticker || isNaN(seed) || seed <= 0) {
    showToast('필수 항목을 모두 올바르게 입력해주세요.', 'error');
    return;
  }

  try {
    const res = await authFetch('/api/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name, ticker, strategy,
        initial_seed: seed,
        start_date: startDate,
        reserve_ratio: reserveRatio,
        memo
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`'${name}' 계좌가 성공적으로 생성되었습니다.`);
      closeModal('newAccountModal');
      loadAccounts();
    }
  } catch (e) {
    showToast('계좌 생성 실패', 'error');
  }
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) {
    modal.classList.remove('active');
    modal.style.display = 'none';
  }
}

// -------------------------------------------------------------------
// 계좌별 자동매매 & 브로커 연동 모달 (Broker Settings Modal)
// -------------------------------------------------------------------
let currentBrokerAccId = null;
let currentBrokerConfig = null;

async function openAccountBrokerModal(accId) {
  currentBrokerAccId = accId;
  const modal = document.getElementById('accountBrokerModal');
  if (!modal) return;

  const keyInput = document.getElementById('meritz-app-key');
  const secInput = document.getElementById('meritz-app-secret');
  const keyBadge = document.getElementById('meritz-key-saved-badge');
  const secBadge = document.getElementById('meritz-sec-saved-badge');
  const resultBox = document.getElementById('meritz-verify-result-box');
  const subtitleEl = document.getElementById('broker-modal-acc-subtitle');

  if (keyInput) keyInput.value = '';
  if (secInput) secInput.value = '';
  if (resultBox) {
    resultBox.style.display = 'none';
    resultBox.innerHTML = '';
  }

  try {
    const res = await fetch(`/api/accounts/${accId}/broker`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const cfg = data.config || {};
    currentBrokerConfig = cfg;

    if (subtitleEl) {
      subtitleEl.textContent = `계좌: ${cfg.account_name || accId} (${cfg.ticker || ''})`;
    }

    const toggle = document.getElementById('broker-autotrade-toggle');
    if (toggle) toggle.checked = !!cfg.enabled;

    const select = document.getElementById('broker-select');
    if (select) select.value = cfg.broker || 'meritz';

    if (cfg.has_credentials) {
      if (keyBadge) keyBadge.style.display = 'inline-block';
      if (secBadge) secBadge.style.display = 'inline-block';
      if (keyInput) keyInput.placeholder = `등록됨 (${cfg.app_key_masked || '******'})`;
      if (secInput) secInput.placeholder = '등록됨 (변경 시에만 입력)';
    } else {
      if (keyBadge) keyBadge.style.display = 'none';
      if (secBadge) secBadge.style.display = 'none';
      if (keyInput) keyInput.placeholder = '발급받은 APP KEY 입력';
      if (secInput) secInput.placeholder = '발급받은 APP SECRET 입력';
    }

    if (resultBox) {
      resultBox.style.display = 'none';
      resultBox.innerHTML = '';
    }

    onAutoTradeToggleChange();
    onBrokerSelectChange();

    modal.style.display = 'flex';
  } catch (e) {
    console.error('브로커 설정 로드 실패:', e);
    showToast('계좌 브로커 설정을 불러오지 못했습니다.', 'error');
  }
}

function closeAccountBrokerModal() {
  const modal = document.getElementById('accountBrokerModal');
  if (modal) modal.style.display = 'none';
  currentBrokerAccId = null;
}

function onAutoTradeToggleChange() {
  const toggle = document.getElementById('broker-autotrade-toggle');
  const isEnabled = toggle ? toggle.checked : false;
  const selectContainer = document.getElementById('broker-select-container');

  if (selectContainer) {
    selectContainer.style.opacity = isEnabled ? '1' : '0.6';
  }
  onBrokerSelectChange();
}

function onBrokerSelectChange() {
  const select = document.getElementById('broker-select');
  const broker = select ? select.value : 'meritz';
  const toggle = document.getElementById('broker-autotrade-toggle');
  const isEnabled = toggle ? toggle.checked : false;

  const meritzForm = document.getElementById('broker-meritz-form');
  const pendingBanner = document.getElementById('broker-pending-banner');
  const pendingTitle = document.getElementById('broker-pending-title');
  const btnText = document.getElementById('btn-broker-save-text');
  const btnIcon = document.getElementById('btn-broker-save-icon');

  if (broker === 'kiwoom' || broker === 'kis') {
    if (meritzForm) meritzForm.style.display = 'none';
    if (pendingBanner) {
      pendingBanner.style.display = 'block';
      const name = broker === 'kiwoom' ? '키움증권 (영웅문 API)' : '한국투자증권 (KIS Developers)';
      if (pendingTitle) pendingTitle.textContent = `${name} - 구현 예정입니다`;
    }
    if (btnText) btnText.textContent = '설정 저장하기';
    if (btnIcon) btnIcon.textContent = '💾';
  } else {
    // meritz
    if (pendingBanner) pendingBanner.style.display = 'none';
    if (meritzForm) meritzForm.style.display = 'flex';
    if (btnText) {
      btnText.textContent = isEnabled ? 'Check & Save (연동 검증 및 저장)' : '설정 저장하기';
    }
    if (btnIcon) btnIcon.textContent = isEnabled ? '🔍' : '💾';
  }
}

async function handleBrokerCheckAndSave() {
  if (!currentBrokerAccId) return;

  const toggle = document.getElementById('broker-autotrade-toggle');
  const select = document.getElementById('broker-select');
  const keyInput = document.getElementById('meritz-app-key');
  const secInput = document.getElementById('meritz-app-secret');
  const btn = document.getElementById('btn-broker-save');
  const btnText = document.getElementById('btn-broker-save-text');
  const resultBox = document.getElementById('meritz-verify-result-box');

  const enabled = toggle ? toggle.checked : false;
  const broker = select ? select.value : 'meritz';
  const appKey = keyInput ? keyInput.value.trim() : '';
  const appSecret = secInput ? secInput.value.trim() : '';

  // 1. 키움 / 한국투자증권 선택 시
  if (broker === 'kiwoom' || broker === 'kis') {
    try {
      btn.disabled = true;
      const res = await fetch(`/api/accounts/${currentBrokerAccId}/broker`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ broker, enabled })
      });
      const data = await res.json();
      showToast(data.message || '설정이 저장되었습니다.');
      closeAccountBrokerModal();
      await loadAccounts();
      if (state.activeAccountDetail && state.activeAccountDetail.account && state.activeAccountDetail.account.id === currentBrokerAccId) {
        await openAccountDetailModal(currentBrokerAccId, false);
      }
    } catch (e) {
      showToast('설정 저장 실패: ' + e.message, 'error');
    } finally {
      btn.disabled = false;
    }
    return;
  }

  // 2. 메리츠증권 - 자동매매가 OFF이고 키 변경 없이 저장만 하는 경우
  if (!enabled && !appKey && !appSecret) {
    try {
      btn.disabled = true;
      const res = await fetch(`/api/accounts/${currentBrokerAccId}/broker`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ broker: 'meritz', enabled: false })
      });
      const data = await res.json();
      showToast('자동매매가 비활성화되었습니다.');
      closeAccountBrokerModal();
      await loadAccounts();
      if (state.activeAccountDetail && state.activeAccountDetail.account && state.activeAccountDetail.account.id === currentBrokerAccId) {
        await openAccountDetailModal(currentBrokerAccId, false);
      }
    } catch (e) {
      showToast('설정 저장 실패: ' + e.message, 'error');
    } finally {
      btn.disabled = false;
    }
    return;
  }

  // 3. 메리츠증권 - Check & Save 검증 및 저장
  try {
    btn.disabled = true;
    if (btnText) btnText.textContent = '⏳ 메리츠 Open API 검증 중...';
    if (resultBox) {
      resultBox.style.display = 'block';
      resultBox.style.background = 'rgba(56, 189, 248, 0.12)';
      resultBox.style.border = '1px solid rgba(56, 189, 248, 0.3)';
      resultBox.style.color = 'var(--accent-cyan)';
      resultBox.innerHTML = '메리츠증권 Open API에 접속하여 연동 검증을 진행하고 있습니다...';
    }

    const res = await fetch(`/api/accounts/${currentBrokerAccId}/broker/check-save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        broker: 'meritz',
        enabled: enabled,
        app_key: appKey || null,
        app_secret: appSecret || null
      })
    });

    const data = await res.json();

    if (data.success) {
      if (resultBox) {
        resultBox.style.background = 'rgba(16, 185, 129, 0.15)';
        resultBox.style.border = '1px solid rgba(16, 185, 129, 0.4)';
        resultBox.style.color = '#34d399';
        resultBox.innerHTML = `<strong>✅ 연동 검증 성공!</strong><br>메리츠증권 Open API 인증 및 암호화 저장이 완료되었습니다.`;
      }
      showToast('🎉 메리츠증권 연동 성공! 암호화 저장이 완료되었습니다.');
      
      setTimeout(async () => {
        closeAccountBrokerModal();
        await loadAccounts();
        if (state.activeAccountDetail && state.activeAccountDetail.account && state.activeAccountDetail.account.id === currentBrokerAccId) {
          await openAccountDetailModal(currentBrokerAccId, false);
        }
      }, 900);
    } else {
      if (resultBox) {
        resultBox.style.background = 'rgba(239, 68, 68, 0.15)';
        resultBox.style.border = '1px solid rgba(239, 68, 68, 0.4)';
        resultBox.style.color = '#f87171';
        resultBox.innerHTML = `<strong>❌ 연동 검증 실패:</strong><br>${data.message || 'API 연결에 실패했습니다. 키 값을 다시 확인해 주세요.'}`;
      }
      showToast('메리츠증권 검증 실패: ' + (data.message || '오류 발생'), 'error');
    }
  } catch (e) {
    console.error('Check & Save 에러:', e);
    if (resultBox) {
      resultBox.style.background = 'rgba(239, 68, 68, 0.15)';
      resultBox.style.border = '1px solid rgba(239, 68, 68, 0.4)';
      resultBox.style.color = '#f87171';
      resultBox.innerHTML = `<strong>❌ 통신 오류:</strong> ${e.message}`;
    }
    showToast('통신 오류: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    onBrokerSelectChange();
  }
}

// -------------------------------------------------------------------
// 백테스트 시뮬레이터
// -------------------------------------------------------------------
function initBacktestPresets() {
  document.querySelectorAll('.preset-period-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.preset-period-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const years = parseInt(btn.dataset.years);
      setBacktestPeriodByYears(years);
    });
  });

  // 초기 3년 기본 설정
  setBacktestPeriodByYears(3);
}

function formatLocalDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function setBacktestPeriodByYears(years) {
  const now = new Date();
  const days = years * 365; // 모바일 앱(timedelta(days=365*years))과 100% 동일한 일수 계산
  const start = new Date(now.getTime() - (days * 24 * 60 * 60 * 1000));

  document.getElementById('bt-start-date').value = formatLocalDate(start);
  document.getElementById('bt-end-date').value = formatLocalDate(now);
}

function resetBtJongJongParams() {
  if (document.getElementById('bt-jj-hold-days')) document.getElementById('bt-jj-hold-days').value = '10';
  if (document.getElementById('bt-jj-reserve-ratio')) document.getElementById('bt-jj-reserve-ratio').value = '5.00';
  if (document.getElementById('bt-jj-fee-rate')) document.getElementById('bt-jj-fee-rate').value = '0.000';
  if (document.getElementById('bt-jj-normal-yield')) document.getElementById('bt-jj-normal-yield').value = '2.75';
  if (document.getElementById('bt-jj-normal-splits')) document.getElementById('bt-jj-normal-splits').value = '8';
  if (document.getElementById('bt-jj-safe-yield')) document.getElementById('bt-jj-safe-yield').value = '0.25';
  if (document.getElementById('bt-jj-safe-splits')) document.getElementById('bt-jj-safe-splits').value = '7';
  if (document.getElementById('bt-jj-riskoff-yield')) document.getElementById('bt-jj-riskoff-yield').value = '0.70';
  if (document.getElementById('bt-jj-riskoff-splits')) document.getElementById('bt-jj-riskoff-splits').value = '5';
  showToast('종종이 전략 인자가 기본값으로 초기화되었습니다.');
}

async function runBacktest() {
  const ticker = document.getElementById('bt-ticker').value.trim().toUpperCase();
  const capital = parseFloat(document.getElementById('bt-capital').value) || 200000;
  const startDate = document.getElementById('bt-start-date').value;
  const endDate = document.getElementById('bt-end-date').value;
  const useAdjClose = document.getElementById('bt-adj-close') ? document.getElementById('bt-adj-close').checked : true;

  // 종종이 전략 맞춤 설정 인자 수집
  const holdDays = parseInt(document.getElementById('bt-jj-hold-days')?.value, 10) || 10;
  const reserveRatio = (parseFloat(document.getElementById('bt-jj-reserve-ratio')?.value) || 5.0) / 100.0;
  const feeRate = (parseFloat(document.getElementById('bt-jj-fee-rate')?.value) || 0.0) / 100.0;

  const normalYield = (parseFloat(document.getElementById('bt-jj-normal-yield')?.value) || 2.75) / 100.0;
  const normalSplits = parseFloat(document.getElementById('bt-jj-normal-splits')?.value) || 8.0;

  const safeYield = (parseFloat(document.getElementById('bt-jj-safe-yield')?.value) || 0.25) / 100.0;
  const safeSplits = parseFloat(document.getElementById('bt-jj-safe-splits')?.value) || 7.0;

  const riskoffYield = (parseFloat(document.getElementById('bt-jj-riskoff-yield')?.value) || 0.70) / 100.0;
  const riskoffSplits = parseFloat(document.getElementById('bt-jj-riskoff-splits')?.value) || 5.0;

  const jongjongParams = {
    max_hold_days: holdDays,
    reserve_ratio: reserveRatio,
    fee_rate: feeRate,
    target_yields: {
      'Normal': normalYield,
      'Safe': safeYield,
      'Riskoff': riskoffYield
    },
    div_rounds: {
      'Normal': normalSplits,
      'Safe': safeSplits,
      'Riskoff': riskoffSplits
    }
  };

  // 기본 비교군 4종(무한매수, VR5.0, 웅덩이, 단순보유)과 종종이 전략 항상 자동 시뮬레이션
  const strategies = [
    '종종이 전략',
    '무한매수법 v4.0',
    'VR 5.0 (밸류리밸런싱)',
    '웅덩이 매매법',
    `${ticker} 단순보유(B&H)`
  ];

  const runBtn = document.getElementById('btn-run-backtest');
  const loader = document.getElementById('bt-loader');
  runBtn.disabled = true;
  loader.style.display = 'inline-flex';

  try {
    const res = await fetch('/api/backtest/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker,
        capital,
        start_date: startDate,
        end_date: endDate,
        strategies,
        use_adj_close: useAdjClose,
        jongjong_params: jongjongParams
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '백테스트 실패');
    }

    const data = await res.json();
    state.backtestResults = data;
    renderBacktestResults(data);
    showToast(data.use_adj_close 
      ? '백테스트 완료: 배당금 재투자(Total Return)가 반영되었습니다.' 
      : '백테스트 완료: 단순 주가(Price Return) 기준입니다.');
  } catch (e) {
    showToast(`백테스트 실패: ${e.message}`, 'error');
  } finally {
    runBtn.disabled = false;
    loader.style.display = 'none';
  }
}

function renderBacktestResults(data) {
  const container = document.getElementById('backtest-results-container');
  container.style.display = 'block';

  // 1. 전략 비교 테이블
  const tableTitle = document.querySelector('#backtest-results-container .section-title');
  if (tableTitle) {
    tableTitle.innerHTML = `
      <span>🏆</span> 전략별 핵심 성과 지표 비교
      <span style="margin-left:10px;font-size:0.75rem;padding:3px 8px;border-radius:6px;font-weight:600;background:${data.use_adj_close ? 'rgba(16,185,129,0.15)' : 'rgba(148,163,184,0.15)'};color:${data.use_adj_close ? '#34d399' : '#94a3b8'};border:1px solid ${data.use_adj_close ? 'rgba(16,185,129,0.3)' : 'rgba(148,163,184,0.3)'}">
        ${data.use_adj_close ? '💰 배당 재투자(Total Return) 반영' : '📈 단순 종가(Price Return) 기준'}
      </span>
    `;
  }

  const tableBody = document.getElementById('bt-comparison-tbody');
  tableBody.innerHTML = data.strategies.map(s => {
    const m = s.metrics;
    const isWinner = s.name.includes('종종이');
    return `
      <tr style="${isWinner ? 'background: rgba(59, 130, 246, 0.08); font-weight: 600;' : ''}">
        <td>
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;background:${getStrategyColor(s.name)};"></span>
          ${s.name} ${isWinner ? '⭐' : ''}
        </td>
        <td style="font-weight:700;color:var(--text-primary);">${fmt.usdk(m.final_asset)}</td>
        <td style="color:${m.total_return >= 0 ? 'var(--profit-green)' : 'var(--loss-red)'};font-weight:700;">${fmt.pct(m.total_return)}</td>
        <td style="color:${m.cagr >= 0 ? 'var(--profit-green)' : 'var(--loss-red)'};">${fmt.pct(m.cagr)}</td>
        <td style="color:var(--loss-red);font-weight:700;">${fmt.pct(m.mdd)}</td>
        <td>${m.sharpe ? m.sharpe.toFixed(2) : '-'}</td>
        <td>${m.calmar ? m.calmar.toFixed(2) : '-'}</td>
        <td>${fmt.usdk(m.final_cash)}</td>
      </tr>
    `;
  }).join('');

  // 2. 자산 성장 곡선 차트 (Equity Curve)
  renderEquityChart(data);

  // 3. 낙폭 추이 차트 (Drawdown)
  renderDrawdownChart(data);
}

function getStrategyColor(name) {
  if (name.includes('종종이')) return '#06b6d4'; // Cyan
  if (name.includes('무한')) return '#3b82f6';   // Blue
  if (name.includes('VR')) return '#f59e0b';     // Amber
  if (name.includes('웅덩이')) return '#10b981'; // Emerald Green
  return '#94a3b8';                             // Muted Gray (B&H)
}

function renderEquityChart(data) {
  const canvas = document.getElementById('equityCurveChart');
  if (!canvas) return;

  if (state.charts.equity) {
    state.charts.equity.destroy();
  }

  const isLog = document.getElementById('bt-log-scale')?.checked || false;
  const labels = data.strategies[0]?.chart?.dates || [];

  const datasets = data.strategies.map(s => ({
    label: s.name,
    data: s.chart.assets,
    borderColor: getStrategyColor(s.name),
    backgroundColor: getStrategyColor(s.name) + '15',
    borderWidth: s.name.includes('종종이') ? 3 : 2,
    fill: s.name.includes('종종이'),
    tension: 0.1,
    pointRadius: 0,
    pointHoverRadius: 5
  }));

  state.charts.equity = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', maxTicksLimit: 12 }
        },
        y: {
          type: isLog ? 'logarithmic' : 'linear',
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: {
            color: '#64748b',
            callback: (v) => fmt.usdk(v)
          }
        }
      },
      plugins: {
        legend: { labels: { color: '#cbd5e1' } },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${fmt.usdk(ctx.raw)}`
          }
        }
      }
    }
  });
}

function renderDrawdownChart(data) {
  const canvas = document.getElementById('drawdownChart');
  if (!canvas) return;

  if (state.charts.drawdown) {
    state.charts.drawdown.destroy();
  }

  const labels = data.strategies[0]?.chart?.dates || [];
  const datasets = data.strategies.map(s => ({
    label: `${s.name} 낙폭`,
    data: s.chart.drawdowns,
    borderColor: getStrategyColor(s.name),
    backgroundColor: getStrategyColor(s.name) + '15',
    borderWidth: 1.5,
    fill: true,
    tension: 0.1,
    pointRadius: 0
  }));

  state.charts.drawdown = new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', maxTicksLimit: 12 }
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: {
            color: '#64748b',
            callback: (v) => `${v}%`
          }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${ctx.raw}%`
          }
        }
      }
    }
  });
}

function toggleLogScale() {
  if (state.backtestResults) {
    renderEquityChart(state.backtestResults);
  }
}

// -------------------------------------------------------------------
// 자동매매 토글
// -------------------------------------------------------------------
async function toggleAutotrade() {
  try {
    const res = await fetch('/api/autotrade/toggle', { method: 'POST' });
    const data = await res.json();
    showToast(`자동매매 상태가 '${data.status}'로 변경되었습니다.`);
    loadServerStatus();
  } catch (e) {
    showToast('자동매매 상태 변경 실패', 'error');
  }
}

// -------------------------------------------------------------------
// 토스트 알림
// -------------------------------------------------------------------
function showToast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${type === 'error' ? '⚠️' : '✅'}</span> <span>${msg}</span>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// -------------------------------------------------------------------
// 시스템 설정 모달 (텔레그램 / 자동매매 / 관리자)
// -------------------------------------------------------------------
let currentSettingTab = 'tg';

function switchSettingTab(tab) {
  currentSettingTab = tab;
  const tabs = ['tg', 'autotrade', 'admin'];

  tabs.forEach(t => {
    const btn = document.getElementById(`btn-setting-tab-${t}`);
    const panel = document.getElementById(`setting-panel-${t}`);
    const isActive = (tab === t);

    if (btn) {
      btn.classList.toggle('active', isActive);
      if (!isActive) btn.blur();
    }
    if (panel) {
      panel.style.display = isActive ? 'block' : 'none';
    }
  });

  const saveBtn = document.getElementById('btn-save-settings');
  if (saveBtn) {
    saveBtn.style.display = (tab === 'tg') ? 'inline-flex' : 'none';
  }

  if (tab === 'admin') {
    loadAdminUsers();
  } else if (tab === 'autotrade') {
    loadServerStatus();
    loadScheduleConfig();
  }
}

async function openSyncSettingsModal() {
  const adminBtn = document.getElementById('btn-setting-tab-admin');
  if (adminBtn) {
    adminBtn.style.display = (state.user && state.user.role === 'admin') ? 'inline-flex' : 'none';
  }

  switchSettingTab('tg'); // 기본으로 텔레그램 알림 탭 활성화
  document.getElementById('cloudSyncModal').classList.add('active');

  // 1. 텔레그램 설정 로드
  try {
    const resTg = await fetch('/api/telegram/config');
    if (resTg.ok) {
      const dataTg = await resTg.json();
      document.getElementById('tg-bot-token').value = dataTg.bot_token || '';
      document.getElementById('tg-chat-id').value = dataTg.chat_id || '';
      document.getElementById('tg-enabled-check').checked = Boolean(dataTg.enabled);
      
      const stEl = document.getElementById('tg-modal-status-text');
      if (stEl) {
        if (dataTg.enabled && dataTg.bot_token && dataTg.chat_id) {
          stEl.textContent = '연동 활성화 (Active)';
          stEl.style.color = 'var(--profit-green)';
        } else {
          stEl.textContent = '미연동 / 비활성화';
          stEl.style.color = 'var(--text-muted)';
        }
      }
      const timeEl = document.getElementById('tg-modal-last-time');
      if (timeEl) timeEl.textContent = dataTg.last_test_time || '테스트 이력 없음';
      const statusEl = document.getElementById('tg-modal-last-status');
      if (statusEl) statusEl.textContent = dataTg.last_test_status || '';
    }
  } catch (e) {
    console.error('Telegram config load error:', e);
  }
}

async function sendTelegramTest() {
  const bot_token = document.getElementById('tg-bot-token').value.trim();
  const chat_id = document.getElementById('tg-chat-id').value.trim();
  const testBtn = document.getElementById('btn-tg-test');

  if (!bot_token) {
    showToast('텔레그램 봇 토큰(Bot Token)을 먼저 입력해주세요.', 'error');
    document.getElementById('tg-bot-token').focus();
    return;
  }
  if (!chat_id) {
    showToast('텔레그램 챗 ID(Chat ID)를 먼저 입력해주세요.', 'error');
    document.getElementById('tg-chat-id').focus();
    return;
  }

  const origText = testBtn ? testBtn.innerHTML : '';
  if (testBtn) {
    testBtn.disabled = true;
    testBtn.innerHTML = '<span>⏳</span> 스마트폰으로 전송 중...';
  }

  try {
    const res = await fetch('/api/telegram/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bot_token, chat_id })
    });
    const data = await res.json();
    if (data.success) {
      showToast('스마트폰 텔레그램으로 테스트 메시지가 발송되었습니다! 🔔', 'success');
      const stEl = document.getElementById('tg-modal-status-text');
      if (stEl) {
        stEl.textContent = '연동 성공 (Active)';
        stEl.style.color = 'var(--profit-green)';
      }
      const timeEl = document.getElementById('tg-modal-last-time');
      if (timeEl) timeEl.textContent = new Date().toLocaleString();
      const statusEl = document.getElementById('tg-modal-last-status');
      if (statusEl) statusEl.textContent = 'SUCCESS';
    } else {
      showToast(`발송 실패: ${data.message}`, 'error');
    }
  } catch (e) {
    showToast(`전송 오류: ${e.message}`, 'error');
  } finally {
    if (testBtn) {
      testBtn.disabled = false;
      testBtn.innerHTML = origText;
    }
  }
}

async function saveActiveSettings() {
  if (currentSettingTab === 'tg') {
    // 텔레그램 설정 저장
    const bot_token = document.getElementById('tg-bot-token').value.trim();
    const chat_id = document.getElementById('tg-chat-id').value.trim();
    const enabled = document.getElementById('tg-enabled-check').checked;

    try {
      const res = await fetch('/api/telegram/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bot_token, chat_id, enabled, notify_on_orders: true })
      });
      const data = await res.json();
      if (data.success) {
        showToast('텔레그램 알림 설정이 저장되었습니다!');
        closeModal('cloudSyncModal');
      } else {
        showToast(`저장 실패: ${data.message}`, 'error');
      }
    } catch (e) {
      showToast('설정 저장 실패', 'error');
    }
  }
}

// -------------------------------------------------------------------
// 자동매매 정기 스케줄러 설정 (주문 20:20, 결산 05:10)
// -------------------------------------------------------------------
async function loadScheduleConfig() {
  const orderInput = document.getElementById('sched-order-time');
  const settleInput = document.getElementById('sched-settle-time');
  const toggle = document.getElementById('sched-enabled-toggle');
  const statusEl = document.getElementById('sched-last-run-status');
  if (!orderInput || !settleInput) return;

  try {
    const res = await fetch('/api/autotrade/schedule');
    const data = await res.json();
    if (data.success && data.config) {
      const cfg = data.config;
      orderInput.value = cfg.order_time || '20:20';
      settleInput.value = cfg.settle_time || '05:10';
      if (toggle) toggle.checked = cfg.enabled !== false;
      if (statusEl) {
        statusEl.textContent = cfg.last_order_status || cfg.last_settle_status || '정상 대기 중';
      }
    }
  } catch (e) {
    console.error('스케줄 설정 로드 실패:', e);
  }
}

async function saveScheduleConfig() {
  const order_time = document.getElementById('sched-order-time').value.trim() || '20:20';
  const settle_time = document.getElementById('sched-settle-time').value.trim() || '05:10';
  const toggle = document.getElementById('sched-enabled-toggle');
  const enabled = toggle ? toggle.checked : true;

  try {
    const res = await fetch('/api/autotrade/schedule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order_time, settle_time, enabled })
    });
    const data = await res.json();
    if (data.success) {
      showToast('🎉 자동매매 스케줄(주문/결산 시각)이 저장되었습니다!');
    } else {
      showToast(`저장 실패: ${data.message}`, 'error');
    }
  } catch (e) {
    showToast(`저장 오류: ${e.message}`, 'error');
  }
}

async function triggerManualOrders() {
  if (!confirm('현재 자동매매 활성화 계좌들의 당일 LOC 주문표를 지금 즉시 메리츠증권으로 전송하시겠습니까?')) return;
  try {
    showToast('⏳ 정기 자동매매 주문 전송을 실행하고 있습니다...');
    const res = await fetch('/api/autotrade/run-orders', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(`🎉 총 ${data.count}개 계좌 주문 전송 완료! (텔레그램 전송 확인)`);
      await loadAccounts();
    } else {
      showToast(`실행 실패: ${data.message}`, 'error');
    }
  } catch (e) {
    showToast(`실행 오류: ${e.message}`, 'error');
  }
}

async function triggerManualSettlement() {
  if (!confirm('현재 SOXL 최신 종가 및 체결 내역으로 정산하고 다음 거래일로 즉시 진행하시겠습니까?')) return;
  try {
    showToast('⏳ 일일 결산 및 익일 진행을 실행하고 있습니다...');
    const res = await fetch('/api/autotrade/run-settlement', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(`🎉 결산 완료 (종가: $${data.close_price})! 다음 거래일로 갱신되었습니다.`);
      await loadAccounts();
    } else {
      showToast(`결산 실패: ${data.message}`, 'error');
    }
  } catch (e) {
    showToast(`결산 오류: ${e.message}`, 'error');
  }
}

// -------------------------------------------------------------------
// 관리자 전용: 회원 목록 조회 및 계정 삭제
// -------------------------------------------------------------------
async function loadAdminUsers() {
  const tbody = document.getElementById('admin-users-tbody');
  const countBadge = document.getElementById('admin-user-count-badge');
  if (!tbody) return;

  try {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align:center;padding:2.5rem;color:var(--text-muted);">
          <span>🔄</span> 회원 목록을 조회하는 중입니다...
        </td>
      </tr>
    `;

    const res = await authFetch('/api/admin/users');
    if (!res.ok) {
      if (res.status === 403) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" style="text-align:center;padding:2.5rem;color:var(--loss-red);">
              ⚠️ 회원 관리 접근 권한이 없습니다. 관리자(Admin) 계정으로 로그인해주세요.
            </td>
          </tr>
        `;
        return;
      }
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    const users = data.users || [];
    if (countBadge) {
      countBadge.textContent = `총 ${users.length}명 등록됨`;
    }

    if (users.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align:center;padding:2.5rem;color:var(--text-muted);">
            등록된 회원이 없습니다.
          </td>
        </tr>
      `;
      return;
    }

    const currentUsername = state.user ? state.user.username.toLowerCase() : '';

    tbody.innerHTML = users.map((u, idx) => {
      const isMe = u.username.toLowerCase() === currentUsername;
      const isMaster = u.username.toLowerCase() === 'huxley';
      const isAdmin = u.role === 'admin';

      const roleBadge = isAdmin
        ? `<span class="badge" style="background:rgba(99,102,241,0.18);color:#a5b4fc;border:1px solid rgba(99,102,241,0.35);font-weight:600;padding:0.25rem 0.55rem;border-radius:4px;">👑 관리자</span>`
        : `<span class="badge" style="background:rgba(100,116,139,0.18);color:#94a3b8;border:1px solid rgba(100,116,139,0.3);padding:0.25rem 0.55rem;border-radius:4px;">👤 일반회원</span>`;

      const actionBtn = (isMe || isMaster)
        ? `<span class="badge" style="background:rgba(148,163,184,0.12);color:var(--text-muted);font-size:0.75rem;padding:0.25rem 0.5rem;border-radius:4px;">${isMe ? '본인 (삭제 불가)' : '마스터 관리자'}</span>`
        : `<button class="btn btn-danger btn-xs" onclick="deleteUserByAdmin('${u.username}')" style="padding:0.25rem 0.6rem;font-size:0.8rem;background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);cursor:pointer;border-radius:4px;">🗑️ 계정 삭제</button>`;

      return `
        <tr style="border-bottom:1px solid var(--border-subtle);">
          <td style="text-align:center;color:var(--text-muted);font-size:0.85rem;">${idx + 1}</td>
          <td>
            <div style="font-weight:600;color:var(--text-bright);display:flex;align-items:center;gap:0.4rem;">
              <span>${u.username}</span>
              ${isMe ? '<span style="font-size:0.7rem;color:#38bdf8;background:rgba(56,189,248,0.15);padding:0.1rem 0.35rem;border-radius:3px;">나</span>' : ''}
            </div>
          </td>
          <td style="color:var(--text-secondary);font-size:0.9rem;">
            ${u.email || '<span style="color:var(--text-muted);">-</span>'}
          </td>
          <td style="text-align:center;">${roleBadge}</td>
          <td style="color:var(--text-muted);font-size:0.85rem;">${u.created_at || '-'}</td>
          <td style="text-align:center;">${actionBtn}</td>
        </tr>
      `;
    }).join('');

  } catch (e) {
    console.error('loadAdminUsers error:', e);
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align:center;padding:2rem;color:var(--loss-red);">
          회원 목록을 불러오는 중 오류가 발생했습니다: ${e.message}
        </td>
      </tr>
    `;
    showToast('회원 목록 조회 실패', 'error');
  }
}

async function deleteUserByAdmin(targetUsername) {
  if (!targetUsername) return;
  const ok = confirm(`정말 '${targetUsername}' 회원을 영구 삭제하시겠습니까?\n\n⚠️ 해당 회원의 모든 투자 계좌와 데이터도 함께 삭제되며, 이 작업은 되돌릴 수 없습니다.`);
  if (!ok) return;

  try {
    const res = await authFetch(`/api/admin/users/${encodeURIComponent(targetUsername)}`, {
      method: 'DELETE'
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      showToast(data.detail || data.message || '회원 삭제에 실패했습니다.', 'error');
      return;
    }

    showToast(`'${targetUsername}' 회원이 정상적으로 삭제되었습니다.`, 'success');
    await loadAdminUsers();
  } catch (e) {
    showToast(`회원 삭제 처리 오류: ${e.message}`, 'error');
  }
}

