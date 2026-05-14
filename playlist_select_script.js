const API_BASE = 'http://127.0.0.1:3000';

/**
 * POST /selected_playlists expects JSON: { "input": [...], "output": [...] }
 * Each entry may be a playlist id string or { "id": "..." } (see spotify_auth_server.py).
 */
function buildSelectedPlaylistsPayload() {
    const inputChecked = document.querySelectorAll('input[id^="playlist-input-"]:checked');
    const outputChecked = document.querySelectorAll('input[id^="playlist-output-"]:checked');

    const input = Array.from(inputChecked)
        .map((el) => el.value)
        .filter((id) => typeof id === 'string' && id.trim().length > 0);
    const output = Array.from(outputChecked)
        .map((el) => el.value)
        .filter((id) => typeof id === 'string' && id.trim().length > 0);

    return { input, output };
}

async function readJsonResponse(response) {
    const text = await response.text();
    if (!text) {
        return {};
    }
    try {
        return JSON.parse(text);
    } catch {
        return { message: text || response.statusText };
    }
}

function setColumnsMessage(html) {
    ['input', 'output'].forEach((column) => {
        const container = document.getElementById(`songlist-${column}`);
        if (container) container.innerHTML = html;
    });
}

function fetchPlaylists() {
    fetch(`${API_BASE}/playlists`)
        .then(async (response) => {
            const data = await readJsonResponse(response);
            if (!response.ok) {
                const msg =
                    (data && data.message) ||
                    `Could not load playlists (HTTP ${response.status}).`;
                if (response.status === 401) {
                    const origin = encodeURIComponent(window.location.origin);
                    setColumnsMessage(
                        `<p style="color: #ff5555;">${msg}</p>
                        <p><a href="${API_BASE}/login?origin=${origin}" target="_blank" rel="noopener">Sign in with Spotify</a> (opens a new window), then reload this page.</p>`
                    );
                } else {
                    setColumnsMessage(`<p style="color: #ff5555;">${msg}</p>`);
                }
                return;
            }

            // Spotify Web API shape: { items: [ { id, name, ... }, ... ], ... }
            let playlists = data && (data.playlists ?? data);

            if (playlists && typeof playlists === 'object' && !Array.isArray(playlists)) {
                if (Array.isArray(playlists.items)) playlists = playlists.items;
                else if (Array.isArray(playlists.data)) playlists = playlists.data;
                else if (playlists.playlists && Array.isArray(playlists.playlists))
                    playlists = playlists.playlists;
                else {
                    console.warn('Unexpected playlists shape from server, falling back to empty array.', playlists);
                    playlists = [];
                }
            }

            if (!Array.isArray(playlists)) {
                console.warn('playlists is not an array, received:', playlists);
                playlists = [];
            }

            const columns = ['input', 'output'];

            columns.forEach((column) => {
                const container = document.getElementById(`songlist-${column}`);
                if (!container) return;
                container.innerHTML = '';

                playlists.forEach((playlist, index) => {
                    const playlistDiv = document.createElement('div');
                    playlistDiv.classList.add('playlist-item');

                    const pid = playlist && playlist.id != null ? String(playlist.id) : '';
                    if (!pid) {
                        console.warn('Skipping playlist without id', playlist);
                        return;
                    }

                    playlistDiv.addEventListener('click', () => {
                        const checkbox = document.getElementById(`playlist-${column}-${index}`);
                        if (!checkbox) return;
                        checkbox.checked = !checkbox.checked;
                        playlistDiv.classList.toggle('selected', checkbox.checked);
                    });

                    playlistDiv.innerHTML = `
                        <input type="checkbox" id="playlist-${column}-${index}" value="${pid.replace(/"/g, '&quot;')}">
                        <div class="custom-checkbox"></div>
                        <span class="playlist-name">${(playlist.name || playlist.title || 'Untitled').replace(/</g, '&lt;')}</span>
                    `;

                    container.appendChild(playlistDiv);
                });
            });
        })
        .catch((error) => {
            console.error('Error fetching playlists:', error);
            setColumnsMessage(
                '<p style="color: #ff5555;">Error fetching playlists. Is the server running on port 3000?</p>'
            );
        });
}

document.addEventListener('DOMContentLoaded', fetchPlaylists);

function submitPlaylists() {
    const submitBtn = document.querySelector('.submit-btn');
    const statusEl = document.getElementById('submit-status');

    const payload = buildSelectedPlaylistsPayload();

    if (payload.input.length === 0 || payload.output.length === 0) {
        if (statusEl) {
            statusEl.textContent = 'Select at least one input playlist and one output playlist.';
            statusEl.style.color = '#ff5555';
        }
        return;
    }

    if (submitBtn) submitBtn.disabled = true;
    if (statusEl) {
        statusEl.textContent = 'Submitting playlists...';
        statusEl.style.color = '#E0E0E0';
    }

    fetch(`${API_BASE}/selected_playlists`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    })
        .then(async (response) => {
            const data = await readJsonResponse(response);
            if (!response.ok) {
                const msg = (data && data.message) || `Server responded ${response.status}`;
                throw new Error(msg);
            }
            return data;
        })
        .then((data) => {
            if (statusEl) {
                statusEl.textContent = 'Playlists submitted successfully.';
                statusEl.style.color = '#1DB954';
            }
            console.log('Submit response:', data);
            window.location.href = 'prompt_page.html';
        })
        .catch((err) => {
            console.error('Error submitting playlists:', err);
            if (statusEl) {
                statusEl.textContent = err.message || 'Error submitting playlists. See console.';
                statusEl.style.color = '#ff5555';
            }
        })
        .finally(() => {
            if (submitBtn) submitBtn.disabled = false;
        });
}
