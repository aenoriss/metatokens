const functions = require('firebase-functions');
const axios = require('axios');

exports.cleanTokens = functions.pubsub
    .schedule('every 1 minutes')
    .timeZone('UTC')
    .onRun(async (context) => {
        try {
            const response = await axios({
                method: 'get',
                url: "https://xrb8-joaquinquiroga-prototype1-backendd-28244255329.us-central1.run.app/updateTokensIndex",
            });
            console.log('FastAPI response:', response.data);
            return null;
        } catch (error) {
            console.error('Error calling FastAPI:', error.response?.data || error.message);
            return null;
        }
    });