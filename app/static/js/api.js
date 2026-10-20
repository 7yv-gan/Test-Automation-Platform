/* API 封装：axios 实例 + token 注入 + 401 处理 + 通用格式化工具 */
window.Api = (function () {
  const http = axios.create({ baseURL: '/api', timeout: 30000 });

  http.interceptors.request.use(function (cfg) {
    const token = localStorage.getItem('token');
    if (token) cfg.headers.Authorization = 'Bearer ' + token;
    return cfg;
  });

  http.interceptors.response.use(
    function (res) { return res.data; },
    function (err) {
      if (err.response && err.response.status === 401) {
        // 仅在“有 token 但已失效”时强制登出；未登录状态下的 401 静默处理，避免刷新死循环
        if (localStorage.getItem('token')) {
          localStorage.removeItem('token');
          localStorage.removeItem('user');
          location.hash = '#/login';
          location.reload();
        }
      }
      const msg = err.response && err.response.data && err.response.data.detail
        ? err.response.data.detail : (err.message || '请求失败');
      const e = new Error(msg);
      e.status = err.response ? err.response.status : 0;
      return Promise.reject(e);
    }
  );

  /* ------- 通用工具 ------- */
  function fmt(ts) {
    if (!ts) return '-';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  const STATUS_TEXT = {
    pending: '排队中', running: '执行中', success: '成功',
    failed: '失败', timeout: '超时', error: '拉取失败', cancelled: '已取消',
  };
  const STATUS_TYPE = {
    pending: 'info', running: 'warning', success: 'success',
    failed: 'danger', timeout: 'danger', error: 'danger', cancelled: 'info',
  };
  function statusText(s) { return STATUS_TEXT[s] || s; }
  function statusType(s) { return STATUS_TYPE[s] || 'info'; }
  const SEV_TEXT = { low: '低', medium: '中', high: '高', critical: '严重' };
  const SEV_TYPE = { low: 'info', medium: 'warning', high: 'danger', critical: 'danger' };
  function sevText(s) { return SEV_TEXT[s] || s; }
  function sevType(s) { return SEV_TYPE[s] || 'info'; }

  return { http, fmt, statusText, statusType, sevText, sevType };
})();
