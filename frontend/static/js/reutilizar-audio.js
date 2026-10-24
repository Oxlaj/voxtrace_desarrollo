(() => {
  const actions = document.getElementById("reuse-actions");
  if (!actions) return;
  const result = document.getElementById("analysis-results");
  const context = document.getElementById("detail-context");
  const getId = () => result ? result.dataset.analysisId : context.dataset.analysisId;
  const link = document.getElementById("reuse-new-person");
  const form = document.getElementById("reuse-person-form");
  const select = document.getElementById("reuse-person-select");
  const message = document.getElementById("reuse-message");
  const update = () => {
    link.href = `/app/personas/nueva?id_analisis=${encodeURIComponent(getId())}`;
    form.hidden = true;
    select.replaceChildren(new Option("Seleccione una persona", ""));
    message.textContent = "";
  };
  update();
  if (result) new MutationObserver(update).observe(result, {attributes: true, attributeFilter: ["data-analysis-id"]});
  async function search() {
    try {
      const search = document.getElementById("reuse-person-search").value.trim();
      const people = await VoxTraceAPI.request(`/personas?search=${encodeURIComponent(search)}`);
      select.replaceChildren(new Option("Seleccione una persona", ""));
      people.forEach(person => select.add(new Option(`${person.identificador} · ${person.nombre}${person.alias ? ` · ${person.alias}` : ""}`, String(person.id_persona))));
      message.textContent = people.length ? "Seleccione la persona y confirme la asociación." : "No se encontraron personas.";
    } catch (error) { message.textContent = "No fue posible consultar las personas."; }
  }
  document.getElementById("reuse-existing-person").addEventListener("click", () => { form.hidden = false; search(); });
  document.getElementById("reuse-search").addEventListener("click", search);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const personId = Number(select.value);
    const label = select.selectedOptions[0].textContent;
    if (!window.confirm(`¿Confirma asociar el audio del análisis #${getId()} a ${label}?`)) return;
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const response = await VoxTraceAPI.request(`/analisis/${getId()}/muestra`, {method: "POST", body: JSON.stringify({id_persona: personId, confirmar: true})});
      window.location.assign(`/app/personas/${response.id_persona}/muestras`);
    } catch (error) { message.textContent = error.message || "No fue posible asociar el audio."; }
    finally { button.disabled = false; }
  });
})();
