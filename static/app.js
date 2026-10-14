const state = {
  token: "",
  bootstrap: null,
  items: [],
  selected: new Set(),
  edits: new Map(),
  activeId: null,
  activeSource: "tbl_recv",
  expanded: new Set(),
};

const $ = (id) => document.getElementById(id);
const refs = {
  sourceStatus: $("sourceStatus"), candidateCount: $("candidateCount"), selectedCount: $("selectedCount"),
  googleStatus: $("googleStatus"), connectionBadge: $("connectionBadge"), updatedAt: $("updatedAt"),
  candidateList: $("candidateList"), loadingState: $("loadingState"), emptyState: $("emptyState"),
  searchInput: $("searchInput"), hidePast: $("hidePast"), hideSynced: $("hideSynced"), hideDismissed: $("hideDismissed"),
  selectAll: $("selectAll"), calendarButton: $("calendarButton"), icsButton: $("icsButton"),
  dismissButton: $("dismissButton"), periodSelect: $("periodSelect"), settingsDialog: $("settingsDialog"),
  connectedPanel: $("connectedPanel"), setupPanel: $("setupPanel"), reviewEmpty: $("reviewEmpty"),
  reviewForm: $("reviewForm"), editTitle: $("editTitle"), editDate: $("editDate"), editTime: $("editTime"),
  editEndTime: $("editEndTime"), editAllDay: $("editAllDay"), editLocation: $("editLocation"),
  editAssignee: $("editAssignee"), editReminder: $("editReminder"), editContext: $("editContext"), toast: $("toast"),
  editMessageDate: $("editMessageDate"),
  allTabCount: $("allTabCount"), receivedTabCount: $("receivedTabCount"), sentTabCount: $("sentTabCount"),
  messageDateHeading: $("messageDateHeading"), personHeading: $("personHeading"),
  sourcePathInput: $("sourcePathInput"), sourceChoiceHint: $("sourceChoiceHint"),
};

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers["X-App-Token"] = state.token;
  if (options.body && typeof options.body !== "string") {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, { ...options, headers });
  if (options.raw) return response;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `요청 실패 (${response.status})`);
  return data;
}

function showToast(message, timeout = 3200) {
  refs.toast.textContent = message;
  refs.toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => refs.toast.classList.add("hidden"), timeout);
}

function formatDate(value) {
  const parsed = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric", weekday: "short" }).format(parsed);
}

function formatMessageDate(item) {
  const match = String(item.message_date || "").match(/^(\d{4})\/(\d{2})\/(\d{2})\s+(\d{2}):(\d{2})/);
  const value = match ? `${match[1]}.${match[2]}.${match[3]} ${match[4]}:${match[5]}` : item.message_date;
  const label = item.source_table === "tbl_recv" ? "수신" : "발신";
  return `${label} ${value || "일시 미상"}`;
}

function messageDateParts(item) {
  const formatted = formatMessageDate(item);
  const separator = formatted.indexOf(" ");
  return { label: formatted.slice(0, separator), value: formatted.slice(separator + 1) };
}

