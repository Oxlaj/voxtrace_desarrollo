const personForm = document.getElementById("create-person-form");
const personMessage = document.getElementById("form-message");
const optional = id => document.getElementById(id).value.trim() || null;
const sourceId = new URLSearchParams(window.location.search).get("id_analisis");
const validSource = sourceId !== null && /^[1-9][0-9]*$/.test(sourceId);
const firstSample = document.getElementById("first-sample");
if (sourceId !== null) {
  document.getElementById("first-sample-field").hidden = true;
  firstSample.disabled = true;
}
if (sourceId !== null) {
  const note = document.createElement("p");
  note.textContent = validSource ? `El audio del análisis #${sourceId} se asociará como primera muestra después de su confirmación.` : "Referencia de análisis inválida.";
  personForm.prepend(note);
}
personForm.addEventListener("submit", async event => {
  event.preventDefault();
  personMessage.textContent = "";
  if (!personForm.reportValidity()) return;
  if (sourceId !== null && !validSource) { personMessage.textContent = "Referencia de análisis inválida."; return; }
  const payload = {identificador: document.getElementById("identificador").value.trim(), nombre: document.getElementById("nombre").value.trim(), alias: optional("alias"), descripcion: optional("descripcion"), observaciones: optional("observaciones")};
  const audio = validSource ? null : firstSample.files[0];
  if (audio && !/\.(mp3|ogg|mp4|wav)$/i.test(audio.name)) {
    personMessage.textContent = "Formato no admitido. Seleccione MP3, OGG, MP4 o WAV.";
    return;
  }
  if (validSource && !window.confirm(`¿Confirma registrar a ${payload.nombre} (${payload.identificador}) y asociar el audio del análisis #${sourceId} como primera muestra?`)) return;
  const button = personForm.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    let body = JSON.stringify(validSource ? {nueva_persona: payload, confirmar: true} : payload);
    if (audio) {
      body = new FormData();
      body.append("persona", JSON.stringify(payload));
      body.append("file", audio);
    }
    const response = await window.VoxTraceAPI.request(validSource ? `/analisis/${sourceId}/muestra` : audio ? "/personas/con-muestra" : "/personas", {method: "POST", body});
    personMessage.textContent = "Persona registrada correctamente.";
    personMessage.className = "message success";
    window.setTimeout(() => window.location.assign(validSource || audio ? `/app/personas/${response.id_persona}/muestras` : "/app/personas?creada=1"), 500);
  } catch (error) {
    personMessage.textContent = error.status === 403 ? "No tienes permisos para registrar personas." : error.message || "No fue posible registrar la persona.";
    personMessage.className = "message error";
  } finally { button.disabled = false; }
});
