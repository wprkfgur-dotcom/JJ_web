/**
 * JJ Invest - Mobile Web Application Controller
 * Optimized for Mobile Safari & Android Chrome
 */

// PC 버전과 동일한 저장 키를 사용하여 로그인 세션을 공유한다.
const M_TOKEN_KEY = 'jj_auth_token';
const M_USER_KEY = 'jj_auth_user';

const mState = {
  token: localStorage.getItem(M_TOKEN_KEY) || sessionStorage.getItem(M_TOKEN_KEY) || '',
  user: null,
  portfolio: null,
  accounts: [],
  currentAccountId: null,
  currentAccountData: null,
  activeTab: 'dashboard',
  activeDetailSubtab: 'orders',
  backtestChart: null
};

const mFmt = {
  usd: (v) => '$' + (Number(v) || 0).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 }),
  pct: (v) => ((Number(v) >= 0 ? '+' : '') + (Number(v) || 0).toFixed(2) + '%'),
  num: (v) => (Number(v) || 0).toLocaleString('en-US')
};

function mToast(msg, isError = false) {
  const toast = document.getElementById('m-toast-box');
  if (!toast) return;
  toast.textContent = msg;
  toast.style.borderColor = isError ? 'var(--m-loss-red)' : 'var(--m-accent-cyan)';
  toast.style.display = 'block';
  setTimeout(() => { toast.style.display = 'none'; }, 2500);
}

async function mApi(endpoint, options = {}) {
  const headers = options.headers || {};
  if (mState.token) {
    headers['Authorization'] = `Bearer ${mState.token}`;
  }
  options.headers = headers;
  
  const res = await fetch(endpoint, options);
  if (res.status === 401) {
    mLogout();
    throw new Error('인증이 만료되었습니다. 다시 로그인해주세요.');
  }
  return res;
}

// =====================================================================
// Auth & Lifecycle
// =====================================================================
document.addEventListener('DOMContentLoaded', async () => {
  initDatePresets();
  if (mState.token) {
    await checkAuth();
  } else {
    showLoginView();
  }
});

async function checkAuth() {
  try {
    const res = await mApi('/api/auth/me');
    if (!res.ok) throw new Error();
    const data = await res.json();
    if (!data.authenticated || !data.user) throw new Error();
    mState.user = data.user;
    showAppView();
    loadAccounts();
    loadSettings();
  } catch (e) {
    showLoginView();
  }
}

function showLoginView() {
  document.getElementById('m-login-view').style.display = 'block';
  document.getElementById('m-app-view').style.display = 'none';
  document.getElementById('m-bottom-nav').style.display = 'none';
}

function showAppView() {
  document.getElementById('m-login-view').style.display = 'none';
  document.getElementById('m-app-view').style.display = 'block';
  document.getElementById('m-bottom-nav').style.display = 'flex';
  
  if (mState.user) {
    const nameEl = document.getElementById('m-header-user-name');
    if (nameEl) nameEl.textContent = mState.user.username;
  }
}

async function handleMobileLogin(e) {
  e.preventDefault();
  const u = document.getElementById('m-login-user').value.trim();
  const p = document.getElementById('m-login-pass').value.trim();
  
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p })
    });
    const data = await res.json();
    if (!res.ok || !data.success) throw new Error(data.detail || data.message || '로그인 실패');
    
    mState.token = data.token;
    mState.user = data.user;
    localStorage.setItem(M_TOKEN_KEY, data.token);
    localStorage.setItem(M_USER_KEY, JSON.stringify(data.user));
    mToast('로그인 성공!');
    showAppView();
    loadAccounts();
    loadSettings();
  } catch (err) {
    mToast(err.message, true);
  }
}

function mLogout() {
  [localStorage, sessionStorage].forEach(s => {
    s.removeItem(M_TOKEN_KEY);
    s.removeItem(M_USER_KEY);
  });
  mState.token = '';
  mState.user = null;
  mToast('로그아웃 되었습니다.');
  showLoginView();
}

