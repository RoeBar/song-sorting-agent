const API_BASE = 'http://127.0.0.1:3000';

function fetchPlaylists() {
    fetch('http://localhost:3000/playlists')
        .then(response => response.json())
        .then(data => {
            // Normalize common response shapes into an array of playlists.
            // If backend returns a direct list, 'data' is the array.
            // If it returns an object like { playlists: [...] } use that.
            let playlists = data && (data.playlists ?? data);

            // Handle a few common wrapper shapes (e.g., { items: [...] }, { data: [...] })
            if (playlists && typeof playlists === 'object' && !Array.isArray(playlists)) {
                if (Array.isArray(playlists.items)) playlists = playlists.items;
                else if (Array.isArray(playlists.data)) playlists = playlists.data;
                else if (playlists.playlists && Array.isArray(playlists.playlists)) playlists = playlists.playlists;
                else {
                    console.warn('Unexpected playlists shape from server, falling back to empty array.', playlists);
                    playlists = [];
                }
            }

            if (!Array.isArray(playlists)) {
                console.warn('playlists is not an array, received:', playlists);
                playlists = [];
            }

            // Render playlists into both columns (input and output) with the same style
            const columns = ['input', 'output'];

            columns.forEach(column => {
                const container = document.getElementById(`songlist-${column}`);
                if (!container) return;
                container.innerHTML = ''; // Clear loading text

                playlists.forEach((playlist, index) => {
                    const playlistDiv = document.createElement('div');
                    playlistDiv.classList.add('playlist-item');

                    // Make the whole slab clickable
                    playlistDiv.addEventListener('click', () => {
                        const checkbox = document.getElementById(`playlist-${column}-${index}`);
                        if (!checkbox) return;
                        checkbox.checked = !checkbox.checked; // Toggle the hidden checkbox
                        playlistDiv.classList.toggle('selected', checkbox.checked); // Toggle the green CSS
                    });

                    playlistDiv.innerHTML = `
                        <input type="checkbox" id="playlist-${column}-${index}" value="${playlist.id}">
                        <div class="custom-checkbox"></div>
                        <span class="playlist-name">${playlist.name || playlist.title || 'Untitled'}</span>
                    `;

                    container.appendChild(playlistDiv);
                });
            });
        })
        .catch(error => {
            console.error('Error fetching playlists:', error);
            const container = document.querySelector('.songlist-container');
            container.innerHTML = '<p style="color: #ff5555;">Error fetching playlists. Please try again later.</p>';
        });
}

document.addEventListener('DOMContentLoaded', fetchPlaylists);

function submitPlaylists() {
    const submitBtn = document.querySelector('.submit-btn');
    const statusEl = document.getElementById('submit-status');

    const inputChecked = document.querySelectorAll('input[id^="playlist-input-"]:checked');
    const outputChecked = document.querySelectorAll('input[id^="playlist-output-"]:checked');

    const inputIds = Array.from(inputChecked).map(n => n.value);
    const outputIds = Array.from(outputChecked).map(n => n.value);

    const payload = { input: inputIds, output: outputIds };

    if (submitBtn) submitBtn.disabled = true;
    if (statusEl) {
        statusEl.textContent = 'Submitting playlists...';
        statusEl.style.color = '#E0E0E0';
    }

    fetch(`${API_BASE}/selected_playlists`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(response => {
        if (!response.ok) throw new Error(`Server responded ${response.status}`);
        return response.json().catch(() => ({}));
    })
    .then(data => {
        if (statusEl) {
            statusEl.textContent = 'Playlists submitted successfully.';
            statusEl.style.color = '#1DB954';
        }
        console.log('Submit response:', data);
    })
    .catch(err => {
        console.error('Error submitting playlists:', err);
        if (statusEl) {
            statusEl.textContent = 'Error submitting playlists. See console.';
            statusEl.style.color = '#ff5555';
        }
    })
    .finally(() => {
        if (submitBtn) submitBtn.disabled = false;
    });
}
