"use strict";

const byId = (id) => document.getElementById(id);
const state = { catalog: null };

function setText(id, value) {
  const element = byId(id);
  if (element) element.textContent = value == null || value === "" ? "—" : String(value);
}

function setStatus(prefix, status, isMock, warnings) {
  const element = byId(`${prefix}-status`);
  element.className = "status-pill";
  const dangerous = warnings.includes("non_read_only_candidate") || warnings.includes("multiple_statements");
  if (status === "generated" && dangerous) {
    element.classList.add("status-danger");
    element.textContent = isMock ? "危险候选 · 模拟" : "危险候选";
  } else if (status === "generated") {
    element.classList.add("status-success");
    element.textContent = isMock ? "已生成 · 模拟" : "已生成";
  } else if (status === "refused") {
    element.classList.add("status-success");
    element.textContent = isMock ? "已拒绝 · 模拟" : "已拒绝";
  } else if (status === "invalid_output") {
    element.classList.add("status-danger");
    element.textContent = "格式无效";
  } else {
    element.classList.add("status-neutral");
    element.textContent = status;
  }
}

function resetResult(prefix, message) {
  setText(`${prefix}-status`, message);
  const status = byId(`${prefix}-status`);
  status.className = "status-pill status-neutral";
  setText(`${prefix}-version`, "—");
  setText(`${prefix}-latency`, "—");
  setText(`${prefix}-sql`, message);
  setText(`${prefix}-diagnostics`, "—");
  setText(`${prefix}-raw`, "—");
}

function renderResult(prefix, data) {
  const isMock = data.provenance.provider === "mock";
  setStatus(prefix, data.status, isMock, data.diagnostics.warnings);
  setText(`${prefix}-version`, `${data.provenance.prompt_version} / ${data.provenance.prompt_hash}`);
  setText(`${prefix}-latency`, `${data.provenance.latency_ms} ms`);
  const primaryOutput = data.candidate_sql || data.refusal_reason || "模型未返回可用结果";
  setText(`${prefix}-sql`, primaryOutput);
  setText(`${prefix}-diagnostics`, JSON.stringify(data.diagnostics, null, 2));
  setText(`${prefix}-raw`, data.raw_model_output || "Demo 模式关闭，原始输出未返回");
}

function executorLabel(data) {
  if (data.executor === "lab_direct") return "实验室直连（非 C 网关）";
  if (data.status === "unavailable") return "C 未接入";
  if (data.status === "refused" || data.status === "invalid_output") return "C 未参与（模型未生成）";
  return "C 正式网关";
}

function clearGatewayTable() {
  const container = byId("gateway-table");
  if (!container) return;
  container.replaceChildren();
  container.hidden = true;
}

function renderRowsTable(container, result) {
  if (!container) return;
  container.replaceChildren();
  if (!result) {
    container.hidden = true;
    return;
  }
  if (result.rows.length === 0) {
    const note = document.createElement("p");
    note.textContent = "查询成功，结果为空：可能是 RLS 行级权限过滤，也可能本身没有匹配行。";
    container.appendChild(note);
    container.hidden = false;
    return;
  }
  const table = document.createElement("table");
  table.className = "gateway-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const column of result.columns) {
    const th = document.createElement("th");
    th.textContent = column.name;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const row of result.rows) {
    const tr = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      td.textContent = cell == null ? "NULL" : String(cell);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  container.appendChild(table);
  container.hidden = false;
}

function renderGatewayTable(result) {
  renderRowsTable(byId("gateway-table"), result);
}

function resetGateway(message) {
  const status = byId("gateway-status");
  status.className = "status-pill status-neutral";
  status.textContent = message;
  setText("gateway-summary", message);
  setText("gateway-decision", "—");
  setText("gateway-executor", "—");
  setText("gateway-db-role", "—");
  setText("gateway-rows", "—");
  setText("gateway-masked", "—");
  setText("gateway-policy-version", "—");
  setText("gateway-execution", "—");
  setText("gateway-request-id", "—");
  setText("gateway-audit", "—");
  setText("gateway-result", message);
  clearGatewayTable();
}