// =====================================================================
// Navigation
// =====================================================================
function mSwitchTab(tabName) {
  mState.activeTab = tabName;
  
  document.querySelectorAll('.m-view-section').forEach(sec => sec.classList.remove('active'));
  document.querySelectorAll('.m-nav-item').forEach(item => item.classList.remove('active'));
  
  const targetSec = document.getElementById(`m-section-${tabName}`);
  if (targetSec) targetSec.classList.add('active');
  
  const targetNav = document.getElementById(`m-nav-${tabName}`);
  if (targetNav) targetNav.classList.add('active');
  
  // 탭별 새로고침
  if (tabName === 'dashboard') loadDashboard();
  if (tabName === 'accounts') {
    closeAccountDetail();
    loadAccounts();
  }
  if (tabName === 'settings') loadSettings();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// =====================================================================
// Dashboard
// =====================================================================
// 대시보드와 계좌 목록은 동일한 /api/accounts 응답을 공유한다.
async function loadDashboard() {
  await loadAccounts();
}

function renderDashboard() {
  const p = mState.portfolio;
  if (!p) return;
  
  document.getElementById('m-hero-asset').textContent = mFmt.usd(p.total_asset);
  
  const profitEl = document.getElementById('m-hero-profit');
  const isProfit = p.total_profit >= 0;
  profitEl.innerHTML = `
    <span style="color:${isProfit ? 'var(--m-profit-green)' : 'var(--m-loss-red)'}">
      ${isProfit ? '▲' : '▼'} ${mFmt.usd(p.total_profit)} (${mFmt.pct(p.return_pct)})
    </span>
  `;
  
  document.getElementById('m-sub-cash').textContent = mFmt.usd(p.total_cash);
  document.getElementById('m-sub-seed').textContent = mFmt.usd(p.total_seed);
  
  // 대시보드 내 계좌 빠른 리스트
  const listEl = document.getElementById('m-dash-accounts-list');
  if (listEl) {
    if (mState.accounts.length === 0) {
      listEl.innerHTML = `<div style="text-align:center;padding:1.5rem;color:var(--m-text-muted);">등록된 계좌가 없습니다.</div>`;
    } else {
      listEl.innerHTML = mState.accounts.map(acc => renderAccountItemHtml(acc)).join('');
    }
  }
}

function renderAccountItemHtml(acc) {
  const isProfit = acc.total_profit >= 0;
  return `
    <div class="m-account-item" onclick="openAccountDetail('${acc.id}')">
      <div class="m-acc-header">
        <div class="m-acc-name-group">
          <span class="m-ticker-badge">${acc.ticker}</span>
          <span class="m-acc-name">${acc.name}</span>
        </div>
        <span class="m-strat-tag">${acc.strategy}</span>
      </div>
      <div class="m-acc-metrics">
        <div>
          <div style="font-size:0.75rem;color:var(--m-text-muted);">총 평가액</div>
          <div style="font-size:1.15rem;font-weight:800;color:#fff;">${mFmt.usd(acc.total_asset)}</div>
        </div>
        <div style="text-align:right;">
          <span class="m-badge ${isProfit ? 'm-badge-profit' : 'm-badge-loss'}">
            ${mFmt.pct(acc.return_pct)}
          </span>
          <div style="font-size:0.75rem;color:var(--m-text-secondary);margin-top:2px;">
            ${mFmt.usd(acc.total_profit)}
          </div>
        </div>
      </div>
    </div>
  `;
}

// =====================================================================
// Accounts & Detail View
// =====================================================================
async function loadAccounts() {
  try {
    const res = await mApi('/api/accounts');
    if (!res.ok) return;
    const data = await res.json();
    mState.portfolio = data.portfolio;
    mState.accounts = data.accounts || [];
    renderDashboard();
    renderAccountsView();
  } catch (e) {
    console.error('계좌 로드 오류:', e);
  }
}

function renderAccountsView() {
  const container = document.getElementById('m-accounts-container');
  if (!container) return;
  if (mState.accounts.length === 0) {
    container.innerHTML = `<div style="text-align:center;padding:2rem;color:var(--m-text-muted);">등록된 투자 계좌가 없습니다.<br>상단 버튼으로 계좌를 등록해보세요.</div>`;
    return;
  }
  container.innerHTML = mState.accounts.map(acc => renderAccountItemHtml(acc)).join('');
}

async function openAccountDetail(accId) {
  mState.currentAccountId = accId;
  document.getElementById('m-accounts-list-wrap').style.display = 'none';
  const detailWrap = document.getElementById('m-account-detail-wrap');
  detailWrap.style.display = 'block';
  window.scrollTo({ top: 0, behavior: 'smooth' });
  
  try {
    const res = await mApi(`/api/accounts/${accId}`);
    if (!res.ok) throw new Error('계좌 조회 실패');
    const data = await res.json();
    mState.currentAccountData = data;
    renderAccountDetail(data);
  } catch (e) {
    mToast(e.message, true);
    closeAccountDetail();
  }
}

function closeAccountDetail() {
  mState.currentAccountId = null;
  mState.currentAccountData = null;
  const listWrap = document.getElementById('m-accounts-list-wrap');
  if (listWrap) listWrap.style.display = 'block';
  const detailWrap = document.getElementById('m-account-detail-wrap');
  if (detailWrap) detailWrap.style.display = 'none';
}

function renderAccountDetail(data) {
  const acc = data.account;
  const det = data.details || {};
  
  document.getElementById('m-det-title').textContent = acc.name;
  document.getElementById('m-det-ticker').textContent = acc.ticker;
  document.getElementById('m-det-strat').textContent = acc.strategy;
  
  document.getElementById('m-det-asset').textContent = mFmt.usd(det.current_asset);
  const profitEl = document.getElementById('m-det-profit');
  const isProfit = (det.total_profit || 0) >= 0;
  profitEl.innerHTML = `
    <span style="color:${isProfit ? 'var(--m-profit-green)' : 'var(--m-loss-red)'}">
      ${isProfit ? '▲' : '▼'} ${mFmt.usd(det.total_profit)} (${mFmt.pct(det.total_return_pct)})
    </span>
  `;
  
  document.getElementById('m-det-cash').textContent = mFmt.usd(det.current_cash);
  document.getElementById('m-det-hold').textContent = `${mFmt.num(det.current_hold)} 주`;
  document.getElementById('m-det-price').textContent = mFmt.usd(det.current_price);
  document.getElementById('m-det-date').textContent = det.target_order_date || acc.current_date;
  
  mSwitchDetailSubtab('orders');
}

function mSwitchDetailSubtab(subtab) {
  mState.activeDetailSubtab = subtab;
  document.querySelectorAll('.m-subtab-btn').forEach(b => b.classList.remove('active'));
  const activeBtn = document.getElementById(`m-subtab-btn-${subtab}`);
  if (activeBtn) activeBtn.classList.add('active');
  
  const container = document.getElementById('m-detail-content-area');
  const data = mState.currentAccountData;
  if (!data) return;
  
  if (subtab === 'orders') renderMobileOrders(container, data);
  if (subtab === 'unsold') renderMobileUnsold(container, data);
  if (subtab === 'records') renderMobileRecords(container, data);
  if (subtab === 'adjustments') renderMobileAdjustments(container, data);
}

// 주문 항목은 영문/한글 키가 혼재하므로 한 곳에서 정규화한다.
function mNormOrder(o) {
  const price = Number(o.price ?? o['주문단가']) || 0;
  const qty = Number(o.qty ?? o.shares ?? o['주문수량']) || 0;
  const amount = Number(o.amount ?? o['예상금액']) || price * qty;
  const label = o['주문유형'] || o.type || '';
  const memo = o['비고'] || o.memo || o['체결조건'] || o['구분'] || o['호가단계'] || '';
  return { price, qty, amount, label, memo };
}

function renderMobileOrders(container, data) {
  const buyOrders = data.orders?.buy_orders || [];
  const sellOrders = data.orders?.sell_orders || [];
  const netting = data.orders?.netting_info;
  
  let html = '';
  
  // 상계 요약 배너
  if (netting && netting.needs_action) {
    html += `
      <div style="background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.3);padding:0.8rem;border-radius:10px;margin-bottom:0.85rem;">
        <div style="font-weight:700;color:var(--m-accent-cyan);font-size:0.85rem;margin-bottom:0.2rem;">
          ⚡ 최종 상계 주문: ${netting.action_type === 'BUY' ? '순매수' : '순매도'} ${netting.net_qty}주
        </div>
        <div style="font-size:0.775rem;color:var(--m-text-secondary);">
          체결 예상 금액: ${mFmt.usd(netting.est_amount)} (매수 ${netting.total_buy_qty}주 / 매도 ${netting.total_sell_qty}주)
        </div>
      </div>
    `;
  }
  
  // 매수 주문
  html += `<div style="font-size:0.8rem;font-weight:700;color:var(--m-accent-blue);margin:0.5rem 0;">📥 예약 매수 주문 (${buyOrders.length}건)</div>`;
  if (buyOrders.length === 0) {
    html += `<div style="color:var(--m-text-muted);font-size:0.775rem;padding:0.5rem 0;">당일 매수 주문이 없습니다.</div>`;
  } else {
    html += buyOrders.map(raw => {
      const o = mNormOrder(raw);
      return `
      <div class="m-order-card buy">
        <div>
          <div class="m-order-type">${o.label || '매수'}${o.memo ? ` [${o.memo}]` : ''}</div>
          <div class="m-order-detail">${mFmt.num(o.qty)}주 · 소요예상 ${mFmt.usd(o.amount)}</div>
        </div>
        <div class="m-order-price" style="color:var(--m-accent-blue);">
          ${mFmt.usd(o.price)}
        </div>
      </div>
    `;
    }).join('');
  }
  
  // 매도 주문
  html += `<div style="font-size:0.8rem;font-weight:700;color:var(--m-loss-red);margin:0.8rem 0 0.5rem;">📤 지정가 매도 주문 (${sellOrders.length}건)</div>`;
  if (sellOrders.length === 0) {
    html += `<div style="color:var(--m-text-muted);font-size:0.775rem;padding:0.5rem 0;">당일 매도 주문이 없습니다.</div>`;
  } else {
    html += sellOrders.map(raw => {
      const o = mNormOrder(raw);
      return `
      <div class="m-order-card sell">
        <div>
          <div class="m-order-type">${o.label || '지정가 매도'}${o.memo ? ` [${o.memo}]` : ''}</div>
          <div class="m-order-detail">${mFmt.num(o.qty)}주 · 예상회수 ${mFmt.usd(o.amount)}</div>
        </div>
        <div class="m-order-price" style="color:var(--m-loss-red);">
          ${mFmt.usd(o.price)}
        </div>
      </div>
    `;
    }).join('');
  }
  
  container.innerHTML = html;
}

function renderMobileUnsold(container, data) {
  const lots = data.unsold_lots || [];
  if (lots.length === 0) {
    container.innerHTML = `<div style="text-align:center;padding:1.5rem;color:var(--m-text-muted);">미매도 슬롯(보유 포지션)이 없습니다.</div>`;
    return;
  }
  
  container.innerHTML = lots.map((lot, idx) => {
    // 슬롯 필드: date(매수일), R(수량), U(목표가), hold_days. 매수가는 별도 필드가 없을 수 있다.
    const qty = Number(lot.R ?? lot.qty) || 0;
    const target = Number(lot.U ?? lot.target_price) || 0;
    const buyPrice = Number(lot.price ?? lot.buy_price) || 0;
    const cur = Number(data.details?.current_price) || 0;
    const profitPct = buyPrice > 0 ? ((cur - buyPrice) / buyPrice) * 100 : 0;
    const isP = profitPct >= 0;
    return `
      <div style="background:rgba(15,23,42,0.7);border:1px solid var(--m-border-subtle);border-radius:8px;padding:0.75rem;margin-bottom:0.5rem;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-weight:700;font-size:0.825rem;color:#fff;">#${idx+1} ${lot.date || ''} (${qty}주)</span>
          ${buyPrice > 0 ? `<span class="m-badge ${isP ? 'm-badge-profit' : 'm-badge-loss'}">${mFmt.pct(profitPct)}</span>` : ''}
        </div>
        <div style="display:flex;justify-content:space-between;font-size:0.75rem;color:var(--m-text-secondary);margin-top:0.35rem;">
          <span>보유일: ${lot.hold_days ?? '-'}일</span>
          <span>목표가: ${mFmt.usd(target)}</span>
        </div>
      </div>
    `;
  }).join('');
}

function renderMobileRecords(container, data) {
  const records = data.trade_records || [];
  if (records.length === 0) {
    container.innerHTML = `<div style="text-align:center;padding:1.5rem;color:var(--m-text-muted);">기록된 매매일지가 없습니다.</div>`;
    return;
  }
  
  container.innerHTML = records.slice().reverse().map(r => `
    <div style="background:rgba(15,23,42,0.6);border:1px solid var(--m-border-subtle);border-radius:8px;padding:0.7rem;margin-bottom:0.5rem;font-size:0.775rem;">
      <div style="display:flex;justify-content:space-between;font-weight:700;color:#fff;">
        <span>${r.Date} (종가: ${mFmt.usd(r.Close)})</span>
        <span>자산: ${mFmt.usd(r.Asset)}</span>
      </div>
      <div style="color:var(--m-text-secondary);margin-top:0.25rem;">
        매수 ${r.R || 0}주 · 매도 ${r.SellQty || 0}주 · 현금 ${mFmt.usd(r.Cash)}
      </div>
    </div>
  `).join('');
}

function renderMobileAdjustments(container, data) {
  const adjs = data.adjustments || [];
  if (adjs.length === 0) {
    container.innerHTML = `<div style="text-align:center;padding:1.5rem;color:var(--m-text-muted);">입출금 내역이 없습니다.</div>`;
    return;
  }
  container.innerHTML = adjs.map(a => `
    <div style="background:rgba(15,23,42,0.6);border:1px solid var(--m-border-subtle);border-radius:8px;padding:0.7rem;margin-bottom:0.5rem;display:flex;justify-content:space-between;align-items:center;">
      <div>
        <div style="font-weight:700;color:#fff;font-size:0.8rem;">${a.type === 'DEPOSIT' ? '💵 입금' : '💸 출금'}</div>
        <div style="font-size:0.725rem;color:var(--m-text-muted);">${a.date} · ${a.reason || ''}</div>
      </div>
      <div style="font-weight:800;font-size:0.95rem;color:${a.type === 'DEPOSIT' ? 'var(--m-profit-green)' : 'var(--m-loss-red)'};">
        ${a.type === 'DEPOSIT' ? '+' : '-'}${mFmt.usd(a.amount)}
      </div>
    </div>
  `).join('');
}

// =====================================================================
// Account Actions (Advance, Settle, Undo)
// =====================================================================
async function mAdvanceDay() {
  if (!mState.currentAccountId) return;
  if (!confirm('다음 미국 개장일로 진행하고 (예약)매수/매도 주문표를 생성하시겠습니까?')) return;
  
  try {
    const res = await mApi(`/api/accounts/${mState.currentAccountId}/advance-day`, { method: 'POST' });
    if (!res.ok) throw new Error('진행 실패');
    mToast('다음 거래일 주문표가 생성되었습니다! 텔레그램 알림 발송됨');
    await openAccountDetail(mState.currentAccountId);
    loadDashboard();
  } catch (e) {
    mToast(e.message, true);
  }
}

// 계좌 생성은 PC 버전에서 지원한다.
function mOpenCreateAccountModal() {
  mToast('계좌 등록은 PC 버전에서 이용해주세요. (?view=pc)', true);
}

function mOpenSettlementModal() {
  const d = mState.currentAccountData;
  if (!d) return;
  document.getElementById('m-settle-close').value = d.details?.current_price || '';
  document.getElementById('m-settle-buy-qty').value = '';
  document.getElementById('m-settle-buy-price').value = d.details?.current_price || '';
  document.getElementById('m-settle-sell-qty').value = '';
  document.getElementById('m-settle-sell-price').value = d.details?.current_price || '';
  document.getElementById('m-modal-settle').classList.add('active');
}

async function mSubmitSettlement(e) {
  e.preventDefault();
  const c = parseFloat(document.getElementById('m-settle-close').value);
  const bq = parseInt(document.getElementById('m-settle-buy-qty').value) || 0;
  const bp = parseFloat(document.getElementById('m-settle-buy-price').value) || c;
  const sq = parseInt(document.getElementById('m-settle-sell-qty').value) || 0;
  const sp = parseFloat(document.getElementById('m-settle-sell-price').value) || c;
  
  try {
    const res = await mApi(`/api/accounts/${mState.currentAccountId}/close-settlement`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        close_price: c,
        buy_qty: bq,
        buy_price: bp,
        sell_qty: sq,
        sell_price: sp
      })
    });
    if (!res.ok) throw new Error('정산 실패');
    mToast('장마감 정산이 완료되었습니다.');
    mCloseModal('m-modal-settle');
    await openAccountDetail(mState.currentAccountId);
    loadDashboard();
  } catch (err) {
    mToast(err.message, true);
  }
}

