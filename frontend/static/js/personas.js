const context = document.getElementById("page-context");
const role = context.dataset.role;
const canEdit = ["Administrador", "Investigador"].includes(role);
const canDelete = role === "Administrador";
const body = document.getElementById("persons-body");
const message = document.getElementById("persons-message");
const dialog = document.getElementById("person-dialog");
let selected = null;

function showMessage(text, type = "") { message.textContent = text; message.className = `message ${type}`; }
function dateLabel(value) { return value ? new Intl.DateTimeFormat("es", {dateStyle: "medium"}).format(new Date(value)) : "No disponible"; }
function render(items) {
  body.replaceChildren();
  if (!items.length) { const cell = body.insertRow().insertCell(); cell.colSpan = 5; cell.className = "empty-state"; cell.textContent = "No hay personas registradas para mostrar."; return; }
  items.forEach((person) => {
    const row = body.insertRow();
    [person.identificador, person.nombre, person.alias || "—", dateLabel(person.fecha_registro)].forEach((value) => { row.insertCell().textContent = value; });
    const actions = row.insertCell();
    const button = document.createElement("button"); button.className = "table-action"; button.type = "button"; button.textContent = "Ver detalle"; button.addEventListener("click", () => openPerson(person.id_persona)); actions.append(button);
    const samples = document.createElement("a"); samples.className = "table-action"; samples.href = `/app/personas/${person.id_persona}/muestras`; samples.textContent = "Muestras"; actions.append(" ", samples);
  });
}
async function loadPeople() {
  showMessage("Cargando personas…");
  try { const query = document.getElementById("person-search").value.trim(); const items = await window.VoxTraceAPI.request(`/personas${query ? `?search=${encodeURIComponent(query)}` : ""}`); render(items); showMessage(items.length ? `${items.length} registro(s) encontrado(s).` : ""); }
  catch (error) { showMessage(error.status === 403 ? "No tienes permisos para consultar personas." : "No fue posible cargar las personas.", "error"); }
}
async function openPerson(id) {
  try {
    selected = await window.VoxTraceAPI.request(`/personas/${id}`);
    ["identificador", "nombre", "alias", "descripcion", "observaciones"].forEach((field) => { document.getElementById(`edit-${field}`).value = selected[field] || ""; });
    document.querySelectorAll("#edit-person-form input, #edit-person-form textarea").forEach((input) => { input.disabled = !canEdit; });
    const editAction = document.querySelector(".can-edit");
    const deleteAction = document.querySelector(".can-delete");
    if (editAction) editAction.hidden = !canEdit;
    if (deleteAction) deleteAction.hidden = !canDelete;
    document.getElementById("dialog-message").textContent = ""; dialog.showModal();
  } catch (error) { showMessage(error.status === 404 ? "La persona ya no está disponible." : "No fue posible consultar el detalle.", "error"); }
}
document.getElementById("search-button").addEventListener("click", loadPeople);
document.getElementById("person-search").addEventListener("keydown", (event) => { if (event.key === "Enter") loadPeople(); });
document.getElementById("close-dialog").addEventListener("click", () => dialog.close());
document.getElementById("edit-person-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (!canEdit || !selected) return;
  const optional = (field) => document.getElementById(`edit-${field}`).value.trim() || null;
  try { await window.VoxTraceAPI.request(`/personas/${selected.id_persona}`, {method: "PATCH", body: JSON.stringify({identificador: document.getElementById("edit-identificador").value.trim(), nombre: document.getElementById("edit-nombre").value.trim(), alias: optional("alias"), descripcion: optional("descripcion"), observaciones: optional("observaciones")})}); dialog.close(); showMessage("Persona actualizada correctamente.", "success"); loadPeople(); }
  catch (error) {
    const note = document.getElementById("dialog-message");
    const messages = {
      400: "Los datos enviados no son válidos.",
      403: "No tienes permisos para editar personas.",
      404: "La persona ya no está disponible.",
      409: "El identificador ya está registrado.",
      422: "Revisa los campos obligatorios y sus longitudes.",
      500: "No fue posible guardar los cambios. Inténtalo nuevamente.",
    };
    note.textContent = messages[error.status] || "No fue posible actualizar la persona.";
    note.className = "message error";
  }
});
document.getElementById("delete-person")?.addEventListener("click", async () => {
  if (!canDelete || !selected || !window.confirm("¿Eliminar este registro? La operación respetará las restricciones del sistema.")) return;
  try { await window.VoxTraceAPI.request(`/personas/${selected.id_persona}`, {method: "DELETE"}); dialog.close(); showMessage("Persona eliminada.", "success"); loadPeople(); }
  catch (error) {
    const note = document.getElementById("dialog-message");
    const messages = {
      403: "No tienes permisos para eliminar personas.",
      404: "La persona ya no está disponible.",
      409: error.message || "No es posible eliminar la persona porque posee información asociada que debe conservarse.",
    };
    note.textContent = messages[error.status] || "No fue posible eliminar la persona.";
    note.className = "message error";
  }
});
if (new URLSearchParams(window.location.search).has("creada")) showMessage("Persona registrada correctamente.", "success");
loadPeople();