function messageTimestamp(item) {
  const match = String(item.message_date || "").match(/^(\d{4})\/(\d{2})\/(\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!match) return 0;
  return new Date(
    Number(match[1]), Number(match[2]) - 1, Number(match[3]),
    Number(match[4]), Number(match[5]), Number(match[6] || 0)
  ).getTime();
}

function baseEdit(item) {
  return {
    ...item,
    end_time: item.end_time || (item.time ? `${String((Number(item.time.slice(0,2)) + 1) % 24).padStart(2,"0")}:${item.time.slice(3)}` : ""),
    reminder_minutes: -2,
  };
}

function editFor(item) {
  if (!state.edits.has(item.id)) state.edits.set(item.id, baseEdit(item));
  return state.edits.get(item.id);
}

function matchesCommonFilters(item) {
  const query = refs.searchInput.value.trim().toLocaleLowerCase("ko");
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
  if (refs.hidePast.checked && editFor(item).date < today) return false;
  if (refs.hideSynced.checked && item.synced) return false;
  if (refs.hideDismissed.checked && item.dismissed) return false;
  if (!query) return true;
  return [item.title, item.person, item.location, item.assignee, item.context].join(" ").toLocaleLowerCase("ko").includes(query);
}

function filteredItems() {
  return state.items.filter((item) =>
    matchesCommonFilters(item) && (state.activeSource === "all" || item.source_table === state.activeSource)
  );
}

function groupCandidates(items) {
  const groups = new Map();
  for (const item of items) {
    const key = `${item.source_table}:${item.source_key}`;
    if (!groups.has(key)) groups.set(key, { key, items: [] });
    groups.get(key).items.push(item);
  }
  return [...groups.values()];
}

function render() {
  const items = filteredItems();
  const groups = groupCandidates(items);
  const commonItems = state.items.filter(matchesCommonFilters);
  const headings = {
    all: ["받은/보낸 일시", "보낸/받는 사람"],
    tbl_recv: ["받은 일시", "보낸 사람"],
    tbl_send: ["보낸 일시", "받는 사람"],
  }[state.activeSource];
  refs.messageDateHeading.textContent = headings[0];
  refs.personHeading.textContent = headings[1];
  refs.allTabCount.textContent = groupCandidates(commonItems).length;
  refs.receivedTabCount.textContent = groupCandidates(commonItems.filter((item) => item.source_table === "tbl_recv")).length;
  refs.sentTabCount.textContent = groupCandidates(commonItems.filter((item) => item.source_table === "tbl_send")).length;
  refs.candidateCount.textContent = groups.length;
  refs.selectedCount.textContent = state.selected.size;
  refs.selectAll.checked = items.length > 0 && items.every((item) => state.selected.has(item.id));
  refs.selectAll.indeterminate = items.some((item) => state.selected.has(item.id)) && !refs.selectAll.checked;
  refs.candidateList.innerHTML = "";
  const noSource = !state.bootstrap?.sourceExists;
  $("emptyTitle").textContent = noSource ? "쿨메신저 UDB 파일을 찾지 못했습니다" : "조건에 맞는 메시지가 없습니다";
  $("emptyText").textContent = noSource ? "환경 설정에서 UDB 파일을 직접 선택해 주세요." : "검색 조건을 바꾸거나 새로고침해 보세요.";
  $("emptySetupButton").classList.toggle("hidden", !noSource);
  refs.emptyState.classList.toggle("hidden", groups.length > 0);
  refs.candidateList.classList.toggle("hidden", groups.length === 0);
  for (const group of groups) {
    const item = group.items[0];
    const edit = editFor(item);
    const messageDate = messageDateParts(item);
    const selectedItems = group.items.filter((entry) => state.selected.has(entry.id));
    const scheduleOptions = group.items.map((entry) => {
      const entryEdit = editFor(entry);
      const selected = state.selected.has(entry.id);
      const active = state.activeId === entry.id;
      return `<button class="schedule-option${selected ? " is-selected" : ""}${active ? " is-active" : ""}" type="button" data-id="${escapeHtml(entry.id)}">
        <strong>${escapeHtml(formatDate(entryEdit.date))}</strong>
        <span>${entryEdit.all_day ? "종일" : escapeHtml(entryEdit.time || "시간 미정")}</span>
      </button>`;
    }).join("");
    const expanded = state.expanded.has(group.key);
    const fullText = item.full_text || item.context;
    const canExpand = fullText.length > item.context.length;
    const row = document.createElement("article");
    row.className = `candidate-row${selectedItems.length ? " is-selected" : ""}${group.items.every((entry) => entry.synced) ? " is-synced" : ""}`;
    row.dataset.group = group.key;
    row.dataset.source = item.source_table;
    row.innerHTML = `
      <input class="row-check" type="checkbox" aria-label="${escapeHtml(edit.title)}의 모든 일정 선택" ${selectedItems.length === group.items.length ? "checked" : ""}>
      <div class="message-date-cell"><strong>${escapeHtml(messageDate.value)}</strong><span>${escapeHtml(messageDate.label)}</span></div>
      <div class="schedule-cell">${scheduleOptions}</div>
      <div class="title-cell"><strong>${escapeHtml(edit.title)}</strong>${item.synced ? '<span class="row-badge">등록 완료</span>' : ""}<p class="${expanded ? "is-full" : ""}">${escapeHtml(expanded ? fullText : item.context)}</p>${canExpand ? `<button class="expand-toggle" type="button" aria-expanded="${expanded}">${expanded ? "접기" : "전체 내용 보기"}</button>` : ""}${edit.location ? `<span class="location-meta">장소 ${escapeHtml(edit.location)}</span>` : ""}</div>
      <div class="person-cell">${escapeHtml(item.person || "")}</div>
      `;
    row.querySelector(".expand-toggle")?.addEventListener("click", () => {
      state.expanded.has(group.key) ? state.expanded.delete(group.key) : state.expanded.add(group.key);
      render();
    });
    const groupCheck = row.querySelector(".row-check");
    groupCheck.indeterminate = selectedItems.length > 0 && selectedItems.length < group.items.length;
    groupCheck.addEventListener("change", (event) => {
      for (const entry of group.items) event.target.checked ? state.selected.add(entry.id) : state.selected.delete(entry.id);
      state.activeId = event.target.checked ? group.items[0].id : ([...state.selected][0] || null);
      render();
      renderReview();
    });
    row.querySelectorAll(".schedule-option").forEach((button) => {
      button.addEventListener("click", () => {
        state.activeId = button.dataset.id;
        state.selected.add(button.dataset.id);
        render();
        renderReview();
      });
    });
    row.addEventListener("click", (event) => {
      if (event.target.closest("input, button")) return;
      state.activeId = selectedItems[0]?.id || item.id;
      state.selected.add(state.activeId);
      render();
      renderReview();
    });
    refs.candidateList.appendChild(row);
  }
  updateActions();
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
}

function toggleItem(id, checked) {
  checked ? state.selected.add(id) : state.selected.delete(id);
  if (checked) state.activeId = id;
  if (!checked && state.activeId === id) state.activeId = [...state.selected][0] || null;
  render();
  renderReview();
}

function updateActions() {
  const disabled = state.selected.size === 0;
  refs.icsButton.disabled = disabled;
  refs.dismissButton.disabled = disabled;
  refs.calendarButton.disabled = disabled || !state.bootstrap?.googleConnected;
}

function renderReview() {
  const item = state.items.find((entry) => entry.id === state.activeId);
  refs.reviewEmpty.classList.toggle("hidden", Boolean(item));
  refs.reviewForm.classList.toggle("hidden", !item);
  if (!item) return;
  const edit = editFor(item);
  refs.editTitle.value = edit.title;
  refs.editDate.value = edit.date;
  refs.editTime.value = edit.time;
  refs.editEndTime.value = edit.end_time;
  refs.editAllDay.checked = edit.all_day;
  refs.editTime.disabled = edit.all_day;
  refs.editEndTime.disabled = edit.all_day;
  refs.editLocation.value = edit.location;
  refs.editAssignee.value = edit.assignee;
  refs.editReminder.value = String(edit.reminder_minutes);
  refs.editMessageDate.textContent = formatMessageDate(item);
  refs.editContext.textContent = item.full_text || item.context;
}

function selectedEvents() {
  return [...state.selected].map((id) => {
    const item = state.items.find((entry) => entry.id === id);
    const edit = editFor(item);
    return {
      ...edit,
      uid: `coolmemo-${item.source_table}-${item.source_key}-${item.occurrence_key}@local`,
      description: `담당자: ${edit.assignee || ""}\n${formatMessageDate(item)}\n쿨메신저 원본: ${item.source_table} #${item.source_key}\n\n${item.context}`,
    };
  });
}

function applyTheme(theme) {
  if (!theme) return;
  document.documentElement.dataset.theme = theme;
  document.querySelectorAll(".theme-option").forEach((button) => {
    button.setAttribute("aria-checked", String(button.dataset.themeId === theme));
  });
}

async function loadBootstrap() {
  const data = await api("/api/bootstrap");
  state.token = data.token;
  state.bootstrap = data;
  refs.sourceStatus.textContent = data.sourceExists ? `메신저 ${new Date(data.sourceUpdated * 1000).toLocaleString("ko-KR")} 갱신` : "UDB 선택 필요";
  refs.sourceStatus.title = data.sourcePath || "쿨메신저 UDB 파일을 선택해 주세요.";
  refs.sourcePathInput.value = data.sourcePath || "";
  refs.sourceChoiceHint.textContent = `자동 검색 ${data.sourceCandidates?.length || 0}개`;
  refs.sourceStatus.classList.toggle("is-warn", !data.sourceExists);
  applyTheme(data.theme);
  $("appVersion").textContent = `v${data.version}`;
  refs.googleStatus.textContent = data.googleConnected ? "연결됨" : "미연결";
  refs.connectionBadge.textContent = data.googleConnected ? "Google 연결됨" : "Google 미연결";
  refs.connectionBadge.className = `badge ${data.googleConnected ? "connected" : "neutral"}`;
  refs.connectedPanel.classList.toggle("hidden", !data.googleConnected);
  refs.setupPanel.classList.toggle("hidden", data.googleConnected);
  updateActions();
  await loadCalendars();
}

async function loadCalendars() {
  const picker = $("calendarPicker");
  const select = $("calendarSelect");
  const connected = state.bootstrap?.googleConnected;
  $("reconnectNote").classList.toggle("hidden", !connected || state.bootstrap.googleCanListCalendars);
  picker.classList.add("hidden");
  if (!connected || !state.bootstrap.googleCanListCalendars) return;
  try {
    const data = await api("/api/google/calendars");
    if (!data.calendars.length) return;
    select.innerHTML = data.calendars.map((cal) =>
      `<option value="${escapeHtml(cal.id)}">${escapeHtml(cal.name)}${cal.primary ? " (기본)" : ""}</option>`).join("");
    const exists = data.calendars.some((cal) => cal.id === data.selected);
    select.value = exists ? data.selected : data.calendars[0].id;
    picker.classList.remove("hidden");
  } catch (error) {
    showToast(error.message, 6000);
  }
}

async function checkUpdate(manual = false) {
  try {
    const info = await api(`/api/update?force=${manual ? 1 : 0}`);
    state.update = info;
    const banner = $("updateBanner");
    const dismissed = state.updateDismissed === info.latest;
    if (info.available && (manual || !dismissed)) {
      $("updateText").textContent = `새 버전 v${info.latest}이 있습니다. (현재 v${info.current})`;
      $("updateInstallButton").textContent = info.canAutoInstall ? "업데이트" : "다운로드 페이지 열기";
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }
    if (manual) {
      showToast(info.available ? `새 버전 v${info.latest}이 있습니다.` : info.error || "최신 버전입니다.", 4000);
    }
  } catch (error) {
    if (manual) showToast(error.message, 5000);
  }
}

async function installUpdate() {
  const info = state.update;
  if (!info?.available) return;
  if (!info.canAutoInstall) {
    window.open(info.pageUrl, "_blank", "noopener");
    return;
  }
  if (!confirm(`v${info.latest}로 업데이트할까요?\n설치하는 동안 프로그램이 잠시 종료되었다가 다시 열립니다.\n설정과 Google 연결은 그대로 유지됩니다.`)) return;
  const button = $("updateInstallButton");
  button.disabled = true;
  button.textContent = "내려받는 중...";
  try {
    await api("/api/update/install", {method: "POST", body: {}});
    $("updateText").textContent = "설치 중입니다. 잠시 후 프로그램이 다시 열립니다. 이 탭은 닫아도 됩니다.";
    $("updateInstallButton").classList.add("hidden");
    $("updateLaterButton").classList.add("hidden");
  } catch (error) {
    button.disabled = false;
    button.textContent = "업데이트";
    showToast(error.message, 8000);
  }
}

async function loadCandidates(force = false) {
  refs.loadingState.classList.remove("hidden");
  refs.candidateList.classList.add("hidden");
  refs.emptyState.classList.add("hidden");
  try {
    const days = refs.periodSelect.value;
    const data = await api(`/api/candidates?days=${days}&force=${force ? 1 : 0}`);
    state.items = data.items.sort((left, right) =>
      messageTimestamp(right) - messageTimestamp(left) || right.source_key - left.source_key
    );
    state.selected.clear();
    state.activeId = null;
    refs.updatedAt.textContent = `${new Date(data.updated * 1000).toLocaleTimeString("ko-KR", {hour:"2-digit",minute:"2-digit"})} 확인`;
    render();
    renderReview();
  } catch (error) {
    showToast(error.message, 6000);
  } finally {
    refs.loadingState.classList.add("hidden");
  }
}

refs.reviewForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const item = state.items.find((entry) => entry.id === state.activeId);
  if (!item) return;
  state.edits.set(item.id, {
    ...editFor(item), title: refs.editTitle.value.trim(), date: refs.editDate.value,
    time: refs.editTime.value, end_time: refs.editEndTime.value, all_day: refs.editAllDay.checked,
    location: refs.editLocation.value.trim(), assignee: refs.editAssignee.value.trim(),
    reminder_minutes: Number(refs.editReminder.value),
  });
  showToast("수정 내용을 선택 일정에 적용했습니다.");
  render();
});