function renderGatewayResult(data) {
  const status = byId("gateway-status");
  status.className = "status-pill";
  const decision = data.gateway ? data.gateway.decision : null;
  const result = data.result || null;
  const error = data.error || null;
  let summary;

  if (data.status === "executed") {
    status.classList.add("status-success");
    if (result && result.row_count === 0) {
      status.textContent = "成功 · 空结果";
      summary = "C 放行 → PostgreSQL 返回 0 行（可能被 RLS 过滤，也可能本身为空）";
    } else {
      status.textContent = "已执行";
      summary = `C ${decision || "ALLOW"} → PostgreSQL 返回 ${result ? result.row_count : 0} 行`;
    }
  } else if (data.status === "blocked") {
    status.classList.add("status-danger");
    status.textContent = "C 已阻断";
    summary = "C 阻断候选 SQL，未执行数据库查询";
  } else if (data.status === "error") {
    status.classList.add("status-danger");
    status.textContent = "数据库错误";
    summary = "C 已放行，但 PostgreSQL 执行失败";
  } else if (data.status === "unavailable") {
    status.classList.add("status-neutral");
    status.textContent = "C 未接入";
    summary = "C 未接入，SQL 未执行";
  } else if (data.status === "refused" || data.status === "invalid_output") {
    status.classList.add("status-neutral");
    status.textContent = "未进入网关";
    summary = "没有候选 SQL，不向网关发送载荷";
  } else {
    status.classList.add("status-neutral");
    status.textContent = data.status;
    summary = `状态：${data.status}`;
  }

  const modelOutcome = data.status === "refused" || data.status === "invalid_output";
  let decisionText = "—";
  if (data.gateway) {
    decisionText = `${data.gateway.decision} / ${data.gateway.reason_code}`;
    if (error) decisionText += `；数据库 ${error.stage}/${error.code}`;
  } else if (error) {
    decisionText = `${error.stage} / ${error.code}`;
  } else if (data.status === "unavailable") {
    decisionText = "未产生决策（C 未接入）";
  } else if (data.status === "refused") {
    decisionText = "未产生决策（模型拒答）";
  } else if (data.status === "invalid_output") {
    decisionText = "未产生决策（模型输出无效）";
  }

  let dbRoleText = data.db_role || "—";
  if (data.status === "blocked") dbRoleText = "未执行（C 阻断）";
  else if (data.status === "unavailable") dbRoleText = "未连接";
  else if (modelOutcome) dbRoleText = "未连接（无候选 SQL）";

  let rowsText = "—";
  if (result) rowsText = `${result.row_count} 行${result.truncated ? "（已截断）" : ""}`;
  else if (data.status === "blocked") rowsText = "0（未执行）";
  else if (data.status === "error") rowsText = "0（执行失败）";
  else if (data.status === "unavailable" || modelOutcome) rowsText = "未执行";

  const maskedText = result
    ? (result.masked_columns && result.masked_columns.length
      ? result.masked_columns.join(", ")
      : "—")
    : data.status === "error" ? "未返回结果" : "未执行";

  setText("gateway-summary", summary);
  setText("gateway-decision", decisionText);
  setText("gateway-executor", executorLabel(data));
  setText("gateway-db-role", dbRoleText);
  setText("gateway-rows", rowsText);
  setText("gateway-masked", maskedText);
  setText("gateway-policy-version", data.gateway ? data.gateway.policy_version : "未调用 C");
  setText(
    "gateway-execution",
    result ? `${result.execution_ms} ms` : data.status === "error" ? "执行失败" : "未执行",
  );
  setText("gateway-request-id", data.request_id || "—");
  setText("gateway-audit", data.gateway ? data.gateway.audit_id : "未写入审计");

  if (result) {
    setText(
      "gateway-result",
      `列：${result.columns.map((column) => column.name).join(", ")}${result.truncated ? "（已截断）" : ""}`,
    );
  } else if (error) {
    setText("gateway-result", `SQLSTATE ${error.sqlstate || "—"} / ${error.code}\n${error.message}`);
  } else if (data.status === "blocked") {
    setText("gateway-result", `C 策略阻断：${data.gateway ? data.gateway.reason_code : "—"}`);
  } else {
    setText("gateway-result", summary);
  }
  renderGatewayTable(result);
}

function fillSelect(selectId, items, valueKey, labelKey) {
  const select = byId(selectId);
  select.replaceChildren();
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item[valueKey];
    option.textContent = item[labelKey];
    select.appendChild(option);
  }
}

function applyScenario() {
  if (!state.catalog) return;
  const selectedId = byId("scenario").value;
  const scenario = state.catalog.scenarios.find((item) => item.id === selectedId);
  if (!scenario) return;
  byId("principal").value = scenario.principal_id;
  byId("context-profile").value = scenario.context_profile;
  byId("question").value = scenario.question;
  updateQuestionCount();
}