async function mUndoLastTrade() {
  if (!mState.currentAccountId) return;
  if (!confirm('마지막 거래일 정산 기록을 취소(Undo)하시겠습니까?')) return;
  
  try {
    const res = await mApi(`/api/accounts/${mState.currentAccountId}/undo`, { method: 'POST' });
    if (!res.ok) throw new Error('취소 실패');
    mToast('마지막 거래가 취소되었습니다.');
    await openAccountDetail(mState.currentAccountId);
    loadDashboard();
  } catch (e) {
    mToast(e.message, true);
  }
}

function mCloseModal(id) {
  const el = document.getElementById(id);
  if (el) {
    el.classList.remove('active');
    el.style.display = 'none';
  }
}

// =====================================================================
// 모바일 계좌별 자동매매 & 브로커 연동 모달 제어
// =====================================================================
let mCurrentBrokerAccId = null;

async function mOpenBrokerModal() {
  const data = mState.currentAccountData;
  if (!data || !data.account) return;
  const accId = data.account.id;
  mCurrentBrokerAccId = accId;

  const modal = document.getElementById('m-modal-broker');
  if (!modal) return;

  const keyInput = document.getElementById('m-meritz-app-key');
  const secInput = document.getElementById('m-meritz-app-secret');
  const keyBadge = document.getElementById('m-meritz-key-saved-badge');
  const secBadge = document.getElementById('m-meritz-sec-saved-badge');
  const resultBox = document.getElementById('m-meritz-verify-result-box');
  const titleEl = document.getElementById('m-broker-sheet-title');

  if (keyInput) keyInput.value = '';
  if (secInput) secInput.value = '';
  if (resultBox) {
    resultBox.style.display = 'none';
    resultBox.innerHTML = '';
  }

  try {
    const res = await fetch(`/api/accounts/${accId}/broker`);
    const json = await res.json();
    const cfg = json.config || {};

    if (titleEl) {
      titleEl.textContent = `🤖 ${cfg.account_name || '계좌'} 자동매매 설정`;
    }

    const toggle = document.getElementById('m-broker-autotrade-toggle');
    if (toggle) toggle.checked = !!cfg.enabled;

    const select = document.getElementById('m-broker-select');
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

    mOnAutoTradeToggleChange();
    mOnBrokerSelectChange();

    modal.style.display = 'flex';
    modal.classList.add('active');
  } catch (e) {
    mToast('브로커 설정을 불러오지 못했습니다: ' + e.message, true);
  }
}

