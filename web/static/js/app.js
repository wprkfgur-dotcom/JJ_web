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
    const linkedEl = document.getElementById('user-linked-badge');
    if (linkedEl) {
      if (state.accounts && state.accounts.length > 0) {
        if (state.accounts.length === 1) {
          linkedEl.textContent = `연동: ${state.accounts[0].name} (${state.accounts[0].ticker})`;
        } else {
          linkedEl.textContent = `연동: ${state.accounts[0].name} 외 ${state.accounts.length - 1}개`;
        }
      } else {
        linkedEl.textContent = '연동 계좌 조회 중...';
      }
    }

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
  const container = document.getElementById('ticker-ribbon');
  if (!container) return;

  container.innerHTML = WATCH_TICKERS.map(sym => `
    <div class="ticker-chip" onclick="quickFillBacktest('${sym}')" id="chip-${sym}">
      <span class="sym">${sym}</span>
      <span class="price" id="price-${sym}">조회중...</span>
      <span class="change" id="chg-${sym}"></span>
    </div>
  `).join('');

  for (const sym of WATCH_TICKERS) {
    try {
      const res = await fetch(`/api/market/quote/${sym}`);
      const data = await res.json();
      if (data && data.close > 0) {
        document.getElementById(`price-${sym}`).textContent = fmt.usd(data.close);
        const chgEl = document.getElementById(`chg-${sym}`);
        chgEl.textContent = fmt.pct(data.change_pct);
        chgEl.className = `change ${data.change_pct >= 0 ? 'up' : 'down'}`;
      }
    } catch (e) {
      console.warn(`시세 조회 실패: ${sym}`, e);
    }
  }
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
    renderDashboardOrders(data.accounts);
    renderAllocationDonut(data.accounts);

    // 헤더 사용자 계좌 상태 업데이트
    if (state.user) {
      const linkedEl = document.getElementById('user-linked-badge');
      if (linkedEl) {
        if (!data.accounts || data.accounts.length === 0) {
          linkedEl.textContent = '연동: 등록된 계좌 없음';
        } else if (data.accounts.length === 1) {
          linkedEl.textContent = `연동: ${data.accounts[0].name} (${data.accounts[0].ticker})`;
        } else {
          linkedEl.textContent = `연동: ${data.accounts[0].name} 외 ${data.accounts.length - 1}개`;
        }
      }
    }
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
    const isOwner = acc.is_my_account || (state.user && acc.owner === state.user.username);
    const ownerBadge = isOwner ? `<span class="badge badge-owner">⭐ 내 계좌 (${state.user ? state.user.username : 'Owner'})</span>` : '';
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
                ${ownerBadge}
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
// 대시보드 당일 주문표 종합
// -------------------------------------------------------------------
async function renderDashboardOrders(accounts) {
  const container = document.getElementById('dashboard-orders-container');
  if (!container) return;

  if (!accounts || accounts.length === 0) {
    container.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">등록된 계좌가 없습니다.</p>';
    return;
  }

  let rowsHtml = '';
  for (const acc of accounts) {
    try {
      const res = await authFetch(`/api/accounts/${acc.id}`);
      const data = await res.json();
      const orders = data.orders || {};
      const buyOrders = orders.buy_orders || [];
      const sellOrders = orders.sell_orders || [];

      if (buyOrders.length === 0 && sellOrders.length === 0) {
        continue;
      }

      // 매도 주문행
      sellOrders.forEach(o => {
        const { p, q, a, m } = parseOrderItem(o, '목표가 도달 시 청산');
        const typeStr = o['주문유형'] || 'LOC 매도';
        rowsHtml += `
          <tr>
            <td><strong>${acc.name}</strong> (${acc.ticker})</td>
            <td><span class="tag-sell">${typeStr}</span></td>
            <td>${fmt.usd(p)}</td>
            <td>${fmt.num(q)}주</td>
            <td>${fmt.usd(a)}</td>
            <td><span style="font-size:0.75rem;color:var(--text-muted);">${m}</span></td>
          </tr>
        `;
      });

      // 매수 주문행
      buyOrders.forEach(o => {
        const { p, q, a, m } = parseOrderItem(o, '분할 LOC 매수');
        const typeStr = o['주문유형'] || 'LOC 매수';
        rowsHtml += `
          <tr>
            <td><strong>${acc.name}</strong> (${acc.ticker})</td>
            <td><span class="tag-buy">${typeStr}</span></td>
            <td>${fmt.usd(p)}</td>
            <td>${fmt.num(q)}주</td>
            <td>${fmt.usd(a)}</td>
            <td><span style="font-size:0.75rem;color:var(--text-muted);">${m}</span></td>
          </tr>
        `;
      });
    } catch (e) {
      console.warn(e);
    }
  }

  if (rowsHtml) {
    container.innerHTML = `
      <table class="custom-table">
        <thead>
          <tr>
            <th>계좌 / 종목</th>
            <th>주문 구분</th>
            <th>주문 단가</th>
            <th>수량</th>
            <th>주문 예상액</th>
            <th>주문 메모</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    `;
  } else {
    container.innerHTML = `
      <div style="padding: 1.5rem; text-align: center; color: var(--text-muted);">
        오늘 대기 중인 LOC 주문이 없거나 마감 정산이 완료되었습니다.
      </div>
    `;
  }
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
      headerTitle.textContent = `${acc.name} (${acc.ticker})`;
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

  // 3. 매매 일지 서브탭
  const recordsPane = document.getElementById('subtab-records');
  if (recordsPane) {
    if (records.length > 0) {
      const reversed = [...records].reverse();
      recordsPane.innerHTML = `
        <div style="display:flex;justify-content:flex-end;margin-bottom:0.75rem;">
          <button class="btn btn-danger btn-sm" onclick="undoLastTradeRecord('${acc.id}')">↩ 마지막 기록 취소 (Undo)</button>
        </div>
        <table class="custom-table">
          <thead>
            <tr>
              <th>날짜</th>
              <th>종가</th>
              <th>매수량</th>
              <th>매도량</th>
              <th>실현손익</th>
              <th>예수금</th>
              <th>보유수량</th>
              <th>총자산</th>
            </tr>
          </thead>
          <tbody>
            ${reversed.map(r => `
              <tr>
                <td>${r.Date ? String(r.Date).substring(0, 10) : ''}</td>
                <td>${fmt.usd(r.Close)}</td>
                <td>${r.R ? `${fmt.num(r.R)}주` : '-'}</td>
                <td>${r.SellQty ? `${fmt.num(r.SellQty)}주` : '-'}</td>
                <td style="${r.Profit > 0 ? 'color:var(--profit-green);font-weight:700;' : (r.Profit < 0 ? 'color:var(--loss-red);font-weight:700;' : '')}">
                  ${r.Profit !== null && r.Profit !== undefined ? fmt.usd(r.Profit) : '-'}
                </td>
                <td>${fmt.usd(r.Cash)}</td>
                <td>${fmt.num(r.Hold)}주</td>
                <td><strong>${fmt.usd(r.Asset)}</strong></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
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
}

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
  if (modal) modal.classList.remove('active');
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

async function runBacktest() {
  const ticker = document.getElementById('bt-ticker').value.trim().toUpperCase();
  const capital = parseFloat(document.getElementById('bt-capital').value) || 200000;
  const startDate = document.getElementById('bt-start-date').value;
  const endDate = document.getElementById('bt-end-date').value;
  const useAdjClose = document.getElementById('bt-adj-close') ? document.getElementById('bt-adj-close').checked : true;

  const strategies = [];
  if (document.getElementById('strat-jj').checked) strategies.push('종종이 기본전략');
  if (document.getElementById('strat-inf').checked) strategies.push('무한매수법 v4.0');
  if (document.getElementById('strat-vr').checked) strategies.push('VR 5.0 (밸류리밸런싱)');
  if (document.getElementById('strat-puddle')?.checked) strategies.push('웅덩이 매매법');
  if (document.getElementById('strat-bnh').checked) strategies.push(`${ticker} 단순보유(B&H)`);

  if (strategies.length === 0) {
    showToast('비교할 전략을 최소 1개 이상 선택해주세요.', 'error');
    return;
  }

  const runBtn = document.getElementById('btn-run-backtest');
  const loader = document.getElementById('bt-loader');
  runBtn.disabled = true;
  loader.style.display = 'inline-flex';

  try {
    const res = await fetch('/api/backtest/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker, capital,
        start_date: startDate,
        end_date: endDate,
        strategies,
        use_adj_close: useAdjClose
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

