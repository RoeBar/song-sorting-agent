document.getElementById('prompt-form').addEventListener('submit', SendPrompt);


function SendPrompt(event) {
    event.preventDefault();
    const criteria = document.getElementById('criteria').value;
    console.log('User Prompt:', criteria);
    // send the prompt to the server
    // while you wait for the response, disable the submit button and show a loading gif
    waitingResponse();
    fetch('http://localhost:3000/prompt', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ prompt: criteria })
    })
    .then(response => response.json())
    .then(data => {
        console.log('Response from server:', data);
        // re-enable the submit button
        gotResponse();
        // song lists is either 2 or the value we got from the server
        const songLists = data.songLists || 2;
        // redirect to the song list page with the song lists as a query parameter
        window.location.href = `playlist_descriptions.html?songLists=${songLists}`;
    })
    .catch(error => {
        console.error('Error:', error);
    });
}

function waitingResponse() {
    const submitBtn = document.querySelector('.submit-btn');
    submitBtn.disabled = true;
    submitBtn.value = 'Processing...';
    criteria = document.getElementById('criteria')
    // clear the textarea
    criteria.value = '';
    criteria.disabled = true;
}

function gotResponse() {
    const criteria = document.getElementById('criteria');
    criteria.disabled = false;
    const submitBtn = document.querySelector('.submit-btn');
    submitBtn.disabled = false;
    submitBtn.value = 'Continue';
}