function mOnAutoTradeToggleChange() {
  mOnBrokerSelectChange();
}

function mOnBrokerSelectChange() {
  const select = document.getElementById('m-broker-select');
  const broker = select ? select.value : 'meritz';
  const toggle = document.getElementById('m-broker-autotrade-toggle');
  const isEnabled = toggle ? toggle.checked : false;

  const meritzForm = document.getElementById('m-broker-meritz-form');
  const pendingBanner = document.getElementById('m-broker-pending-banner');
  const btnText = document.getElementById('m-btn-broker-save-text');
  const btnIcon = document.getElementById('m-btn-broker-save-icon');

  if (broker === 'kiwoom' || broker === 'kis') {
    if (meritzForm) meritzForm.style.display = 'none';
    if (pendingBanner) pendingBanner.style.display = 'block';
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

async function mHandleBrokerCheckAndSave() {
  if (!mCurrentBrokerAccId) return;

  const toggle = document.getElementById('m-broker-autotrade-toggle');
  const select = document.getElementById('m-broker-select');
  const keyInput = document.getElementById('m-meritz-app-key');
  const secInput = document.getElementById('m-meritz-app-secret');
  const btn = document.getElementById('m-btn-broker-save');
  const btnText = document.getElementById('m-btn-broker-save-text');
  const resultBox = document.getElementById('m-meritz-verify-result-box');

  const enabled = toggle ? toggle.checked : false;
  const broker = select ? select.value : 'meritz';
  const appKey = keyInput ? keyInput.value.trim() : '';
  const appSecret = secInput ? secInput.value.trim() : '';

  if (broker === 'kiwoom' || broker === 'kis') {
    try {
      btn.disabled = true;
      const res = await fetch(`/api/accounts/${mCurrentBrokerAccId}/broker`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ broker, enabled })
      });
      const data = await res.json();
      mToast(data.message || '설정이 저장되었습니다.');
      mCloseModal('m-modal-broker');
      await openAccountDetail(mCurrentBrokerAccId);
    } catch (e) {
      mToast('저장 실패: ' + e.message, true);
    } finally {
      btn.disabled = false;
    }
    return;
  }

  if (!enabled && !appKey && !appSecret) {
    try {
      btn.disabled = true;
      const res = await fetch(`/api/accounts/${mCurrentBrokerAccId}/broker`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ broker: 'meritz', enabled: false })
      });
      const data = await res.json();
      mToast('자동매매가 비활성화되었습니다.');
      mCloseModal('m-modal-broker');
      await openAccountDetail(mCurrentBrokerAccId);
    } catch (e) {
      mToast('저장 실패: ' + e.message, true);
    } finally {
      btn.disabled = false;
    }
    return;
  }

  try {
    btn.disabled = true;
    if (btnText) btnText.textContent = '⏳ 메리츠 검증 중...';
    if (resultBox) {
      resultBox.style.display = 'block';
      resultBox.style.background = 'rgba(56, 189, 248, 0.12)';
      resultBox.style.border = '1px solid rgba(56, 189, 248, 0.3)';
      resultBox.style.color = 'var(--m-accent-cyan)';
      resultBox.innerHTML = '메리츠 API 연동 상태를 검증하고 있습니다...';
    }

    const res = await fetch(`/api/accounts/${mCurrentBrokerAccId}/broker/check-save`, {
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
      mToast('🎉 메리츠증권 연동 성공! 암호화 저장이 완료되었습니다.');
      setTimeout(async () => {
        mCloseModal('m-modal-broker');
        await openAccountDetail(mCurrentBrokerAccId);
      }, 900);
    } else {
      if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.style.background = 'rgba(239, 68, 68, 0.15)';
        resultBox.style.border = '1px solid rgba(239, 68, 68, 0.4)';
        resultBox.style.color = '#f87171';
        resultBox.innerHTML = `<strong>검증 실패:</strong> ${data.message || '오류'}`;
      }
      mToast(data.message || '검증 실패', true);
    }
  } catch (e) {
    mToast('통신 오류: ' + e.message, true);
  } finally {
    btn.disabled = false;
    mOnBrokerSelectChange();
  }
}

