/* 根应用：登录 / 布局 / 菜单路由 / 全局状态
   说明：#app 内静态 HTML 即根组件模板（Vue3 In-DOM 模板，多根 fragment）。
*/
(function () {
  const { createApp, ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } = Vue;
  const { http } = window.Api;

  const TITLES = {
    dashboard: '仪表盘', tasks: '任务管理', runs: '执行记录', reports: '报告中心',
    feedback: 'AI 反馈中心', agents: '节点管理', resources: '真机池 / 环境',
    cases: '用例库', notifications: '通知中心', users: '用户管理', settings: '系统设置',
  };

  const app = createApp({
    setup() {
      const logged = ref(false);
      const user = ref({});
      const view = ref('dashboard');
      const pendingReview = ref(0);
      const unreadNotify = ref(0);
      const focusRunId = ref(null);
      const loginForm = reactive({ username: '', password: '' });
      const loginLoading = ref(false);
      let notifyTimer = null;

      const isAdmin = computed(() => user.value.role === 'admin');
      const viewTitle = computed(() => TITLES[view.value] || '');

      function restore() {
        const token = localStorage.getItem('token');
        const saved = localStorage.getItem('user');
        if (token && saved) {
          try { user.value = JSON.parse(saved); } catch (e) { return; }
          logged.value = true;
          const hash = location.hash.replace('#/', '');
          if (TITLES[hash]) view.value = hash;
        }
      }

      async function doLogin() {
        if (!loginForm.username || !loginForm.password) {
          ElementPlus.ElMessage.warning('请输入用户名和密码'); return;
        }
        loginLoading.value = true;
        try {
          const data = await http.post('/auth/login', loginForm);
          localStorage.setItem('token', data.access_token);
          localStorage.setItem('user', JSON.stringify({ username: data.username, role: data.role }));
          user.value = { username: data.username, role: data.role };
          logged.value = true;
          view.value = 'dashboard';
          location.hash = '#/dashboard';
          refreshPending();
          ElementPlus.ElMessage.success('登录成功');
        } catch (e) {
          ElementPlus.ElMessage.error(e.message);
        } finally { loginLoading.value = false; }
      }

      function onMenuSelect(index) {
        view.value = index;
        location.hash = '#/' + index;
        refreshPending();
      }

      function goNotifications() {
        view.value = 'notifications';
        location.hash = '#/notifications';
      }

      function goToRun(runId) {
        focusRunId.value = runId;
        view.value = 'runs';
        location.hash = '#/runs';
      }

      function clearFocus() { focusRunId.value = null; }

      function onUserCommand(cmd) {
        if (cmd === 'logout') {
          localStorage.removeItem('token');
          localStorage.removeItem('user');
          logged.value = false;
          location.hash = '#/login';
          ElementPlus.ElMessage.info('已退出登录');
        }
      }

      async function refreshPending() {
        try {
          const ov = await http.get('/dashboard/overview');
          pendingReview.value = ov.pending_review || 0;
        } catch (e) { /* 忽略 */ }
      }

      async function refreshNotify() {
        try {
          const r = await http.get('/notifications/unread-count');
          unreadNotify.value = r.count || 0;
        } catch (e) { /* 忽略 */ }
      }

      // 子组件需要操作根状态的桥接
      window.__goToRun = goToRun;
      window.__refreshPendingGlobal = refreshPending;
      window.__refreshNotify = refreshNotify;

      onMounted(() => {
        restore();
        if (logged.value) {
          refreshPending();
          refreshNotify();
          notifyTimer = setInterval(refreshNotify, 30000);
        }
      });
      onBeforeUnmount(() => { if (notifyTimer) clearInterval(notifyTimer); });

      return {
        logged, user, view, pendingReview, unreadNotify, focusRunId, isAdmin, viewTitle,
        loginForm, loginLoading, doLogin, onMenuSelect, onUserCommand,
        goToRun, goNotifications, clearFocus,
      };
    },
  });

  app.component('dashboard-view', window.DashboardView);
  app.component('tasks-view', window.TasksView);
  app.component('runs-view', window.RunsView);
  app.component('feedback-view', window.FeedbackView);
  app.component('reports-view', window.ReportsView);
  app.component('agents-view', window.AgentsView);
  app.component('resources-view', window.ResourcesView);
  app.component('cases-view', window.CasesView);
  app.component('notifications-view', window.NotificationsView);
  app.component('users-view', window.UsersView);
  app.component('settings-view', window.SettingsView);
  app.use(ElementPlus);
  app.mount('#app');
})();
