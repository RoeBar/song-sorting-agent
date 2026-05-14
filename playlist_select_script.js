function fetchPlaylists() {
    fetch('http://localhost:3000/playlists')
        .then(response => response.json())
        .then(data => {
            // each playlist should have a name, and a checkbox next to it
            const playlists = data.playlists || [];
            const container = document.querySelector('.songlist-container');
            container.innerHTML = '';
            playlists.forEach((playlist, index) => {
                const playlistDiv = document.createElement('div');
                playlistDiv.classList.add('playlist-item');
                playlistDiv.innerHTML = `
                    <input type="checkbox" id="playlist-${index}" name="playlist-${index}" value="${playlist.id}">
                    <label for="playlist-${index}">${playlist.name}</label>
                `;
                container.appendChild(playlistDiv);
            }
            );
        }
        )
        .catch(error => {
            console.error('Error fetching playlists:', error);
             const container = document.querySelector('.songlist-container');
             container.innerHTML = '<p>Error fetching playlists. Please try again later.</p>';
        }
    );
}

document.addEventListener('DOMContentLoaded', fetchPlaylists);

function submitPlaylists() {
    return;
}