// Copier le flux initial dans le volume modifiable, sans remplacer un flux sauvegardé.
const fs = require('node:fs');
const path = require('node:path');

function seed(dataDirectory = '/data', source = '/seed/flows.json') {
    fs.mkdirSync(dataDirectory, { recursive: true });
    const destination = path.join(dataDirectory, 'flows.json');
    try {
        fs.copyFileSync(source, destination, fs.constants.COPYFILE_EXCL);
        console.log('Flux initial copié dans le volume Node-RED.');
    } catch (error) {
        if (error.code !== 'EEXIST') throw error;
        console.log('Flux Node-RED existant conservé.');
    }
}

if (require.main === module) seed();
module.exports = { seed };
