document.addEventListener('DOMContentLoaded', () => {
    const loginForm = document.getElementById('loginForm');
    const loginErrorDiv = document.getElementById('loginError');
    const plagiarismCheckForm = document.getElementById('plagiarismCheckForm');
    const analysisResultsDiv = document.getElementById('analysisResults');
    const plagiarismPercentageTextSpan = document.getElementById('plagiarismPercentageText');
    const plagiarismDetailsTextDiv = document.getElementById('plagiarismDetailsText');
    const aiDetectionPercentageSpan = document.getElementById('aiDetectionPercentage');
    const aiDetectionDetailsDiv = document.getElementById('aiDetectionDetails');
    const downloadReportButton = document.getElementById('downloadReport');
    const analysisErrorDiv = document.getElementById('analysisError');
    const loadingIndicatorDiv = document.getElementById('loadingIndicator');

    const API_BASE_URL = 'http://localhost:5000'; // Ajusta si tu backend está en otra URL

    // --- Lógica de Inicio de Sesión ---
    if (loginForm) {
        loginForm.addEventListener('submit', async (event) => {
            event.preventDefault(); // Evitar el envío predeterminado del formulario

            // Obtener los datos del formulario
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            try {
                // Enviar la solicitud al backend
                const response = await fetch(`${API_BASE_URL}/token`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ username, password }),
                });

                if (!response.ok) {
                    throw new Error('Usuario o contraseña incorrectos');
                }

                const data = await response.json();

                // Guardar el token en localStorage
                localStorage.setItem('access_token', data.access_token);

                // Redirigir al usuario a la página de verificación de plagio
                window.location.href = 'check.html';
            } catch (error) {
                // Mostrar el mensaje de error
                loginErrorDiv.textContent = error.message;
                loginErrorDiv.style.display = 'block';
            }
        });
    }

    // --- Lógica de Verificación de Plagio ---
    if (plagiarismCheckForm) {
        plagiarismCheckForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            loadingIndicatorDiv.style.display = 'block';
            analysisResultsDiv.style.display = 'none';
            analysisErrorDiv.style.display = 'none';

            const formData = new FormData(plagiarismCheckForm);
            try {
                const response = await fetch(`${API_BASE_URL}/analyze`, {
                    method: 'POST',
                    body: formData,
                });

                if (!response.ok) {
                    throw new Error('Error al analizar el documento.');
                }

                const result = await response.json();
                document.getElementById('plagiarismPercentageText').textContent = result.plagiarism_percentage_text || 'N/A';
                analysisResultsDiv.style.display = 'block';
            } catch (error) {
                analysisErrorDiv.textContent = error.message || 'Error desconocido.';
                analysisErrorDiv.style.display = 'block';
            } finally {
                loadingIndicatorDiv.style.display = 'none';
            }
        });
    }

    // --- Otras funcionalidades (logout, registro, etc.) se agregarían aquí ---
});