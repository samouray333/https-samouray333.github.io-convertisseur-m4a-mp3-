document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('fileInput');
    const convertButton = document.getElementById('convertButton');
    const fileList = document.getElementById('fileList');
    const result = document.getElementById('result');
    const dropZone = document.getElementById('dropZone');
    const themeToggle = document.getElementById('themeToggle');
    const bitrateSelect = document.getElementById('bitrate');

    let files = [];

    // Fonctionnalité glisser-déposer
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        files = [...files, ...e.dataTransfer.files];
        updateFileList();
    });

    // Sélection de fichiers
    fileInput.addEventListener('change', () => {
        files = [...files, ...fileInput.files];
        updateFileList();
    });

    // Mise à jour de la liste des fichiers
    function updateFileList() {
        fileList.innerHTML = '';
        files.forEach((file, index) => {
            const fileItem = document.createElement('div');
            fileItem.textContent = file.name;
            const removeButton = document.createElement('button');
            removeButton.textContent = 'Supprimer';
            removeButton.onclick = () => {
                files.splice(index, 1);
                updateFileList();
            };
            fileItem.appendChild(removeButton);
            fileList.appendChild(fileItem);
        });
    }

    // Conversion
    convertButton.addEventListener('click', async () => {
        if (files.length === 0) {
            result.textContent = 'Veuillez sélectionner au moins un fichier M4A.';
            return;
        }

        result.innerHTML = '';
        const bitrate = bitrateSelect.value;

        for (let file of files) {
            const resultItem = document.createElement('div');
            resultItem.textContent = `Conversion de ${file.name} en cours...`;
            const progressBar = document.createElement('div');
            progressBar.className = 'progress-bar';
            const progress = document.createElement('div');
            progress.className = 'progress';
            progressBar.appendChild(progress);
            resultItem.appendChild(progressBar);
            result.appendChild(resultItem);

            try {
                const arrayBuffer = await file.arrayBuffer();
                const ffmpeg = FFmpeg.createFFmpeg({ log: true });
                await ffmpeg.load();

                ffmpeg.FS('writeFile', 'input.m4a', new Uint8Array(arrayBuffer));

                await ffmpeg.run('-i', 'input.m4a', '-b:a', bitrate, 'output.mp3');

                const data = ffmpeg.FS('readFile', 'output.mp3');
                const blob = new Blob([data.buffer], { type: 'audio/mp3' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = file.name.replace('.m4a', '.mp3');
                a.textContent = `Télécharger ${a.download}`;
                resultItem.innerHTML = '';
                resultItem.appendChild(a);

            } catch (error) {
                console.error('Erreur lors de la conversion:', error);
                resultItem.textContent = `Erreur lors de la conversion de ${file.name}.`;
            }
        }
    });

    // Basculement du thème
    themeToggle.addEventListener('click', () => {
        document.body.classList.toggle('dark-theme');
        themeToggle.innerHTML = document.body.classList.contains('dark-theme') ? 
            '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
    });
});