refs.editAllDay.addEventListener("change", () => {
  refs.editTime.disabled = refs.editAllDay.checked;
  refs.editEndTime.disabled = refs.editAllDay.checked;
});
refs.searchInput.addEventListener("input", render);
refs.hidePast.addEventListener("change", render);
refs.hideSynced.addEventListener("change", render);
refs.hideDismissed.addEventListener("change", render);
document.querySelectorAll(".message-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    state.activeSource = tab.dataset.source;
    document.querySelectorAll(".message-tab").forEach((item) => {
      const active = item === tab;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-selected", String(active));
    });
    state.activeId = filteredItems().find((item) => state.selected.has(item.id))?.id || null;
    render();
    renderReview();
  });
});
refs.periodSelect.addEventListener("change", () => loadCandidates(false));
$("refreshButton").addEventListener("click", () => loadCandidates(true));
refs.selectAll.addEventListener("change", () => {
  for (const item of filteredItems()) refs.selectAll.checked ? state.selected.add(item.id) : state.selected.delete(item.id);
  state.activeId = [...state.selected][0] || null;
  render(); renderReview();
});

refs.icsButton.addEventListener("click", async () => {
  try {
    const response = await api("/api/export-ics", {method:"POST", body:{events:selectedEvents()}, raw:true});
    if (!response.ok) throw new Error("ICS 파일을 만들지 못했습니다.");
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "쿨메신저_선택일정.ics";
    link.click();
    URL.revokeObjectURL(link.href);
    showToast("선택 일정을 ICS 파일로 만들었습니다.");
  } catch (error) { showToast(error.message, 6000); }
});

