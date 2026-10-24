const sampleContext = document.getElementById("samples-context");
const personId = sampleContext.dataset.personId;
const samplesBody = document.getElementById("samples-body");
const samplesMessage = document.getElementById("samples-message");

function sampleDate(value) { return value ? new Intl.DateTimeFormat("es", {dateStyle: "medium", timeStyle: "short"}).format(new Date(value)) : "No disponible"; }
function renderSamples(items) {
  samplesBody.replaceChildren();
  if (!items.length) { const cell = samplesBody.insertRow().insertCell(); cell.colSpan = 5; cell.className = "empty-state"; cell.textContent = "No existen muestras registradas para esta persona."; return; }
  items.forEach((item) => { const row = samplesBody.insertRow(); [item.nombre_original, item.formato_original.toUpperCase(), item.duracion_segundos == null ? "No disponible" : `${item.duracion_segundos} s`, sampleDate(item.fecha_subida), item.estado_procesamiento === "embedding_disponible" ? "Representación biométrica disponible" : "Representación biométrica no disponible"].forEach((value) => row.insertCell().textContent = value); });
}
async function loadSamples() {
  samplesMessage.textContent = "Cargando muestras…";
  try {
    const [person, items] = await Promise.all([window.VoxTraceAPI.request(`/personas/${personId}`), window.VoxTraceAPI.request(`/personas/${personId}/muestras`)]);
    document.getElementById("person-summary").textContent = `${person.identificador} · ${person.nombre}${person.alias ? ` · ${person.alias}` : ""}`;
    renderSamples(items); samplesMessage.textContent = items.length ? `${items.length} muestra(s) registrada(s).` : "";
  } catch (error) { samplesMessage.textContent = error.status === 404 ? "La persona no está disponible." : "No fue posible cargar las muestras."; samplesMessage.className = "message error"; }
}
const sampleForm = document.getElementById("sample-form");
if (sampleForm) sampleForm.addEventListener("submit", async (event) => {
  event.preventDefault(); const fileInput = document.getElementById("sample-file"); const note = document.getElementById("upload-message");
  if (!fileInput.files.length) { note.textContent = "Selecciona un archivo de audio."; note.className = "message error"; return; }
  note.textContent = "Validando y normalizando audio; después se generará la representación biométrica…"; note.className = "message";
  const data = new FormData(); data.append("file", fileInput.files[0]);
  try { await window.VoxTraceAPI.request(`/personas/${personId}/muestras`, {method: "POST", body: data}); sampleForm.reset(); note.textContent = "Muestra y representación biométrica registradas correctamente."; note.className = "message success"; await loadSamples(); }
  catch (error) { note.textContent = error.status === 409 ? "El archivo ya está registrado." : error.status === 400 ? (error.message || "El archivo no cumple las validaciones.") : "No fue posible registrar la muestra."; note.className = "message error"; }
});
loadSamples();