// =====================================================================
// Backtest View
// =====================================================================
function initDatePresets() {
  const end = new Date();
  const start = new Date();
  start.setFullYear(start.getFullYear() - 3);
  
  const sInput = document.getElementById('m-bt-start');
  const eInput = document.getElementById('m-bt-end');
  if (sInput) sInput.value = start.toISOString().slice(0, 10);
  if (eInput) eInput.value = end.toISOString().slice(0, 10);
}

function mSetBtPeriod(years) {
  const end = new Date();
  const start = new Date();
  start.setFullYear(start.getFullYear() - years);
  document.getElementById('m-bt-start').value = start.toISOString().slice(0, 10);
  document.getElementById('m-bt-end').value = end.toISOString().slice(0, 10);
}

function mQuickFillTicker(t) {
  document.getElementById('m-bt-ticker').value = t;
}

async function mRunBacktest() {
  const ticker = document.getElementById('m-bt-ticker').value.trim().toUpperCase();
  const capital = parseFloat(document.getElementById('m-bt-capital').value) || 100000;
  const start_date = document.getElementById('m-bt-start').value;
  const end_date = document.getElementById('m-bt-end').value;
  const use_adj_close = document.getElementById('m-bt-adj-close').checked;
  
  const strategies = [];
  if (document.getElementById('m-strat-jj').checked) strategies.push('종종이 기본전략');
  if (document.getElementById('m-strat-inf').checked) strategies.push('무한매수법 v4.0');
  if (document.getElementById('m-strat-vr').checked) strategies.push('VR 5.0 (밸류리밸런싱)');
  if (document.getElementById('m-strat-puddle').checked) strategies.push('웅덩이 매매법');
  if (document.getElementById('m-strat-bnh').checked) strategies.push(`${ticker} 단순보유(B&H)`);
  
  if (strategies.length === 0) {
    mToast('최소 1개 이상의 전략을 선택하세요.', true);
    return;
  }
  
  const btn = document.getElementById('m-btn-run-bt');
  btn.disabled = true;
  btn.innerHTML = '⏳ 계산 중...';
  
  try {
    const res = await mApi('/api/backtest/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ticker, capital, start_date, end_date, strategies, use_adj_close
      })
    });
    if (!res.ok) throw new Error('백테스트 실패');
    const data = await res.json();
    renderBacktestResults(data);
    mToast(data.use_adj_close ? '백테스트 완료 (배당 재투자 반영)' : '백테스트 완료');
  } catch (e) {
    mToast(e.message, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🚀 백테스트 실행하기';
  }
}