refs.calendarButton.addEventListener("click", async () => {
  const events = selectedEvents();
  const calName = $("calendarSelect").selectedOptions[0]?.textContent || "Google Calendar";
  if (!confirm(`${events.length}개 일정을 [${calName}]에 등록할까요?\n이미 등록한 일정은 수정되고, 다른 캘린더에 있으면 선택한 캘린더로 옮겨집니다.`)) return;
  refs.calendarButton.disabled = true;
  refs.calendarButton.textContent = "등록 중...";
  try {
    const data = await api("/api/calendar/events", {method:"POST", body:{events, calendar_id: $("calendarSelect").value || undefined}});
    showToast(`${data.results.length}개 일정을 등록했습니다.`);
    await loadCandidates(true);
  } catch (error) { showToast(error.message, 7000); }
  finally { refs.calendarButton.textContent = "Google Calendar에 등록"; updateActions(); }
});

refs.dismissButton.addEventListener("click", async () => {
  const ids = [...state.selected];
  if (!ids.length) return;
  await api("/api/dismiss", {method:"POST", body:{ids}});
  showToast(`${ids.length}개 후보를 제외했습니다.`);
  await loadCandidates(true);
});

$("settingsButton").addEventListener("click", () => refs.settingsDialog.showModal());
$("emptySetupButton").addEventListener("click", () => refs.settingsDialog.showModal());
document.querySelectorAll(".theme-option").forEach((button) => {
  button.addEventListener("click", async () => {
    const previous = document.documentElement.dataset.theme;
    applyTheme(button.dataset.themeId);
    try {
      await api("/api/theme", {method:"POST", body:{theme:button.dataset.themeId}});
    } catch (error) {
      applyTheme(previous);
      showToast(error.message, 6000);
    }
  });
});
$("updateInstallButton").addEventListener("click", installUpdate);
$("updateLaterButton").addEventListener("click", () => {
  state.updateDismissed = state.update?.latest;
  $("updateBanner").classList.add("hidden");
});
$("checkUpdateButton").addEventListener("click", () => checkUpdate(true));
$("quitButton").addEventListener("click", async () => {
  if (!confirm("메모 일정함을 완전히 종료할까요?\n종료 후에는 바로가기로 다시 실행할 수 있습니다.")) return;
  try { await api("/api/quit", {method:"POST", body:{}}); } catch (_) { /* 서버가 먼저 닫혀도 정상입니다. */ }
  document.body.innerHTML = '<p style="padding:48px;font-size:16px">메모 일정함이 종료되었습니다. 이 탭은 닫아도 됩니다.</p>';
});
$("autoSourceButton").addEventListener("click", async () => {
  try {
    const data = await api("/api/source/auto", {method:"POST", body:{}});
    await loadBootstrap();
    await loadCandidates(true);
    showToast(`UDB를 자동 선택했습니다: ${data.path.split(/[\\/]/).pop()}`);
  } catch (error) { showToast(error.message, 7000); }
});
$("applySourceButton").addEventListener("click", async () => {
  try {
    const path = refs.sourcePathInput.value.trim();
    if (!path) throw new Error("UDB 파일 경로를 입력해 주세요.");
    await api("/api/source/set", {method:"POST", body:{path}});
    await loadBootstrap();
    await loadCandidates(true);
    showToast("입력한 UDB 파일을 적용했습니다.");
  } catch (error) { showToast(error.message, 7000); }
});
$("pickSourceButton").addEventListener("click", async () => {
  const button = $("pickSourceButton");
  button.disabled = true;
  button.textContent = "선택 창 여는 중...";
  try {
    const data = await api("/api/source/pick", {method:"POST", body:{}});
    if (!data.path) return;
    await loadBootstrap();
    await loadCandidates(true);
    showToast("선택한 UDB 파일을 적용했습니다.");
  } catch (error) { showToast(error.message, 7000); }
  finally { button.disabled = false; button.textContent = "UDB 파일 선택"; }
});
$("connectButton").addEventListener("click", async () => {
  try {
    const file = $("credentialsFile").files[0];
    if (file) {
      const credentials = JSON.parse(await file.text());
      await api("/api/google/credentials", {method:"POST", body:{credentials}});
      await loadBootstrap();
    }
    if (!state.bootstrap.googleConfigured) throw new Error("OAuth 클라이언트 JSON 파일을 먼저 선택해 주세요.");
    const {url} = await api("/api/google/auth-url");
    const popup = window.open(url, "google-oauth", "width=640,height=760");
    if (!popup) { location.href = url; return; }
    showToast("Google 계정에서 연결을 승인한 뒤 이 화면으로 돌아오세요.", 6000);
    waitForGoogleConnection();
  } catch (error) { showToast(error.message, 7000); }
});

