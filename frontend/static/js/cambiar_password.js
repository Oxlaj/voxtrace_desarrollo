const form = document.getElementById("change-password-form");
const message = document.getElementById("form-message");
const submit = form.querySelector('button[type="submit"]');

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    message.textContent = "";
    message.className = "message";

    if (!form.reportValidity()) {
        return;
    }

    const password = document.getElementById("password").value;
    const passwordConfirm = document.getElementById("password-confirm").value;

    if (password !== passwordConfirm) {
        message.textContent = "Las contraseñas no coinciden.";
        message.className = "message error";
        return;
    }

    submit.disabled = true;

    try {
        await window.VoxTraceAPI.request("/cuenta/password", {
            method: "POST",
            body: JSON.stringify({
                password: password
            })
        });

        message.textContent = "Contraseña actualizada correctamente.";
        message.className = "message success";

        setTimeout(() => {
            window.location.assign("/dashboard");
        }, 800);

    } catch (error) {
        message.textContent =
            error.status === 422
                ? "La contraseña debe contener al menos 12 caracteres."
                : "No fue posible actualizar la contraseña.";

        message.className = "message error";
        submit.disabled = false;
    }
});