function renderBacktestResults(data) {
  const container = document.getElementById('m-bt-results-wrap');
  container.style.display = 'block';
  
  const listEl = document.getElementById('m-bt-cards-list');
  listEl.innerHTML = data.strategies.map(s => {
    const m = s.metrics;
    const isP = m.total_return >= 0;
    return `
      <div style="background:rgba(15,23,42,0.8);border:1px solid var(--m-border-subtle);border-radius:10px;padding:0.85rem;margin-bottom:0.6rem;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.4rem;">
          <span style="font-weight:800;color:#fff;font-size:0.9rem;">${s.name}</span>
          <span class="m-badge ${isP ? 'm-badge-profit' : 'm-badge-loss'}">${mFmt.pct(m.total_return)}</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;font-size:0.775rem;">
          <div>최종 자산: <strong style="color:#fff;">${mFmt.usd(m.final_asset)}</strong></div>
          <div>최대 낙폭: <strong style="color:var(--m-loss-red);">${mFmt.pct(m.mdd)}</strong></div>
          <div>연평균(CAGR): <strong>${mFmt.pct(m.cagr)}</strong></div>
          <div>보유 수량: <strong>${mFmt.num(m.final_hold)}주</strong></div>
        </div>
      </div>
    `;
  }).join('');
  
  // Chart.js 모바일 렌더링
  if (window.Chart && data.strategies.length > 0) {
    renderMobileChart(data);
  }
  
  container.scrollIntoView({ behavior: 'smooth' });
}