async function waitForGoogleConnection() {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 3000));
    try {
      await loadBootstrap();
      if (state.bootstrap.googleConnected) {
        refs.settingsDialog.close();
        showToast("Google Calendar 연결이 완료되었습니다.");
        return;
      }
    } catch (_) {
      // 다음 확인 때 다시 시도합니다.
    }
  }
  showToast("연결 상태를 확인하지 못했습니다. 연결 설정을 다시 열어 확인해 주세요.", 7000);
}
$("calendarSelect").addEventListener("change", async () => {
  try { await api("/api/google/calendar", {method:"POST", body:{calendar_id: $("calendarSelect").value}}); }
  catch (error) { showToast(error.message, 6000); }
});
$("reauthButton").addEventListener("click", async () => {
  try {
    const {url} = await api("/api/google/auth-url");
    location.href = url;
  } catch (error) { showToast(error.message, 7000); }
});
$("disconnectButton").addEventListener("click", async () => {
  if (!confirm("이 PC에 저장된 Google 연결 정보를 삭제할까요?")) return;
  await api("/api/google/disconnect", {method:"POST", body:{}});
  await loadBootstrap();
  showToast("Google Calendar 연결을 해제했습니다.");
});

(async function init() {
  try {
    await loadBootstrap();
    checkUpdate(false);
    await loadCandidates(false);
  } catch (error) {
    showToast(error.message, 8000);
  }
})();
