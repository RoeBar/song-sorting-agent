document.getElementById('prompt-form').addEventListener('submit', SendPrompt);

const magicSortBtn = document.getElementById('magic-sort-btn');
if (magicSortBtn) {
    magicSortBtn.addEventListener('click', SendMagicSort);
}

function SendPrompt(event) {
    event.preventDefault();
    const criteria = document.getElementById('criteria').value;
    console.log('User Prompt:', criteria);
    waitingResponse({ clearCriteria: true });
    fetch('http://localhost:3000/prompt', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ prompt: criteria })
    })
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
            console.log('Response from server:', data);
            if (!ok || !data.ok) {
                gotResponse();
                alert(data.message || 'Could not generate descriptions. Please try again.');
                return;
            }
            gotResponse();
            window.location.href = 'playlist_descriptions.html';
        })
        .catch((error) => {
            console.error('Error:', error);
            gotResponse();
            alert('Network error. Please try again.');
        });
}

function SendMagicSort() {
    console.log('Magic sort requested');
    waitingResponse({ clearCriteria: false });
    fetch('http://localhost:3000/magic_sort', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({})
    })
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
            console.log('Magic sort response:', data);
            if (!ok || !data.ok) {
                gotResponse();
                alert(data.message || 'Magic sort failed. Please try again.');
                return;
            }
            gotResponse();
            window.location.href = 'playlist_descriptions.html';
        })
        .catch((error) => {
            console.error('Error:', error);
            gotResponse();
            alert('Network error. Please try again.');
        });
}

function waitingResponse(options) {
    const clearCriteria = !options || options.clearCriteria !== false;
    const submitBtn = document.querySelector('#prompt-form .submit-btn');
    const magicBtn = document.getElementById('magic-sort-btn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.value = 'Processing...';
    }
    if (magicBtn) {
        magicBtn.disabled = true;
    }
    const criteria = document.getElementById('criteria');
    criteria.disabled = true;
    if (clearCriteria) {
        criteria.value = '';
    }
}

function gotResponse() {
    const criteria = document.getElementById('criteria');
    criteria.disabled = false;
    const submitBtn = document.querySelector('#prompt-form .submit-btn');
    const magicBtn = document.getElementById('magic-sort-btn');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.value = 'Continue';
    }
    if (magicBtn) {
        magicBtn.disabled = false;
    }
}