function renderMobileChart(data) {
  const ctx = document.getElementById('m-bt-chart').getContext('2d');
  if (mState.backtestChart) {
    mState.backtestChart.destroy();
  }
  
  const first = data.strategies[0];
  const dates = first.chart.dates;
  
  const colors = ['#06b6d4', '#3b82f6', '#f59e0b', '#10b981', '#94a3b8'];
  const datasets = data.strategies.map((s, idx) => ({
    label: s.name,
    data: s.chart.assets,
    borderColor: colors[idx % colors.length],
    borderWidth: 2,
    pointRadius: 0,
    tension: 0.1
  }));
  
  mState.backtestChart = new Chart(ctx, {
    type: 'line',
    data: { labels: dates, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { size: 10 } } }
      },
      scales: {
        x: { ticks: { color: '#64748b', maxTicksLimit: 6 } },
        y: { ticks: { color: '#64748b' } }
      }
    }
  });
}

// =====================================================================
// Settings (Telegram, Google Sync, Autotrade, Admin)
// =====================================================================
async function loadSettings() {
  try {
    const tgRes = await mApi('/api/telegram/config');
    if (tgRes.ok) {
      const tg = await tgRes.json();
      document.getElementById('m-tg-token').value = tg.bot_token || '';
      document.getElementById('m-tg-chatid').value = tg.chat_id || '';
      document.getElementById('m-tg-enabled').checked = tg.enabled;
    }
    
    
    const atRes = await mApi('/api/autotrade/status');
    if (atRes.ok) {
      const at = await atRes.json();
      document.getElementById('m-at-toggle').checked = at.enabled;
      document.getElementById('m-at-status-badge').textContent = at.status;
    }
  } catch (e) {
    console.error('설정 로드 오류:', e);
  }
}

