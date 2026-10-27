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
  setText("service-link", provider.name === "ollama" ? `API → Ollama: ${catalog.deployment.ollama_url}` : "API → Mock（模拟）");
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
  resetResult("hardened", "等待基线推理完成…");
  setText("gateway-payload", "等待加固提示词结果");
  setText("live-status", "开始运行基线提示词。提示：模型输出不会执行。 ");

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
    resetResult("hardened", "正在运行加固提示词…");
    setText("live-status", "基线完成，正在运行加固提示词。 ");

    const hardened = await generate("hardened", payload);
    renderResult("hardened", hardened);
    completed.add("hardened");
    if (hardened.candidate_sql) {
      const handoff = {
        request_id: hardened.request_id,
        principal_id: payload.principal_id,
        candidate_sql: hardened.candidate_sql,
        schema_version: hardened.provenance.schema_version,
      };
      setText("gateway-payload", JSON.stringify(handoff, null, 2));
    } else {
      setText("gateway-payload", "加固提示词已拒绝：没有候选 SQL，不向网关发送载荷。");
    }
    setText("live-status", "攻防对照运行完成。安全网关尚未接入。 ");
  } catch (error) {
    for (const profile of ["baseline", "hardened"]) {
      if (!completed.has(profile)) {
        resetResult(profile, "本轮未取得结果，SQL 未执行");
        byId(`${profile}-status`).className = "status-pill status-danger";
      }
    }
    setText("gateway-payload", "本轮失败，没有可发送的联调载荷。");
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