function updateQuestionCount() {
  setText("question-count", byId("question").value.length);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload && payload.error ? payload.error.message : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

async function loadCatalog() {
  const catalog = await fetchJson("/api/v1/demo/catalog", { headers: { Accept: "application/json" } });
  state.catalog = catalog;
  fillSelect("principal", catalog.principals, "id", "label");
  fillSelect("scenario", catalog.scenarios, "id", "label");
  fillSelect("context-profile", catalog.contexts, "id", "label");
  applyScenario();

  const provider = catalog.provider;
  const badge = byId("provider-badge");
  badge.className = `status-pill ${provider.ready ? "status-success" : "status-danger"}`;
  badge.textContent = `${provider.name.toUpperCase()} · ${provider.ready ? "READY" : "DEGRADED"}`;
  setText("model-name", `model: ${provider.model}`);
  setText("schema-version", `schema: ${catalog.schema_version}`);
  setText("model-digest", `digest: ${provider.digest || "unavailable"}`);
  setText("prompt-versions", `prompts: ${catalog.prompt_versions.join(" / ")}`);
  const deployment = catalog.deployment || {};
  setText("service-link", provider.name === "ollama" ? `API → Ollama: ${deployment.ollama_url}` : "API → Mock（模拟）");
  setText(
    "gateway-executor",
    deployment.executor === "lab_direct"
      ? "实验室直连（非 C 网关）"
      : deployment.gateway_connected
        ? "C 正式网关"
        : "C 未接入",
  );
  if (!catalog.demo_mode) {
    byId("run-button").disabled = true;
    throw new Error("Demo 模式未开启。请按 README 的本地演示命令启动后运行对照。");
  }
}

async function generate(profile, payload) {
  return fetchJson("/api/v1/generations", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ ...payload, prompt_profile: profile }),
  });
}

async function queryDatabase(payload) {
  const response = await fetch("/api/v1/queries", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (response.status === 503 && body && body.status === "unavailable") {
    return body;
  }
  if (!response.ok) {
    const message = body && body.error ? body.error.message : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return body;
}

function showError(message) {
  const panel = byId("error-panel");
  panel.textContent = message;
  panel.hidden = false;
  setText("live-status", `运行失败：${message}`);
}

function setBusy(busy) {
  byId("run-button").disabled = busy;
  document.querySelector(".button-idle").hidden = busy;
  document.querySelector(".button-busy").hidden = !busy;
}

async function runExperiment(event) {
  event.preventDefault();
  byId("error-panel").hidden = true;
  setBusy(true);
  resetResult("baseline", "正在运行基线提示词…");
  resetResult("hardened", "等待生成加固候选…");
  resetGateway("等待安全查询");
  setText("gateway-payload", "仅发送自然语言、演示身份和上下文");
  setText("live-status", "开始运行基线提示词。提示：模型输出不会直接执行。 ");

  const payload = {
    question: byId("question").value,
    principal_id: byId("principal").value,
    context_profile: byId("context-profile").value,
  };
  const completed = new Set();

  try {
    const baseline = await generate("baseline", payload);
    renderResult("baseline", baseline);
    completed.add("baseline");
    resetResult("hardened", "正在生成加固候选并交给 C…");
    setText("live-status", "基线完成，正在生成加固候选并交给 C。 ");

    const queryResult = await queryDatabase(payload);
    renderResult("hardened", queryResult.generation);
    completed.add("hardened");
    renderGatewayResult(queryResult);
    setText("gateway-payload", JSON.stringify(payload, null, 2));
    setText("live-status", "安全查询完成：生成、C 决策、PostgreSQL 结果均已返回。 ");
  } catch (error) {
    for (const profile of ["baseline", "hardened"]) {
      if (!completed.has(profile)) {
        resetResult(profile, "本轮未取得结果，SQL 未执行");
        byId(`${profile}-status`).className = "status-pill status-danger";
      }
    }
    resetGateway("本轮未取得结果，SQL 未执行");
    setText("gateway-payload", "本轮失败，没有发送 SQL 或数据库配置。");
    const message = error instanceof Error ? error.message : "未知错误";
    showError(message === "Failed to fetch" ? "无法连接本地服务，请确认服务已启动后重试。" : message);
  } finally {
    setBusy(false);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  byId("scenario").addEventListener("change", applyScenario);
  byId("question").addEventListener("input", updateQuestionCount);
  byId("experiment-form").addEventListener("submit", runExperiment);
  try {
    await loadCatalog();
    setText("live-status", "演示环境已就绪。 ");
  } catch (error) {
    showError(error instanceof Error ? error.message : "无法加载演示配置");
  }
});