async function mSaveTelegram() {
  const token = document.getElementById('m-tg-token').value.trim();
  const chat_id = document.getElementById('m-tg-chatid').value.trim();
  const enabled = document.getElementById('m-tg-enabled').checked;
  
  try {
    const res = await mApi('/api/telegram/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bot_token: token, chat_id, enabled, notify_on_orders: true })
    });
    if (!res.ok) throw new Error('저장 실패');
    mToast('텔레그램 설정이 저장되었습니다.');
  } catch (e) {
    mToast(e.message, true);
  }
}

async function mTestTelegram() {
  try {
    const res = await mApi('/api/telegram/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const d = await res.json();
    if (d.success) mToast('테스트 메시지가 전송되었습니다!');
    else throw new Error(d.message);
  } catch (e) {
    mToast(`전송 실패: ${e.message}`, true);
  }
}


async function mToggleAutotrade() {
  try {
    const res = await mApi('/api/autotrade/toggle', { method: 'POST' });
    const d = await res.json();
    document.getElementById('m-at-toggle').checked = d.enabled;
    document.getElementById('m-at-status-badge').textContent = d.status;
    mToast(`자동매매 봇이 ${d.enabled ? '활성화' : '비활성화'}되었습니다.`);
  } catch (e) {
    mToast(e.message, true);
  }
}
