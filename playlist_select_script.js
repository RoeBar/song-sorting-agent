const API_BASE = 'http://127.0.0.1:3000';

function fetchPlaylists() {
    const container = document.querySelector('.songlist-container');
    if (!container) {
        console.error('Missing .songlist-container element');
        return;
    }

    fetch(`${API_BASE}/playlists`)
        .then(async (response) => {
            const text = await response.text();
            let data;
            try {
                data = text ? JSON.parse(text) : {};
            } catch {
                throw new Error('Invalid response from server');
            }
            if (!response.ok) {
                const msg =
                    data.message ||
                    (response.status === 401
                        ? 'Not logged in. Open auth_page.html and connect Spotify first, then try again.'
                        : 'Request failed');
                throw new Error(msg);
            }
            return data;
        })
        .then((data) => {
            const playlists = data.items || data.playlists || [];
            container.innerHTML = '';
            playlists.forEach((playlist, index) => {
                const playlistDiv = document.createElement('div');
                playlistDiv.classList.add('playlist-item');
                playlistDiv.innerHTML = `
                    <input type="checkbox" id="playlist-${index}" name="playlist-${index}" value="${playlist.id}">
                    <label for="playlist-${index}">${playlist.name}</label>
                `;
                container.appendChild(playlistDiv);
            });
        })
        .catch((error) => {
            console.error('Error fetching playlists:', error);
            container.innerHTML =
                '<p>Error fetching playlists. ' +
                (error.message ? String(error.message) : 'Please try again later.') +
                '</p>';
        });
}

document.addEventListener('DOMContentLoaded', fetchPlaylists);

function submitPlaylists() {
    return;
}
