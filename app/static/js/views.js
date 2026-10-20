/* 各视图组件：仪表盘 / 任务管理 / 执行记录 / AI反馈中心 / 用户管理 / 系统设置 */
(function () {
  const { http, fmt, statusText, statusType, sevText, sevType } = window.Api;
  const { defineComponent, ref, reactive, computed, onMounted, onBeforeUnmount, watch } = Vue;

  /* ================= 仪表盘 ================= */
  window.DashboardView = defineComponent({
    template: '#tpl-dashboard',
    setup() {
      const ov = reactive({});
      const recent = ref([]);
      const cards = computed(() => [
        { label: '任务总数', value: ov.total_tasks ?? 0, color: '#2563eb' },
        { label: '执行次数', value: ov.total_runs ?? 0, color: '#0ea5e9' },
        { label: '通过率', value: (ov.pass_rate ?? 0) + '%', color: '#10b981', sub: `${ov.success_runs ?? 0} 成功 / ${ov.failed_runs ?? 0} 失败` },
        { label: 'AI 分析', value: ov.analyses ?? 0, color: '#8b5cf6', sub: `待审核 ${ov.pending_review ?? 0}` },
        { label: '反馈样本', value: ov.feedback_count ?? 0, color: '#f59e0b', sub: '人工沉淀知识' },
        { label: 'AI 准确率', value: ov.ai_accuracy == null ? '—' : ov.ai_accuracy + '%', color: '#ef4444', sub: ov.reviewed_count ? `已审 ${ov.reviewed_count} 条` : '暂无审核数据' },
      ]);

      let trendChart = null, bugChart = null;
      function renderCharts(trend, bugDist) {
        if (trendChart) trendChart.dispose();
        if (bugChart) bugChart.dispose();
        trendChart = echarts.init(document.getElementById('trendChart'));
        bugChart = echarts.init(document.getElementById('bugChart'));

        trendChart.setOption({
          tooltip: { trigger: 'axis' },
          legend: { data: ['总执行', '成功', '失败'], top: 0 },
          grid: { left: 40, right: 16, top: 30, bottom: 28 },
          xAxis: { type: 'category', data: trend.map((t) => t.date.slice(5)) },
          yAxis: { type: 'value', minInterval: 1 },
          series: [
            { name: '总执行', type: 'line', smooth: true, data: trend.map((t) => t.total), itemStyle: { color: '#2563eb' } },
            { name: '成功', type: 'line', smooth: true, data: trend.map((t) => t.success), itemStyle: { color: '#10b981' } },
            { name: '失败', type: 'line', smooth: true, data: trend.map((t) => t.failed), itemStyle: { color: '#ef4444' } },
          ],
        });
        bugChart.setOption({
          tooltip: { trigger: 'item' },
          legend: { bottom: 0, type: 'scroll' },
          series: [{
            type: 'pie', radius: ['38%', '66%'], center: ['50%', '46%'],
            label: { formatter: '{b}: {c}' },
            data: bugDist.length ? bugDist : [{ name: '暂无', value: 1 }],
          }],
        });
      }

      async function load() {
        try {
          const [o, t, r] = await Promise.all([
            http.get('/dashboard/overview'),
            http.get('/dashboard/trend?days=14'),
            http.get('/dashboard/recent-runs?limit=10'),
          ]);
          Object.assign(ov, o);
          recent.value = r;
          Vue.nextTick(() => renderCharts(t, o.bug_distribution || []));
        } catch (e) { ElementPlus.ElMessage.error('加载看板失败: ' + e.message); }
      }
      onMounted(load);
      onBeforeUnmount(() => { trendChart && trendChart.dispose(); bugChart && bugChart.dispose(); });
      return { cards, recent, statusType, statusText, fmt };
    },
  });

  /* ================= 任务管理 ================= */
  window.TasksView = defineComponent({
    template: '#tpl-tasks',
    emits: ['go-run'],
    setup(_, { emit }) {
      const tasks = ref([]);
      const dialogVisible = ref(false);
      const editing = ref(false);
      const editingId = ref(null);
      const saving = ref(false);
      const runningId = ref(null);
      const form = reactive({
        name: '', description: '', repo_url: '', branch: 'main',
        command: 'pytest -q', timeout: 600, schedule_interval_min: null,
        env_vars_text: '{}', enabled: true,
      });

      async function load() {
        try { tasks.value = await http.get('/tasks'); } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      onMounted(load);

      function resetForm() {
        Object.assign(form, {
          name: '', description: '', repo_url: '', branch: 'main',
          command: 'pytest -q', timeout: 600, schedule_interval_min: null,
          env_vars_text: '{}', enabled: true,
        });
      }
      function openCreate() { resetForm(); editing.value = false; editingId.value = null; dialogVisible.value = true; }
      function openEdit(row) {
        editing.value = true; editingId.value = row.id;
        Object.assign(form, {
          name: row.name, description: row.description, repo_url: row.repo_url,
          branch: row.branch, command: row.command, timeout: row.timeout,
          schedule_interval_min: row.schedule_interval_min,
          env_vars_text: JSON.stringify(row.env_vars || {}, null, 2),
          enabled: !!row.enabled,
        });
        dialogVisible.value = true;
      }

      function parseEnv(text) {
        try { return JSON.parse(text || '{}'); }
        catch (e) { ElementPlus.ElMessage.warning('环境变量不是合法 JSON'); throw e; }
      }

      async function saveTask() {
        if (!form.name || !form.repo_url || !form.command) {
          ElementPlus.ElMessage.warning('请填写任务名称、仓库地址与执行命令'); return;
        }
        let env = {};
        try { env = parseEnv(form.env_vars_text); } catch (e) { return; }
        saving.value = true;
        const payload = {
          name: form.name, description: form.description, repo_url: form.repo_url,
          branch: form.branch || 'main', command: form.command, timeout: form.timeout,
          schedule_interval_min: form.schedule_interval_min || null,
          env_vars: env, enabled: form.enabled ? 1 : 0,
        };
        try {
          if (editing.value) { await http.put('/tasks/' + editingId.value, payload); }
          else { await http.post('/tasks', payload); }
          ElementPlus.ElMessage.success('保存成功');
          dialogVisible.value = false;
          load();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
        finally { saving.value = false; }
      }

      async function runTask(row) {
        runningId.value = row.id;
        try {
          const run = await http.post('/tasks/' + row.id + '/run');
          ElementPlus.ElMessage.success(`已触发执行 Run#${run.id}`);
          emit('go-run', run.id);
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
        finally { runningId.value = null; }
      }

      async function toggleTask(row) {
        try {
          await http.put('/tasks/' + row.id, { enabled: row.enabled ? 0 : 1 });
          row.enabled = row.enabled ? 0 : 1;
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }

      async function removeTask(row) {
        try {
          await ElementPlus.ElMessageBox.confirm(`确认删除任务「${row.name}」？`, '提示', { type: 'warning' });
          await http.delete('/tasks/' + row.id);
          ElementPlus.ElMessage.success('已删除');
          load();
        } catch (e) {
          if (e !== 'cancel' && !(e && e.message && e.message.includes('cancel'))) ElementPlus.ElMessage.error(e.message || '已取消');
        }
      }

      return { tasks, dialogVisible, editing, form, saving, runningId, openCreate, openEdit, saveTask, runTask, toggleTask, removeTask };
    },
  });

  /* ================= 执行记录 ================= */
  window.RunsView = defineComponent({
    template: '#tpl-runs',
    props: { focusRunId: { type: Number, default: null } },
    emits: ['clear-focus'],
    setup(props, { emit }) {
      const runs = ref([]);
      const taskOptions = ref([]);
      const filterTask = ref(null);
      const filterStatus = ref(null);
      const drawerVisible = ref(false);
      const current = ref(null);
      const logs = ref('');
      const logOffset = ref(0);
      let logTimer = null;

      const analysis = ref(null);
      const review = reactive({ result: 'correct', bug_type: '', root_cause: '', suggestion: '' });
      const reviewing = ref(false);
      const logLoading = ref(false);

      async function load() {
        try {
          const params = new URLSearchParams({ limit: '100' });
          if (filterTask.value) params.set('task_id', filterTask.value);
          if (filterStatus.value) params.set('status', filterStatus.value);
          runs.value = await http.get('/runs?' + params.toString());
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      async function loadTasks() {
        try { taskOptions.value = await http.get('/tasks'); } catch (e) {}
      }
      async function openDetailById(id) {
        try {
          const row = await http.get('/runs/' + id);
          openDetail(row);
        } catch (e) { ElementPlus.ElMessage.warning('执行记录不存在或已删除'); }
      }

      onMounted(() => {
        load();
        loadTasks();
        if (props.focusRunId) openDetailById(props.focusRunId);
      });

      async function openDetail(row) {
        if (!row || row.id == null) { ElementPlus.ElMessage.warning('无效的执行记录'); return; }
        emit('clear-focus');
        clearInterval(logTimer);
        logTimer = null;
        current.value = row;
        drawerVisible.value = true;
        logs.value = '';
        logOffset.value = 0;
        analysis.value = null;
        Object.assign(review, { result: 'correct', bug_type: '', root_cause: '', suggestion: '' });
        await pullLogs();
        loadAnalysis();
        logTimer = setInterval(async () => {
          await pullLogs();
          if (current.value && ['success', 'failed', 'timeout', 'error', 'cancelled'].includes(current.value.status)) {
            const a = await loadAnalysis();
            if (a && a.status === 'done' && a.reviewed) clearInterval(logTimer);
          }
        }, 2000);
      }

      // 关闭抽屉时停止轮询并清理状态
      watch(drawerVisible, (v) => {
        if (!v) {
          clearInterval(logTimer);
          logTimer = null;
          current.value = null;
        }
      });

      async function pullLogs() {
        if (!current.value) return;
        try {
          const resp = await axios.get('/api/runs/' + current.value.id + '/logs?offset=' + logOffset.value, {
            headers: { Authorization: 'Bearer ' + localStorage.getItem('token') },
          });
          if (resp.data) {
            logs.value += resp.data;
            logOffset.value += resp.data.length;
          }
          const end = resp.headers['x-log-end'];
          if (end === '-1' && logTimer) { /* 保持轮询以刷新分析状态 */ }
          Vue.nextTick(() => {
            const box = document.querySelector('.log-box');
            if (box) box.scrollTop = box.scrollHeight;
          });
        } catch (e) {}
      }

      async function loadAnalysis() {
        if (!current.value) return null;
        try {
          const a = await http.get('/runs/' + current.value.id + '/analysis');
          analysis.value = a;
          return a;
        } catch (e) { return null; }
      }

      async function submitReview() {
        if (!analysis.value) return;
        if (review.result === 'incorrect' && !review.bug_type && !review.root_cause) {
          ElementPlus.ElMessage.warning('请填写纠正后的 Bug 类型或根因'); return;
        }
        reviewing.value = true;
        try {
          await http.post('/ai/analyses/' + analysis.value.id + '/review', {
            result: review.result,
            bug_type: review.bug_type, root_cause: review.root_cause, suggestion: review.suggestion,
          });
          ElementPlus.ElMessage.success('审核已提交，结论已沉淀到样本库');
          await loadAnalysis();
          window.__refreshPending && window.__refreshPending();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
        finally { reviewing.value = false; }
      }

      watch(() => props.focusRunId, (id) => {
        if (id) openDetailById(id);
      });

      onBeforeUnmount(() => clearInterval(logTimer));
      return {
        runs, taskOptions, filterTask, filterStatus, drawerVisible, current, logs,
        analysis, review, reviewing, openDetail, load, loadAnalysis, submitReview,
        statusType, statusText, sevType, sevText, fmt,
      };
    },
  });

  /* ================= AI 反馈中心 ================= */
  window.FeedbackView = defineComponent({
    template: '#tpl-feedback',
    setup() {
      const tab = ref('pending');
      const pendingList = ref([]);
      const reviewedList = ref([]);
      const samples = ref([]);
      const reviewVisible = ref(false);
      const reviewTarget = ref(null);
      const reviewForm = reactive({ result: 'correct', bug_type: '', root_cause: '', suggestion: '' });
      const reviewing = ref(false);
      const ov = reactive({});

      const cards = computed(() => [
        { label: 'AI 分析总数', value: ov.analyses ?? 0, color: '#8b5cf6' },
        { label: '待审核', value: ov.pending_review ?? 0, color: '#f59e0b' },
        { label: '已审核', value: ov.reviewed_count ?? 0, color: '#0ea5e9' },
        { label: 'AI 准确率', value: ov.ai_accuracy == null ? '—' : ov.ai_accuracy + '%', color: '#10b981' },
        { label: '反馈样本数', value: ov.feedback_count ?? 0, color: '#2563eb' },
        { label: '样本被引用', value: ov.feedback_use ?? 0, color: '#ef4444' },
      ]);

      async function loadAll() {
        try {
          const [o, pend, rev, sam] = await Promise.all([
            http.get('/dashboard/overview'),
            http.get('/ai/analyses?reviewed=0&limit=100'),
            http.get('/ai/analyses?reviewed=1&limit=100'),
            http.get('/ai/feedback?limit=200'),
          ]);
          Object.assign(ov, o);
          pendingList.value = pend.filter((a) => a.status === 'done');
          reviewedList.value = rev;
          samples.value = sam;
          window.__refreshPending = loadAll;
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      onMounted(loadAll);

      function openReview(a) {
        reviewTarget.value = a;
        Object.assign(reviewForm, { result: 'correct', bug_type: '', root_cause: '', suggestion: '' });
        reviewVisible.value = true;
      }
      async function submitReview() {
        if (!reviewTarget.value) return;
        if (reviewForm.result === 'incorrect' && !reviewForm.bug_type && !reviewForm.root_cause) {
          ElementPlus.ElMessage.warning('请填写纠正后的 Bug 类型或根因'); return;
        }
        reviewing.value = true;
        try {
          await http.post('/ai/analyses/' + reviewTarget.value.id + '/review', {
            result: reviewForm.result,
            bug_type: reviewForm.bug_type, root_cause: reviewForm.root_cause, suggestion: reviewForm.suggestion,
          });
          ElementPlus.ElMessage.success('审核完成，结论已沉淀为样本');
          reviewVisible.value = false;
          loadAll();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
        finally { reviewing.value = false; }
      }
      async function delSample(row) {
        try {
          await ElementPlus.ElMessageBox.confirm('确认删除该样本？', '提示', { type: 'warning' });
          await http.delete('/ai/feedback/' + row.id);
          loadAll();
        } catch (e) {}
      }

      return {
        tab, pendingList, reviewedList, samples, reviewVisible, reviewTarget, reviewForm,
        reviewing, cards, openReview, submitReview, delSample, sevText, sevType, fmt,
      };
    },
  });

  /* ================= 用户管理 ================= */
  window.UsersView = defineComponent({
    template: '#tpl-users',
    setup() {
      const users = ref([]);
      const createVisible = ref(false);
      const createForm = reactive({ username: '', password: '', role: 'user' });
      const user = JSON.parse(localStorage.getItem('user') || '{}');

      async function load() {
        try { users.value = await http.get('/auth/users'); } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      onMounted(load);

      async function createUser() {
        if (!createForm.username || createForm.password.length < 6) {
          ElementPlus.ElMessage.warning('用户名必填，密码至少 6 位'); return;
        }
        try {
          await http.post('/auth/users', { ...createForm });
          ElementPlus.ElMessage.success('创建成功');
          createVisible.value = false;
          createForm.username = ''; createForm.password = ''; createForm.role = 'user';
          load();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      async function delUser(row) {
        try {
          await ElementPlus.ElMessageBox.confirm(`确认删除用户「${row.username}」？`, '提示', { type: 'warning' });
          await http.delete('/auth/users/' + row.id);
          load();
        } catch (e) {}
      }
      return { users, createVisible, createForm, user, createUser, delUser, fmt };
    },
  });

  /* ================= 节点管理（Agent 集群） ================= */
  window.AgentsView = defineComponent({
    template: '#tpl-agents',
    setup() {
      const agents = ref([]);
      const cards = computed(() => {
        const online = agents.value.filter((a) => a.status === 'online').length;
        const capacity = agents.value.reduce((s, a) => s + a.capacity, 0);
        const running = agents.value.reduce((s, a) => s + (a.running_count || 0), 0);
        return [
          { label: '节点总数', value: agents.value.length, color: '#2563eb' },
          { label: '在线节点', value: online, color: '#10b981' },
          { label: '总容量', value: capacity, color: '#0ea5e9', sub: '并行任务上限' },
          { label: '当前负载', value: running, color: '#f59e0b', sub: capacity ? `利用率 ${Math.round(running / capacity * 100)}%` : '' },
        ];
      });
      async function load() {
        try { agents.value = await http.get('/agents'); } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      onMounted(load);
      async function setStatus(row, status) {
        try {
          await http.post(`/agents/${row.id}/${status}`);
          ElementPlus.ElMessage.success(status === 'online' ? '节点已上线' : '节点已下线，已通知');
          load();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      async function register() {
        try {
          await http.post('/agents/register');
          ElementPlus.ElMessage.success('节点注册成功（本机模拟集群）');
          load();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      return { agents, cards, setStatus, register, fmt };
    },
  });

  /* ================= 资源中心（真机池 + 测试环境） ================= */
  window.ResourcesView = defineComponent({
    template: '#tpl-resources',
    setup() {
      const tab = ref('devices');
      const devices = ref([]);
      const envs = ref([]);
      const devDialog = ref(false);
      const devEditing = ref(false);
      const devEditingId = ref(null);
      const devSaving = ref(false);
      const devForm = reactive({ name: '', model: '', platform: 'Android', os_version: '', adb_serial: '', remark: '' });
      const envDialog = ref(false);
      const envEditing = ref(false);
      const envEditingId = ref(null);
      const envSaving = ref(false);
      const envForm = reactive({ name: '', env_type: '测试服', base_url: '', remark: '' });

      async function loadDevices() {
        try { devices.value = await http.get('/devices'); } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      async function loadEnvs() {
        try { envs.value = await http.get('/envs'); } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      onMounted(() => { loadDevices(); loadEnvs(); });

      function openDevCreate() {
        devEditing.value = false;
        devEditingId.value = null;
        Object.assign(devForm, { name: '', model: '', platform: 'Android', os_version: '', adb_serial: '', remark: '' });
        devDialog.value = true;
      }
      function openDevEdit(row) {
        devEditing.value = true;
        devEditingId.value = row.id;
        Object.assign(devForm, { name: row.name, model: row.model, platform: row.platform, os_version: row.os_version, adb_serial: row.adb_serial, remark: row.remark });
        devDialog.value = true;
      }
      async function saveDev() {
        if (!devForm.name) { ElementPlus.ElMessage.warning('请填写设备名'); return; }
        devSaving.value = true;
        try {
          if (devEditing.value && devEditingId.value) await http.put('/devices/' + devEditingId.value, { ...devForm });
          else await http.post('/devices', { ...devForm });
          ElementPlus.ElMessage.success('保存成功');
          devDialog.value = false;
          loadDevices();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
        finally { devSaving.value = false; }
      }
      async function claim(row) {
        try { await http.post(`/devices/${row.id}/claim`); ElementPlus.ElMessage.success('设备已占用（模拟真机抢占）'); loadDevices(); }
        catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      async function release(row) {
        try { await http.post(`/devices/${row.id}/release`); ElementPlus.ElMessage.success('设备已释放'); loadDevices(); }
        catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      async function removeDev(row) {
        try {
          await ElementPlus.ElMessageBox.confirm(`确认删除设备「${row.name}」？`, '提示', { type: 'warning' });
          await http.delete('/devices/' + row.id);
          loadDevices();
        } catch (e) {}
      }

      function openEnvCreate() {
        envEditing.value = false;
        envEditingId.value = null;
        Object.assign(envForm, { name: '', env_type: '测试服', base_url: '', remark: '' });
        envDialog.value = true;
      }
      function openEnvEdit(row) {
        envEditing.value = true;
        envEditingId.value = row.id;
        Object.assign(envForm, { name: row.name, env_type: row.env_type, base_url: row.base_url, remark: row.remark });
        envDialog.value = true;
      }
      async function saveEnv() {
        if (!envForm.name) { ElementPlus.ElMessage.warning('请填写环境名'); return; }
        envSaving.value = true;
        try {
          if (envEditing.value && envEditingId.value) await http.put('/envs/' + envEditingId.value, { ...envForm });
          else await http.post('/envs', { ...envForm });
          ElementPlus.ElMessage.success('保存成功');
          envDialog.value = false;
          loadEnvs();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
        finally { envSaving.value = false; }
      }
      async function removeEnv(row) {
        try {
          await ElementPlus.ElMessageBox.confirm(`确认删除环境「${row.name}」？`, '提示', { type: 'warning' });
          await http.delete('/envs/' + row.id);
          loadEnvs();
        } catch (e) {}
      }

      return {
        tab, devices, envs, devDialog, devEditing, devSaving, devForm,
        envDialog, envEditing, envSaving, envForm,
        openDevCreate, openDevEdit, saveDev, claim, release, removeDev,
        openEnvCreate, openEnvEdit, saveEnv, removeEnv,
      };
    },
  });

  /* ================= 用例库 ================= */
  window.CasesView = defineComponent({
    template: '#tpl-cases',
    emits: ['go-run'],
    setup(_, { emit }) {
      const cases = ref([]);
      const filterModule = ref(null);
      const filterPriority = ref(null);
      const modules = computed(() => [...new Set(cases.value.map((c) => c.module).filter(Boolean))]);
      const dialogVisible = ref(false);
      const editing = ref(false);
      const editingId = ref(null);
      const saving = ref(false);
      const runningId = ref(null);
      const form = reactive({
        name: '', module: '', priority: 'P1', command: 'pytest -q',
        repo_url: '', branch: 'main', tags: '',
      });

      async function load() {
        try {
          const params = new URLSearchParams();
          if (filterModule.value) params.set('module', filterModule.value);
          if (filterPriority.value) params.set('priority', filterPriority.value);
          cases.value = await http.get('/cases?' + params.toString());
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      onMounted(load);

      function openCreate() {
        editing.value = false; editingId.value = null;
        Object.assign(form, { name: '', module: '', priority: 'P1', command: 'pytest -q', repo_url: '', branch: 'main', tags: '' });
        dialogVisible.value = true;
      }
      function openEdit(row) {
        editing.value = true; editingId.value = row.id;
        Object.assign(form, {
          name: row.name, module: row.module, priority: row.priority, command: row.command,
          repo_url: row.repo_url, branch: row.branch, tags: row.tags,
        });
        dialogVisible.value = true;
      }
      async function saveCase() {
        if (!form.name || !form.command) { ElementPlus.ElMessage.warning('请填写用例名称与执行命令'); return; }
        saving.value = true;
        const payload = { ...form, enabled: 1 };
        try {
          if (editing.value) await http.put('/cases/' + editingId.value, payload);
          else await http.post('/cases', payload);
          ElementPlus.ElMessage.success('保存成功');
          dialogVisible.value = false;
          load();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
        finally { saving.value = false; }
      }
      async function runCase(row) {
        runningId.value = row.id;
        try {
          const run = await http.post('/cases/' + row.id + '/run');
          ElementPlus.ElMessage.success(`已触发执行 Run#${run.id}（动态生成任务）`);
          emit('go-run', run.id);
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
        finally { runningId.value = null; }
      }
      async function toggle(row) {
        try {
          await http.put('/cases/' + row.id, { enabled: row.enabled ? 0 : 1 });
          row.enabled = row.enabled ? 0 : 1;
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      async function removeCase(row) {
        try {
          await ElementPlus.ElMessageBox.confirm(`确认删除用例「${row.name}」？`, '提示', { type: 'warning' });
          await http.delete('/cases/' + row.id);
          load();
        } catch (e) {}
      }
      return {
        cases, filterModule, filterPriority, modules, dialogVisible, editing, form, saving, runningId,
        openCreate, openEdit, saveCase, runCase, toggle, removeCase, load,
      };
    },
  });

  /* ================= 报告中心 ================= */
  window.ReportsView = defineComponent({
    template: '#tpl-reports',
    emits: ['go-run'],
    setup(_, { emit }) {
      const ov = reactive({});
      const recent = ref([]);
      const days = ref(14);
      let trendChart = null, failChart = null, moduleChart = null;

      const cards = computed(() => [
        { label: '执行次数', value: ov.total_runs ?? 0, color: '#2563eb', sub: `近 ${ov.days ?? 14} 天` },
        { label: '通过率', value: (ov.pass_rate ?? 0) + '%', color: '#10b981', sub: `${ov.success_runs ?? 0} 成功 / ${ov.failed_runs ?? 0} 失败` },
        { label: '平均耗时', value: (ov.avg_duration_s ?? 0) + 's', color: '#0ea5e9' },
        { label: 'AI 准确率', value: ov.ai_accuracy == null ? '—' : ov.ai_accuracy + '%', color: '#8b5cf6', sub: `反馈样本 ${ov.feedback_count ?? 0}` },
      ]);

      function renderCharts(trend, failTop, moduleDist) {
        if (trendChart) trendChart.dispose();
        if (failChart) failChart.dispose();
        if (moduleChart) moduleChart.dispose();
        trendChart = echarts.init(document.getElementById('reportTrend'));
        failChart = echarts.init(document.getElementById('reportFailTop'));
        moduleChart = echarts.init(document.getElementById('reportModule'));
        trendChart.setOption({
          tooltip: { trigger: 'axis' },
          legend: { data: ['总执行', '成功', '失败'], top: 0 },
          grid: { left: 40, right: 16, top: 30, bottom: 28 },
          xAxis: { type: 'category', data: trend.map((t) => t.date.slice(5)) },
          yAxis: { type: 'value', minInterval: 1 },
          series: [
            { name: '总执行', type: 'line', smooth: true, data: trend.map((t) => t.total), itemStyle: { color: '#2563eb' } },
            { name: '成功', type: 'line', smooth: true, data: trend.map((t) => t.success), itemStyle: { color: '#10b981' } },
            { name: '失败', type: 'line', smooth: true, data: trend.map((t) => t.failed), itemStyle: { color: '#ef4444' } },
          ],
        });
        failChart.setOption({
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          grid: { left: 110, right: 20, top: 16, bottom: 24 },
          xAxis: { type: 'value', minInterval: 1 },
          yAxis: { type: 'category', inverse: true, data: failTop.map((f) => f.name) },
          series: [{
            name: '失败次数', type: 'bar', data: failTop.map((f) => f.value),
            itemStyle: { color: '#ef4444', borderRadius: [0, 4, 4, 0] },
          }],
        });
        moduleChart.setOption({
          tooltip: { trigger: 'item' },
          legend: { bottom: 0, type: 'scroll' },
          series: [{
            type: 'pie', radius: ['36%', '62%'], center: ['50%', '44%'],
            label: { formatter: '{b}: {c}' },
            data: moduleDist.length ? moduleDist : [{ name: '暂无', value: 1 }],
          }],
        });
      }

      async function load() {
        try {
          const [o, t, r] = await Promise.all([
            http.get('/reports/overview?days=' + days.value),
            http.get('/reports/trend?days=' + days.value),
            http.get('/reports/recent?limit=30'),
          ]);
          Object.assign(ov, o);
          recent.value = r;
          Vue.nextTick(() => renderCharts(t, o.fail_top || [], o.module_dist || []));
        } catch (e) { ElementPlus.ElMessage.error('加载报告失败: ' + e.message); }
      }
      onMounted(load);
      onBeforeUnmount(() => { trendChart && trendChart.dispose(); failChart && failChart.dispose(); moduleChart && moduleChart.dispose(); });
      function openRun(row) {
        emit('go-run', row.id);
      }
      return { cards, recent, days, openRun, statusText, statusType, fmt };
    },
  });

  /* ================= 通知中心 ================= */
  window.NotificationsView = defineComponent({
    template: '#tpl-notifications',
    setup() {
      const list = ref([]);
      const filterType = ref(null);
      const cards = computed(() => {
        const total = list.value.length;
        const unread = list.value.filter((n) => !n.read).length;
        const mock = list.value.filter((n) => n.status === 'mock').length;
        const sent = list.value.filter((n) => n.status === 'success').length;
        return [
          { label: '通知总数', value: total, color: '#2563eb' },
          { label: '未读', value: unread, color: '#f59e0b' },
          { label: '已送达', value: sent, color: '#10b981' },
          { label: '模拟发送', value: mock, color: '#8b5cf6' },
        ];
      });
      async function load() {
        try {
          const params = new URLSearchParams({ limit: '200' });
          if (filterType.value) params.set('ntype', filterType.value);
          list.value = await http.get('/notifications?' + params.toString());
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      onMounted(load);
      async function markOne(row) {
        try { await http.post('/notifications/' + row.id + '/read'); row.read = 1; window.__refreshNotify && window.__refreshNotify(); }
        catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      async function markAll() {
        try { await http.post('/notifications/read-all'); load(); window.__refreshNotify && window.__refreshNotify(); }
        catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      async function resend(row) {
        try {
          const r = await http.post('/notifications/' + row.id + '/resend');
          ElementPlus.ElMessage.success(r.status === 'mock' ? '已重发（模拟渠道）' : '已重发并送达');
          load();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      return { list, filterType, cards, load, markOne, markAll, resend, fmt };
    },
  });

  /* ================= 系统设置 ================= */
  window.SettingsView = defineComponent({
    template: '#tpl-settings',
    setup() {
      const form = reactive({});
      const saving = ref(false);
      async function load() {
        try {
          const data = await http.get('/settings');
          Object.assign(form, {
            llm_base_url: data.llm_base_url || '', llm_api_key: data.llm_api_key || '',
            llm_model: data.llm_model || '', github_token: data.github_token || '',
            max_concurrent_runs: Number(data.max_concurrent_runs) || 3,
            default_timeout: Number(data.default_timeout) || 600,
            llm_max_log_chars: Number(data.llm_max_log_chars) || 8000,
            llm_api_key_configured: !!data.llm_api_key_configured,
            github_token_configured: !!data.github_token_configured,
            feishu_webhook: data.feishu_webhook || '',
            dingtalk_webhook: data.dingtalk_webhook || '',
            wecom_webhook: data.wecom_webhook || '',
            smtp_host: data.smtp_host || '', smtp_port: data.smtp_port || '',
            smtp_user: data.smtp_user || '', smtp_to: data.smtp_to || '',
            feishu_webhook_configured: !!data.feishu_webhook_configured,
          });
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
      }
      onMounted(load);

      async function save() {
        saving.value = true;
        const updates = {};
        const fields = ['llm_base_url', 'llm_api_key', 'llm_model', 'github_token',
          'max_concurrent_runs', 'default_timeout', 'llm_max_log_chars',
          'feishu_webhook', 'dingtalk_webhook', 'wecom_webhook',
          'smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', 'smtp_to'];
        fields.forEach((f) => { if (form[f] !== undefined && form[f] !== '') updates[f] = form[f]; });
        try {
          await http.put('/settings', { updates });
          ElementPlus.ElMessage.success('配置已保存并立即生效');
          load();
        } catch (e) { ElementPlus.ElMessage.error(e.message); }
        finally { saving.value = false; }
      }
      return { form, saving, save };
    },
  });
})();
