/** Live audit-chain replay from the real agentsys demo story. */
const DEMO_EVENTS = [
  { kind: "task.claim", actor: "mock:local:work", hash: "a3f91c02" },
  { kind: "task.submit", actor: "mock:local:work", hash: "b804e119" },
  { kind: "verify.results", actor: "system:verifier", hash: "c12d44aa", fail: true },
  { kind: "task.submit", actor: "mock:local:work", hash: "d9e0f331" },
  { kind: "verify.results", actor: "system:verifier", hash: "e41ab902" },
  { kind: "task.approve", actor: "claude:peer:reviewer", hash: "f550c218" },
  { kind: "approval.granted", actor: "human:demo", hash: "0a61d44e" },
  { kind: "task.merge", actor: "human:demo", hash: "1b72e55f" },
];

export function initChain(root) {
  const list = root.querySelector(".chain-list");
  const status = root.querySelector(".chain-status");
  const stepBtn = root.querySelector("[data-chain-step]");
  const tamperBtn = root.querySelector("[data-chain-tamper]");
  const resetBtn = root.querySelector("[data-chain-reset]");
  let idx = 0;
  let tampered = false;

  function render() {
    list.innerHTML = "";
    for (let i = 0; i < idx; i++) {
      const e = { ...DEMO_EVENTS[i] };
      if (tampered && i === 2) e.hash = "deadbeef";
      const li = document.createElement("li");
      li.innerHTML = `<span class="kind">${e.kind}</span><span class="actor">${e.actor}</span><span class="hash">${e.hash}</span>`;
      list.appendChild(li);
    }
    if (idx === 0) {
      status.textContent = "Step through the demo audit trail.";
      return;
    }
    if (tampered) {
      status.textContent = "verify-log would FAIL: hash mismatch at event 3.";
      return;
    }
    if (idx >= DEMO_EVENTS.length) {
      status.textContent = "Chain clean — same story as AGENTSYS_DEMO=1 agentsys demo.";
      return;
    }
    status.textContent = `Event ${idx} of ${DEMO_EVENTS.length}.`;
  }

  stepBtn?.addEventListener("click", () => {
    if (idx < DEMO_EVENTS.length) idx += 1;
    render();
  });
  tamperBtn?.addEventListener("click", () => {
    tampered = true;
    if (idx < 3) idx = 3;
    render();
  });
  resetBtn?.addEventListener("click", () => {
    idx = 0;
    tampered = false;
    render();
  });
  render();
}
